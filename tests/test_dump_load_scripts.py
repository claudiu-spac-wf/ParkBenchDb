"""Tests for db/dump_db.* and db/load_db.* against the stub OpenEdge install (spec 003 US7, T058).

Everything happens in fresh temporary directories under .tmp/; no real database is touched.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT
from test_build_scripts import CMD, FAKE_DLC, TMP_ROOT, winpath

DUMP_STEPS = ["Check prerequisites", "Dump schema and sequences", "Dump tables", "Summary"]
LOAD_STEPS = ["Check prerequisites", "Create structure", "Copy UTF-8 metaschema", "Configure before-image",
              "Load schema", "Load data", "Rebuild indexes", "Restore sequences and verify"]
TABLES = ["Currency", "Customer", "LoaderRun"]


class DumpLoadMixin:
    """Scenarios shared by the bash and batch variants. Subclasses implement run_script(script, args, env)."""

    def setUp(self):
        TMP_ROOT.mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(dir=TMP_ROOT))
        self.log = self.tmp / "calls.log"
        (self.tmp / "src").mkdir()
        (self.tmp / "src" / "parkbench.db").write_text("")
        self.src = self.tmp / "src" / "parkbench"
        self.dump = self.tmp / "dump"
        self.target = self.tmp / "target"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def calls(self) -> list[str]:
        if not self.log.exists():
            return []
        return [" ".join(x.replace('"', "").replace("\\", "/").split()) for x in
                self.log.read_text(encoding="utf-8", errors="replace").splitlines()]

    def dump_db(self, *extra, env=None):
        return self.run_script("dump_db", [self.src, self.dump, *extra], env)

    def load_db(self, *extra, env=None):
        return self.run_script("load_db", [self.dump, self.target, *extra], env)

    def make_dump(self):
        r = self.dump_db(env={"FAKE_HOLDER_RC": "16"})
        self.assertEqual(r.returncode, 0, r.stdout)
        self.log.unlink(missing_ok=True)

    # ------------------------------------------------------------------ dump
    def test_dump_served(self):
        r = self.dump_db(env={"FAKE_HOLDER_RC": "16"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for n, name in enumerate(DUMP_STEPS, 1):
            self.assertIn(f"[{n}/4] {name} ... ok", r.stdout)
        self.assertIn("ok (served)", r.stdout)
        self.assertIn("Dumped 3 tables, 21 rows", r.stdout)
        manifest = (self.dump / "manifest.txt").read_text()
        for t in TABLES:
            self.assertTrue((self.dump / f"{t}.bd").exists(), t)
            self.assertIn(f"rows={t}=7", manifest)
        c = self.calls()
        self.assertTrue(c[0].startswith("proutil ") and c[0].endswith("-C holder"), c[0])
        self.assertIn("_progres -b -db ", c[1])          # served: no -1
        self.assertIn("dump|", c[1])
        self.assertEqual([x.split()[2:4] for x in c[2:]], [["-C", "dump"]] * 3)
        self.assertEqual([x.split()[4] for x in c[2:]], TABLES)
        self.assertFalse(any(" load " in x or "truncate" in x or "prostrct" in x for x in c))

    def test_dump_offline_uses_single_user(self):
        r = self.dump_db(env={"FAKE_HOLDER_RC": "0"})
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("ok (offline)", r.stdout)
        self.assertIn("_progres -b -1 -db ", self.calls()[1])

    def test_dump_refusals(self):
        cases = [
            ({"FAKE_HOLDER_RC": "14"}, None, "open single-user"),
            ({"FAKE_HOLDER_RC": "16"}, "notempty", "is not empty"),
            ({"FAKE_HOLDER_RC": "16"}, "nodb", "not found"),
        ]
        for env, setup, text in cases:
            with self.subTest(text=text):
                self.log.unlink(missing_ok=True)
                shutil.rmtree(self.dump, ignore_errors=True)
                if setup == "notempty":
                    self.dump.mkdir()
                    (self.dump / "keep.txt").write_text("x")
                if setup == "nodb":
                    (self.tmp / "src" / "parkbench.db").unlink()
                r = self.dump_db(env=env)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn(text, r.stdout)
                self.assertFalse(any("-C dump" in x or "_progres" in x for x in self.calls()))
                if setup == "notempty":
                    self.assertEqual(sorted(p.name for p in self.dump.iterdir()), ["keep.txt"])
                if setup == "nodb":
                    (self.tmp / "src" / "parkbench.db").write_text("")

    def test_dump_refuses_active_workers(self):
        r = self.dump_db(env={"FAKE_HOLDER_RC": "16", "FAKE_ACTIVE_CLAIMS": "3"})
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("3 pbgen unit(s) are claimed", r.stdout)
        self.assertFalse(any("-C dump" in x for x in self.calls()))
        self.assertFalse((self.dump / "manifest.txt").exists())
        shutil.rmtree(self.dump)
        r = self.dump_db("--allow-active", env={"FAKE_HOLDER_RC": "16", "FAKE_ACTIVE_CLAIMS": "3"})
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_dump_table_failure(self):
        r = self.dump_db(env={"FAKE_HOLDER_RC": "16", "FAKE_FAIL_TOOL": "proutil", "FAKE_FAIL_MATCH": "dump Customer"})
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("FAILED at step 3 (Dump tables)", r.stdout)

    # ------------------------------------------------------------------ load
    def test_load_success(self):
        self.make_dump()
        r = self.load_db("--bi-block-size", "8", "--bi-cluster-size", "32")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for n, name in enumerate(LOAD_STEPS, 1):
            self.assertIn(f"[{n}/8] {name} ... ok", r.stdout)
        self.assertIn("FINISH OK", r.stdout)
        c = self.calls()
        self.assertEqual(c[0], "prostrct create parkbench parkbench.st -blocksize 8192")
        self.assertTrue(c[1].startswith("procopy ") and c[1].endswith("prolang/utf/empty8 parkbench"), c[1])
        self.assertEqual(c[2], "proutil parkbench -C truncate bi -bi 32768 -biblocksize 8")
        self.assertIn("load_df.p", c[3])
        self.assertIn("schema.df|", c[3])
        loads = [x for x in c if " -C load " in x]
        self.assertEqual(len(loads), 3)
        self.assertTrue(all(x.endswith(".bd -cpinternal UTF-8") for x in loads), loads)
        self.assertTrue(any("-C idxbuild all" in x for x in c))
        self.assertIn("finish|", c[-1])
        self.assertTrue((self.target / "parkbench.st").exists())
        log = (self.target / "parkbench_load.log").read_text()
        for t in TABLES:
            self.assertIn(f"COUNT {t}: ok (7)", log)

    def test_load_refuses_existing_database(self):
        self.make_dump()
        self.target.mkdir()
        (self.target / "parkbench.db").write_text("precious")
        r = self.load_db()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("never overwritten", r.stdout)
        self.assertEqual(self.calls(), [])
        self.assertEqual((self.target / "parkbench.db").read_text(), "precious")
        self.assertEqual(sorted(p.name for p in self.target.iterdir()), ["parkbench.db"])

    def test_load_refuses_incomplete_dump(self):
        self.make_dump()
        (self.dump / "Customer.bd").unlink()
        r = self.load_db()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("Customer.bd is missing", r.stdout)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.target.exists())

    def test_load_refuses_bad_options(self):
        self.make_dump()
        for extra, text in ((["--bi-block-size", "3"], "1, 2, 4, 8, 16"), (["--bi-cluster-size", "256"], "1-255")):
            r = self.load_db(*extra)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertIn(text, r.stdout)
        self.assertEqual(self.calls(), [])

    def test_load_count_mismatch(self):
        self.make_dump()
        r = self.load_db(env={"FAKE_LOAD_SHORT": "Customer"})
        self.assertEqual(r.returncode, 4, r.stdout)
        self.assertIn("FAILED at step 6 (Load data)", r.stdout)
        self.assertIn("COUNT Customer: FAIL (loaded 6, dumped 7)", r.stdout)

    def test_load_idxbuild_errors(self):
        self.make_dump()
        r = self.load_db(env={"FAKE_IDXBUILD_ERRORS": "2"})
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("FAILED at step 7 (Rebuild indexes)", r.stdout)

    def test_load_finish_failure(self):
        self.make_dump()
        r = self.load_db(env={"FAKE_FINISH_STATUS": "FAILED: 1 check(s)"})
        self.assertEqual(r.returncode, 4, r.stdout)
        self.assertIn("FAILED at step 8 (Restore sequences and verify)", r.stdout)


class BashDumpLoadTests(DumpLoadMixin, unittest.TestCase):
    def run_script(self, script, args, env=None):
        e = {k: v for k, v in os.environ.items() if not k.startswith("FAKE_") and k != "DLC"}
        e.update(DLC=str(FAKE_DLC), FAKE_DLC_LOG=str(self.log), **(env or {}))
        return subprocess.run(["bash", str(ROOT / "db" / f"{script}.sh"), *map(str, args)],
                              capture_output=True, text=True, env=e, cwd=self.tmp)

    def test_bash_syntax(self):
        for s in ("dump_db", "load_db"):
            r = subprocess.run(["bash", "-n", str(ROOT / "db" / f"{s}.sh")], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


@unittest.skipUnless(CMD, "cmd.exe is not reachable; Windows batch tests skipped")
class BatchDumpLoadTests(DumpLoadMixin, unittest.TestCase):
    def run_script(self, script, args, env=None):
        e = {k: v for k, v in os.environ.items() if not k.startswith("FAKE_") and k != "DLC"}
        e.update(DLC=str(FAKE_DLC), FAKE_DLC_LOG=str(self.log))
        passed = ["DLC/p", "FAKE_DLC_LOG/p"]
        for k, v in (env or {}).items():
            e[k] = v
            passed.append(k)
        e["WSLENV"] = ":".join(passed)

        def win(a):
            if isinstance(a, Path):
                return winpath(a) if a.exists() else winpath(a.parent) + "\\" + a.name
            return a
        cmd = [CMD, "/d", "/c", winpath(ROOT / "db" / f"{script}.bat"), *map(win, args)]
        r = subprocess.run(cmd, capture_output=True, env=e, cwd=self.tmp)
        return subprocess.CompletedProcess(cmd, r.returncode, r.stdout.decode("utf-8", "replace").replace("\r\n", "\n"),
                                           r.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
