"""Shared helpers for the unit tests."""

import copy
import os
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE = ROOT / "tests" / "fixtures" / "minimal_valid.yaml"
REAL = ROOT / "schema" / "parkbench-schema.yaml"
GOLDEN = ROOT / "tests" / "golden"


def fixture_dict() -> dict:
    with open(FIXTURE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def real_dict() -> dict:
    with open(REAL, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def write_temp(data: dict) -> str:
    """Dump a (mutated) schema dict to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
    return path


def table(data: dict, name: str) -> dict:
    return next(t for t in data["tables"] if t["name"] == name)


def field(data: dict, tname: str, fname: str) -> dict:
    return next(f for f in table(data, tname)["fields"] if f["name"] == fname)


def mutated(mutator) -> dict:
    data = copy.deepcopy(fixture_dict())
    mutator(data)
    return data


# ---------------------------------------------------------------- pbgen helpers
def small_plan(customer_units: int = 6, seed: int = 7, as_of: str = "2026-08-31"):
    """A real planner run at SF 0.01 truncated to reference + 1 employee + 1 merchant + N customer units."""
    import datetime as _dt
    import json as _json
    from pbgen import planner
    from tools import schema_model as _m
    schema = _m.load_expanded(REAL)
    run, units, summary = planner.plan_run(schema, {"runs": []}, planner.Target(scale=0.01), growth=False,
                                           seed=seed, as_of=_dt.date.fromisoformat(as_of))
    keep, cust = [], 0
    for u in units:
        if u["UnitKind"] == "CUSTOMER":
            if cust >= customer_units:
                continue
            cust += 1
        keep.append(u)
    for i, u in enumerate(keep, 1):
        u["UnitNo"] = i
    run["UnitCount"] = len(keep)
    run["PlanSummary"] = _json.dumps(summary)
    return schema, run, keep, summary


def fake_with_plan(tmpdir, customer_units: int = 6, seed: int = 7):
    """A FakeAgent in tmpdir holding small_plan(); returns (agent, schema, run, units)."""
    import json as _json
    from pbgen.fakeagent import FakeAgent
    schema, run, units, _summary = small_plan(customer_units, seed)
    agent = FakeAgent(Path(tmpdir) / "fake.sqlite")
    plan_file = Path(tmpdir) / "plan.json"
    plan_file.write_text(_json.dumps({"LoaderRun": [run], "LoaderUnit": units}), encoding="utf-8")
    agent.request("plan", file=str(plan_file))
    return agent, schema, run, units
