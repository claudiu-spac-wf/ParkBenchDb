"""Planner and count-model tests (T015, T039)."""

import datetime as dt
import json
import unittest

from helpers import REAL

from pbgen import counts, planner
from pbgen.generate.common import _parse_map
from tools import schema_model as m

AS_OF = dt.date(2026, 8, 31)
PER_CUSTOMER = {"CustomerAddress": 1.5, "CustomerContact": 2.5, "CustomerDocument": 1.0, "CustomerNote": 1.5,
                "Account": 1.5, "AccountHolder": 2.0, "Payee": 2.5, "Card": 1.2, "Loan": 0.25,
                "AccountStatement": 18, "MonthlyBalance": 18, "DebitTransaction": 50, "CreditTransaction": 18,
                "Transfer": 6, "CardAuthorization": 50, "LoginEvent": 12, "AuditLog": 50}


def complete(run, units, summary, prev=None):
    """State as the agent would report it after the run completed (on top of an earlier state)."""
    run = dict(run, RunStatus="COMPLETE", UnitsDone=run["UnitCount"])
    last = {b["TableName"]: b["MaxId"] for b in (prev or {}).get("bti", [])}
    last.update({t: v["last"] for t, v in summary["tables"].items()})
    bti = [{"TableName": t, "MaxId": n, "TableRowCount": n} for t, n in last.items()]
    return {"runs": (prev or {}).get("runs", []) + [run], "bti": bti}


class PlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = m.load_expanded(REAL)
        cls.prun, cls.units, cls.summary = planner.plan_run(cls.schema, {"runs": []}, planner.Target(scale=0.05),
                                                           growth=False, seed=7, as_of=AS_OF)

    def test_count_model_deterministic(self):
        self.assertEqual(counts.customer_unit_counts(12345, 50), counts.customer_unit_counts(12345, 50))
        self.assertNotEqual(counts.customer_unit_counts(1, 50), counts.customer_unit_counts(2, 50))

    def test_plan_is_deterministic(self):
        _, units2, _ = planner.plan_run(self.schema, {"runs": []}, planner.Target(scale=0.05), growth=False,
                                        seed=7, as_of=AS_OF)
        self.assertEqual(units2, self.units)

    def test_units_fit_the_lock_table(self):
        self.assertTrue(all(u["TotalRows"] <= planner.UNIT_MAX_ROWS for u in self.units))
        self.assertTrue(all(u["TotalRows"] == sum(_parse_map(u["RowCounts"]).values()) for u in self.units))

    def test_ids_are_dense_and_contiguous(self):
        nxt = {}
        for u in self.units:
            first, cnt = _parse_map(u["FirstIds"]), _parse_map(u["RowCounts"])
            for t, c in cnt.items():
                self.assertEqual(first[t], nxt.get(t, 1), f"unit {u['UnitNo']} {t}")
                nxt[t] = first[t] + c
        for t, v in self.summary["tables"].items():
            self.assertEqual(v["first"], 1)
            self.assertEqual(v["last"], nxt[t] - 1)

    def test_phases_and_seeds(self):
        self.assertEqual([u["Phase"] for u in self.units], sorted(u["Phase"] for u in self.units))
        self.assertEqual(self.units[0]["UnitKind"], "REFERENCE")
        seeds = [u["UnitSeed"] for u in self.units]
        self.assertTrue(all(len(s) == 64 and int(s, 16) >= 0 for s in seeds))
        self.assertEqual(len(set(seeds)), len(seeds))

    def test_fixed_and_scaled_counts(self):
        t = self.summary["tables"]
        for name, n in counts.REFERENCE_TABLES.items():
            self.assertEqual(t[name]["rows"], n, name)
        self.assertEqual(t["Customer"]["rows"], 50_000)
        self.assertEqual(t["Employee"]["rows"], 250)       # 5000 x 0.05
        self.assertEqual(t["Merchant"]["rows"], 4000)
        for name, per in PER_CUSTOMER.items():
            ratio = t[name]["rows"] / 50_000 / per
            self.assertTrue(0.85 <= ratio <= 1.15, f"{name}: {ratio:.2f} of documented per-customer ratio")

    def test_run_one_has_enough_employees(self):
        _, _, s = planner.plan_run(self.schema, {"runs": []}, planner.Target(scale=0.01), growth=False, as_of=AS_OF)
        self.assertGreaterEqual(s["tables"]["Employee"]["rows"], 250)

    def test_refusals(self):
        with self.assertRaises(planner.PlanError):
            planner.plan_run(self.schema, {"runs": [self.prun]}, planner.Target(scale=0.05), growth=False)
        with self.assertRaises(planner.PlanError):
            planner.plan_run(self.schema, {"runs": []}, planner.Target(size_bytes=0.1e9), growth=False)
        with self.assertRaises(planner.PlanError):
            planner.plan_run(self.schema, {"runs": []}, planner.Target(scale=0.004), growth=False)

    def test_size_target(self):
        run, _, _ = planner.plan_run(self.schema, {"runs": []}, planner.Target(size_bytes=1e9), growth=False, as_of=AS_OF)
        self.assertTrue(0.006 <= run["TargetScale"] <= 0.009)
        self.assertEqual(run["TargetDiskBytes"], 1_000_000_000)


class GrowthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = m.load_expanded(REAL)
        cls.run1, cls.units1, cls.sum1 = planner.plan_run(cls.schema, {"runs": []}, planner.Target(scale=0.01),
                                                          growth=False, seed=7, as_of=AS_OF)
        cls.state = complete(cls.run1, cls.units1, cls.sum1)
        cls.run2, cls.units2, cls.sum2 = planner.plan_run(cls.schema, cls.state, planner.Target(scale=0.02),
                                                          growth=True)

    def test_growth_above_the_employee_floor(self):
        # 0.03 -> 0.1 cumulative: 500 employees in total, so this step adds 250 on top of the 250 floor
        state = complete(self.run2, self.units2, self.sum2, self.state)
        _, _, s3 = planner.plan_run(self.schema, state, planner.Target(scale=0.07), growth=True)
        self.assertEqual(s3["tables"]["Employee"]["rows"], 250)
        self.assertNotIn("Employee", self.sum2["tables"])

    def test_ids_continue(self):
        for t, v in self.sum2["tables"].items():
            self.assertEqual(v["first"], self.sum1["tables"][t]["last"] + 1, t)

    def test_no_reference_unit_and_no_fixed_tables(self):
        self.assertNotIn("REFERENCE", {u["UnitKind"] for u in self.units2})
        for name in counts.REFERENCE_TABLES:
            self.assertNotIn(name, self.sum2["tables"])

    def test_inherited_values(self):
        self.assertEqual(self.run2["RunKind"], "GROWTH")
        self.assertEqual(self.run2["AsOfDate"], self.run1["AsOfDate"])
        self.assertEqual(self.run2["RunSeed"], self.run1["RunSeed"] + 1)
        self.assertAlmostEqual(self.run2["TargetScale"], 0.03)
        self.assertEqual(json.loads(self.run2["PlanSummary"])["baseSeed"], self.run1["RunSeed"])

    def test_refusals(self):
        with self.assertRaises(planner.PlanError):
            planner.plan_run(self.schema, self.state, planner.Target(scale=0.0), growth=True)
        with self.assertRaises(planner.PlanError):
            planner.plan_run(self.schema, {"runs": [dict(self.run1)], "bti": []}, planner.Target(scale=0.01), growth=True)
        with self.assertRaises(planner.PlanError):
            planner.plan_run(self.schema, {"runs": []}, planner.Target(scale=0.01), growth=True)

    def test_growth_matches_direct_plan(self):
        _, _, direct = planner.plan_run(self.schema, {"runs": []}, planner.Target(scale=0.03), growth=False,
                                        seed=7, as_of=AS_OF)
        for t, v in direct["tables"].items():
            grown = self.sum1["tables"].get(t, {}).get("rows", 0) + self.sum2["tables"].get(t, {}).get("rows", 0)
            if t in counts.REFERENCE_TABLES:
                self.assertEqual(grown, v["rows"], t)
            elif t in ("Employee", "Merchant", "Customer"):   # cumulative targets: exactly equal
                self.assertEqual(grown, v["rows"], t)
            else:
                self.assertTrue(abs(grown - v["rows"]) <= max(3, 0.03 * v["rows"]), f"{t}: {grown} vs {v['rows']}")


if __name__ == "__main__":
    unittest.main()
