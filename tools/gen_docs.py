"""Generate the published schema documentation (docs/schema/) from schema/parkbench-schema.yaml.

Layout: specs/001-banking-benchmark-schema/contracts/published-docs-layout.md

Usage:
  python3 tools/gen_docs.py <schema.yaml> --out docs/schema          # write
  python3 tools/gen_docs.py <schema.yaml> --out docs/schema --check  # verify, write nothing

The output is deterministic: running it twice produces identical bytes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import schema_model as m  # noqa: E402
from tools import validate_schema as v  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ACCESS_CONTRACT = ROOT / "specs" / "001-banking-benchmark-schema" / "contracts" / "benchmark-access.md"
CSV_HEADER = "table,rows_sf1,scaling,avg_record_bytes,data_gb,lob_gb,volume_tier,size_tier"
CLASS_NAMES = {"R": "Reference", "M": "Master", "T": "Transactional"}


# --------------------------------------------------------------------------- helpers

def cell(text, html: bool = True) -> str:
    """Make text safe for a Markdown table cell (and, outside code spans, for HTML)."""
    s = str(text).replace("|", "\\|").replace("\n", " ").strip()
    return s.replace("<", "&lt;") if html else s


def code(text) -> str:
    return f"`{cell(text, html=False)}`" if str(text) != "" else ""


def num(n) -> str:
    return f"{int(n):,}"


def initial_text(f: m.Field) -> str:
    if f.initial == "?":
        return "`?` (unknown)"
    if f.initial == "":
        return '`""`' if f.type == "CHARACTER" else ""
    return code(f.initial)


def components_text(i: m.Index) -> str:
    return ", ".join(f"{c.field} {c.order.upper()}" for c in i.components)


def yn(flag: bool) -> str:
    return "Y" if flag else "N"


def table_rows(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def children_of(schema: m.Schema, name: str) -> list[tuple[m.Table, m.Field]]:
    return [(t, f) for t in schema.tables for f in t.fk_fields if f.fk.table == name]


def lob_kind_text(t: m.Table) -> str:
    return {"none": "none", "CLOB": "CLOB", "BLOB": "BLOB", "both": "CLOB + BLOB"}[m.lob_kind(t)]


def area_text(schema: m.Schema, name: str) -> str:
    a = schema.get_area(name)
    if a is None:
        return code(name)
    parts = []
    if a.recordsPerBlock:
        parts.append(f"RPB {a.recordsPerBlock}")
    if a.blocksPerCluster:
        parts.append(f"BPC {a.blocksPerCluster}")
    return f"{code(name)} ({', '.join(parts)})" if parts else code(name)


def max_children(cardinality: str) -> str:
    mm = re.match(r"^[0-9][0-9,.]* / [0-9][0-9,.]*–([0-9][0-9,.]*)", cardinality or "")
    return mm.group(1) if mm else ""


# --------------------------------------------------------------------------- table page

def render_table_page(schema: m.Schema, t: m.Table) -> str:
    vt, st = m.volume_tier(t.rows), m.size_tier(t)
    size_label = "LOB-bearing" if st == "LOB" else st
    out = [f"# {t.name}", "",
           f"`Class {t.cls} ({CLASS_NAMES.get(t.cls, t.cls)})` · `{vt}` · `{size_label}` · `LOB: {lob_kind_text(t)}`",
           "", "[← Schema overview](../README.md)", ""]

    # 2. Description
    out += ["## Description", "", t.description.rstrip(".") + "."]
    if t.notes:
        out += ["", t.notes]
    out.append("")

    # 3. Facts
    rec = m.estimate_record_bytes(t)
    facts = [
        ["Rows at scale factor 1", num(t.rows)],
        ["Scaling", "fixed (does not change with scale factor)" if t.scaling == "fixed"
         else "linear (rows × scale factor)"],
        ["Volume tier", vt],
        ["Estimated average record", f"{num(rec)} bytes (field-by-field estimate: {num(m.computed_record_bytes(t))} bytes)"],
        ["Record-size tier", size_label],
        ["Estimated data at SF 1", f"{m.estimate_data_bytes(t) / 1e9:.3f} GB"],
    ]
    if t.lob_fields:
        facts.append(["Estimated LOB content at SF 1", f"{m.estimate_lob_bytes(t) / 1e9:.3f} GB"])
    facts += [
        ["Data area", area_text(schema, t.area)],
        ["Index area", area_text(schema, t.indexArea)],
    ]
    lob_areas = sorted({f.lob.area for f in t.lob_fields if f.lob})
    if lob_areas:
        facts.append(["LOB areas", ", ".join(area_text(schema, a) for a in lob_areas)])
    facts.append(["Sequence", code(f"Seq{t.name}Id") + " (INT64, starts at 1, increment 1, no cycle)"])
    out += ["## Facts", ""] + table_rows(["Property", "Value"], facts) + [""]

    # 4. Fields
    rows = []
    for n, f in enumerate(t.fields, 1):
        name = code(f.name) + (" *(std)*" if f.standard else "")
        desc = cell(f.description)
        if f.fk:
            link = f"[{f.fk.table}]({f.fk.table}.md).`{f.fk.parent_field}`"
            if desc in ("", f"Reference to {f.fk.table}"):
                desc = f"Reference to {link}"
            else:
                desc = f"{desc} → {link}"
        rows.append([str(n), name, f.type, code(f.format) if f.format else "–",
                     str(f.decimals) if f.decimals is not None else "",
                     yn(f.mandatory), initial_text(f), cell(f.display_label), desc, cell(f.gen)])
    out += ["## Fields", "",
            f"{len(t.fields)} fields. *(std)* marks the standard fields present on every table.", ""]
    out += table_rows(["#", "Name", "Type", "Format", "Decimals", "Mandatory", "Initial", "Label",
                       "Description", "Generation"], rows) + [""]

    # 5. LOB fields
    if t.lob_fields:
        lrows = []
        for f in t.lob_fields:
            lob = f.lob or m.LobSpec()
            pct = f"{(lob.fractionPopulated or 0) * 100:g}%"
            lrows.append([code(f.name), f.type, code(lob.area), cell(lob.maxSize), cell(lob.codepage or "–"),
                          cell(lob.content), pct,
                          f"{num(lob.minBytes or 0)} / {num(lob.avgBytes or 0)} / {num(lob.maxBytes or 0)}"])
        out += ["## LOB fields", ""]
        out += table_rows(["Field", "Type", "Area", "Max size", "Codepage", "Content", "Populated",
                           "Min / Avg / Max bytes"], lrows) + [""]

    # 6. Indexes
    irows = [[code(i.name) + (" *(std)*" if i.standard else ""), cell(components_text(i)),
              yn(i.primary), yn(i.unique), yn(i.word), cell(i.purpose)] for i in t.indexes]
    out += ["## Indexes", "",
            f"{len(t.indexes)} indexes ({sum(1 for i in t.indexes if not i.standard)} table-specific).", ""]
    out += table_rows(["Name", "Components", "Primary", "Unique", "Word", "Purpose"], irows) + [""]

    # 7. Relationships
    out += ["## Relationships", "", "**Parents**", ""]
    if t.fk_fields:
        for f in t.fk_fields:
            line = (f"- `{f.name}` → [{f.fk.table}]({f.fk.table}.md).`{f.fk.parent_field}`"
                    f" — {f.fk.cardinality} children per parent")
            if f.fk.optional:
                line += "; optional (0 = none)"
            if not f.fk.indexed:
                line += f"; not indexed: {f.fk.reason}"
            out.append(line)
    else:
        out.append("- none")
    out += ["", "**Children**", ""]
    kids = children_of(schema, t.name)
    out += [f"- [{c.name}]({c.name}.md).`{f.name}`" for c, f in kids] or ["- none"]
    out.append("")

    # 8. Access examples
    n = t.name
    out += ["## Access examples", "",
            "ABL: about 1% of rows, then one random existing row.", "", "```abl",
            f"FOR EACH {n} NO-LOCK WHERE {n}.RandomInt100 = 42 USE-INDEX IxRandomInt100:",
            "    /* work */",
            "END.",
            "",
            "DEFINE VARIABLE r AS INT64 NO-UNDO.",
            f'FIND BenchmarkTableInfo NO-LOCK WHERE BenchmarkTableInfo.TableName = "{n}".',
            "r = RANDOM(1, INTEGER(BenchmarkTableInfo.MaxId)).",
            f"FIND {n} NO-LOCK WHERE {n}.{n}Id = r NO-ERROR.   /* not AVAILABLE => draw again */",
            "```", "",
            "SQL:", "", "```sql",
            f"SELECT * FROM PUB.{n} WHERE RandomInt100 = 42;",
            f"SELECT MaxId FROM PUB.BenchmarkTableInfo WHERE TableName = '{n}';",
            f"SELECT * FROM PUB.{n} WHERE {n}Id = ?;   -- ? drawn uniformly from 1..MaxId",
            "```", ""]
    return "\n".join(out)


# --------------------------------------------------------------------------- README

def _access_guide() -> list[str]:
    """The benchmark access contract, with headings demoted one level."""
    text = ACCESS_CONTRACT.read_text(encoding="utf-8")
    body = text[text.index("## Guarantees"):]
    lines = []
    for line in body.rstrip("\n").split("\n"):
        lines.append("#" + line if line.startswith("## ") else line)
    return lines


def _conventions(schema: m.Schema) -> list[str]:
    out = ["## Conventions", "",
           "- **Tables**: PascalCase, singular (`DebitTransaction`).",
           "- **Fields**: PascalCase. The sequential ID is `<Table>Id`. A foreign key reuses the parent's ID name "
           "(`AccountId`); when one table has two keys to the same parent, the role is a prefix (`FromAccountId`, "
           "`ToAccountId`). Currency and country are referenced by ISO code (`CurrencyCode`, `CountryCode`).",
           "- **Indexes**: `Pk<Table>` = primary unique ID index, `Ux…` = other unique, `Ix…` = non-unique, "
           "`Wx…` = word index. The RandomInt indexes are always `IxRandomInt10`, `IxRandomInt100`, `IxRandomInt1000`.",
           "- **Identifiers**: letters and digits only (no hyphens), at most 32 characters, and never an OpenEdge SQL, "
           "SQL-92 or ABL reserved word (see `tools/reserved_words.txt`), so every name works unquoted in both ABL "
           "and OpenEdge SQL.",
           "- **No extent (array) fields** are used anywhere in the schema. Repeating values are separate fields or "
           "child rows.",
           "- **0 and `?`**: an optional foreign key is mandatory with 0 meaning \"none\"; optional dates and LOBs "
           "use the unknown value `?`.",
           "", "### Standard fields (every table, in this order)", ""]
    std = m.expand_standard(schema).tables[0]
    rows = []
    for f in [f for f in std.fields if f.standard][:5]:
        name = f.name.replace(std.name, "<Table>") if f.name == f"{std.name}Id" else f.name
        desc = f.description.replace(std.name, "<Table>")
        rows.append([code(name), f.type, code(f.format), yn(f.mandatory), code(f.initial), cell(desc)])
    for d in schema.masterFields:
        rows.append([code(d["name"]) + " (class M only, last field)", d["type"], code(d.get("format", "")),
                     yn(d.get("mandatory", False)), code(d.get("initial", "")), cell(d.get("description", ""))])
    out += table_rows(["Field", "Type", "Format", "Mandatory", "Initial", "Description"], rows)
    out += ["", "### Standard indexes (every table)", ""]
    irows = []
    for d in schema.standardIndexes:
        comps = ", ".join(f"{c['field']} {c.get('order', 'asc').upper()}" for c in d["components"])
        irows.append([code(d["name"].replace("{Table}", "<Table>")), cell(comps.replace("{Table}", "<Table>")),
                      yn(d.get("primary", False)), yn(d.get("unique", False)), cell(d.get("purpose", ""))])
    out += table_rows(["Index", "Components", "Primary", "Unique", "Purpose"], irows)
    out += ["", "### Format strings", ""]
    out += table_rows(["Kind", "Type", "Decimals", "Format"], [
        ["Money", "DECIMAL", "2", "`->>>,>>>,>>>,>>9.99` (max 999,999,999,999.99)"],
        ["Interest rate (%)", "DECIMAL", "4", "`>>9.9999`"],
        ["FX rate", "DECIMAL", "8", "`>>>>>9.99999999`"],
        ["Percent", "DECIMAL", "2", "`>>9.99`"],
        ["ID / foreign key", "INT64", "–", "`>>>>>>>>>>>9`"],
        ["Date", "DATE", "–", "`99/99/9999`"],
        ["Datetime (local)", "DATETIME", "–", "`99/99/9999 HH:MM:SS.SSS`"],
        ["Datetime-TZ", "DATETIME-TZ", "–", "`99/99/9999 HH:MM:SS.SSS+HH:MM`"],
        ["Logical", "LOGICAL", "–", "`yes/no`"],
        ["Character", "CHARACTER", "–", "`x(n)`; SQL width (MAX-WIDTH) = 2 × n"],
    ])
    return out + [""]


def _summary_matrix(schema: m.Schema) -> list[str]:
    rows = []
    for n, t in enumerate(schema.tables, 1):
        rows.append([str(n), f"[{t.name}](tables/{t.name}.md)", t.cls, num(t.rows), t.scaling,
                     num(m.estimate_record_bytes(t)), m.size_tier(t), m.volume_tier(t.rows), lob_kind_text(t),
                     f"{len(t.indexes)} ({sum(1 for i in t.indexes if not i.standard)} extra)", code(t.area)])
    return ["## Summary matrix", "",
            "Rows and tiers are at scale factor 1. *Indexes* counts the 4 standard indexes plus the table-specific ones.",
            ""] + table_rows(["#", "Table", "Class", "Rows @SF1", "Scaling", "Avg rec (B)", "Size tier",
                              "Volume tier", "LOB", "Indexes", "Area"], rows) + [""]


def _tier_coverage(schema: m.Schema) -> list[str]:
    def members(pred):
        return [t.name for t in schema.tables if pred(t)]

    groups = []
    for tier in m.VOLUME_TIERS:
        groups.append((f"Volume: {tier}", members(lambda t, tier=tier: m.volume_tier(t.rows) == tier), 2, "FR-017"))
    for tier in m.SIZE_TIERS:
        label = "LOB-bearing" if tier == "LOB" else tier
        groups.append((f"Size: {label}", members(lambda t, tier=tier: m.size_tier(t) == tier), 2, "FR-018"))
    groups.append(("LOB: has CLOB", members(lambda t: m.lob_kind(t) in ("CLOB", "both")), 2, "FR-019"))
    groups.append(("LOB: has BLOB", members(lambda t: m.lob_kind(t) in ("BLOB", "both")), 2, "FR-019"))
    groups.append(("LOB: has both", members(lambda t: m.lob_kind(t) == "both"), 1, "FR-019"))
    for c in ("R", "M", "T"):
        groups.append((f"Class: {c} ({CLASS_NAMES[c]})", members(lambda t, c=c: t.cls == c), 3, "US3"))
    rows = [[g, str(len(ts)), f"≥ {need}", "✔" if len(ts) >= need else "✘", src, cell(", ".join(ts))]
            for g, ts, need, src in groups]
    no_lob = sum(1 for t in schema.tables if m.lob_kind(t) == "none")
    rows.append(["LOB: none (majority)", str(no_lob), f"> {len(schema.tables) // 2}",
                 "✔" if no_lob * 2 > len(schema.tables) else "✘", "FR-019", "—"])
    out = ["## Tier coverage", ""] + table_rows(["Group", "Count", "Required", "OK", "Source", "Tables"], rows)

    shapes = []
    all_idx = [(t, i) for t in schema.tables for i in t.indexes if not i.standard]

    def first(pred):
        return next((f"{t.name}.{i.name}" for t, i in all_idx if pred(t, i)), None)

    shapes.append(("Single-field", first(lambda t, i: len(i.components) == 1 and not i.word)))
    shapes.append(("Multi-field", first(lambda t, i: len(i.components) > 1)))
    shapes.append(("Unique, non-primary", first(lambda t, i: i.unique)))
    shapes.append(("Descending component", ", ".join(f"{t.name}.{i.name}" for t, i in all_idx
                                                      if any(c.order == "desc" for c in i.components))))
    shapes.append(("Word index", ", ".join(f"{t.name}.{i.name}" for t, i in all_idx if i.word)))
    shapes.append(("Standard indexes only", ", ".join(t.name for t in schema.tables
                                                       if all(i.standard for i in t.indexes))))
    char_fk = next((f"{t.name}.{f.name} → {f.fk.table}.{f.fk.parent_field}" for t in schema.tables
                    for f in t.fk_fields if f.type == "CHARACTER" and f.fk.indexed), None)
    shapes.append(("Character-key join", char_fk))
    out += ["", "### Index shapes", ""] + table_rows(["Shape", "Examples"],
                                                     [[s, cell(e or "✘ none")] for s, e in shapes])
    return out + [""]


def _er_diagram(schema: m.Schema) -> list[str]:
    out = ["## Entity-relationship diagram", "",
           "`||--o{` = one parent, many children; `||--o|` = at most one child per parent; "
           "`|o` on the parent side = optional FK (0 = none).", "", "```mermaid", "erDiagram"]
    for t in schema.tables:
        for f in t.fk_fields:
            left = "|o" if f.fk.optional else "||"
            right = "o|" if max_children(f.fk.cardinality) == "1" else "o{"
            out.append(f'    {f.fk.table} {left}--{right} {t.name} : "{f.name}"')
    out += ["```", "", "### Relationships", ""]
    rows = []
    for t in schema.tables:
        for f in t.fk_fields:
            rows.append([f"[{t.name}](tables/{t.name}.md)", code(f.name),
                         f"[{f.fk.table}](tables/{f.fk.table}.md).`{f.fk.parent_field}`", cell(f.fk.cardinality),
                         "Y (0 = none)" if f.fk.optional else "N",
                         "Y" if f.fk.indexed else f"N: {cell(f.fk.reason)}"])
    out += table_rows(["Child", "FK field", "Parent", "Cardinality (avg / min–max per parent)", "Optional",
                       "Indexed"], rows)
    out += ["", "`AuditLog.TableName` + `AuditLog.RecordId` form a polymorphic reference to any table's "
            "`<Table>Id`; it is not a foreign key and is not indexed."]
    return out + [""]


def _storage_areas(schema: m.Schema) -> list[str]:
    rows = []
    for a in schema.areas:
        if a.kind == "data":
            contents = [t.name for t in schema.tables if t.area == a.name]
        elif a.kind == "index":
            contents = [f"{t.name} indexes" for t in schema.tables if t.indexArea == a.name]
        else:
            contents = [f"{t.name}.{f.name}" for t in schema.tables for f in t.lob_fields
                        if f.lob and f.lob.area == a.name]
        rows.append([code(a.name), a.kind, str(a.recordsPerBlock or "–"), str(a.blocksPerCluster or "–"),
                     cell(a.description), cell(", ".join(contents) or "—")])
    return ["## Storage areas", "",
            f"Type II storage areas with {num(schema.blockSizeBytes)}-byte blocks. Records per block (RPB) "
            "follows `RPB ≈ 8192 / (average record size + 20)`, rounded down to a power of two (min 4, max 128), "
            "using the largest records in the area. All Tiny and Small tables share `PB_Ref_Data` at 64 RPB "
            "regardless of width, because the waste is negligible under 100,000 rows. Blocks per cluster (BPC) is "
            "8 for Tiny/Small, 64 for Medium and 512 for Large/Very Large tables. Indexes and LOB content always "
            "live in their own areas.", ""] + table_rows(
        ["Area", "Kind", "RPB", "BPC", "Description", "Contents"], rows) + [""]


def _load_order(schema: m.Schema) -> list[str]:
    out = ["## Load order", "",
           "Tables in the same level have no dependencies on each other and can load in parallel. A table's level "
           "is one more than the highest level of its parents.", ""]
    for n, lv in enumerate(m.load_order(schema)):
        out.append(f"{n + 1}. **Level {n}**: " + ", ".join(f"[{x}](tables/{x}.md)" for x in lv))
    out += ["", "Placement notes:", "",
            "- **AccountStatement before its transactions**: AccountStatement loads before the transactions so each "
            "debit/credit can carry an `AccountStatementId`. The loader generates a statement's totals from the "
            "transactions it plans to create, then fills them in.",
            "- **CardAuthorization and LoanPayment after the debits**: both reference `DebitTransactionId`, so they "
            "load after DebitTransaction.",
            "- **No cycles**: the graph has no cycles, because `Branch` deliberately has no manager FK (the manager "
            "is flagged by `Employee.IsBranchManager` instead).",
            "- **Loaded last by convention**: AuditLog (it logs the load itself), then BenchmarkTableInfo (it "
            "records the final row counts and max IDs)."]
    return out + [""]


def _sizing(schema: m.Schema) -> list[str]:
    rows_total = sum(t.rows for t in schema.tables)
    data = sum(m.estimate_data_bytes(t) for t in schema.tables)
    lob = sum(m.estimate_lob_bytes(t) for t in schema.tables)
    tier_rows = []
    for tier in m.VOLUME_TIERS:
        ts = [t for t in schema.tables if m.volume_tier(t.rows) == tier]
        tier_rows.append([tier, str(len(ts)), num(sum(t.rows for t in ts)),
                          f"{sum(m.estimate_data_bytes(t) + m.estimate_lob_bytes(t) for t in ts) / 1e9:.2f}"])
    out = ["## Sizing", "",
           "Estimates at scale factor 1 (≈ 1,000,000 customers). Per-table numbers are in [sizing.csv](sizing.csv).",
           ""] + table_rows(["Measure", "Estimate"], [
        ["Total rows", num(rows_total)],
        ["Record data", f"{data / 1e9:.2f} GB"],
        ["LOB content", f"{lob / 1e9:.2f} GB"],
        ["**Data total**", f"**{(data + lob) / 1e9:.2f} GB** (target 20–50 GB)"],
    ])
    out += ["", "Index space is estimated at a further 15–20 GB; on-disk total ≈ 55–60 GB at SF 1; use SF 0.75 to "
            "stay under 50 GB on disk.", "",
            "**Scaling**: fixed tables do not scale; linear tables = rows × SF. The minimum supported scale factor "
            "is 0.01 (every linear table then has at least 50 rows). Volume tiers are defined at scale factor 1.",
            "", "**Record-size estimates** use 15 bytes of record overhead plus, per field, a 1-byte header and the "
            "stored value (INTEGER 2, INT64 5, DECIMAL ≈ digits/2 + 1, DATE 3, DATETIME 7, DATETIME-TZ 9, "
            "LOGICAL 1, CHARACTER ≈ actual length, LOB locator 10). They are ±25%; measure the real database with "
            "`proutil tabanalys`.", "", "### By volume tier", ""]
    out += table_rows(["Volume tier", "Tables", "Rows", "Data + LOB GB"], tier_rows)
    return out + [""]


def _sequences(schema: m.Schema) -> list[str]:
    out = ["## Sequences", "",
           f"{len(schema.tables)} sequences, one per table: INT64, initial value 1, increment 1, no cycle. After the "
           "load each is set to the table's `MaxId`; runtime inserts use `NEXT-VALUE(Seq<Table>Id)`. Sequences are "
           "not transactional, so a rolled-back insert leaves a gap.", ""]
    out += [f"- `Seq{t.name}Id`" for t in schema.tables]
    return out + [""]


def _building(schema: m.Schema) -> list[str]:
    return ["## Building the database", "",
            "The same schema source generates the OpenEdge 12.8 definition files in [`db/`](../../db/README.md): "
            "`parkbench.df` (sequences, tables, fields, indexes), `parkbench.st` (one variable extent per storage "
            "area) and `parkbench.expect` (values checked after the build).", "",
            "```bash",
            "python3 tools/gen_db_files.py schema/parkbench-schema.yaml --out db   # regenerate (--check to verify)",
            "db/build_db.sh /data/parkbench                                          # or db\\build_db.bat on Windows",
            "```", "",
            "The build script creates the structure, copies in the UTF-8 empty database, sets the before-image to "
            "16 KB blocks and 16 MB clusters, confirms large files, loads the `.df` and verifies the result. See "
            "[db/README.md](../../db/README.md) for the manual steps and exit codes.", "",
            "### Loading data", "",
            "`pbgen` fills a served database with deterministic Faker data, in parallel, resumably and "
            "incrementally (for example 1 GB, then `grow --add-gb 4`). See "
            "[docs/data-generation.md](../data-generation.md).", ""]


def render_readme(schema: m.Schema) -> str:
    nf = sum(len(t.fields) for t in schema.tables)
    ni = sum(len(t.indexes) for t in schema.tables)
    out = [f"# {schema.name} schema", "",
           "> Generated from `schema/parkbench-schema.yaml` by `tools/gen_docs.py`. Do not edit by hand.", "",
           "## Purpose and scope", "",
           f"{schema.name} is a synthetic retail-banking transaction database for **{schema.target}** benchmarking. "
           f"It has {len(schema.tables)} tables, {nf} fields and {ni} indexes, chosen to cover a wide mix of row "
           "counts, record sizes, LOB usage and index shapes. Every table has a dense sequential ID and three "
           "indexed random fields (`RandomInt10`, `RandomInt100`, `RandomInt1000`), so benchmark scripts can "
           "select random subsets or single rows without knowing valid IDs.", "",
           f"The history window is {schema.historyMonths} months, ending on the load's as-of date "
           f"({schema.asOfDateRule}). All data is synthetic. This documentation describes the schema only; creating "
           "the database, loading data and writing benchmarks are separate work.", ""]
    out += _conventions(schema)
    out += ["## Benchmark access guide", ""] + _access_guide() + [""]
    out += _summary_matrix(schema)
    out += _tier_coverage(schema)
    out += _er_diagram(schema)
    out += _storage_areas(schema)
    out += _load_order(schema)
    out += _sizing(schema)
    out += _sequences(schema)
    out += _building(schema)
    return "\n".join(out)


def render_sizing_csv(schema: m.Schema) -> str:
    lines = [CSV_HEADER]
    for t in schema.tables:
        lines.append(",".join([t.name, str(t.rows), t.scaling, str(m.estimate_record_bytes(t)),
                               f"{m.estimate_data_bytes(t) / 1e9:.3f}", f"{m.estimate_lob_bytes(t) / 1e9:.3f}",
                               m.volume_tier(t.rows), m.size_tier(t)]))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- CLI

def render_all(schema: m.Schema) -> dict[str, str]:
    files = {"README.md": render_readme(schema), "sizing.csv": render_sizing_csv(schema)}
    for t in schema.tables:
        files[f"tables/{t.name}.md"] = render_table_page(schema, t)
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("schema")
    ap.add_argument("--out", required=True)
    ap.add_argument("--check", action="store_true", help="verify the output is up to date; write nothing")
    args = ap.parse_args(argv)

    try:
        schema = m.load_expanded(args.schema)
        m.load_order(schema)
    except m.SchemaError as e:
        print(f"{e.rule} {e.location}: {e.message}")
        return 2
    findings = v.validate(schema, profile="full")
    if findings:
        for f in findings:
            print(f)
        print(f"ABORTED: {len(findings)} validation finding(s); nothing generated")
        return 1

    out = Path(args.out)
    files = render_all(schema)
    existing = {p.relative_to(out).as_posix() for p in (out / "tables").glob("*.md")} if (out / "tables").exists() else set()
    stale = sorted(existing - set(files))

    if args.check:
        differ = [rel for rel, text in files.items()
                  if not (out / rel).exists() or (out / rel).read_text(encoding="utf-8") != text]
        for rel in differ + stale:
            print(f"out of date: {out / rel}")
        if differ or stale:
            return 1
        print(f"OK: {len(files)} files up to date in {out}")
        return 0

    (out / "tables").mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        with open(out / rel, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    for rel in stale:
        (out / rel).unlink()
    print(f"Wrote {len(files)} files to {out}" + (f"; removed {len(stale)} stale" if stale else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
