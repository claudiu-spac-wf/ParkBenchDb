"""Generate the OpenEdge database definition files from schema/parkbench-schema.yaml.

Writes <db-name>.df (data definitions), <db-name>.st (structure) and <db-name>.expect
(expected counts for db/abl/verify_db.p).

Formats: specs/002-df-st-generation/contracts/df-format.md and st-format.md
CLI:     specs/002-df-st-generation/contracts/build-cli.md

Usage: python3 tools/gen_db_files.py <schema.yaml> --out <dir> [--db-name parkbench] [--extent-dir .] [--check]
Exit codes: 0 = OK, 1 = validation findings or --check differences, 2 = load error or invalid option.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import schema_model as m  # noqa: E402
from tools import validate_schema as v  # noqa: E402

VALID_RPB = {1, 2, 4, 8, 16, 32, 64, 128, 256}
INDEX_AREA_RPB = 64
LOB_AREA_RPB = 8
FIRST_AREA_NUMBER = 7
DB_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,10}$")
MAX_WIDTH = {"INTEGER": 4, "INT64": 8, "DECIMAL": 17, "LOGICAL": 1, "DATE": 4, "DATETIME": 8, "DATETIME-TZ": 12}
BI_BLOCK_BYTES = 16 * 1024          # proutil -C truncate bi -biblocksize 16
BI_CLUSTER_BYTES = 16 * 1024 * 1024  # proutil -C truncate bi -bi 16384


@dataclass(frozen=True)
class AreaRow:
    name: str
    number: int
    kind: str  # schema | data | index | lob
    rpb: int
    bpc: int


# --------------------------------------------------------------------------- shared helpers

def area_plan(schema: m.Schema) -> list[AreaRow]:
    """Storage areas with stable numbers (data-model.md §4)."""
    rows = [AreaRow("Schema Area", 6, "schema", 32, 1)]
    for n, a in enumerate(schema.areas):
        if a.kind == "data":
            if not a.recordsPerBlock:
                raise ValueError(f"data area {a.name} has no recordsPerBlock")
            rpb = a.recordsPerBlock
        elif a.kind == "index":
            rpb = INDEX_AREA_RPB
        else:
            rpb = LOB_AREA_RPB
        if rpb not in VALID_RPB:
            raise ValueError(f"area {a.name}: records per block {rpb} is not one of {sorted(VALID_RPB)}")
        rows.append(AreaRow(a.name, FIRST_AREA_NUMBER + n, a.kind, rpb, a.blocksPerCluster or 1))
    return rows


def lob_size_bytes(size: str) -> int:
    mm = re.fullmatch(r"(\d+)([KM])", size or "")
    if not mm:
        raise ValueError(f"LOB size {size!r} must look like 64K or 1M")
    return int(mm.group(1)) * (1024 if mm.group(2) == "K" else 1024 * 1024)


def check_areas(schema: m.Schema, plan: list[AreaRow]) -> None:
    """Rules D02/D03: every area used in the .df exists in the .st with the right kind; LOB sizes parse."""
    kinds = {r.name: r.kind for r in plan}
    for t in schema.tables:
        if kinds.get(t.area) != "data":
            raise ValueError(f"{t.name}: area {t.area!r} is not a data area in the .st")
        if kinds.get(t.indexArea) != "index":
            raise ValueError(f"{t.name}: indexArea {t.indexArea!r} is not an index area in the .st")
        for f in t.lob_fields:
            loc = f"{t.name}.{f.name}"
            if f.lob is None or kinds.get(f.lob.area) != "lob":
                raise ValueError(f"{loc}: LOB area {getattr(f.lob, 'area', None)!r} is not a lob area in the .st")
            if lob_size_bytes(f.lob.maxSize) < (f.lob.maxBytes or 0):
                raise ValueError(f"{loc}: maxSize {f.lob.maxSize} is smaller than maxBytes {f.lob.maxBytes}")


def df_string(text) -> str:
    """Quote a string for a .df (research R3)."""
    s = str(text).replace("~", "~~").replace('"', '""').replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return f'"{s}"'


def table_order(schema: m.Schema) -> list[m.Table]:
    return [schema.get_table(n) for level in m.load_order(schema) for n in level]


# --------------------------------------------------------------------------- .df

def _initial(f: m.Field) -> str:
    if f.initial == "?":
        return "  INITIAL ?"
    if f.initial == "NOW":
        return '  INITIAL "now"'
    return f"  INITIAL {df_string(f.initial)}"


def _field_block(t: m.Table, f: m.Field, pos: int) -> str:
    lines = [f'ADD FIELD "{f.name}" OF "{t.name}" AS {f.type.lower()}',
             f"  DESCRIPTION {df_string(f.description)}",
             f"  FORMAT {df_string('x(8)' if f.is_lob else f.format)}",
             _initial(f),
             f"  LABEL {df_string(f.display_label)}",
             f"  POSITION {pos + 2}"]
    if not f.is_lob:
        width = 2 * m.char_width(f.format) if f.type == "CHARACTER" else MAX_WIDTH[f.type]
        lines.append(f"  MAX-WIDTH {width}")
    if f.is_lob:
        lob = f.lob
        lines += [f"  LOB-AREA {df_string(lob.area)}",
                  f"  LOB-BYTES {lob_size_bytes(lob.maxSize)}",
                  f"  LOB-SIZE {lob.maxSize}"]
        if f.type == "CLOB":
            lines += [f"  CLOB-CODEPAGE {df_string(lob.codepage or 'UTF-8')}",
                      '  CLOB-COLLATION "BASIC"',
                      "  CLOB-TYPE 1"]
    lines.append(f"  COLUMN-LABEL {df_string(f.display_label)}")
    if f.type == "DECIMAL":
        lines.append(f"  DECIMALS {f.decimals}")
    lines.append(f"  ORDER {(pos + 1) * 10}")
    if f.mandatory:
        lines.append("  MANDATORY")
    return "\n".join(lines)


def _index_block(t: m.Table, i: m.Index) -> str:
    lines = [f'ADD INDEX "{i.name}" ON "{t.name}"', f"  AREA {df_string(t.indexArea)}"]
    if i.unique:
        lines.append("  UNIQUE")
    if i.primary:
        lines.append("  PRIMARY")
    if i.word:
        lines.append("  WORD")
    for c in i.components:
        lines.append(f'  INDEX-FIELD "{c.field}" {"DESCENDING" if c.order == "desc" else "ASCENDING"}')
    return "\n".join(lines)


def render_df(schema: m.Schema, plan: list[AreaRow], sequences: bool = True) -> str:
    """Data definitions in the exact format prodict/dump_df.p produces (verified on OpenEdge 12.8.11), with trailer."""
    tables = table_order(schema)
    blocks = []
    for t in tables if sequences else []:
        blocks.append(f'ADD SEQUENCE "Seq{t.name}Id"\n  INITIAL 1\n  INCREMENT 1\n  CYCLE-ON-LIMIT no\n'
                      "  MIN-VAL 1")  # no MAX-VAL: unbounded (64-bit) is the default and dump_df.p omits it
    for t in tables:
        blocks.append("\n".join([f'ADD TABLE "{t.name}"', f"  AREA {df_string(t.area)}",
                                 f"  LABEL {df_string(m.split_camel(t.name))}",
                                 f"  DESCRIPTION {df_string(t.description)}",
                                 f"  DUMP-NAME {df_string(t.name.lower())}"]))
        blocks += [_field_block(t, f, pos) for pos, f in enumerate(t.fields)]
        blocks += [_index_block(t, i) for i in t.indexes]
    body = "\n\n".join(blocks) + "\n\n.\n"
    offset = len(body.encode("utf-8"))
    return body + f"PSC\ncpstream=UTF-8\n.\n{offset:010d}\n"


# --------------------------------------------------------------------------- .st and .expect

def st_path(extent_dir: str) -> str:
    return f'!"{extent_dir}"' if " " in extent_dir else extent_dir


def render_st(schema: m.Schema, plan: list[AreaRow], extent_dir: str = ".") -> str:
    """Structure file: BI plus one variable extent per area (research R7)."""
    p = st_path(extent_dir)
    lines = [f"# {schema.name} structure file - generated from schema/parkbench-schema.yaml by tools/gen_db_files.py.",
             "# One variable extent per area; requires large-file support (enabled by db/build_db.*).",
             f"b {p}"]
    lines += [f'd "{r.name}":{r.number},{r.rpb};{r.bpc} {p}' for r in plan]
    return "\n".join(lines) + "\n"


def render_expect(schema: m.Schema) -> str:
    """Expected post-build values for db/abl/verify_db.p (data-model.md §5)."""
    rows = [
        ("tables", len(schema.tables)),
        ("fields", sum(len(t.fields) for t in schema.tables)),
        ("indexes", sum(len(t.indexes) for t in schema.tables)),
        ("sequences", len(schema.tables)),
        ("codepage", "UTF-8"),
        ("largefiles", "yes"),
        ("blocksize", schema.blockSizeBytes),
        ("biblocksize", BI_BLOCK_BYTES),
        ("biclustersize", BI_CLUSTER_BYTES),
        ("table-list", ",".join(sorted((t.name for t in schema.tables), key=str.lower))),  # ABL BY is case-insensitive
    ]
    return "".join(f"{k}={val}\n" for k, val in rows)


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate OpenEdge .df/.st/.expect files from the schema source")
    ap.add_argument("schema")
    ap.add_argument("--out", required=True)
    ap.add_argument("--db-name", default="parkbench")
    ap.add_argument("--extent-dir", default=".")
    ap.add_argument("--check", action="store_true", help="verify the files are up to date; write nothing")
    ap.add_argument("--loader", action="store_true",
                    help="render the internal loader tables (schema/loader-schema.yaml) to <db-name>_loader.df only")
    args = ap.parse_args(argv)

    if not DB_NAME.match(args.db_name):
        print(f"invalid --db-name {args.db_name!r}: letters, digits, _ and -; at most 11 characters; "
              "must start with a letter")
        return 2
    if any(ch in args.extent_dir for ch in '"\r\n') or not args.extent_dir:
        print(f"invalid --extent-dir {args.extent_dir!r}: must be non-empty and contain no quote or line break")
        return 2

    try:
        schema = m.load_expanded(args.schema)
        m.load_order(schema)
    except m.SchemaError as e:
        print(f"{e.rule} {e.location}: {e.message}")
        return 2
    findings = v.validate(schema, profile="loader" if args.loader else "full")
    if findings:
        for f in findings:
            print(f)
        print(f"ABORTED: {len(findings)} validation finding(s); nothing generated")
        return 1
    try:
        plan = area_plan(schema)
        check_areas(schema, plan)
    except ValueError as e:
        print(f"ABORTED: {e}")
        return 2

    db = args.db_name
    if args.loader:
        files = {f"{db}_loader.df": render_df(schema, plan, sequences=False)}
    else:
        files = {f"{db}.df": render_df(schema, plan),
                 f"{db}.st": render_st(schema, plan, args.extent_dir),
                 f"{db}.expect": render_expect(schema)}
    out = Path(args.out)

    if args.check:
        differ = [out / name for name, text in files.items()
                  if not (out / name).exists() or (out / name).read_bytes() != text.encode("utf-8")]
        for p in differ:
            print(f"out of date: {p}")
        if differ:
            return 1
        print(f"OK: {len(files)} files up to date in {out}")
        return 0

    out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        with open(out / name, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    nf = sum(len(t.fields) for t in schema.tables)
    ni = sum(len(t.indexes) for t in schema.tables)
    if args.loader:
        print(f"Wrote {len(files)} file to {out}: {len(schema.tables)} loader tables, {nf} fields, {ni} indexes")
        return 0
    print(f"Wrote {len(files)} files to {out}: {len(schema.tables)} tables, {nf} fields, {ni} indexes, "
          f"{len(schema.tables)} sequences, {len(plan)} areas + before-image")
    return 0


if __name__ == "__main__":
    sys.exit(main())
