"""Object model for the ParkBenchDB schema source (schema/parkbench-schema.yaml).

Loads the YAML with strict key checking, injects the standard fields and indexes,
estimates record/LOB sizes (research.md R6), classifies tiers, and computes the
load order (research.md R12).

The source format is specified in
specs/001-banking-benchmark-schema/contracts/schema-source-format.md.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

TYPES = (
    "CHARACTER", "INTEGER", "INT64", "DECIMAL", "LOGICAL",
    "DATE", "DATETIME", "DATETIME-TZ", "CLOB", "BLOB",
)
LOB_TYPES = ("CLOB", "BLOB")

VOLUME_TIERS = ("Tiny", "Small", "Medium", "Large", "Very Large")
SIZE_TIERS = ("Narrow", "Standard", "Wide", "LOB")

# Keys allowed at each level of the YAML (contracts/schema-source-format.md).
_KEYS = {
    "root": {"schema", "standardFields", "masterFields", "standardIndexes", "areas", "tables"},
    "schema": {"name", "target", "blockSizeBytes", "asOfDateRule", "historyMonths"},
    "area": {"name", "kind", "recordsPerBlock", "blocksPerCluster", "description"},
    "table": {"name", "description", "class", "rows", "scaling", "area", "indexArea",
              "estimatedRecordBytes", "notes", "fields", "indexes"},
    "field": {"name", "type", "format", "decimals", "mandatory", "initial", "label",
              "description", "gen", "avgBytes", "fk", "lob"},
    "fk": {"table", "field", "optional", "indexed", "reason", "cardinality"},
    "lob": {"area", "maxSize", "codepage", "content", "fractionPopulated",
            "avgBytes", "minBytes", "maxBytes"},
    "index": {"name", "unique", "word", "primary", "purpose", "components"},
    "component": {"field", "order"},
}


class SchemaError(Exception):
    """A structural problem that prevents the schema from being loaded."""

    def __init__(self, rule: str, location: str, message: str):
        super().__init__(f"{rule} {location}: {message}")
        self.rule = rule
        self.location = location
        self.message = message


@dataclass
class Area:
    name: str
    kind: str  # data | index | lob
    recordsPerBlock: int | None = None
    blocksPerCluster: int | None = None
    description: str = ""


@dataclass
class LobSpec:
    area: str = ""
    maxSize: str = ""
    codepage: str | None = None
    content: str = ""
    fractionPopulated: float | None = None
    avgBytes: int | None = None
    minBytes: int | None = None
    maxBytes: int | None = None


@dataclass
class FkSpec:
    table: str
    field: str | None = None
    optional: bool = False
    indexed: bool = True
    reason: str = ""
    cardinality: str = ""

    @property
    def parent_field(self) -> str:
        return self.field or f"{self.table}Id"


@dataclass
class Field:
    name: str
    type: str
    format: str | None = None
    decimals: int | None = None
    mandatory: bool = False
    initial: str = ""
    label: str | None = None
    description: str = ""
    gen: str = ""
    avgBytes: int | None = None
    fk: FkSpec | None = None
    lob: LobSpec | None = None
    standard: bool = False

    @property
    def display_label(self) -> str:
        return self.label or split_camel(self.name)

    @property
    def is_lob(self) -> bool:
        return self.type in LOB_TYPES


@dataclass
class IndexComponent:
    field: str
    order: str = "asc"


@dataclass
class Index:
    name: str
    components: list[IndexComponent]
    unique: bool = False
    word: bool = False
    primary: bool = False
    purpose: str = ""
    standard: bool = False


@dataclass
class Table:
    name: str
    description: str
    cls: str
    rows: int
    scaling: str
    area: str
    indexArea: str
    estimatedRecordBytes: int | None = None
    notes: str = ""
    fields: list[Field] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)

    def get_field(self, name: str) -> Field | None:
        return next((f for f in self.fields if f.name == name), None)

    def get_index(self, name: str) -> Index | None:
        return next((i for i in self.indexes if i.name == name), None)

    @property
    def lob_fields(self) -> list[Field]:
        return [f for f in self.fields if f.is_lob]

    @property
    def fk_fields(self) -> list[Field]:
        return [f for f in self.fields if f.fk is not None]


@dataclass
class Schema:
    name: str
    target: str
    blockSizeBytes: int
    asOfDateRule: str
    historyMonths: int
    standardFields: list[dict]
    masterFields: list[dict]
    standardIndexes: list[dict]
    areas: list[Area]
    tables: list[Table]
    expanded: bool = False

    def get_table(self, name: str) -> Table | None:
        return next((t for t in self.tables if t.name == name), None)

    def get_area(self, name: str) -> Area | None:
        return next((a for a in self.areas if a.name == name), None)


# --------------------------------------------------------------------------- loading

def split_camel(name: str) -> str:
    """AccountId -> 'Account Id'; RandomInt10 -> 'Random Int 10'."""
    return re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)


def _check_keys(obj, level: str, location: str) -> None:
    if not isinstance(obj, dict):
        raise SchemaError("S01", location, f"expected a mapping for {level}")
    if "extent" in obj:
        raise SchemaError("S02", location, "extent fields are not allowed (clarification 2026-09-27)")
    unknown = sorted(set(obj) - _KEYS[level])
    if unknown:
        raise SchemaError("S01", location, f"unknown key(s) for {level}: {', '.join(unknown)}")


def _str(value) -> str:
    return "" if value is None else str(value)


def _field(d: dict, location: str) -> Field:
    _check_keys(d, "field", location)
    fk = lob = None
    if d.get("fk") is not None:
        _check_keys(d["fk"], "fk", f"{location}.fk")
        fk = FkSpec(**d["fk"])
        fk.reason = _str(fk.reason)
        fk.cardinality = _str(fk.cardinality)
    if d.get("lob") is not None:
        _check_keys(d["lob"], "lob", f"{location}.lob")
        lob = LobSpec(**d["lob"])
    return Field(
        name=_str(d.get("name")),
        type=_str(d.get("type")),
        format=d.get("format"),
        decimals=d.get("decimals"),
        mandatory=bool(d.get("mandatory", False)),
        initial=_str(d.get("initial", "")),
        label=d.get("label"),
        description=_str(d.get("description")),
        gen=_str(d.get("gen")),
        avgBytes=d.get("avgBytes"),
        fk=fk,
        lob=lob,
    )


def _index(d: dict, location: str) -> Index:
    _check_keys(d, "index", location)
    comps = []
    for n, c in enumerate(d.get("components") or []):
        _check_keys(c, "component", f"{location}.components[{n}]")
        comps.append(IndexComponent(field=_str(c.get("field")), order=_str(c.get("order", "asc")).lower()))
    return Index(
        name=_str(d.get("name")),
        components=comps,
        unique=bool(d.get("unique", False)),
        word=bool(d.get("word", False)),
        primary=bool(d.get("primary", False)),
        purpose=_str(d.get("purpose")),
    )


def load_schema(path: str | Path) -> Schema:
    """Load and structurally parse the schema YAML. Semantics are left to the checker."""
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    _check_keys(raw, "root", "<root>")
    head = raw.get("schema") or {}
    _check_keys(head, "schema", "schema")

    for group in ("standardFields", "masterFields"):
        for n, f in enumerate(raw.get(group) or []):
            _check_keys(f, "field", f"{group}[{n}]")
    for n, i in enumerate(raw.get("standardIndexes") or []):
        _check_keys(i, "index", f"standardIndexes[{n}]")

    areas = []
    for n, a in enumerate(raw.get("areas") or []):
        _check_keys(a, "area", f"areas[{n}]")
        areas.append(Area(**a))

    tables = []
    for n, t in enumerate(raw.get("tables") or []):
        tname = _str(t.get("name")) if isinstance(t, dict) else f"tables[{n}]"
        _check_keys(t, "table", tname)
        tables.append(Table(
            name=tname,
            description=_str(t.get("description")),
            cls=_str(t.get("class")),
            rows=int(t.get("rows") or 0),
            scaling=_str(t.get("scaling")),
            area=_str(t.get("area")),
            indexArea=_str(t.get("indexArea")),
            estimatedRecordBytes=t.get("estimatedRecordBytes"),
            notes=_str(t.get("notes")),
            fields=[_field(f, f"{tname}.{f.get('name', n)}" if isinstance(f, dict) else tname)
                    for n, f in enumerate(t.get("fields") or [])],
            indexes=[_index(i, f"{tname}.{i.get('name', n)}" if isinstance(i, dict) else tname)
                     for n, i in enumerate(t.get("indexes") or [])],
        ))

    return Schema(
        name=_str(head.get("name")),
        target=_str(head.get("target")),
        blockSizeBytes=int(head.get("blockSizeBytes") or 8192),
        asOfDateRule=_str(head.get("asOfDateRule")),
        historyMonths=int(head.get("historyMonths") or 12),
        standardFields=raw.get("standardFields") or [],
        masterFields=raw.get("masterFields") or [],
        standardIndexes=raw.get("standardIndexes") or [],
        areas=areas,
        tables=tables,
    )


# --------------------------------------------------------------------------- expansion

def _subst(value, table: str):
    if isinstance(value, str):
        return value.replace("{Table}", table)
    if isinstance(value, list):
        return [_subst(v, table) for v in value]
    if isinstance(value, dict):
        return {k: _subst(v, table) for k, v in value.items()}
    return value


def expand_standard(schema: Schema) -> Schema:
    """Inject standard fields/indexes (data-model.md §1.1, §1.2) into every table. Idempotent."""
    if schema.expanded:
        return schema
    for t in schema.tables:
        std_fields = []
        for n, d in enumerate(schema.standardFields):
            f = _field(_subst(d, t.name), f"standardFields[{n}]")
            f.standard = True
            std_fields.append(f)
        extra = []
        if t.cls == "M":
            if t.get_field("UpdatedAt") is not None:
                raise SchemaError("S03", f"{t.name}.UpdatedAt", "UpdatedAt is injected; remove it from the table")
            for n, d in enumerate(schema.masterFields):
                f = _field(_subst(d, t.name), f"masterFields[{n}]")
                f.standard = True
                extra.append(f)
        t.fields = std_fields + t.fields + extra

        std_idx = []
        for n, d in enumerate(schema.standardIndexes):
            i = _index(_subst(d, t.name), f"standardIndexes[{n}]")
            i.standard = True
            std_idx.append(i)
        t.indexes = std_idx + t.indexes
    schema.expanded = True
    return schema


def load_expanded(path: str | Path) -> Schema:
    return expand_standard(load_schema(path))


# --------------------------------------------------------------------------- sizing

_FIXED_BYTES = {"INTEGER": 2, "INT64": 5, "DATE": 3, "DATETIME": 7, "DATETIME-TZ": 9,
                "LOGICAL": 1, "CLOB": 10, "BLOB": 10}
RECORD_OVERHEAD = 15


def char_width(fmt: str | None) -> int:
    """Width of a CHARACTER format such as x(40) or xxx."""
    if not fmt:
        return 0
    m = re.fullmatch(r"[xX]\((\d+)\)", fmt.strip())
    if m:
        return int(m.group(1))
    return len(fmt)


def field_value_bytes(f: Field) -> int:
    if f.avgBytes is not None and not f.is_lob:
        return int(f.avgBytes)
    if f.type in _FIXED_BYTES:
        return _FIXED_BYTES[f.type]
    if f.type == "DECIMAL":
        digits = sum(1 for ch in (f.format or "") if ch in "9><")
        return math.ceil(digits / 2) + 1
    if f.type == "CHARACTER":
        return max(1, char_width(f.format) // 2)
    return 1


def computed_record_bytes(table: Table) -> int:
    return RECORD_OVERHEAD + sum(1 + field_value_bytes(f) for f in table.fields)


def estimate_record_bytes(table: Table) -> int:
    """Average stored record size; the table's explicit estimate wins when present."""
    if table.estimatedRecordBytes:
        return int(table.estimatedRecordBytes)
    return computed_record_bytes(table)


def lob_bytes_per_row(table: Table) -> float:
    return sum((f.lob.fractionPopulated or 0) * (f.lob.avgBytes or 0)
               for f in table.lob_fields if f.lob is not None)


def estimate_lob_bytes(table: Table, sf: float = 1.0) -> float:
    return rows_at(table, sf) * lob_bytes_per_row(table)


def estimate_data_bytes(table: Table, sf: float = 1.0) -> float:
    return rows_at(table, sf) * estimate_record_bytes(table)


def rows_at(table: Table, sf: float) -> int:
    return table.rows if table.scaling == "fixed" else round(table.rows * sf)


def volume_tier(rows: int) -> str:
    if rows < 1_000:
        return "Tiny"
    if rows < 100_000:
        return "Small"
    if rows < 5_000_000:
        return "Medium"
    if rows < 50_000_000:
        return "Large"
    return "Very Large"


def size_tier(table: Table) -> str:
    if table.lob_fields:
        return "LOB"
    b = estimate_record_bytes(table)
    if b < 150:
        return "Narrow"
    if b <= 600:
        return "Standard"
    return "Wide"


def lob_kind(table: Table) -> str:
    kinds = {f.type for f in table.lob_fields}
    if kinds == {"CLOB", "BLOB"}:
        return "both"
    if kinds:
        return kinds.pop()
    return "none"


def rpb_for(avg_bytes: int, block_size: int = 8192) -> int:
    """Records-per-block recommendation (research.md R9): power of two, 4..128."""
    raw = block_size / (avg_bytes + 20)
    rpb = 1 << max(0, int(math.floor(math.log2(raw)))) if raw >= 1 else 1
    return max(4, min(128, rpb))


# --------------------------------------------------------------------------- load order

LAST_TABLES = ("AuditLog", "BenchmarkTableInfo")


def parents_of(table: Table) -> set[str]:
    return {f.fk.table for f in table.fk_fields if f.fk.table != table.name}


def load_order(schema: Schema) -> list[list[str]]:
    """Topological levels over the FK graph (research.md R12)."""
    names = {t.name for t in schema.tables}
    parents = {t.name: parents_of(t) & names for t in schema.tables}
    for t in schema.tables:
        for f in t.fk_fields:
            if f.fk.table == t.name:
                raise SchemaError("S04", f"{t.name}.{f.name}", "self-referencing FKs are not allowed")

    level: dict[str, int] = {}
    visiting: list[str] = []

    def visit(n: str) -> int:
        if n in level:
            return level[n]
        if n in visiting:
            cycle = visiting[visiting.index(n):] + [n]
            raise SchemaError("S04", n, "FK cycle: " + " -> ".join(cycle))
        visiting.append(n)
        lv = 1 + max((visit(p) for p in parents[n]), default=-1)
        visiting.pop()
        level[n] = lv
        return lv

    for t in schema.tables:
        visit(t.name)

    regular = [n for n in names if n not in LAST_TABLES]
    depth = 1 + max((level[n] for n in regular), default=-1)
    levels: list[list[str]] = [sorted(n for n in regular if level[n] == d) for d in range(depth)]
    for n in LAST_TABLES:
        if n in names:
            levels.append([n])
    return [lv for lv in levels if lv]
