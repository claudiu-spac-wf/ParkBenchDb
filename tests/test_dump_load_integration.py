"""Opt-in real OpenEdge test of db/dump_db.bat and db/load_db.bat (spec 003 US7, T061).

Builds and populates its own source database .tmp/dl/src (SF 0.005, port 29320), dumps it, loads the dump
into .tmp/dl/dst (port 29321) and compares the two. The binary dump format is platform-independent, so a
Windows -> Windows round trip exercises the same files a Windows -> Linux move uses.
No other database is touched: every path is under .tmp/dl/ and the ports are test-only.

Enable with:  PARKBENCH_OE_TESTS=1 .venv/bin/python -m unittest tests.test_dump_load_integration -v
"""

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from helpers import ROOT
from test_openedge_integration import CMD, DLC, to_win, to_wsl

WORK = ROOT / ".tmp" / "dl"
VENV_PY = ROOT / ".venv-win" / "Scripts" / "python.exe"
PORTS = {"src": 29320, "dst": 29321}
SAMPLES = ("Customer", "Account", "DebitTransaction", "CustomerDocument")


def _env() -> dict:
    return dict(os.environ, DLC=DLC, PBGEN_PYTHON=to_win(VENV_PY), WSLENV="DLC:PBGEN_PYTHON")


def win(*args, timeout=3 * 3600):
    r = subprocess.run([CMD, "/d", "/c", *args], capture_output=True, env=_env(), cwd=ROOT, timeout=timeout)
    r.out = r.stdout.decode("utf-8", "replace").replace("\r\n", "\n") + r.stderr.decode("utf-8", "replace")
    return r


def db(name: str) -> str:
    return to_win(WORK / name) + "\\parkbench"


def pbgen(name: str, *args):
    return win("db\\pbgen.bat", args[0], "--db", db(name), *args[1:])


def progres(name: str, program: str, param: str) -> str:
    exe = to_wsl(DLC) / "bin" / "_progres.exe"
    r = subprocess.run([str(exe), "-b", "-db", db(name), "-cpinternal", "UTF-8", "-cpstream", "UTF-8",
                        "-p", to_win(ROOT / "db" / "abl" / program), "-param", param],
                       capture_output=True, env=_env(), cwd=WORK / name, timeout=3600)
    return r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")


def snapshot(name: str) -> dict:
    """Counts, sequences, BenchmarkTableInfo, sampled rows (LOBs included) and the loader state."""
    out = WORK / name / "snap"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    log = progres(name, "pbgen_counts.p", f"{to_win(out)}|{','.join(SAMPLES)}")
    assert (out / "counts.json").exists(), log
    snap = json.loads((out / "counts.json").read_text(encoding="utf-8-sig"))
    for t in SAMPLES:
        data = json.loads((out / f"sample-{t}.json").read_text(encoding="utf-8-sig"))
        snap[f"sample-{t}"] = next(iter(data.values()), [])
    r = pbgen(name, "status", "--json")
    st = json.loads(r.out[r.out.index("{"):r.out.rindex("}") + 1])
    snap["runs"] = st["runs"]
    snap["units"] = {k: st[k] for k in ("pending", "claimed", "done", "doneRows")}
    return snap


def serve(name: str, action: str = "start"):
    args = ["db\\server.bat", action, db(name)] + (["--port", str(PORTS[name]), "--workers", "2"] if action == "start" else [])
    return win(*args)


@unittest.skipUnless(DLC and VENV_PY.exists() and (to_wsl(DLC) / "bin" / "_progres.exe").exists(),
                     "set PARKBENCH_OE_TESTS=1 with a real OpenEdge 12.8 DLC and a .venv-win to run")
class RealDumpLoad(unittest.TestCase):
    """Tests run in name order and share the databases."""

    @classmethod
    def setUpClass(cls):
        for name in ("src", "dst"):
            if (WORK / name / "parkbench.db").exists():
                serve(name, "stop")
        shutil.rmtree(WORK, ignore_errors=True)
        WORK.mkdir(parents=True)
        r = win("db\\build_db.bat", to_win(WORK) + "\\src")
        assert r.returncode == 0, r.out
        assert serve("src").returncode == 0
        for args in (("init",), ("plan", "--scale", "0.005", "--seed", "7"), ("run", "--workers", "2")):
            r = pbgen("src", *args)
            assert r.returncode == 0, r.out

    @classmethod
    def tearDownClass(cls):
        for name in ("src", "dst"):
            if (WORK / name / "parkbench.db").exists():
                serve(name, "stop")

    def test_1_dump_online_and_load(self):
        r = win("db\\dump_db.bat", db("src"), to_win(WORK) + "\\dump")
        self.assertEqual(r.returncode, 0, r.out)
        self.assertIn("ok (served)", r.out)
        self.assertIn("Dumped 34 tables", r.out)
        r = win("db\\load_db.bat", to_win(WORK / "dump"), to_win(WORK) + "\\dst", "--bi-cluster-size", "32")
        self.assertEqual(r.returncode, 0, r.out)
        self.assertIn("FINISH OK", r.out)
        self.assertIn("(34 tables) and verified", r.out)
        self.assertEqual(serve("dst").returncode, 0)
        src, dst = snapshot("src"), snapshot("dst")
        for key in src:
            self.assertEqual(dst[key], src[key], key)
        self.assertEqual(dst["units"]["claimed"], 0)

    def test_2_check_passes_on_the_copy(self):
        r = pbgen("dst", "check")
        self.assertEqual(r.returncode, 0, r.out)
        self.assertIn("CHECK OK", r.out)

    def test_3_existing_target_is_never_overwritten(self):
        before = {p.name: p.stat().st_size for p in (WORK / "dst").glob("parkbench*.d*")}
        r = win("db\\load_db.bat", to_win(WORK / "dump"), to_win(WORK / "dst"))
        self.assertEqual(r.returncode, 2, r.out)
        self.assertIn("never overwritten", r.out)
        self.assertEqual({p.name: p.stat().st_size for p in (WORK / "dst").glob("parkbench*.d*")}, before)
        self.assertEqual(win("db\\server.bat", "status", db("dst")).returncode, 0)   # still served

    def test_4_active_workers_refused(self):
        save = to_win(WORK / "claim-save.json")
        self.assertIn("CORRUPT OK", progres("dst", "pbgen_corrupt.p", f"apply|claim|{save}"))
        try:
            r = win("db\\dump_db.bat", db("dst"), to_win(WORK) + "\\dump-active")
            self.assertEqual(r.returncode, 2, r.out)
            self.assertIn("1 pbgen unit(s) are claimed", r.out)
            self.assertFalse(any((WORK / "dump-active").glob("*.bd")))
        finally:
            self.assertIn("CORRUPT OK", progres("dst", "pbgen_corrupt.p", f"restore|claim|{save}"))

    def test_5_offline_dump_matches(self):
        serve("src", "stop")
        try:
            r = win("db\\dump_db.bat", db("src"), to_win(WORK) + "\\dump-offline")
            self.assertEqual(r.returncode, 0, r.out)
            self.assertIn("ok (offline)", r.out)
        finally:
            serve("src")

        def rows(d):
            return sorted(x for x in (WORK / d / "manifest.txt").read_text().splitlines()
                          if x.startswith(("rows=", "seq=", "table=")))
        self.assertEqual(rows("dump-offline"), rows("dump"))


if __name__ == "__main__":
    unittest.main()
