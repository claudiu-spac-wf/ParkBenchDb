"""Size model: scale factor <-> approximate on-disk bytes (research.md R9).

The model counts blocks, not bytes: small records are limited by the area's records-per-block, every
table, index and LOB column owns whole clusters, and index blocks are only partly full after a load.
"""

from __future__ import annotations

import math

from tools import schema_model as m

MIN_SCALE = 0.005        # below this, fixed per-object overhead dominates; employees are floored at 250
MAX_SCALE = 100.0

# Fitted on a real SF 0.01 database with proutil -C dbanalys (research.md R9, "Measured model"):
BLOCK_USABLE_BYTES = 7900    # of an 8 KB block, after the block header and create limit
RECORD_SLOT_BYTES = 20       # per-record directory entry and header
INDEX_ENTRY_BYTES = {"pk": 12, "random": 16, "other": 18}   # on disk, at the fill of an unordered load
LOB_FILL = 0.65              # LOB bytes / LOB block bytes
DATA_OBJECT_CLUSTERS = 1.0   # clusters pre-allocated per table beyond its data
INDEX_OBJECT_CLUSTERS = 0.6  # average partly used last cluster per index
FIXED_BYTES = 80 * 2 ** 20   # before-image, schema and control areas after a load


class SizeError(Exception):
    """A requested size or scale outside the supported range (exit code 2)."""


def _cluster_bytes(schema: m.Schema, area_name: str) -> int:
    a = schema.get_area(area_name)
    return (a.blocksPerCluster if a and a.blocksPerCluster else 8) * schema.blockSizeBytes


def _records_per_block(schema: m.Schema, table: m.Table) -> int:
    a = schema.get_area(table.area)
    rpb = a.recordsPerBlock if a and a.recordsPerBlock else 64
    fit = BLOCK_USABLE_BYTES // (m.estimate_record_bytes(table) + RECORD_SLOT_BYTES)
    return max(1, min(rpb, fit))


def _index_kind(index: m.Index) -> str:
    if index.name.startswith("Pk"):
        return "pk"
    return "random" if "RandomInt" in index.name else "other"


def table_bytes(schema: m.Schema, table: m.Table, sf: float) -> tuple[float, float]:
    """(data + LOB bytes, index bytes) of one table on disk at scale factor sf."""
    rows = m.rows_at(table, sf)
    data = math.ceil(rows / _records_per_block(schema, table)) * schema.blockSizeBytes
    data += DATA_OBJECT_CLUSTERS * _cluster_bytes(schema, table.area)
    for f in table.lob_fields:
        if f.lob is not None:
            data += rows * (f.lob.fractionPopulated or 0) * (f.lob.avgBytes or 0) / LOB_FILL
            data += DATA_OBJECT_CLUSTERS * _cluster_bytes(schema, f.lob.area)
    index = 0.0
    for i in table.indexes:
        index += rows * INDEX_ENTRY_BYTES[_index_kind(i)]
        index += INDEX_OBJECT_CLUSTERS * _cluster_bytes(schema, table.indexArea)
    return data, index


def estimate_data_bytes(schema: m.Schema, sf: float) -> float:
    return FIXED_BYTES + sum(table_bytes(schema, t, sf)[0] for t in schema.tables)


def estimate_index_bytes(schema: m.Schema, sf: float) -> float:
    return sum(table_bytes(schema, t, sf)[1] for t in schema.tables)


def estimate_disk_bytes(schema: m.Schema, sf: float) -> float:
    return estimate_data_bytes(schema, sf) + estimate_index_bytes(schema, sf)


def min_disk_bytes(schema: m.Schema) -> float:
    return estimate_disk_bytes(schema, MIN_SCALE)


def solve_scale(target_bytes: float, schema: m.Schema, calibration: float = 1.0) -> float:
    """Scale factor whose estimated on-disk size (x calibration) equals target_bytes."""
    def est(sf):
        return estimate_disk_bytes(schema, sf) * calibration
    if target_bytes < est(MIN_SCALE):
        raise SizeError(f"{target_bytes / 1e9:.2f} GB is below the smallest supported database "
                        f"(about {est(MIN_SCALE) / 1e9:.2f} GB on disk, scale factor {MIN_SCALE})")
    if target_bytes > est(MAX_SCALE):
        raise SizeError(f"{target_bytes / 1e9:.0f} GB is above the largest supported size (scale factor {MAX_SCALE})")
    lo, hi = MIN_SCALE, MAX_SCALE
    while hi - lo > 1e-7:
        mid = (lo + hi) / 2
        if est(mid) < target_bytes:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 6)


def describe(schema: m.Schema, sf: float) -> str:
    d, i = estimate_data_bytes(schema, sf), estimate_index_bytes(schema, sf)
    return f"data {d / 1e9:.2f} GB + indexes {i / 1e9:.2f} GB = {(d + i) / 1e9:.2f} GB"
