"""Data-check tests: distribution checks, formatting, and the six corruption cases (T043, SC-005)."""

import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from helpers import fake_with_plan

from pbgen import check, report
from pbgen.worker import Worker


class DistributionTests(unittest.TestCase):
    def test_within_and_outside_tolerance(self):
        rows = {"Customer": [{"CustomerKind": "I"}] * 920 + [{"CustomerKind": "B"}] * 80}
        exp = [("Customer", "CustomerKind", "I", 0.92)]
        self.assertTrue(report.check_distributions(rows, exp)[0]["ok"])
        rows = {"Customer": [{"CustomerKind": "I"}] * 850 + [{"CustomerKind": "B"}] * 150}
        r = report.check_distributions(rows, exp)[0]
        self.assertFalse(r["ok"])
        self.assertIn("85.0% observed", r["detail"])

    def test_small_samples_are_skipped(self):
        r = report.check_distributions({"Customer": [{"CustomerKind": "I"}] * 10},
                                       [("Customer", "CustomerKind", "I", 0.92)])[0]
        self.assertTrue(r["ok"] and r["skipped"])

    def test_format(self):
        text, failed = report.format_checks([{"check": "A.x", "ok": True, "detail": "fine"},
                                             {"check": "B.y", "ok": False, "detail": "bad", "exampleId": 42}])
        self.assertEqual(failed, 1)
        self.assertIn("CHECK A.x: ok (fine)", text)
        self.assertIn("CHECK B.y: FAIL (bad, e.g. id 42)", text)
        self.assertTrue(text.endswith("CHECK FAILED (1)"))


class CorruptionTests(unittest.TestCase):
    """Loads a small fake database once, then corrupts copies of it."""

    @classmethod
    def setUpClass(cls):
        cls.base = Path(tempfile.mkdtemp())
        agent, cls.schema, _run, _units = fake_with_plan(cls.base, customer_units=3)
        Worker(agent, 1, cls.base / "w1", cls.schema, log=lambda *a: None).run()
        cls.db_path = Path(agent.path)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "db.sqlite"
        src = sqlite3.connect(self.db_path)
        dst = sqlite3.connect(self.path)
        src.backup(dst)
        src.close()
        dst.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_check(self):
        from pbgen.fakeagent import FakeAgent
        a = FakeAgent(self.path)
        rows = {t.name: a.all_rows(t.name) for t in self.schema.tables}
        return check.check_rows(self.schema, rows, a.request("state")["bti"])

    def failures(self):
        return {r["check"] + "@" + r["table"] for r in self.run_check() if not r["ok"]}

    def sql(self, statement, *params):
        db = sqlite3.connect(self.path)
        db.execute(statement, params)
        db.commit()
        db.close()

    def update_row(self, table, row_id, **changes):
        db = sqlite3.connect(self.path)
        (data,) = db.execute("SELECT data FROM row WHERE tbl=? AND id=?", (table, row_id)).fetchone()
        d = json.loads(data)
        d.update(changes)
        db.execute("UPDATE row SET data=? WHERE tbl=? AND id=?", (json.dumps(d), table, row_id))
        db.commit()
        db.close()

    def test_clean_database_passes(self):
        self.assertEqual(self.failures(), set())

    def test_gap_in_ids(self):
        self.sql("DELETE FROM row WHERE tbl='Customer' AND id=5")
        f = self.failures()
        self.assertIn("density@Customer", f)
        self.assertIn("BenchmarkTableInfo@Customer", f)

    def test_duplicate_id(self):
        db = sqlite3.connect(self.path)
        (data,) = db.execute("SELECT data FROM row WHERE tbl='Payee' AND id=1").fetchone()
        (mx,) = db.execute("SELECT MAX(id) FROM row WHERE tbl='Payee'").fetchone()
        d = json.loads(data)
        d["PayeeId"] = mx + 1            # a copied row beyond MaxId: counts and BenchmarkTableInfo disagree
        db.execute("INSERT INTO row VALUES ('Payee', ?, ?)", (mx + 1, json.dumps(d)))
        db.commit()
        db.close()
        self.assertIn("BenchmarkTableInfo@Payee", self.failures())

    def test_broken_foreign_key(self):
        self.update_row("Account", 1, BranchId=999999)
        self.assertIn("fk.BranchId@Account", self.failures())

    def test_random_int_out_of_range(self):
        self.update_row("DebitTransaction", 1, RandomInt100=0)
        self.assertIn("RandomInt100@DebitTransaction", self.failures())

    def test_wrong_statement_total(self):
        db = sqlite3.connect(self.path)
        (data,) = db.execute("SELECT data FROM row WHERE tbl='AccountStatement' AND id=1").fetchone()
        db.close()
        self.update_row("AccountStatement", 1, TotalDebits=round(json.loads(data)["TotalDebits"] + 1, 2))
        self.assertIn("derived.statementTotals@AccountStatement", self.failures())

    def test_stale_benchmark_table_info(self):
        db = sqlite3.connect(self.path)
        (data,) = db.execute("SELECT data FROM bti WHERE tbl='Card'").fetchone()
        b = json.loads(data)
        b["MaxId"] -= 1
        db.execute("UPDATE bti SET data=? WHERE tbl='Card'", (json.dumps(b),))
        db.commit()
        db.close()
        self.assertIn("BenchmarkTableInfo@Card", self.failures())


if __name__ == "__main__":
    unittest.main()
