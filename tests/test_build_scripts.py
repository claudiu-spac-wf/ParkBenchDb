"""Tests for db/build_db.sh and db/build_db.bat against a stub OpenEdge install (T018)."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

FAKE_DLC = ROOT / "tests" / "fixtures" / "fake_dlc"
SCRIPT_SH = ROOT / "db" / "build_db.sh"
SCRIPT_BAT = ROOT / "db" / "build_db.bat"
STEP_NAMES = ["Check prerequisites", "Create structure", "Copy UTF-8 metaschema", "Configure before-image",
              "Confirm large files", "Load schema", "Verify database"]
CMD = next((c for c in (shutil.which("cmd.exe"), "/mnt/c/Windows/System32/cmd.exe") if c and Path(c).exists()), None)
# Temp dirs live under the repo so that cmd.exe can reach them through a drive letter.
TMP_ROOT = ROOT / ".tmp"


def winpath(p: Path) -> str:
    return subprocess.run(["wslpath", "-w", str(p)], capture_output=True, text=True, check=True).stdout.strip()


class BuildScriptMixin:
    """Scenarios shared by the bash and batch variants. Subclasses implement run()."""

    def setUp(self):
        TMP_ROOT.mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(dir=TMP_ROOT))
        self.log = self.tmp / "calls.log"
        self.target = self.tmp / "target"
        self.dlc = FAKE_DLC

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def calls(self) -> list[str]:
        if not self.log.exists():
            return []
        # batch passes quoted paths; normalise quotes and doubled spaces so both variants compare equal
        return [" ".join(x.replace('"', "").split()) for x in
                self.log.read_text(encoding="utf-8", errors="replace").splitlines()]

    # (a)
    def test_success(self):
        r = self.run_build(self.target)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for n, name in enumerate(STEP_NAMES, 1):
            self.assertIn(f"[{n}/7] {name} ... ok", r.stdout)
        c = self.calls()
        self.assertEqual([x.split(" ", 1)[0] for x in c],
                         ["prostrct", "procopy", "proutil", "proutil", "_progres", "_progres"])
        self.assertEqual(c[0], "prostrct create parkbench parkbench.st -blocksize 8192")
        self.assertTrue(c[1].startswith("procopy ") and c[1].replace("\\", "/").endswith("prolang/utf/empty8 parkbench"), c[1])
        self.assertEqual(c[2], "proutil parkbench -C truncate bi -bi 16384 -biblocksize 16")
        self.assertEqual(c[3], "proutil parkbench -C describe")
        for line, prog in ((c[4], "load_df.p"), (c[5], "verify_db.p")):
            self.assertIn("_progres -b -1 -db parkbench -cpinternal UTF-8 -cpstream UTF-8 -p ", line)
            self.assertIn(prog, line)
        self.assertIn("parkbench.df|", c[4])
        self.assertIn("parkbench.expect|", c[5])
        self.assertTrue((self.target / "parkbench.st").exists())
        self.assertTrue((self.target / "parkbench_build.log").exists())
        self.assertIn("VERIFY OK", r.stdout)

    # (b)
    def test_existing_database_refused(self):
        self.target.mkdir()
        (self.target / "parkbench.db").write_text("")
        r = self.run_build(self.target)
        self.assertEqual(r.returncode, 2)
        self.assertIn("already exists", r.stdout)
        self.assertEqual(self.calls(), [])

    # (c)
    def test_missing_dlc(self):
        r = self.run_build(self.target, dlc=None)
        self.assertEqual(r.returncode, 2)
        self.assertIn("DLC", r.stdout)
        self.assertFalse(self.target.exists())

    def test_wrong_version(self):
        dlc = self.tmp / "dlc117"
        shutil.copytree(FAKE_DLC, dlc)
        (dlc / "version").write_text("OpenEdge Release 11.7.4 as of Mon Jan 1 2019\n")
        r = self.run_build(self.target, dlc=dlc)
        self.assertEqual(r.returncode, 2)
        self.assertIn("12.8", r.stdout)
        self.assertEqual(self.calls(), [])

    def test_missing_utf8_empty_database(self):
        dlc = self.tmp / "dlcnoutf"
        shutil.copytree(FAKE_DLC, dlc)
        (dlc / "prolang" / "utf" / "empty8.db").unlink()
        r = self.run_build(self.target, dlc=dlc)
        self.assertEqual(r.returncode, 2)
        self.assertIn("empty8", r.stdout)

    # (d)
    def test_load_failure_stops_and_keeps_target(self):
        r = self.run_build(self.target, env={"FAKE_LOAD_STATUS": "FAILED: x"})
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("FAILED at step 6 (Load schema)", r.stdout)
        self.assertTrue(self.target.exists())
        self.assertTrue((self.target / "parkbench.db").exists())
        self.assertEqual(len([c for c in self.calls() if c.startswith("_progres")]), 1)

    def test_tool_failure_stops(self):
        r = self.run_build(self.target, env={"FAKE_FAIL_TOOL": "proutil", "FAKE_FAIL_MATCH": "describe"})
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("FAILED at step 5 (Confirm large files)", r.stdout)

    def test_large_files_not_active_stops(self):
        r = self.run_build(self.target, env={"FAKE_NO_LARGE_FILES": "1"})
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("FAILED at step 5 (Confirm large files)", r.stdout)

    # (e)
    def test_verify_failure(self):
        r = self.run_build(self.target, env={"FAKE_VERIFY_STATUS": "FAILED: x"})
        self.assertEqual(r.returncode, 4, r.stdout)
        self.assertIn("[6/7] Load schema ... ok", r.stdout)
        self.assertIn("VERIFY FAILED", r.stdout)
        self.assertIn("FAILED at step 7 (Verify database)", r.stdout)

    # (f)
    def test_target_with_spaces(self):
        target = self.tmp / "pb target dir"
        r = self.run_build(target)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((target / "parkbench.db").exists())

    # (g)
    def test_custom_db_name(self):
        r = self.run_build(self.target, db="pbtest")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        c = self.calls()
        self.assertEqual(c[0], "prostrct create pbtest pbtest.st -blocksize 8192")
        self.assertTrue(all(" pbtest" in x for x in c), c)
        self.assertTrue((self.target / "pbtest.st").exists())

    # US6: before-image options
    def test_bi_options(self):
        r = self.run_build(self.target, extra=["--bi-block-size", "8", "--bi-cluster-size", "32"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        c = self.calls()
        self.assertEqual(c[2], "proutil parkbench -C truncate bi -bi 32768 -biblocksize 8")
        self.assertIn("parkbench.expect|", c[5])
        self.assertTrue(c[5].rstrip().endswith("biblocksize=8192;biclustersize=33554432"), c[5])

    def test_bi_options_before_positionals(self):
        r = self.run_build(self.target, extra=["--bi-cluster-size", "64"], options_first=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls()[2], "proutil parkbench -C truncate bi -bi 65536 -biblocksize 16")

    def test_invalid_bi_values(self):
        for extra, allowed in ((["--bi-block-size", "3"], "1, 2, 4, 8, 16"), (["--bi-cluster-size", "0"], "1-255"),
                               (["--bi-cluster-size", "256"], "1-255"), (["--bi-block-size", "x"], "1, 2, 4, 8, 16")):
            r = self.run_build(self.target, extra=extra)
            self.assertEqual(r.returncode, 2, (extra, r.stdout))
            self.assertIn(allowed, r.stdout)
            self.assertEqual(self.calls(), [])

    def test_defaults_unchanged(self):
        r = self.run_build(self.target)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.calls()[2], "proutil parkbench -C truncate bi -bi 16384 -biblocksize 16")
        self.assertTrue(self.calls()[5].rstrip().endswith("biblocksize=16384;biclustersize=16777216"))

    def test_invalid_db_name(self):
        r = self.run_build(self.target, db="9bad")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.calls(), [])


class BashBuildTests(BuildScriptMixin, unittest.TestCase):
    def run_build(self, target: Path, db: str | None = None, dlc: Path | None = FAKE_DLC, env: dict | None = None,
                  extra: list | None = None, options_first: bool = False):
        e = {k: val for k, val in os.environ.items() if not k.startswith("FAKE_") and k != "DLC"}
        e["FAKE_DLC_LOG"] = str(self.log)
        if dlc is not None:
            e["DLC"] = str(dlc)
        e.update(env or {})
        pos = [str(target)] + ([db] if db else [])
        args = ["bash", str(SCRIPT_SH)] + ((extra or []) + pos if options_first else pos + (extra or []))
        return subprocess.run(args, capture_output=True, text=True, env=e, cwd=self.tmp)

    def test_bash_syntax(self):
        r = subprocess.run(["bash", "-n", str(SCRIPT_SH)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_usage(self):
        r = subprocess.run(["bash", str(SCRIPT_SH)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stdout.lower())


@unittest.skipUnless(CMD, "cmd.exe is not reachable; Windows batch tests skipped")
class BatchBuildTests(BuildScriptMixin, unittest.TestCase):
    def run_build(self, target: Path, db: str | None = None, dlc: Path | None = FAKE_DLC, env: dict | None = None,
                  extra: list | None = None, options_first: bool = False):
        e = {k: val for k, val in os.environ.items() if not k.startswith("FAKE_") and k != "DLC"}
        passed = ["FAKE_DLC_LOG/p"]
        e["FAKE_DLC_LOG"] = str(self.log)
        if dlc is not None:
            e["DLC"] = str(dlc)
            passed.append("DLC/p")
        else:
            e["DLC"] = ""  # blank out any DLC set in the Windows environment
            passed.append("DLC")
        for k, val in (env or {}).items():
            e[k] = val
            passed.append(k)
        e["WSLENV"] = ":".join(passed)
        pos = [winpath(target) if target.exists() else winpath(target.parent) + "\\" + target.name] + ([db] if db else [])
        args = [CMD, "/d", "/c", winpath(SCRIPT_BAT)] + ((extra or []) + pos if options_first else pos + (extra or []))
        r = subprocess.run(args, capture_output=True, env=e, cwd=self.tmp)
        return subprocess.CompletedProcess(args, r.returncode, r.stdout.decode("utf-8", "replace").replace("\r\n", "\n"),
                                           r.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
