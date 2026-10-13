"""Opt-in end-to-end tests of pbgen against a real OpenEdge 12.8 install (spec 003 T027-T046).

Everything runs on the Windows side through cmd.exe: db\\build_db.bat, db\\server.bat, db\\pbgen.bat, with
PBGEN_PYTHON pointing at <repo>\\.venv-win (Faker installed). Databases live under .tmp/pbit/.

Enable with:  PARKBENCH_OE_TESTS=1 .venv/bin/python -m unittest tests.test_pbgen_integration -v
The OpenEdge install is taken from PARKBENCH_OE_DLC (a Windows path) or from DLC in the Windows environment.
A full pass builds five SF 0.01-0.03 databases and takes roughly an hour on a desktop.
"""

import json
import os
import shutil
import subprocess
import time
import unittest
from pathlib import Path

from helpers import ROOT
from test_openedge_integration import CMD, DLC, to_win, to_wsl

WORK = ROOT / ".tmp" / "pbit"
VENV_PY = ROOT / ".venv-win" / "Scripts" / "python.exe"
SAMPLE_TABLES = ("Customer", "Account", "DebitTransaction")
SEED = "7"
PORTS = {"it1": 29301, "it4": 29304, "itk": 29305, "it3": 29303}
TIMEOUT = 4 * 3600

# check name expected to fail for each pbgen_corrupt.p case
CORRUPTIONS = {
    "gap": "Customer.density",
    "fk": "Account.fk.BranchId",
    "randomint": "DebitTransaction.RandomInt100",
    "stmttotal": "AccountStatement.derived.statementTotals",
    "bti": "Card.BenchmarkTableInfo",
    "duplicate": "Payee.BenchmarkTableInfo",
}


def _env() -> dict:
    return dict(os.environ, DLC=DLC, PBGEN_PYTHON=to_win(VENV_PY), WSLENV="DLC:PBGEN_PYTHON")


def win(*args, timeout=TIMEOUT) -> subprocess.CompletedProcess:
    r = subprocess.run([CMD, "/d", "/c", *args], capture_output=True, env=_env(), cwd=ROOT, timeout=timeout)
    r.out = r.stdout.decode("utf-8", "replace").replace("\r\n", "\n") + r.stderr.decode("utf-8", "replace")
    return r


def db_win(name: str) -> str:
    return to_win(WORK / name) + "\\parkbench"


def pbgen(name: str, *args, timeout=TIMEOUT) -> subprocess.CompletedProcess:
    return win("db\\pbgen.bat", args[0], "--db", db_win(name), *args[1:], timeout=timeout)


def progres(name: str, program: str, param: str) -> str:
    """Runs a one-shot ABL program with _progres.exe directly (no cmd.exe, so '|' in -param is safe)."""
    exe = to_wsl(DLC) / "bin" / "_progres.exe"
    r = subprocess.run([str(exe), "-b", "-db", db_win(name), "-cpinternal", "UTF-8", "-cpstream", "UTF-8",
                        "-p", to_win(ROOT / "db" / "abl" / program), "-param", param],
                       capture_output=True, env=_env(), cwd=WORK / name, timeout=TIMEOUT)
    return r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")


def counts(name: str) -> tuple[dict, dict]:
    out_dir = WORK / name / "counts"
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir()
    log = progres(name, "pbgen_counts.p", f"{to_win(out_dir)}|{','.join(SAMPLE_TABLES)}")
    if not (out_dir / "counts.json").exists():
        raise AssertionError(f"pbgen_counts.p produced nothing:\n{log}")
    c = json.loads((out_dir / "counts.json").read_text(encoding="utf-8-sig"))
    samples = {}
    for t in SAMPLE_TABLES:
        data = json.loads((out_dir / f"sample-{t}.json").read_text(encoding="utf-8-sig"))
        samples[t] = next(iter(data.values()), []) if isinstance(data, dict) else data
    return c, samples


def status(name: str) -> dict:
    r = pbgen(name, "status", "--json")
    return json.loads(r.out[r.out.index("{"):r.out.rindex("}") + 1])


def plan_summary(st: dict, run_id: int) -> dict:
    run = next(r for r in st["runs"] if int(r["LoaderRunId"]) == run_id)
    s = run["PlanSummary"]
    return json.loads(s) if isinstance(s, str) else s


def kill_launcher(name: str) -> int:
    """taskkill /F /T every pbgen launcher for this database, with its workers and agents."""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          f"Where-Object {{ $_.CommandLine -like '*pbgen*run*{WORK.name}*{name}*' }} | "
          "ForEach-Object { $_.ProcessId }")
    pids = win("powershell", "-NoProfile", "-Command", ps).out.split()
    for pid in pids:
        win("taskkill", "/F", "/T", "/PID", pid)
    return len(pids)


def ensure_served(name: str) -> bool:
    """Restarts the server if a hard kill brought it down; returns True if it had to.

    A self-service client killed inside a microtransaction makes OpenEdge shut the database down
    ((2256) "died during microtransaction", then ABNORMAL shutdown). The next start runs crash recovery."""
    log = (WORK / name / "parkbench.lg").read_text(encoding="utf-8", errors="replace")
    if log.rfind("Begin ABNORMAL shutdown") < log.rfind("(10471)"):
        return False
    deadline = time.monotonic() + 180
    while win("db\\server.bat", "status", db_win(name)).returncode != 3:
        if time.monotonic() > deadline:
            raise AssertionError(f"{name}: the server did not finish its abnormal shutdown")
        time.sleep(5)
    r = win("db\\server.bat", "start", db_win(name), "--port", str(PORTS[name]), "--workers", "4")
    assert r.returncode == 0, r.out
    return True


def fresh_db(name: str) -> None:
    """Builds, starts and initialises .tmp/pbit/<name> (removing an earlier copy)."""
    if (WORK / name / "parkbench.db").exists():
        win("db\\server.bat", "stop", db_win(name))
    shutil.rmtree(WORK / name, ignore_errors=True)
    r = win("db\\build_db.bat", to_win(WORK) + "\\" + name)
    assert r.returncode == 0, r.out
    r = win("db\\server.bat", "start", db_win(name), "--port", str(PORTS[name]), "--workers", "4")
    assert r.returncode == 0, r.out
    r = pbgen(name, "init")
    assert r.returncode == 0, r.out


def populate(name: str, workers: int, scale: str = "0.01") -> float:
    fresh_db(name)
    r = pbgen(name, "plan", "--scale", scale, "--seed", SEED)
    assert r.returncode == 0, r.out
    t0 = time.monotonic()
    r = pbgen(name, "run", "--workers", str(workers))
    assert r.returncode == 0, r.out
    return time.monotonic() - t0


def total_rows(c: dict) -> int:
    return sum(v["count"] for v in c["tables"].values())


VENV_OK = VENV_PY.exists()


@unittest.skipUnless(DLC and VENV_OK and (to_wsl(DLC) / "bin" / "_progres.exe").exists(),
                     "set PARKBENCH_OE_TESTS=1 with a real OpenEdge 12.8 DLC and a .venv-win to run")
class RealOE(unittest.TestCase):
    """Tests run in name order; later ones reuse the databases the earlier ones built."""

    started: list[str] = []

    @classmethod
    def setUpClass(cls):
        WORK.mkdir(parents=True, exist_ok=True)
        cls.started.append("it1")
        cls.t1 = populate("it1", workers=1)
        cls.c1, cls.s1 = counts("it1")
        print(f"\n[it1] SF 0.01, 1 worker: {total_rows(cls.c1):,} rows in {cls.t1:.0f} s "
              f"({total_rows(cls.c1) / cls.t1:,.0f} rows/s)", flush=True)

    @classmethod
    def tearDownClass(cls):
        for name in cls.started:
            win("db\\server.bat", "stop", db_win(name))

    # ------------------------------------------------------------------ US1
    def test_us1_populate(self):
        st = status("it1")
        self.assertEqual(st["runs"][0]["RunStatus"], "COMPLETE")
        planned = plan_summary(st, 1)["tables"]
        for t, v in self.c1["tables"].items():
            self.assertEqual(v["count"], planned[t]["rows"], t)
            self.assertEqual(v["count"], v["maxId"], f"{t} is not dense")
            self.assertEqual(self.c1["bti"][t], {"MaxId": v["maxId"], "TableRowCount": v["count"]}, t)
            self.assertEqual(self.c1["sequences"][f"Seq{t}Id"], v["maxId"], t)

    # ------------------------------------------------------------------ US2
    def test_us2_parallel(self):
        self.started.append("it4")
        t4 = populate("it4", workers=4)
        c4, s4 = counts("it4")
        self.assertEqual(c4["tables"], self.c1["tables"])
        self.assertEqual(s4, self.s1)
        print(f"\n[it4] SF 0.01, 4 workers: {t4:.0f} s ({total_rows(c4) / t4:,.0f} rows/s); "
              f"speed-up over 1 worker x{self.t1 / t4:.2f}", flush=True)

    # ------------------------------------------------------------------ US3
    def test_us3_kill_resume(self):
        self.started.append("itk")
        fresh_db("itk")
        r = pbgen("itk", "plan", "--scale", "0.01", "--seed", SEED)
        self.assertEqual(r.returncode, 0, r.out)
        for attempt in range(2):
            p = subprocess.Popen([CMD, "/d", "/c", "db\\pbgen.bat", "run", "--db", db_win("itk"), "--workers", "4"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_env(), cwd=ROOT)
            time.sleep(20)
            self.assertGreater(kill_launcher("itk"), 0, "no launcher process found to kill")
            p.wait(timeout=120)
            time.sleep(15)                      # give the broker time to clean up (or begin shutting down)
            restarted = ensure_served("itk")
            st = status("itk")
            self.assertNotEqual(st["runs"][0]["RunStatus"], "COMPLETE")
            c, _ = counts("itk")
            for b in st["bti"]:
                t = b["TableName"]
                self.assertLessEqual(b["MaxId"], c["tables"][t]["maxId"], f"attempt {attempt}: {t}")
            print(f"\n[itk] killed after 20 s: {st['done']} of {st['runs'][0]['UnitCount']} units done"
                  f"{'; server restarted after an abnormal shutdown' if restarted else ''}", flush=True)
        r = pbgen("itk", "run", "--workers", "4")
        self.assertEqual(r.returncode, 0, r.out)
        ck, sk = counts("itk")
        self.assertEqual(ck["tables"], self.c1["tables"])
        self.assertEqual(ck["bti"], self.c1["bti"])
        self.assertEqual(sk, self.s1)

    # ------------------------------------------------------------------ US4
    def test_us4_grow(self):
        r = pbgen("it1", "grow", "--add-scale", "0.02")
        self.assertEqual(r.returncode, 0, r.out)
        r = pbgen("it1", "run", "--workers", "4")
        self.assertEqual(r.returncode, 0, r.out)
        cg, sg = counts("it1")
        for t in SAMPLE_TABLES:
            old_max = self.c1["tables"][t]["maxId"]
            self.assertEqual([x for x in sg[t] if x[f"{t}Id"] <= old_max], self.s1[t], f"{t} rows changed")
        self.started.append("it3")
        populate("it3", workers=4, scale="0.03")
        c3, _ = counts("it3")
        for t, v in c3["tables"].items():
            got = cg["tables"][t]["count"]
            self.assertLessEqual(abs(got - v["count"]), max(2, 0.01 * v["count"]), f"{t}: grown {got} vs direct {v['count']}")
            self.assertEqual(cg["tables"][t]["count"], cg["tables"][t]["maxId"], f"{t} is not dense")
        r = pbgen("it1", "check")
        self.assertEqual(r.returncode, 0, r.out)

    # ------------------------------------------------------------------ US5
    def test_us5_check_and_corruption(self):
        name = "it4" if "it4" in self.started else "it1"
        t0 = time.monotonic()
        r = pbgen(name, "check")
        self.assertEqual(r.returncode, 0, r.out)
        self.assertIn("CHECK OK", r.out)
        print(f"\n[{name}] check: {time.monotonic() - t0:.0f} s", flush=True)
        save = WORK / name / "corrupt-save.json"
        for case, check_name in CORRUPTIONS.items():
            with self.subTest(case=case):
                log = progres(name, "pbgen_corrupt.p", f"apply|{case}|{to_win(save)}")
                self.assertIn("CORRUPT OK", log)
                try:
                    r = pbgen(name, "check")
                    self.assertEqual(r.returncode, 1, r.out)
                    self.assertIn(f"CHECK {check_name}: FAIL", r.out)
                finally:
                    log = progres(name, "pbgen_corrupt.p", f"restore|{case}|{to_win(save)}")
                    self.assertIn("CORRUPT OK", log)
        r = pbgen(name, "check")
        self.assertEqual(r.returncode, 0, r.out)


if __name__ == "__main__":
    unittest.main()
