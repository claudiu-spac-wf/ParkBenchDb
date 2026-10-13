"""Deterministic concurrent workload orchestration."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from .agent import AgentClient
from .metrics import RunMetrics
from .model import WorkloadRun
from .operations import read_descriptor, write_descriptor
from .result import make_result, write_result
from .seeds import select_operation


class Runner:
    def __init__(self, conn, profile, *, agent_factory=AgentClient, spool: Path | None = None):
        self.conn = conn
        self.profile = profile
        self.agent_factory = agent_factory
        self.spool = Path(spool or Path.cwd() / "pbwork-spool")

    def execute(self, *, operations: int | None, duration: float | None, seed: int,
                workers: int, mode: str, retain_changes: bool = False, result_path: Path | None = None,
                parameters: dict | None = None):
        if self.profile.kind != "read":
            raise RuntimeError("write and mixed profiles are disabled until isolated-copy execution is verified")
        run = WorkloadRun(str(uuid4()), self.profile.id, self.profile.version, self.profile.kind,
                          self.conn.db, seed, workers, operations, duration, mode, retain_changes)
        metrics = RunMetrics()
        errors: list[dict] = []
        run.transition("VALIDATING")
        run.transition("READY")
        self.spool.mkdir(parents=True, exist_ok=True)
        ordinal = 0
        lock = threading.Lock()
        started = time.monotonic()
        deadline = started + duration if duration is not None else None
        run.transition("RUNNING")

        def worker(worker_no: int):
            nonlocal ordinal
            with self.agent_factory(self.conn, self.spool / run.run_id / f"worker-{worker_no}") as agent:
                agent.hello()
                validation = agent.validate(self.profile.id, self.profile.prerequisites)
                counts = validation.get("counts", {})
                while True:
                    with lock:
                        if (operations is not None and ordinal >= operations) or (deadline is not None and time.monotonic() >= deadline):
                            return
                        ordinal += 1
                        current = ordinal
                    operation = select_operation(seed, self.profile.version, current, self.profile.operations)
                    if self.profile.kind == "read" or operation.handler in {"point_lookup", "indexed_selective", "range_scan", "table_scan", "relationship_navigation", "lob_fetch"}:
                        descriptor = read_descriptor(seed, self.profile.version, current, operation, counts, parameters)
                    else:
                        descriptor = write_descriptor(seed, self.profile.version, current, operation, counts, parameters)
                    reply = agent.batch([descriptor])
                    item = reply["operations"][0]
                    if self.profile.kind == "read" and (item.get("status") not in {"read", "failed"}
                                                        or int(item.get("rows_written", 0)) != 0):
                        raise ValueError("read-only agent response reported a write outcome")
                    with lock:
                        metrics.record(operation.id, current, item)
                        if item.get("error_class"):
                            errors.append({"operation_id": operation.id, "table": operation.table,
                                           "error_class": item["error_class"], "message": item.get("message", ""),
                                           "rolled_back": item.get("status") == "rolled_back"})

        try:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(worker, worker_no) for worker_no in range(workers)]
                for future in futures:
                    future.result()
            run.transition("STOPPING")
            run.transition("SUCCEEDED" if metrics.counts["failed"] == 0 else "FAILED")
        except KeyboardInterrupt:
            run.transition("INTERRUPTED")
            errors.append({"operation_id": "runner", "table": None, "error_class": "Interrupted",
                           "message": "run interrupted by operator", "rolled_back": False})
        except Exception as exc:
            errors.append({"operation_id": "runner", "table": None, "error_class": type(exc).__name__,
                           "message": str(exc), "rolled_back": False})
            run.transition("FAILED")
        result = make_result(run, self.profile, metrics, time.monotonic() - started, errors=errors)
        if result_path:
            write_result(result_path, result)
        return result
