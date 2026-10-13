"""pbgen command line (specs/003-data-generation/contracts/cli.md §3)."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from pbgen import config

EXIT_OK, EXIT_FAIL, EXIT_CONFIG = 0, 1, 2


def _conn(args) -> config.ConnectionConfig:
    if args.host and not args.port:
        raise config.ConfigError("--host needs --port")
    return config.ConnectionConfig(db=_db_arg(args), host=args.host, port=args.port)


def _db_arg(args) -> str:
    """Self-service database paths are made absolute: agents run with their spool dir as working dir."""
    if args.host or not args.db:
        return args.db
    return str(Path(args.db).resolve())


def _spec(args) -> dict:
    if args.fake:
        return {"kind": "fake", "path": args.fake}
    return {"kind": "real", "db": _db_arg(args), "host": args.host, "port": args.port}


def _spool(args) -> Path:
    if args.fake:
        return Path(args.spool or Path(args.fake).with_suffix(".spool"))
    return config.spool_root(_conn(args), args.spool)


def _control(args):
    from pbgen.launcher import make_agent
    return make_agent(_spec(args), _spool(args) / f"ctl-{args.command}")


def _schema():
    from tools import schema_model as m
    return m.load_expanded(config.SCHEMA_FILE)


def _actual_bytes(args) -> int:
    if args.fake or args.host:
        return 0
    return sum(p.stat().st_size for p in _conn(args).db_files() if p.exists())


# ------------------------------------------------------------------ commands
def cmd_init(args) -> int:
    if args.fake:
        print("fake database: loader tables are implicit")
        return EXIT_OK
    from pbgen.agent import NOT_SERVED_HINT, run_oneshot
    spool = _spool(args)
    spool.mkdir(parents=True, exist_ok=True)
    status = spool / "init.status"
    status.unlink(missing_ok=True)
    code, out = run_oneshot(_conn(args), "pbgen_init.p", f"{config.LOADER_DF}|{status}", cwd=spool)
    result = status.read_text(encoding="utf-8").strip() if status.exists() else ""
    if not result.startswith("OK"):
        print(out.strip())
        print(f"ERROR: {result or NOT_SERVED_HINT}")
        return EXIT_CONFIG
    print("Loader tables " + ("created." if result == "OK created" else "already present."))
    return EXIT_OK


def _plan(args, growth: bool) -> int:
    from pbgen import planner, sizing
    from pbgen.unitjson import write_json_atomic
    schema = _schema()
    if growth:
        target = planner.Target(size_bytes=args.add_gb * 1e9 if args.add_gb else None, scale=args.add_scale,
                                customers=args.add_customers)
    else:
        target = planner.Target(size_bytes=args.size_gb * 1e9 if args.size_gb else None, scale=args.scale,
                                customers=args.customers)
    agent = _control(args)
    try:
        state = agent.request("state")
        calibration = 1.0
        if getattr(args, "calibrate", False):
            done = [r for r in state["runs"] if r["RunStatus"] == "COMPLETE" and r.get("MeasuredDiskBytes")]
            if done:
                est = sizing.estimate_disk_bytes(schema, float(done[-1]["TargetScale"]))
                calibration = float(done[-1]["MeasuredDiskBytes"]) / est
                print(f"Calibrating sizes by x{calibration:.2f} (measured / estimated, run {done[-1]['LoaderRunId']})")
        try:
            run, units, summary = planner.plan_run(
                schema, state, target, growth=growth, seed=getattr(args, "seed", None),
                as_of=dt.date.fromisoformat(args.as_of) if getattr(args, "as_of", None) else None,
                calibration=calibration,
                progress=lambda u, c, n: print(f"  planned {u:,} units ({c:,}/{n:,} customers)", flush=True))
        except planner.PlanError as e:
            print(f"ERROR: {e}")
            return EXIT_CONFIG
        hello = agent.request("hello")
        if hello.get("L") is not None and hello["L"] < len(units) + 1000:
            print(f"ERROR: the plan has {len(units):,} units, which needs a server lock table (-L) of at least "
                  f"{len(units) + 1000:,} to insert atomically; restart the server with --lock-table {len(units) + 1000}")
            return EXIT_CONFIG
        plan_file = _spool(args) / f"plan-{run['LoaderRunId']}.json"
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(plan_file, {"LoaderRun": [run], "LoaderUnit": units})
        agent.request("plan", file=str(plan_file))
        plan_file.unlink(missing_ok=True)
    finally:
        agent.close()
    sf = run["TargetScale"]
    print(f"Planned run {run['LoaderRunId']} ({run['RunKind']}): scale factor {sf:.6f} (+{run['DeltaScale']:.6f}), "
          f"{len(units):,} units, seed {run['RunSeed']}, as-of {run['AsOfDate']}")
    print(f"Estimated total size after this run: {sizing.describe(schema, sf)}")
    print(f"{'Table':24s}{'New rows':>14s}{'First id':>14s}{'Last id':>14s}")
    for t, v in sorted(summary["tables"].items(), key=lambda kv: kv[0].lower()):
        print(f"{t:24s}{v['rows']:>14,}{v['first']:>14,}{v['last']:>14,}")
    print("Next: pbgen run --workers N")
    return EXIT_OK


def cmd_run(args) -> int:
    from pbgen import launcher
    return launcher.run(_spec(args), args.workers, _spool(args), force_version=args.force_version)


def cmd_status(args) -> int:
    from pbgen.report import format_status
    agent = _control(args)
    try:
        status = agent.request("status")
    finally:
        agent.close()
    if args.json:
        print(json.dumps(status, indent=2, default=str))
    else:
        print(format_status(status, _schema(), _actual_bytes(args)))
    return EXIT_OK


def cmd_check(args) -> int:
    from pbgen.check import run_check
    return run_check(args, _spec(args), _spool(args), _schema())


def cmd_finalize(args) -> int:
    agent = _control(args)
    try:
        state = agent.request("state")
        runs = [r for r in state["runs"] if r["RunStatus"] != "COMPLETE"] or state["runs"][-1:]
        if not runs:
            print("No runs.")
            return EXIT_OK
        run_id = int(runs[0]["LoaderRunId"])
        wm = agent.request("watermark", run=run_id)
        if not wm["complete"]:
            print(f"Run {run_id} is not complete ({wm['unitsDone']}/{wm['unitCount']} units in the done prefix).")
            return EXIT_FAIL
        agent.request("finalize", run=run_id, diskBytes=_actual_bytes(args))
        print(f"Run {run_id} finalized.")
        return EXIT_OK
    finally:
        agent.close()


def cmd_release(args) -> int:
    agent = _control(args)
    try:
        state = agent.request("state")
        open_runs = [r for r in state["runs"] if r["RunStatus"] != "COMPLETE"]
        if not open_runs:
            print("No open run.")
            return EXIT_OK
        n = agent.request("release", run=int(open_runs[0]["LoaderRunId"]), olderThanSec=int(args.older_than * 60))
        print(f"Released {n['released']} claim(s).")
        return EXIT_OK
    finally:
        agent.close()


# ------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pbgen", description="ParkBenchDB data generator")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--db", required=False, help="database path (self-service) or name (with --host/--port)")
        sp.add_argument("--host")
        sp.add_argument("--port", type=int)
        sp.add_argument("--spool", help="spool directory (default <db-dir>/pbgen-spool)")
        sp.add_argument("--fake", help=argparse.SUPPRESS)  # test hook: FakeAgent database file
        return sp

    common(sub.add_parser("init", help="create the internal loader tables"))
    sp = common(sub.add_parser("plan", help="define the first run"))
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--size-gb", type=float)
    g.add_argument("--scale", type=float)
    g.add_argument("--customers", type=int)
    sp.add_argument("--seed", type=int)
    sp.add_argument("--as-of")
    sp.add_argument("--calibrate", action="store_true")
    sp = common(sub.add_parser("grow", help="define a growth run"))
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--add-gb", type=float)
    g.add_argument("--add-scale", type=float)
    g.add_argument("--add-customers", type=int)
    sp.add_argument("--calibrate", action="store_true")
    sp = common(sub.add_parser("run", help="start N workers on the open run"))
    sp.add_argument("--workers", type=int, default=4)
    sp.add_argument("--force-version", action="store_true")
    sp = common(sub.add_parser("status", help="progress report"))
    sp.add_argument("--json", action="store_true")
    sp = common(sub.add_parser("check", help="data check"))
    sp.add_argument("--full", action="store_true")
    sp.add_argument("--json", action="store_true")
    common(sub.add_parser("finalize", help="re-run finalization"))
    sp = common(sub.add_parser("release-claims", help="release stale claims"))
    sp.add_argument("--older-than", type=float, default=0, help="minutes")
    return p


COMMANDS = {"init": cmd_init, "plan": lambda a: _plan(a, False), "grow": lambda a: _plan(a, True), "run": cmd_run,
            "status": cmd_status, "check": cmd_check, "finalize": cmd_finalize, "release-claims": cmd_release}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    if not args.db and not args.fake:
        print("ERROR: --db is required")
        return EXIT_CONFIG
    from pbgen.agent import NOT_SERVED_HINT, AgentError
    try:
        return COMMANDS[args.command](args)
    except KeyboardInterrupt:
        print("Stopped. Run the same command again to resume.")
        return 130
    except config.ConfigError as e:
        print(f"ERROR: {e}")
        return EXIT_CONFIG
    except AgentError as e:
        msg = str(e)
        if "exited" in msg and ("1423" in msg or "single-user" in msg or "no server" in msg.lower()
                                or "shared memory" in msg.lower() or "(9432)" in msg or "(1384)" in msg):
            print(f"ERROR: {NOT_SERVED_HINT}\n{msg}")
            return EXIT_CONFIG
        print(f"ERROR: {msg}")
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
