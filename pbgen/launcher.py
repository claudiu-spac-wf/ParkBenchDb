"""`pbgen run --workers N`: starts N worker processes against the open run and supervises them.

Running it again while workers are active adds workers to the same run (unique worker
numbers come from lock files in the spool directory). Ctrl+C stops every worker cleanly.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import signal
import socket
import time
from pathlib import Path

import faker

import pbgen
from pbgen import config
from pbgen.agent import AgentClient, AgentError

LOCKS_PER_WORKER = 40_000
EXIT_OK, EXIT_WORKER_ERROR, EXIT_CONFIG, EXIT_INTERRUPTED = 0, 1, 2, 130


class LaunchError(Exception):
    """A refusal before any worker starts (exit code 2)."""


def make_agent(spec: dict, spool: Path):
    """spec = {"kind": "real", "db": .., "host": .., "port": ..} or {"kind": "fake", "path": ..}."""
    if spec["kind"] == "fake":
        from pbgen.fakeagent import FakeAgent
        return FakeAgent(spec["path"])
    conn = config.ConnectionConfig(db=spec["db"], host=spec.get("host"), port=spec.get("port"))
    return AgentClient(conn, spool)


def _db_bytes(spec: dict) -> int:
    if spec["kind"] != "real" or spec.get("host"):
        return 0
    conn = config.ConnectionConfig(db=spec["db"])
    return sum(p.stat().st_size for p in conn.db_files() if p.exists())


# ------------------------------------------------------------------ worker numbers
def claim_worker_numbers(spool_root: Path, n: int) -> list[int]:
    """Allocates n unused worker numbers via O_EXCL lock files; reuses locks of dead local processes."""
    spool_root.mkdir(parents=True, exist_ok=True)
    host = socket.gethostname()
    got: list[int] = []
    k = 0
    while len(got) < n:
        k += 1
        lock = spool_root / f"w{k:02d}.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                owner_host, pid = lock.read_text().split(":")[:2]
                if owner_host == host and not config.pid_alive(int(pid)):
                    lock.unlink()
                    k -= 1  # retry the same number
            except (OSError, ValueError):
                pass
            continue
        with os.fdopen(fd, "w") as fh:
            fh.write(f"{host}:{os.getpid()}:{int(time.time())}")
        got.append(k)
    return got


def _set_lock_owner(spool_root: Path, worker_no: int) -> None:
    (spool_root / f"w{worker_no:02d}.lock").write_text(f"{socket.gethostname()}:{os.getpid()}:{int(time.time())}")


def release_worker_numbers(spool_root: Path, numbers: list[int]) -> None:
    for k in numbers:
        try:
            (spool_root / f"w{k:02d}.lock").unlink()
        except OSError:
            pass


# ------------------------------------------------------------------ child process
def _worker_main(spec: dict, worker_no: int, spool_root: str, stop, result_q) -> None:
    from pbgen.worker import StopFlag, Worker
    from tools import schema_model as m
    flag = StopFlag(shared=stop)     # handlers only flip a plain attribute: no locks inside a signal handler
    signal.signal(signal.SIGINT, lambda *_: flag.set())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: flag.set())
    spool = Path(spool_root) / f"w{worker_no:02d}"
    _set_lock_owner(Path(spool_root), worker_no)
    agent = None
    stats = None
    import traceback
    spool.mkdir(parents=True, exist_ok=True)
    wlog = open(spool.parent / f"w{worker_no:02d}-worker.log", "a", encoding="utf-8")
    w = None
    try:
        agent = make_agent(spec, spool)
        schema = m.load_expanded(config.SCHEMA_FILE)
        w = Worker(agent, worker_no, spool, schema, stop=flag, db_bytes=lambda: _db_bytes(spec),
                   log=lambda *a: print(*a, file=wlog, flush=True))
        stats = w.run()
        print(f"{time.strftime('%H:%M:%S')} finished: {stats.__dict__}", file=wlog, flush=True)
        result_q.put((worker_no, "ok", stats.__dict__))
    except KeyboardInterrupt:  # Windows delivers Ctrl+C to every process in the console
        flag.set()
        result_q.put((worker_no, "ok", {**(w.stats.__dict__ if w is not None else {}), "reason": "stopped"}))
    except BaseException as e:  # noqa: BLE001 - reported to the launcher
        print(f"{time.strftime('%H:%M:%S')} FAILED: {traceback.format_exc()}", file=wlog, flush=True)
        if agent is not None and hasattr(agent, "agent_log"):
            print(f"agent log:\n{agent.agent_log(40)}", file=wlog, flush=True)
        partial = w.stats.__dict__ if w is not None else {}
        result_q.put((worker_no, "error", {**partial, "error": f"{type(e).__name__}: {e}"}))
    finally:
        if agent is not None:
            agent.close()
        wlog.close()


# ------------------------------------------------------------------ launcher
def preflight(control, workers: int, force_version: bool, spec: dict) -> dict:
    hello = control.request("hello")
    if not hello.get("loaderTables"):
        raise LaunchError("the loader tables are missing; run 'pbgen init' first")
    lock_table = hello.get("L")
    if lock_table is not None and lock_table < LOCKS_PER_WORKER * workers:
        raise LaunchError(f"the server lock table (-L {lock_table}) is too small for {workers} workers "
                          f"(need {LOCKS_PER_WORKER * workers}); restart it with: "
                          f"db/server.sh start <db> --workers {workers}")
    state = control.request("state")
    open_runs = [r for r in state["runs"] if r["RunStatus"] != "COMPLETE"]
    if not state["runs"]:
        raise LaunchError("no run is planned; use 'pbgen plan' first")
    if not open_runs:
        return {"run": None}
    run = open_runs[0]
    if not force_version and (run["FakerVersion"] != faker.VERSION or run["GeneratorVersion"] != pbgen.__version__):
        raise LaunchError(f"run {run['LoaderRunId']} was planned with pbgen {run['GeneratorVersion']} / Faker "
                          f"{run['FakerVersion']}, but this is pbgen {pbgen.__version__} / Faker {faker.VERSION}; "
                          "mixing them would change the data. Use --force-version to continue anyway")
    # release claims left by dead workers on this host
    status = control.request("status")
    host = socket.gethostname()
    dead = []
    for c in status.get("claims", []):
        parsed = config.parse_worker_id(c.get("claimedBy", ""))
        if parsed and parsed[0] == host and not config.pid_alive(parsed[1]):
            dead.append(c["claimedBy"])
    released = control.request("release", run=int(run["LoaderRunId"]), workers=sorted(set(dead)))["released"] \
        if dead else 0
    return {"run": run, "released": released}


def run(spec: dict, workers: int, spool_root: Path, force_version: bool = False, log=print,
        poll_seconds: float = 10.0) -> int:
    control = make_agent(spec, spool_root / "control")
    try:
        try:
            pre = preflight(control, workers, force_version, spec)
        except LaunchError as e:
            log(f"ERROR: {e}")
            return EXIT_CONFIG
        if pre["run"] is None:
            log("Nothing to do: every planned run is complete.")
            return EXIT_OK
        run_row = pre["run"]
        if pre.get("released"):
            log(f"Released {pre['released']} unit(s) left claimed by stopped workers.")
        numbers = claim_worker_numbers(spool_root, workers)
        # children inherit "ignore SIGINT" while they start up; each installs its own handler once ready,
        # so an early Ctrl+C becomes a clean stop instead of killing a half-started worker
        old = signal.signal(signal.SIGINT, signal.SIG_IGN)
        ctx = mp.get_context("spawn")
        stop = ctx.Event()
        result_q = ctx.Queue()
        procs = []
        for k in numbers:
            p = ctx.Process(target=_worker_main, args=(spec, k, str(spool_root), stop, result_q), daemon=False)
            p.start()
            procs.append(p)
            log(f"worker {k:02d} started (pid {p.pid})")
        log(f"Run {run_row['LoaderRunId']} ({run_row['RunKind']}): {len(procs)} worker(s) on {run_row['UnitCount']} units")
        t0 = time.monotonic()
        results = {}
        interrupted = False
        failed = False
        sigint = [False]
        signal.signal(signal.SIGINT, lambda *_: sigint.__setitem__(0, True))  # flag only; Event.set() below
        try:
            last = time.monotonic()
            while any(p.is_alive() for p in procs):
                while True:
                    try:
                        k, kind, data = result_q.get_nowait()
                    except Exception:  # noqa: BLE001 - queue.Empty
                        break
                    results[k] = (kind, data)
                    if kind == "error":
                        # fail fast: a worker error is usually deterministic (it would recur on retry)
                        log(f"ERROR: worker {k:02d}: {data['error']} -- stopping all workers")
                        failed = True
                        stop.set()
                if sigint[0] and not stop.is_set():
                    stop.set()
                if stop.is_set() and not failed:
                    interrupted = True
                for p in procs:
                    p.join(timeout=0.5)
                if time.monotonic() - last >= poll_seconds and not stop.is_set():
                    last = time.monotonic()
                    try:
                        st = control.request("status")
                        log(f"  {st['done']}/{st['done'] + st['pending'] + st['claimed']} units done, "
                            f"{st['doneRows']:,} rows, {st['claimed']} in progress")
                    except AgentError:
                        pass
        finally:
            signal.signal(signal.SIGINT, old)
            release_worker_numbers(spool_root, numbers)
        deadline = time.monotonic() + 30
        while len(results) < len(procs) and time.monotonic() < deadline:
            try:
                k, kind, data = result_q.get(timeout=1)
                results[k] = (kind, data)
            except Exception:  # noqa: BLE001 - queue.Empty
                pass
        for k, p in zip(numbers, procs):
            if k not in results and stop.is_set() and not failed:
                results[k] = ("ok", {"units": 0, "rows": 0, "reason": "stopped"})
            elif k not in results:
                results[k] = ("error", {"error": f"exited with code {p.exitcode} without reporting; "
                                                 f"see {spool_root / f'w{k:02d}-worker.log'}"})
        elapsed = time.monotonic() - t0
        units = sum(d.get("units", 0) for _, d in results.values())
        rows = sum(d.get("rows", 0) for _, d in results.values())
        errors = [f"worker {k:02d}: {d['error']}" for k, (kind, d) in sorted(results.items()) if kind == "error"]
        for k, (kind, d) in sorted(results.items()):
            if kind == "ok":
                log(f"  worker {k:02d}: {d.get('units', 0)} units, {d.get('rows', 0):,} rows, "
                    f"gen {d.get('gen_seconds', 0):.0f}s, load {d.get('load_seconds', 0):.0f}s, stop reason "
                    f"{d.get('reason') or 'n/a'}")
        log(f"Loaded {units} units / {rows:,} rows in {elapsed:.1f}s ({rows / elapsed if elapsed else 0:,.0f} rows/s)")
        for e in errors:
            log(f"ERROR: {e}")
        if errors or failed:
            log("Stopped because of the error above. Fix it, then run the same command again to resume.")
            return EXIT_WORKER_ERROR
        if interrupted or stop.is_set():
            log("Stopped. Run the same command again to resume.")
            return EXIT_INTERRUPTED
        st = control.request("state")
        this = next(r for r in st["runs"] if r["LoaderRunId"] == run_row["LoaderRunId"])
        log(f"Run {this['LoaderRunId']} is {this['RunStatus']}.")
        return EXIT_OK if this["RunStatus"] == "COMPLETE" else EXIT_WORKER_ERROR
    finally:
        control.close()
