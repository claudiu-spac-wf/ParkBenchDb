"""Machine-readable results and concise operator summaries."""

from __future__ import annotations

import json
import os
import platform
import re
from dataclasses import asdict
from pathlib import Path

from . import __version__

_SECRET = re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key)(\s*[:=]\s*)([^\s,;]+)")


def redact(message: str) -> str:
    return _SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", str(message))


def make_result(run, profile, metrics, elapsed_seconds: float, *, errors=None, openedge_version=None):
    row = asdict(run)
    row.pop("retain_changes", None)
    return {"schema_version": 1, "run": row,
            "coverage": {"tables": list(profile.tables), **profile.coverage},
            "metrics": metrics.as_dict(elapsed_seconds), "by_operation": metrics.by_operation(elapsed_seconds),
            "environment": {"workload_version": __version__, "python_version": platform.python_version(),
                            "openedge_version": openedge_version, "pasoe_image": os.environ.get("PARKBENCH_PASOE_IMAGE")},
            "errors": [{**error, "message": (redact(error.get("message", "")) if profile.kind == "read"
                                              else "[REDACTED: write payload may be sensitive]")}
                       for error in (errors or [])]}


def write_result(path: str | Path, result: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return target


def human_summary(result: dict, result_path: str | None = None) -> str:
    run, metrics = result["run"], result["metrics"]
    latency = metrics["latency_ms"]
    return (f"{run['profile_id']} {run['status']} run={run['run_id']} seed={run['seed']} workers={run['workers']}\n"
            f"attempted={metrics['attempted']} completed={metrics['completed']} failed={metrics['failed']} "
            f"rows_read={metrics['rows_read']} rows_written={metrics['rows_written']}\n"
            f"throughput={metrics['throughput_ops_per_second']:.2f} ops/s "
            f"latency_ms median={latency['median']} p95={latency['p95']} p99={latency['p99']} "
            f"cleanup={run['cleanup_status']} result={result_path or '-'}")
