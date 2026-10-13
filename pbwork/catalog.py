"""Strict, schema-aware workload catalog loading."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import yaml

from tools.schema_model import load_expanded

from .model import HANDLERS, READ_HANDLERS, WorkloadProfile, OperationSpec

CATALOG_FILE = Path(__file__).resolve().parent / "profiles" / "catalog.yaml"
SCHEMA_FILE = Path(__file__).resolve().parent.parent / "schema" / "parkbench-schema.yaml"
CANONICAL_IDS = (
    "read-reference-point", "read-small-table-scan", "read-medium-narrow-selective",
    "read-medium-wide-selective", "read-large-range", "read-very-large-selective",
    "read-relationship-navigation", "read-lob-fetch", "write-narrow-append",
    "write-wide-update", "write-lob-update", "write-transaction-batch",
    "write-hot-key-contention", "write-cold-distributed", "mixed-balanced",
)
_PROFILE_KEYS = {"id", "version", "name", "kind", "purpose", "tables", "coverage", "prerequisites", "parameters", "requiresWritableDatabase", "cleanup", "operations"}
_OP_KEYS = {"id", "handler", "table", "tables", "access", "weight", "selection", "transaction", "payload", "expected"}
_EXECUTABLE_KEYS = {"sql", "abl", "shell", "command", "expression", "script", "python", "eval", "query", "where", "source_code", "procedure"}


class CatalogError(ValueError):
    pass


def _mapping(value, where):
    if not isinstance(value, dict):
        raise CatalogError(f"{where} must be an object")
    return value


def _reject_executable(value, where):
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in _EXECUTABLE_KEYS:
                raise CatalogError(f"free-form executable field is forbidden in {where}: {key}")
            _reject_executable(item, where)
    elif isinstance(value, list):
        for item in value:
            _reject_executable(item, where)


def load_catalog(path: str | Path = CATALOG_FILE) -> tuple[WorkloadProfile, ...]:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        _mapping(raw, "catalog")
        if raw.get("catalogVersion") != 1 or not isinstance(raw.get("profiles"), list):
            raise CatalogError("catalogVersion must be 1 and profiles must be a list")
        schema = load_expanded(SCHEMA_FILE)
        names = {table.name for table in schema.tables}
        profiles = []
        for item in raw["profiles"]:
            item = _mapping(item, "profile")
            if item.get("version") != 1:
                raise CatalogError(f"unsupported profile version for {item.get('id')}: {item.get('version')}")
            unknown = set(item) - _PROFILE_KEYS
            if unknown:
                raise CatalogError(f"unknown profile keys: {sorted(unknown)}")
            operations = []
            for op in item["operations"]:
                op = _mapping(op, "operation")
                _reject_executable(op, "operation")
                if set(op) - _OP_KEYS:
                    raise CatalogError(f"unknown operation keys: {sorted(set(op) - _OP_KEYS)}")
                if op.get("handler") not in HANDLERS:
                    raise CatalogError(f"unknown handler: {op.get('handler')}")
                if op.get("table") and op["table"] not in names:
                    raise CatalogError(f"unknown table: {op['table']}")
                if set(op.get("tables", [])) - names:
                    raise CatalogError(f"unknown operation table: {sorted(set(op['tables']) - names)}")
                if op["handler"] in READ_HANDLERS:
                    expected = op.get("expected", {})
                    if (type(expected.get("minimumRows")) is not int or expected["minimumRows"] < 0
                            or type(expected.get("maximumRows")) is not int
                            or expected["maximumRows"] < max(1, expected["minimumRows"])):
                        raise CatalogError(f"invalid expected cardinality for {op['id']}")
                operations.append(OperationSpec(id=op["id"], handler=op["handler"], weight=float(op["weight"]),
                                                table=op.get("table"), tables=tuple(op.get("tables", [])),
                                                access=op.get("access", "point"), selection=op.get("selection", {}),
                                                transaction=op.get("transaction", {}), payload=op.get("payload", {}),
                                                expected=op.get("expected", {})))
            tables = tuple(item["tables"])
            if set(tables) - names:
                raise CatalogError(f"unknown profile table: {sorted(set(tables) - names)}")
            requirements = item["prerequisites"]
            for required in requirements.get("tables", []):
                if required["name"] not in names or not isinstance(required["minimumRows"], int) or required["minimumRows"] < 0:
                    raise CatalogError(f"invalid table minimumRows for {required.get('name')}")
            if not set(tables) <= {entry["name"] for entry in requirements.get("tables", [])}:
                raise CatalogError(f"missing minimumRows prerequisite for {item['id']}")
            profiles.append(WorkloadProfile(id=item["id"], version=item["version"], name=item["name"],
                                            kind=item["kind"], purpose=item["purpose"], tables=tables,
                                            coverage=item["coverage"], prerequisites=requirements,
                                            parameters=item["parameters"], operations=tuple(operations),
                                            requires_writable_database=item["requiresWritableDatabase"], cleanup=item["cleanup"]))
        ids = [p.id for p in profiles]
        if len(set(ids)) != len(ids) or not set(CANONICAL_IDS) <= set(ids):
            raise CatalogError("catalog must contain all 15 canonical IDs exactly once")
        return tuple(profiles)
    except (KeyError, TypeError, yaml.YAMLError) as exc:
        raise CatalogError(f"invalid profile catalog: {exc}") from exc


def profile_dict(profile: WorkloadProfile) -> dict:
    return asdict(profile)


def find_profile(profiles: tuple[WorkloadProfile, ...], profile_id: str) -> WorkloadProfile:
    for profile in profiles:
        if profile.id == profile_id:
            return profile
    raise CatalogError(f"unknown profile {profile_id}; choose one of: {', '.join(CANONICAL_IDS)}")
