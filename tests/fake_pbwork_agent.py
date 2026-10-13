"""Protocol-compatible fake agent for offline workload tests."""

from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path


def process(request: dict) -> dict:
    op = request.get("op")
    if op == "hello":
        return {"ok": True, "agent_version": "fake-1", "openedge_version": "fake", "tables": 32}
    if op == "validate":
        return {"ok": True, "available": True,
                "counts": {row["name"]: max(1, row["minimumRows"])
                           for row in request.get("prerequisites", {}).get("tables", [])}}
    if op == "sample":
        rng = random.Random(20260929)
        return {"ok": True, "rows": [{"table": name, "id": rng.randint(1, 1000)} for name in request.get("tables", [])], "sequences": {}, "bti": []}
    if op == "batch":
        rows = []
        for descriptor in request.get("operations", []):
            failure = descriptor.get("inject_failure")
            is_write = descriptor.get("handler", "").startswith(("append", "update", "write", "transaction"))
            transaction_rows = 3 if descriptor.get("handler") == "transaction_batch" else 1
            rows.append({"ordinal": descriptor["ordinal"], "operation_id": descriptor["operation_id"],
                         "status": "rolled_back" if failure else "committed" if is_write else "read",
                         "rows_read": 0 if is_write else 0 if descriptor.get("empty_result") else 1,
                         "rows_written": 0 if failure or not is_write else transaction_rows,
                         "requested_cardinality": descriptor.get("limit", 1),
                         "traversal_depth": descriptor.get("depth"), "lob_mode": descriptor.get("lob_mode"),
                         "elapsed_ms": 0.1, "error_class": failure,
                         "retried": int(descriptor.get("retries", 0)),
                         "contention_events": int(failure in {"deadlock", "lock-timeout"}),
                         "deadlocks": int(failure == "deadlock"),
                         "timeouts": int(failure == "lock-timeout")})
        return {"ok": True, "agent_version": "fake-1", "operations": rows, "transaction_errors": [], "warnings": []}
    if op == "quit":
        return {"ok": True}
    return {"ok": False, "error": "unknown operation"}


def main(spool: Path) -> int:
    sequence = 1
    idle = time.monotonic() + 30
    while time.monotonic() < idle:
        req = spool / f"req-{sequence}.json"
        if not req.exists():
            time.sleep(0.005)
            continue
        # Windows virus scanners can briefly hold a just-renamed request file.
        # Match the real spool consumer's polling behavior instead of exiting.
        try:
            data = json.loads(req.read_text(encoding="utf-8"))
        except PermissionError:
            time.sleep(0.005)
            continue
        response = process(data)
        tmp = spool / f"resp-{sequence}.json.tmp"
        tmp.write_text(json.dumps(response), encoding="utf-8")
        os.replace(tmp, spool / f"resp-{sequence}.json")
        try:
            req.unlink()
        except PermissionError:
            pass
        sequence += 1
        idle = time.monotonic() + 30
        if data.get("op") == "quit":
            return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
