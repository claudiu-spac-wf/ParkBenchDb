"""Foundation tests for pbgen: encodings, sizing, config, loader .df, server script (T003)."""

import base64
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import REAL, ROOT

from pbgen import config, sizing, unitjson
from tools import gen_db_files as g
from tools import schema_model as m

FAKE_DLC = ROOT / "tests" / "fixtures" / "fake_dlc"
TZ = dt.timezone(dt.timedelta(hours=-5))


class UnitJsonTests(unittest.TestCase):
    def test_encodings(self):
        self.assertEqual(unitjson.encode_value("DATE", dt.date(2026, 3, 1)), "2026-03-01")
        self.assertEqual(unitjson.encode_value("DATETIME", dt.datetime(2026, 3, 1, 9, 5, 7, 123000)),
                         "2026-03-01T09:05:07.123")
        self.assertEqual(unitjson.encode_value("DATETIME-TZ", dt.datetime(2026, 3, 1, 9, 5, 7, 123000, tzinfo=TZ)),
                         "2026-03-01T09:05:07.123-05:00")
        self.assertIs(unitjson.encode_value("LOGICAL", 1), True)
        self.assertIsNone(unitjson.encode_value("DATE", None))
        self.assertEqual(unitjson.encode_value("DECIMAL", 12.345678, 2), 12.35)
        self.assertEqual(unitjson.encode_value("BLOB", b"\x00\xff"), base64.b64encode(b"\x00\xff").decode())
        self.assertEqual(unitjson.encode_value("CHARACTER", 'Café "Luna" ~ ≈'), 'Café "Luna" ~ ≈')
        with self.assertRaises(ValueError):
            unitjson.encode_value("DATETIME-TZ", dt.datetime(2026, 1, 1))

    def test_write_unit_is_atomic(self):
        d = Path(tempfile.mkdtemp())
        try:
            p = d / "unit.json"
            unitjson.write_unit(p, {"Currency": [{"CurrencyId": 1, "CurrencyName": "≈"}]})
            self.assertTrue(p.exists())
            self.assertFalse(Path(str(p) + ".tmp").exists())
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["Currency"][0]["CurrencyName"], "≈")
        finally:
            shutil.rmtree(d)


class SizingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = m.load_expanded(REAL)

    def test_matches_measured_database(self):
        # a real SF 0.01 database measured 1.236 GB of extents (research.md R9, "Measured model")
        self.assertTrue(1.15e9 <= sizing.estimate_disk_bytes(self.schema, 0.01) <= 1.30e9)
        self.assertTrue(80e9 <= sizing.estimate_disk_bytes(self.schema, 1.0) <= 100e9)

    def test_one_gb(self):
        self.assertTrue(0.006 <= sizing.solve_scale(1e9, self.schema) <= 0.009)

    def test_monotonic_and_minimum(self):
        a, b = sizing.solve_scale(2e9, self.schema), sizing.solve_scale(5e9, self.schema)
        self.assertLess(a, b)
        with self.assertRaises(sizing.SizeError) as cm:
            sizing.solve_scale(0.1e9, self.schema)
        self.assertIn("smallest supported", str(cm.exception))


class ConfigTests(unittest.TestCase):
    def test_missing_dlc(self):
        old = os.environ.pop("DLC", None)
        try:
            with self.assertRaises(config.ConfigError):
                config.dlc()
        finally:
            if old is not None:
                os.environ["DLC"] = old

    def test_worker_id(self):
        wid = config.worker_id(3)
        self.assertRegex(wid, r"^[^:]+:\d+:3:\d+$")
        self.assertEqual(config.parse_worker_id(wid)[2], 3)
        self.assertIsNone(config.parse_worker_id("garbage"))

    def test_pid_alive(self):
        self.assertTrue(config.pid_alive(os.getpid()))
        self.assertFalse(config.pid_alive(999_999_999))

    def test_connect_args(self):
        self.assertEqual(config.ConnectionConfig("/d/pb").connect_args(), ["-db", "/d/pb"])
        self.assertEqual(config.ConnectionConfig("pb", "h", 20931).connect_args(), ["-db", "pb", "-H", "h", "-S", "20931"])


class LoaderDfTests(unittest.TestCase):
    def test_loader_df(self):
        out = Path(tempfile.mkdtemp())
        try:
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                rc = g.main([str(ROOT / "schema" / "loader-schema.yaml"), "--out", str(out), "--loader"])
            self.assertEqual(rc, 0)
            text = (out / "parkbench_loader.df").read_text(encoding="utf-8")
            self.assertEqual(re.findall(r'^ADD TABLE "(\w+)"', text, re.M), ["LoaderRun", "LoaderUnit"])
            self.assertEqual(text.count("ADD SEQUENCE"), 0)
            self.assertEqual(set(re.findall(r'^ADD TABLE "\w+"\n  AREA "(\w+)"', text, re.M)), {"PB_Ref_Data"})
            self.assertEqual(set(re.findall(r'^ADD INDEX "\w+" ON "\w+"\n  AREA "(\w+)"', text, re.M)), {"PB_Ref_Idx"})
            self.assertEqual((ROOT / "db" / "parkbench_loader.df").read_text(encoding="utf-8"), text)
        finally:
            shutil.rmtree(out)


class ServerScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.log = self.tmp / "calls.log"
        (self.tmp / "pb.db").write_text("")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_script(self, *args, env=None):
        e = {k: v for k, v in os.environ.items() if not k.startswith("FAKE_")}
        e.update(DLC=str(FAKE_DLC), FAKE_DLC_LOG=str(self.log), **(env or {}))
        return subprocess.run(["bash", str(ROOT / "db" / "server.sh"), *args], capture_output=True, text=True,
                              env=e, cwd=self.tmp, timeout=120)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_start(self):
        r = self.run_script("start", str(self.tmp / "pb"), "--workers", "4", env={"FAKE_HOLDER_RC": "0"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        c = self.calls()
        db = str(self.tmp / "pb")
        self.assertIn(f"proserve {db} -S 20931 -n 14 -Mn 5 -L 160000 -B 200000 -bibufs 64 -spin 20000", c)
        # helpers are detached; give them a moment to log
        import time
        for _ in range(50):
            c = self.calls()
            if sum(1 for x in c if x.startswith("proapw")) == 2 and any(x.startswith("probiw") for x in c):
                break
            time.sleep(0.1)
        self.assertEqual(sum(1 for x in c if x == f"probiw {db}"), 1)
        self.assertEqual(sum(1 for x in c if x == f"proapw {db}"), 2)
        self.assertIn("running on port 20931, -L 160000", r.stdout)

    def test_start_refuses_when_running(self):
        r = self.run_script("start", str(self.tmp / "pb"), env={"FAKE_HOLDER_RC": "16"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("already running", r.stdout)

    def test_stop_and_status(self):
        self.assertEqual(self.run_script("status", str(self.tmp / "pb"), env={"FAKE_HOLDER_RC": "16"}).returncode, 0)
        self.assertEqual(self.run_script("status", str(self.tmp / "pb"), env={"FAKE_HOLDER_RC": "0"}).returncode, 3)
        r = self.run_script("stop", str(self.tmp / "pb"), env={"FAKE_HOLDER_RC": "16"})
        self.assertEqual(r.returncode, 0)
        self.assertIn(f"proshut {self.tmp / 'pb'} -by", self.calls())

    def test_bad_arguments(self):
        self.assertEqual(self.run_script("bogus", str(self.tmp / "pb")).returncode, 2)
        self.assertEqual(self.run_script("start", str(self.tmp / "pb"), "--workers", "x").returncode, 2)


if __name__ == "__main__":
    unittest.main()
