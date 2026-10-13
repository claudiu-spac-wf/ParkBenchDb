"""Checker for schema/parkbench-schema.yaml.

Enforces the rules in specs/001-banking-benchmark-schema/data-model.md §6 (rule ids V01–V29).

  structure profile: V01–V16, V24–V26, V29  (well-formedness; valid for any schema)
  full profile:      structure + V17–V23, V27, V28 (ParkBenchDB coverage and sizing targets)

Usage: python3 tools/validate_schema.py <schema.yaml>
Exit codes: 0 = OK, 1 = findings, 2 = the file could not be loaded (SchemaError).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import schema_model as m  # noqa: E402

IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
MONEY_FORMAT = "->>>,>>>,>>>,>>9.99"
MONEY_NAME = re.compile(r"^(.*Amount|.*Balance|.*Fee|.*Fees|Total.*|.*Principal|.*Portion|Salary|AnnualIncome"
                        r"|.*Limit|InterestEarned|FeesCharged)$")
CARDINALITY = re.compile(r"^[0-9][0-9,.]* / [0-9][0-9,.]*–[0-9][0-9,.]*( \(.+\))?$")
RESERVED_FILE = Path(__file__).resolve().parent / "reserved_words.txt"
STANDARD_TYPES = ("INT64", "INTEGER", "INTEGER", "INTEGER", "DATETIME-TZ")
MIN_SCALE_FACTOR = 0.01
MIN_ROWS_AT_MIN_SCALE = 50
DATA_TOTAL_RANGE = (20e9, 50e9)


@dataclass(frozen=True)
class Finding:
    rule: str
    location: str
    message: str

    def __str__(self) -> str:
        return f"{self.rule} {self.location}: {self.message}"


def load_reserved(path: Path = RESERVED_FILE) -> set[str]:
    words = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.add(line.upper())
    return words


def standard_names(table: str) -> list[str]:
    return [f"{table}Id", "RandomInt10", "RandomInt100", "RandomInt1000", "CreatedAt"]


# --------------------------------------------------------------------------- structure rules

def _v01_names(s: m.Schema, out: list) -> None:
    def check(name: str, loc: str) -> None:
        if not IDENT.match(name) or len(name) > 32:
            out.append(Finding("V01", loc, f"invalid identifier {name!r} (must match [A-Za-z][A-Za-z0-9]*, ≤ 32 chars)"))
    for t in s.tables:
        check(t.name, t.name)
        check(f"Seq{t.name}Id", f"{t.name} (sequence)")
        for f in t.fields:
            check(f.name, f"{t.name}.{f.name}")
        for i in t.indexes:
            check(i.name, f"{t.name}.{i.name}")


def _v02_duplicates(s: m.Schema, out: list) -> None:
    def dups(names):
        seen, d = set(), set()
        for n in names:
            (d if n.lower() in seen else seen).add(n.lower())
        return sorted(d)
    for n in dups(t.name for t in s.tables):
        out.append(Finding("V02", n, "duplicate table name"))
    for t in s.tables:
        for n in dups(f.name for f in t.fields):
            out.append(Finding("V02", f"{t.name}.{n}", "duplicate field name"))
        for n in dups(i.name for i in t.indexes):
            out.append(Finding("V02", f"{t.name}.{n}", "duplicate index name"))


def _v03_v04_fields(s: m.Schema, out: list) -> None:
    for t in s.tables:
        for f in t.fields:
            loc = f"{t.name}.{f.name}"
            if f.type not in m.TYPES:
                out.append(Finding("V04", loc, f"type {f.type!r} is not one of {', '.join(m.TYPES)}"))
                continue
            if not f.is_lob and not f.format:
                out.append(Finding("V03", loc, "format is required for non-LOB fields"))
            if f.type == "DECIMAL" and f.decimals is None:
                out.append(Finding("V03", loc, "decimals is required for DECIMAL fields"))


def _v05_v06_v07_indexes(s: m.Schema, out: list) -> None:
    for t in s.tables:
        for i in t.indexes:
            loc = f"{t.name}.{i.name}"
            if not i.components:
                out.append(Finding("V05", loc, "index has no components"))
            for c in i.components:
                if t.get_field(c.field) is None:
                    out.append(Finding("V05", loc, f"component {c.field!r} is not a field of {t.name}"))
                if c.order not in ("asc", "desc"):
                    out.append(Finding("V05", loc, f"component order {c.order!r} must be asc or desc"))
            if i.word:
                f = t.get_field(i.components[0].field) if i.components else None
                if len(i.components) != 1 or f is None or f.type != "CHARACTER":
                    out.append(Finding("V06", loc, "a word index must have exactly one CHARACTER component"))
            if i.primary and not i.standard:
                out.append(Finding("V07", loc, "primary is reserved for the standard Pk index"))


def _v08_lobs(s: m.Schema, out: list) -> None:
    for t in s.tables:
        for f in t.lob_fields:
            loc = f"{t.name}.{f.name}"
            if f.lob is None:
                out.append(Finding("V08", loc, "CLOB/BLOB fields need a lob spec"))
                continue
            a = s.get_area(f.lob.area)
            if a is None or a.kind != "lob":
                out.append(Finding("V08", loc, f"lob.area {f.lob.area!r} is not a lob area"))
            if f.type == "CLOB" and not f.lob.codepage:
                out.append(Finding("V08", loc, "CLOB fields need lob.codepage"))


def _v09_areas(s: m.Schema, out: list) -> None:
    for t in s.tables:
        a = s.get_area(t.area)
        if a is None or a.kind != "data":
            out.append(Finding("V09", t.name, f"area {t.area!r} is not a data area"))
        ia = s.get_area(t.indexArea)
        if ia is None or ia.kind != "index":
            out.append(Finding("V09", t.name, f"indexArea {t.indexArea!r} is not an index area"))


def _v10_descriptions(s: m.Schema, out: list) -> None:
    for t in s.tables:
        if not t.description.strip():
            out.append(Finding("V10", t.name, "table description is empty"))
        for f in t.fields:
            if not f.description.strip():
                out.append(Finding("V10", f"{t.name}.{f.name}", "field description is empty"))
        for i in t.indexes:
            if not i.purpose.strip():
                out.append(Finding("V10", f"{t.name}.{i.name}", "index purpose is empty"))


def _v11_standard_fields(s: m.Schema, out: list) -> None:
    for t in s.tables:
        want = standard_names(t.name)
        got = t.fields[:5]
        for pos, (name, typ) in enumerate(zip(want, STANDARD_TYPES)):
            f = got[pos] if pos < len(got) else None
            if f is None or f.name != name or f.type != typ or not f.mandatory:
                found = f"{f.name} {f.type}" if f else "nothing"
                out.append(Finding("V11", t.name, f"position {pos + 1} must be mandatory {name} {typ}, found {found}"))


def _v12_standard_indexes(s: m.Schema, out: list) -> None:
    for t in s.tables:
        pk = t.get_index(f"Pk{t.name}")
        if pk is None or not pk.primary or not pk.unique or not pk.components \
                or pk.components[0].field != f"{t.name}Id":
            out.append(Finding("V12", t.name, f"Pk{t.name} must be the primary unique index on {t.name}Id"))
        for n in ("10", "100", "1000"):
            ix = t.get_index(f"IxRandomInt{n}")
            if ix is None or not ix.components or ix.components[0].field != f"RandomInt{n}":
                out.append(Finding("V12", t.name, f"IxRandomInt{n} must exist with RandomInt{n} as leading component"))


def _v13_v14_v15_fks(s: m.Schema, out: list) -> None:
    for t in s.tables:
        leading = {i.components[0].field for i in t.indexes if i.components}
        for f in t.fk_fields:
            loc = f"{t.name}.{f.name}"
            parent = s.get_table(f.fk.table)
            if parent is None:
                out.append(Finding("V15", loc, f"fk.table {f.fk.table!r} does not exist"))
            elif parent.get_field(f.fk.parent_field) is None:
                out.append(Finding("V15", loc, f"fk.field {f.fk.parent_field!r} does not exist on {parent.name}"))
            if f.fk.indexed and f.name not in leading:
                out.append(Finding("V13", loc, "FK has no index with it as leading component (set indexed: false with a reason)"))
            if not f.fk.indexed and not f.fk.reason.strip():
                out.append(Finding("V14", loc, "indexed: false requires a reason"))


def _v16_metadata(s: m.Schema, out: list) -> None:
    t = s.get_table("BenchmarkTableInfo")
    if t is None:
        out.append(Finding("V16", "BenchmarkTableInfo", "the benchmark metadata table is missing"))
        return
    for need in ("TableName", "TableRowCount", "MaxId"):
        if t.get_field(need) is None:
            out.append(Finding("V16", f"BenchmarkTableInfo.{need}", "required field is missing"))
    ux = t.get_index("UxTableName")
    if ux is None or not ux.unique:
        out.append(Finding("V16", "BenchmarkTableInfo.UxTableName", "unique index on TableName is missing"))


def _v24_v25_v26_generation(s: m.Schema, out: list) -> None:
    for t in s.tables:
        for f in t.fields:
            loc = f"{t.name}.{f.name}"
            if not f.standard and not f.gen.strip():
                out.append(Finding("V24", loc, "generation rule (gen) is empty"))
            if f.lob is not None:
                lob = f.lob
                missing = [k for k in ("content", "fractionPopulated", "avgBytes", "minBytes", "maxBytes")
                           if getattr(lob, k) in (None, "")]
                if missing:
                    out.append(Finding("V25", loc, f"lob spec is missing {', '.join(missing)}"))
                elif not (lob.minBytes <= lob.avgBytes <= lob.maxBytes):
                    out.append(Finding("V25", loc, "lob sizes must satisfy minBytes ≤ avgBytes ≤ maxBytes"))
            if f.fk is not None and not CARDINALITY.match(f.fk.cardinality or ""):
                out.append(Finding("V26", loc, f"cardinality {f.fk.cardinality!r} must look like 'avg / min–max'"))


def _v29_reserved(s: m.Schema, out: list, reserved: set[str]) -> None:
    def check(name: str, loc: str) -> None:
        if name.upper() in reserved:
            out.append(Finding("V29", loc, f"{name!r} is a reserved word (tools/reserved_words.txt)"))
    for t in s.tables:
        check(t.name, t.name)
        check(f"Seq{t.name}Id", f"{t.name} (sequence)")
        for f in t.fields:
            check(f.name, f"{t.name}.{f.name}")
        for i in t.indexes:
            check(i.name, f"{t.name}.{i.name}")


# --------------------------------------------------------------------------- full-profile rules

def _v17_v18_v19_coverage(s: m.Schema, out: list) -> None:
    vol = {k: 0 for k in m.VOLUME_TIERS}
    size = {k: 0 for k in m.SIZE_TIERS}
    cls = {"R": 0, "M": 0, "T": 0}
    lob = {"CLOB": 0, "BLOB": 0, "both": 0, "any": 0}
    for t in s.tables:
        vol[m.volume_tier(t.rows)] += 1
        size[m.size_tier(t)] += 1
        cls[t.cls] = cls.get(t.cls, 0) + 1
        kind = m.lob_kind(t)
        if kind != "none":
            lob["any"] += 1
        if kind in ("CLOB", "both"):
            lob["CLOB"] += 1
        if kind in ("BLOB", "both"):
            lob["BLOB"] += 1
        if kind == "both":
            lob["both"] += 1
    for k, n in vol.items():
        if n < 2:
            out.append(Finding("V17", "<schema>", f"volume tier {k} has {n} table(s); at least 2 required (FR-017)"))
    for k, n in size.items():
        if n < 2:
            out.append(Finding("V17", "<schema>", f"size tier {k} has {n} table(s); at least 2 required (FR-018)"))
    if lob["CLOB"] < 2 or lob["BLOB"] < 2 or lob["both"] < 1 or lob["any"] * 2 >= len(s.tables):
        out.append(Finding("V18", "<schema>", f"LOB mix CLOB={lob['CLOB']} BLOB={lob['BLOB']} both={lob['both']} "
                                              f"any={lob['any']}/{len(s.tables)} violates FR-019"))
    for k, n in cls.items():
        if n < 3:
            out.append(Finding("V19", "<schema>", f"class {k} has {n} table(s); at least 3 required"))


def _v20_types(s: m.Schema, out: list) -> None:
    used = {f.type for t in s.tables for f in t.fields}
    for typ in m.TYPES:
        if typ not in used:
            out.append(Finding("V20", "<schema>", f"data type {typ} is not used by any field (FR-021)"))


def _v21_index_shapes(s: m.Schema, out: list) -> None:
    idx = [i for t in s.tables for i in t.indexes]
    if not any(c.order == "desc" for i in idx for c in i.components):
        out.append(Finding("V21", "<schema>", "no index has a descending component (FR-020)"))
    if not any(i.word for i in idx):
        out.append(Finding("V21", "<schema>", "no word index (FR-020)"))
    if not any(all(i.standard for i in t.indexes) for t in s.tables):
        out.append(Finding("V21", "<schema>", "no table has only the standard indexes (FR-020)"))


def _v22_table_count(s: m.Schema, out: list) -> None:
    if len(s.tables) < 25:
        out.append(Finding("V22", "<schema>", f"{len(s.tables)} tables; at least 25 required (SC-006)"))


def _v23_money(s: m.Schema, out: list) -> None:
    for t in s.tables:
        for f in t.fields:
            loc = f"{t.name}.{f.name}"
            if f.format == MONEY_FORMAT and f.decimals != 2:
                out.append(Finding("V23", loc, "money-format fields must have decimals = 2 (FR-016)"))
            if f.type == "DECIMAL" and MONEY_NAME.match(f.name) and f.format != MONEY_FORMAT:
                out.append(Finding("V23", loc, f"money field must use format {MONEY_FORMAT} (FR-016)"))
    rate = s.get_table("ExchangeRate")
    rf = rate.get_field("Rate") if rate else None
    if rf is not None and (rf.decimals or 0) < 6:
        out.append(Finding("V23", "ExchangeRate.Rate", "FX rates need at least 6 decimals (FR-016)"))


def _v27_size(s: m.Schema, out: list) -> None:
    total = sum(m.estimate_data_bytes(t) + m.estimate_lob_bytes(t) for t in s.tables)
    lo, hi = DATA_TOTAL_RANGE
    if not lo <= total <= hi:
        out.append(Finding("V27", "<schema>", f"estimated data total {total / 1e9:.2f} GB is outside 20–50 GB (SC-008)"))


def _v28_min_scale(s: m.Schema, out: list) -> None:
    for t in s.tables:
        if t.scaling == "linear" and m.rows_at(t, MIN_SCALE_FACTOR) < MIN_ROWS_AT_MIN_SCALE:
            out.append(Finding("V28", t.name, f"only {m.rows_at(t, MIN_SCALE_FACTOR)} rows at scale factor "
                                              f"{MIN_SCALE_FACTOR}; at least {MIN_ROWS_AT_MIN_SCALE} required"))


def validate(schema: m.Schema, profile: str = "structure", reserved: set[str] | None = None) -> list[Finding]:
    """Validate an expanded schema. profile = 'structure' | 'full' | 'loader' (structure minus V11, V12, V16)."""
    if profile not in ("structure", "full", "loader"):
        raise ValueError("profile must be 'structure', 'full' or 'loader'")
    m.expand_standard(schema)
    out: list[Finding] = []
    _v01_names(schema, out)
    _v02_duplicates(schema, out)
    _v03_v04_fields(schema, out)
    _v05_v06_v07_indexes(schema, out)
    _v08_lobs(schema, out)
    _v09_areas(schema, out)
    _v10_descriptions(schema, out)
    if profile != "loader":  # internal loader tables have no standard fields/indexes and no metadata table
        _v11_standard_fields(schema, out)
        _v12_standard_indexes(schema, out)
    _v13_v14_v15_fks(schema, out)
    if profile != "loader":
        _v16_metadata(schema, out)
    _v24_v25_v26_generation(schema, out)
    _v29_reserved(schema, out, load_reserved() if reserved is None else reserved)
    if profile == "full":
        _v17_v18_v19_coverage(schema, out)
        _v20_types(schema, out)
        _v21_index_shapes(schema, out)
        _v22_table_count(schema, out)
        _v23_money(schema, out)
        _v27_size(schema, out)
        _v28_min_scale(schema, out)
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: validate_schema.py <schema.yaml>", file=sys.stderr)
        return 2
    try:
        schema = m.load_expanded(argv[0])
        m.load_order(schema)
    except m.SchemaError as e:
        print(f"{e.rule} {e.location}: {e.message}")
        return 2
    findings = validate(schema, profile="full")
    for f in findings:
        print(f)
    if findings:
        print(f"FAILED: {len(findings)} finding(s)")
        return 1
    nf = sum(len(t.fields) for t in schema.tables)
    ni = sum(len(t.indexes) for t in schema.tables)
    total = sum(m.estimate_data_bytes(t) + m.estimate_lob_bytes(t) for t in schema.tables)
    print(f"OK: {len(schema.tables)} tables, {nf} fields, {ni} indexes, "
          f"estimated data total {total / 1e9:.2f} GB at scale factor 1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
