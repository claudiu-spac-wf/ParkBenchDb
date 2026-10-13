"""Operator CLI for ParkBench workloads."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from uuid import uuid4

from . import check_runtime
from .agent import AgentClient, AgentError
from .catalog import CatalogError, find_profile, load_catalog, profile_dict
from .config import ConfigError, NOT_SERVED_HINT, connection, limits, spool_root, validate_output_path, validate_seed
from .result import human_summary, write_result
from .runner import Runner

# Write/mixed profiles stay unavailable until isolated-copy execution is safe.
ACTIVE_PROFILE_IDS = frozenset({
    "read-reference-point", "read-small-table-scan", "read-medium-narrow-selective",
    "read-medium-wide-selective", "read-large-range", "read-very-large-selective",
    "read-relationship-navigation", "read-lob-fetch",
})


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pbwork")
    commands = parser.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser("catalog")
    catalog.add_argument("--json", action="store_true")
    for command in ("validate", "run"):
        sub = commands.add_parser(command)
        sub.add_argument("--db", required=True)
        sub.add_argument("--profile", required=True)
        sub.add_argument("--host")
        sub.add_argument("--port", type=int)
        sub.add_argument("--seed", type=int, default=20260929)
        sub.add_argument("--workers", type=int, default=1 if command == "validate" else 4)
        sub.add_argument("--operations", type=int)
        sub.add_argument("--duration", type=float)
        sub.add_argument("--mode", choices=("direct-read", "isolated", "in-place-retain"))
        sub.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
        if command == "run":
            sub.add_argument("--retain-changes", action="store_true")
            sub.add_argument("--spool")
            sub.add_argument("--result")
            sub.add_argument("--json", action="store_true")
    cleanup = commands.add_parser("cleanup")
    cleanup.add_argument("--run", required=True)
    cleanup.add_argument("--spool")
    cleanup.add_argument("--force", action="store_true")
    compare = commands.add_parser("compare")
    compare.add_argument("result_a")
    compare.add_argument("result_b")
    compare.add_argument("--json", action="store_true")
    return parser


def _parameters(profile, values: list[str]) -> dict:
    result = {}
    for pair in values:
        if "=" not in pair:
            raise ConfigError("--param requires KEY=VALUE")
        key, raw = pair.split("=", 1)
        if key not in profile.parameters:
            raise ConfigError(f"unknown parameter {key} for {profile.id}")
        schema = profile.parameters[key]
        try:
            value = int(raw) if schema["type"] == "integer" else float(raw) if schema["type"] == "number" else raw
        except ValueError as exc:
            raise ConfigError(f"invalid {key}: {raw}") from exc
        if isinstance(value, float) and not math.isfinite(value):
            raise ConfigError(f"invalid {key}: {raw}")
        if ("min" in schema and value < schema["min"]) or ("max" in schema and value > schema["max"]) or ("enum" in schema and value not in schema["enum"]):
            raise ConfigError(f"invalid {key}: {raw}")
        result[key] = value
    return result


def _compare(a: Path, b: Path) -> dict:
    first = json.loads(a.read_text(encoding="utf-8"))
    second = json.loads(b.read_text(encoding="utf-8"))
    if first["run"]["profile_version"] != second["run"]["profile_version"]:
        raise ConfigError("profile versions differ; cannot compare")
    return {"profiles": [first["run"]["profile_id"], second["run"]["profile_id"]],
            "workers": [first["run"]["workers"], second["run"]["workers"]],
            "coverage": [first.get("coverage"), second.get("coverage")],
            "metrics": {key: [first["metrics"].get(key), second["metrics"].get(key)] for key in
                        ("completed", "failed", "throughput_ops_per_second", "rows_read", "rows_written")},
            "latency_ms": [first["metrics"]["latency_ms"], second["metrics"]["latency_ms"]]}


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "compare":
            report = _compare(Path(args.result_a), Path(args.result_b))
            print(json.dumps(report, indent=2) if args.json else str(report))
            return 0
        if args.command == "cleanup":
            raise ConfigError("cleanup is unavailable until isolated working-copy support is installed")
        profiles = load_catalog()
        if args.command == "catalog":
            data = {"catalogVersion": 1, "profiles": [profile_dict(p) for p in profiles]}
            print(json.dumps(data, indent=2) if args.json else "\n".join(f"{p.id}: {p.purpose}" for p in profiles))
            return 0
        profile = find_profile(profiles, args.profile)
        limits(args.operations, args.duration, args.workers) if args.command == "run" or args.operations is not None or args.duration is not None else None
        if args.workers < 1:
            raise ConfigError("--workers must be positive")
        validate_seed(args.seed)
        parameters = _parameters(profile, args.param)
        mode = args.mode or ("direct-read" if profile.kind == "read" else "isolated")
        retain = getattr(args, "retain_changes", False)
        if profile.kind == "read" and (retain or mode != "direct-read"):
            raise ConfigError("read profiles require direct-read mode and cannot retain changes")
        if mode == "in-place-retain" and not retain:
            raise ConfigError("in-place-retain requires --retain-changes")
        if profile.kind != "read" and mode == "direct-read":
            raise ConfigError("write profile cannot use direct-read")
        if profile.id not in ACTIVE_PROFILE_IDS:
            raise ConfigError(f"profile {profile.id} is in the catalog but its workload handler is unavailable")
        conn = connection(args.db, args.host, args.port)
        check_runtime()
        if args.command == "validate":
            with AgentClient(conn, spool_root(conn) / f"validation-{uuid4()}") as agent:
                agent.hello()
                agent.validate(profile.id, profile.prerequisites)
            print(f"{profile.id}: ready")
            return 0
        validate_output_path(args.spool, "--spool")
        validate_output_path(args.result, "--result")
        root = spool_root(conn, args.spool)
        runner = Runner(conn, profile, spool=root)
        result = runner.execute(operations=args.operations, duration=args.duration, seed=args.seed,
                                workers=args.workers, mode=mode, retain_changes=retain,
                                parameters=parameters)
        target = Path(args.result) if args.result else root / result["run"]["run_id"] / "result.json"
        write_result(target, result)
        print(json.dumps(result, indent=2) if args.json else human_summary(result, str(target)))
        return 130 if result["run"]["status"] == "INTERRUPTED" else 0 if result["run"]["status"] == "SUCCEEDED" else 1
    except (ConfigError, CatalogError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except AgentError as exc:
        message = str(exc)
        if "exited" in message and any(token in message.lower() for token in
                                        ("1423", "single-user", "no server", "shared memory", "(9432)", "(1384)")):
            print(f"{NOT_SERVED_HINT}\n{message}", file=sys.stderr)
            return 2
        print(message, file=sys.stderr)
        return 1
    except (OSError, RuntimeError, json.JSONDecodeError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
