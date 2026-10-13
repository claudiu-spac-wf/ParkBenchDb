"""Safe manifest parsing and path guards for future isolated write runs.

The CLI deliberately does not call this module yet: creating and deleting a
working OpenEdge database needs a real integration gate before activation.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from tools.schema_model import load_expanded

from .model import BaselineManifest

SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "parkbench-schema.yaml"


def benchmark_names() -> frozenset[str]:
    return frozenset(table.name for table in load_expanded(SCHEMA).tables)


def parse_dump_manifest(path: str | Path) -> tuple[dict[str, int], dict[str, int]]:
    """Parse the existing binary dump manifest and require every benchmark table."""
    rows: dict[str, int] = {}
    sequences: dict[str, int] = {}
    format_seen = False
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line == "format=parkbench-dump-1":
            format_seen = True
        elif line.startswith("rows="):
            table, value = line[5:].split("=", 1)
            if table in rows:
                raise ValueError(f"duplicate dump row count for {table}")
            rows[table] = int(value)
            if rows[table] < 0:
                raise ValueError(f"negative dump row count for {table}")
        elif line.startswith("seq="):
            name, value = line[4:].split("=", 1)
            if name in sequences:
                raise ValueError(f"duplicate dump sequence {name}")
            sequences[name] = int(value)
    required = benchmark_names()
    if not format_seen or not required <= rows.keys():
        raise ValueError(f"incomplete ParkBench dump manifest: {sorted(required - rows.keys())}")
    if not all(f"Seq{name}Id" in sequences for name in required):
        raise ValueError("dump manifest is missing benchmark sequence values")
    return {name: rows[name] for name in sorted(required)}, sequences


def baseline_from_dump(run_id: str, source_database: str, dump_directory: str,
                       working_directory: str, source_benchmark_counts: dict,
                       created_at: str) -> BaselineManifest:
    dump = Path(dump_directory).resolve()
    rows, sequences = parse_dump_manifest(dump / "manifest.txt")
    digest = hashlib.sha256((dump / "schema.df").read_bytes()).hexdigest()
    manifest = BaselineManifest(run_id, source_database, digest, rows,
                                source_benchmark_counts, sequences, str(dump),
                                str(Path(working_directory).resolve()), created_at)
    manifest.validate_paths()
    return manifest
