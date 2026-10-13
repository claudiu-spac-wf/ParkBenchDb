"""Plans a generation run: target -> units with exact row counts and ID ranges (data-model.md §2).

IDs are fixed here, before any data exists, so the final data is dense and identical whatever
the number of workers, the completion order, or how often the run is stopped and resumed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass

import faker

import pbgen
from pbgen import counts, sizing
from pbgen.generate.common import default_as_of, format_map

EMPLOYEES_PER_UNIT = 1000
MERCHANTS_PER_UNIT = 2000
CUSTOMERS_PER_UNIT = 50
UNIT_MAX_ROWS = 35_000
EMPLOYEES_AT_SF1 = 5000
MERCHANTS_AT_SF1 = 80_000
CUSTOMERS_AT_SF1 = 1_000_000
MIN_RUN1_EMPLOYEES = 250   # one manager per branch; >= 60 for InterestRateHistory (research R7)
DEFAULT_SEED = 20260927


class PlanError(Exception):
    """A plan request that must be refused (exit code 2)."""


@dataclass
class Target:
    size_bytes: float | None = None
    scale: float | None = None
    customers: int | None = None


def unit_seed(run_seed: int, run_id: int, unit_no: int) -> str:
    return hashlib.sha256(f"{run_seed}:{run_id}:{unit_no}".encode()).hexdigest()


def _complete_scale(runs: list[dict]) -> float:
    done = [r for r in runs if r["RunStatus"] == "COMPLETE"]
    return float(done[-1]["TargetScale"]) if done else 0.0


def resolve_scale(schema, target: Target, current: float, growth: bool, calibration: float = 1.0) -> float:
    """Returns the cumulative target scale factor for this run."""
    if target.scale is not None:
        total = current + target.scale if growth else target.scale
    elif target.customers is not None:
        total = current + target.customers / CUSTOMERS_AT_SF1 if growth else target.customers / CUSTOMERS_AT_SF1
    elif target.size_bytes is not None:
        wanted = (sizing.estimate_disk_bytes(schema, current) * calibration + target.size_bytes) if growth \
            else target.size_bytes
        try:
            total = sizing.solve_scale(wanted, schema, calibration)
        except sizing.SizeError as e:
            raise PlanError(str(e)) from e
    else:
        raise PlanError("give a size, a scale factor or a customer count")
    total = round(total, 6)
    if total < sizing.MIN_SCALE:
        raise PlanError(f"scale factor {total:g} is below the minimum {sizing.MIN_SCALE} "
                        f"(about {sizing.min_disk_bytes(schema) / 1e9:.2f} GB on disk)")
    if growth and total - current <= 1e-9:
        raise PlanError("a growth step must add data (the requested size is not larger than the current one)")
    return total


def plan_run(schema, state: dict, target: Target, *, growth: bool, seed: int | None = None,
             as_of: dt.date | None = None, calibration: float = 1.0, progress=None):
    """Returns (run_row, unit_rows, summary). state = {"runs": [...], "bti": [...]} from the agent."""
    runs = state.get("runs") or []
    if growth:
        if not runs:
            raise PlanError("the database has no data yet; use 'plan' for the first run")
        if any(r["RunStatus"] != "COMPLETE" for r in runs):
            raise PlanError("a previous run is not complete; resume it with 'run' first")
    elif runs:
        raise PlanError("the database already has generation runs; use 'grow' to add data")

    current = _complete_scale(runs)
    total = resolve_scale(schema, target, current, growth, calibration)
    delta = round(total - current, 6)
    run_id = (max(r["LoaderRunId"] for r in runs) + 1) if runs else 1
    base_seed = int(runs[0]["RunSeed"]) if runs else (seed if seed is not None else DEFAULT_SEED)
    run_seed = base_seed + run_id - 1
    as_of = dt.date.fromisoformat(runs[0]["AsOfDate"]) if runs else (as_of or default_as_of())

    max_ids = {b["TableName"]: int(b["MaxId"]) for b in state.get("bti") or []}
    next_id = {t.name: max_ids.get(t.name, 0) + 1 for t in schema.tables}

    # cumulative targets minus what exists: growth steps add up to the same counts as a direct plan
    have = {t: next_id[t] - 1 for t in ("Employee", "Merchant", "Customer")}
    n_emp = max(0, max(MIN_RUN1_EMPLOYEES, round(EMPLOYEES_AT_SF1 * total)) - have["Employee"])
    n_mer = max(0, round(MERCHANTS_AT_SF1 * total) - have["Merchant"])
    n_cus = max(1, round(CUSTOMERS_AT_SF1 * total) - have["Customer"])

    units: list[dict] = []

    def add_unit(phase: int, kind: str, row_counts: dict[str, int], seed_hex: str):
        first = {}
        for t, c in row_counts.items():
            first[t] = next_id[t]
            next_id[t] += c
        units.append({"LoaderRunId": run_id, "UnitNo": len(units) + 1, "Phase": phase, "UnitKind": kind,
                      "UnitStatus": "P", "UnitSeed": seed_hex, "FirstIds": format_map(first),
                      "RowCounts": format_map(row_counts), "TotalRows": sum(row_counts.values()),
                      "ClaimedBy": "", "ClaimedAt": None, "HeartbeatAt": None, "DoneAt": None, "Attempts": 0})

    def seed_for_next() -> str:
        return unit_seed(run_seed, run_id, len(units) + 1)

    if not growth:
        add_unit(0, "REFERENCE", counts.reference_unit_counts(), seed_for_next())
    for start in range(0, n_emp, EMPLOYEES_PER_UNIT):
        add_unit(1, "EMPLOYEE", {"Employee": min(EMPLOYEES_PER_UNIT, n_emp - start)}, seed_for_next())
    for start in range(0, n_mer, MERCHANTS_PER_UNIT):
        add_unit(1, "MERCHANT", {"Merchant": min(MERCHANTS_PER_UNIT, n_mer - start)}, seed_for_next())
    remaining = n_cus
    while remaining > 0:
        n = min(CUSTOMERS_PER_UNIT, remaining)
        s = seed_for_next()
        c = counts.customer_unit_counts(int(s, 16), n)
        while sum(c.values()) > UNIT_MAX_ROWS and n > 1:   # split oversized units (rare)
            n //= 2
            c = counts.customer_unit_counts(int(s, 16), n)
        add_unit(2, "CUSTOMER", c, s)
        remaining -= n
        if progress and len(units) % 500 == 0:
            progress(len(units), n_cus - remaining, n_cus)

    tables = {}
    for t in schema.tables:
        first = max_ids.get(t.name, 0) + 1
        last = next_id[t.name] - 1
        if last >= first:
            tables[t.name] = {"rows": last - first + 1, "first": first, "last": last}
    summary = {"tables": tables, "employeeMax": next_id["Employee"] - 1, "merchantMax": next_id["Merchant"] - 1,
               "baseSeed": base_seed, "estimatedDiskBytes": round(sizing.estimate_disk_bytes(schema, total)),
               "estimatedDataBytes": round(sizing.estimate_data_bytes(schema, total))}
    run = {"LoaderRunId": run_id, "RunKind": "GROWTH" if growth else "INITIAL", "RunStatus": "PLANNED",
           "TargetScale": total, "DeltaScale": delta,
           "TargetDiskBytes": int(target.size_bytes if not growth else 0) if target.size_bytes else 0,
           "RunSeed": run_seed, "AsOfDate": as_of.isoformat(), "GeneratorVersion": pbgen.__version__,
           "FakerVersion": faker.VERSION, "UnitCount": len(units), "UnitsDone": 0,
           "PlanSummary": json.dumps(summary), "PlannedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
           "CompletedAt": None, "MeasuredDiskBytes": 0}
    return run, units, summary
