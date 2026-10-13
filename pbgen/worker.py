"""One worker: claim a unit -> generate it -> load it (one transaction) -> advance the watermark.

A worker never holds a database transaction while Python generates data: claiming is a short
transaction, and loading plus marking the unit done is one transaction inside the agent.
Stopping (event or signal) abandons the unit being generated; it is simply claimed again later.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from pbgen import config
from pbgen.agent import AgentError
from pbgen.generate import generate_unit
from pbgen.generate.common import RunContext
from pbgen.unitjson import write_unit
from tools import schema_model as m

HEARTBEAT_SECONDS = 60
PHASE_WAIT_SECONDS = 2.0


@dataclass
class WorkerStats:
    units: int = 0
    rows: int = 0
    lost: int = 0
    gen_seconds: float = 0.0
    load_seconds: float = 0.0
    finalized: bool = False
    reason: str = ""
    errors: list[str] = field(default_factory=list)


def context_for_run(schema: m.Schema, run: dict) -> RunContext:
    summary = json.loads(run["PlanSummary"]) if isinstance(run.get("PlanSummary"), str) else run.get("PlanSummary") or {}
    as_of = run["AsOfDate"]
    as_of = dt.date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    return RunContext(schema=schema, run_id=int(run["LoaderRunId"]), run_seed=int(run["RunSeed"]),
                      base_seed=int(summary.get("baseSeed", run["RunSeed"])), as_of=as_of,
                      scale=float(run["TargetScale"]), employee_max=int(summary.get("employeeMax", 0)),
                      merchant_max=int(summary.get("merchantMax", 0)))


class StopFlag:
    """Stop request that is safe to set from a signal handler (a plain attribute, no locks).

    It also polls an optional shared multiprocessing Event set by the launcher."""

    def __init__(self, shared=None):
        self.requested = False
        self.shared = shared

    def set(self) -> None:
        self.requested = True

    def is_set(self) -> bool:
        return self.requested or (self.shared is not None and self.shared.is_set())

    def wait(self, seconds: float) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.is_set():
                return True
            time.sleep(0.1)
        return self.is_set()


class Worker:
    def __init__(self, agent, worker_no: int, spool: str | os.PathLike, schema: m.Schema,
                 stop: threading.Event | None = None, db_bytes=lambda: 0, log=print):
        self.agent = agent
        self.worker_no = worker_no
        self.wid = config.worker_id(worker_no)
        self.spool = Path(spool)
        self.spool.mkdir(parents=True, exist_ok=True)
        self.schema = schema
        self.stop = stop or threading.Event()
        self.db_bytes = db_bytes
        self.log = log
        self.stats = WorkerStats()
        self._contexts: dict[int, RunContext] = {}

    # ------------------------------------------------------------------ helpers
    def _context(self, run_id: int) -> RunContext:
        if run_id not in self._contexts:
            state = self.agent.request("state")
            run = next(r for r in state["runs"] if int(r["LoaderRunId"]) == run_id)
            self._contexts[run_id] = context_for_run(self.schema, run)
        return self._contexts[run_id]

    def _heartbeat(self, run_id: int, unit_no: int, done: threading.Event) -> None:
        while not done.wait(HEARTBEAT_SECONDS):
            try:
                self.agent.request("heartbeat", run=run_id, unitNo=unit_no, worker=self.wid)
            except AgentError:
                return

    # ------------------------------------------------------------------ main loop
    def run(self) -> WorkerStats:
        while not self.stop.is_set():
            reply = self.agent.request("claim", worker=self.wid)
            unit = reply.get("unit")
            if unit is None:
                reason = reply.get("reason", "")
                if reason == "phase-blocked":
                    self.stop.wait(PHASE_WAIT_SECONDS)
                    continue
                self.stats.reason = reason
                break
            self._process(unit)
        return self.stats

    def _process(self, unit: dict) -> None:
        run_id, unit_no = int(unit["LoaderRunId"]), int(unit["UnitNo"])
        done = threading.Event()
        hb = threading.Thread(target=self._heartbeat, args=(run_id, unit_no, done), daemon=True)
        hb.start()
        path = self.spool / f"unit-{run_id}-{unit_no}.json"
        try:
            t0 = time.perf_counter()
            tables = generate_unit(unit, self._context(run_id))
            write_unit(path, tables)
            t1 = time.perf_counter()
            if self.stop.is_set():
                return  # abandon: the unit stays claimed and is reclaimed later
            try:
                reply = self.agent.request("load", run=run_id, unitNo=unit_no, worker=self.wid, file=str(path))
            except AgentError as e:
                if e.lost:
                    self.stats.lost += 1
                    return
                raise
            t2 = time.perf_counter()
            self.stats.units += 1
            self.stats.rows += int(reply.get("rows", 0))
            self.stats.gen_seconds += t1 - t0
            self.stats.load_seconds += t2 - t1
        finally:
            done.set()
            try:
                path.unlink()
            except OSError:
                pass
        wm = self.agent.request("watermark", run=run_id)
        if wm.get("complete"):
            try:
                self.agent.request("finalize", run=run_id, diskBytes=int(self.db_bytes()))
                self.stats.finalized = True
            except AgentError as e:
                if "not complete" not in str(e):
                    raise
