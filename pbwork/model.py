"""Validated workload definitions and run state."""

from __future__ import annotations

import re
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
MODES = frozenset({"direct-read", "isolated", "in-place-retain"})
READ_HANDLERS = frozenset({"point_lookup", "indexed_selective", "range_scan", "table_scan", "relationship_navigation", "lob_fetch"})
WRITE_HANDLERS = frozenset({"append_narrow", "update_wide", "write_lob", "transaction_batch"})
HANDLERS = READ_HANDLERS | WRITE_HANDLERS


@dataclass(frozen=True)
class OperationSpec:
    id: str
    handler: str
    weight: float
    table: str | None = None
    tables: tuple[str, ...] = ()
    access: str = "point"
    selection: dict[str, Any] = field(default_factory=dict)
    transaction: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not ID_PATTERN.fullmatch(self.id) or self.handler not in HANDLERS or not 0 < self.weight < float("inf"):
            raise ValueError(f"invalid operation id, handler, or weight: {self.id}")
        if not self.table and not self.tables:
            raise ValueError(f"operation {self.id} has no table")


@dataclass(frozen=True)
class WorkloadProfile:
    id: str
    version: int
    name: str
    kind: str
    purpose: str
    tables: tuple[str, ...]
    coverage: dict[str, list[str]]
    prerequisites: dict[str, Any]
    parameters: dict[str, Any]
    operations: tuple[OperationSpec, ...]
    requires_writable_database: bool
    cleanup: str

    def __post_init__(self):
        if not ID_PATTERN.fullmatch(self.id) or self.version < 1 or self.kind not in {"read", "write", "mixed"}:
            raise ValueError(f"invalid profile identity: {self.id}")
        if not self.operations or len({x.id for x in self.operations}) != len(self.operations):
            raise ValueError(f"profile {self.id} needs unique operations")
        has_read = any(x.handler in READ_HANDLERS for x in self.operations)
        has_write = any(x.handler in WRITE_HANDLERS for x in self.operations)
        if (self.kind == "read" and has_write) or (self.kind == "write" and not has_write) or (self.kind == "mixed" and not (has_read and has_write)):
            raise ValueError(f"profile {self.id} has inconsistent operation kind")
        if self.requires_writable_database != (self.kind != "read"):
            raise ValueError(f"profile {self.id} has inconsistent writable setting")
        if self.cleanup != ("none" if self.kind == "read" else "isolated-copy"):
            raise ValueError(f"profile {self.id} has inconsistent cleanup setting")


@dataclass
class WorkloadRun:
    run_id: str
    profile_id: str
    profile_version: int
    kind: str
    database_target: str
    seed: int
    workers: int
    operation_limit: int | None
    duration_seconds: float | None
    mode: str
    retain_changes: bool = False
    working_database: str | None = None
    status: str = "CREATED"
    cleanup_status: str = "not-required"
    started_at: str | None = None
    ended_at: str | None = None

    def __post_init__(self):
        if self.mode not in MODES or self.workers < 1:
            raise ValueError("invalid workload mode or worker count")
        if (self.operation_limit is None) == (self.duration_seconds is None):
            raise ValueError("exactly one operation limit or duration is required")
        if self.operation_limit is not None and self.operation_limit < 1:
            raise ValueError("operation limit must be positive")
        if self.duration_seconds is not None and (not math.isfinite(self.duration_seconds) or self.duration_seconds <= 0):
            raise ValueError("duration must be positive")
        if self.mode == "in-place-retain" and not self.retain_changes:
            raise ValueError("in-place-retain requires retained changes")
        if self.kind != "read" and self.mode == "direct-read":
            raise ValueError("write profiles cannot use direct-read mode")

    def transition(self, state: str):
        allowed = {
            "CREATED": {"VALIDATING"}, "VALIDATING": {"READY", "FAILED"},
            "READY": {"RUNNING", "FAILED"}, "RUNNING": {"STOPPING", "FAILED", "INTERRUPTED"},
            "STOPPING": {"SUCCEEDED", "FAILED", "INTERRUPTED"},
            "SUCCEEDED": {"CLEANING", "RETAINED"},
            "FAILED": {"CLEANING", "CLEANUP_FAILED"},
            "INTERRUPTED": {"CLEANING", "CLEANUP_FAILED"},
            "CLEANING": {"CLEANED", "CLEANUP_FAILED"},
            "CLEANUP_FAILED": {"CLEANING", "RETAINED"},
        }
        if state not in allowed.get(self.status, set()):
            raise ValueError(f"invalid run transition {self.status} -> {state}")
        self.status = state
        if state == "RUNNING":
            self.started_at = datetime.now(timezone.utc).isoformat()
        if state in {"SUCCEEDED", "FAILED", "INTERRUPTED"}:
            self.ended_at = datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class OperationExecution:
    ordinal: int
    operation_id: str
    handler: str
    transaction_id: str
    selected_keys: dict[str, Any]
    elapsed_ms: float
    status: str
    rows_read: int = 0
    rows_written: int = 0
    error_class: str | None = None
    error_message: str | None = None


@dataclass
class BaselineManifest:
    run_id: str
    source_database: str
    source_schema_digest: str
    source_row_counts: dict[str, int]
    source_benchmark_counts: dict[str, Any]
    source_sequences: dict[str, int]
    dump_directory: str
    working_directory: str
    created_at: str
    cleaned_at: str | None = None
    cleanup_action: str | None = None

    def validate_paths(self):
        source = Path(self.source_database).resolve()
        work = Path(self.working_directory).resolve()
        dump = Path(self.dump_directory).resolve()
        if work == source or source in work.parents or work in source.parents:
            raise ValueError("working directory overlaps source database")
        if dump == source or source in dump.parents or dump in source.parents or dump == work or dump in work.parents or work in dump.parents:
            raise ValueError("dump directory overlaps source or working database")
