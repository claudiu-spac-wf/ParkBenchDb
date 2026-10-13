"""Parallel and stop/resume tests against the FakeAgent (T029, T033)."""

import json
import os
import random
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from helpers import ROOT, fake_with_plan

from pbgen import launcher
from pbgen.fakeagent import FakeAgent
from pbgen.generate.common import _parse_map
from pbgen.worker import Worker

PY = sys.executable


def run_threads(path, schema, n_workers, stagger=0.0):
    stop = threading.Event()
    stats, threads = [], []

    def go(k):
        w = Worker(FakeAgent(path), k, Path(path).parent / f"w{k}", schema, stop=stop, log=lambda *a: None)
        stats.append(w.run())

    for k in range(1, n_workers + 1):
        t = threading.Thread(target=go, args=(k,))
        t.start()
        threads.append(t)
        if stagger:
            time.sleep(stagger)
    for t in threads:
        t.join()
    return stats


def units_state(path):
    import sqlite3
    db = sqlite3.connect(path)
    try:
        return db.execute("SELECT unitno, status, attempts FROM unit ORDER BY unitno").fetchall()
    finally:
        db.close()


class ParallelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make(self, name, units=8):
        d = self.tmp / name
        d.mkdir()
        agent, schema, run, plan_units = fake_with_plan(d, customer_units=units)
        return agent, schema, run, plan_units

    def test_parallel_claims_each_unit_once_and_matches_one_worker(self):
        a1, schema, run, units = self.make("one")
        a4, *_ = self.make("four")
        run_threads(a1.path, schema, 1)
        stats = run_threads(a4.path, schema, 4)
        self.assertEqual(sum(s.units for s in stats), len(units))
        self.assertTrue(all(st == "D" and att == 1 for _, st, att in units_state(a4.path)))
        self.assertEqual(a1.table_digest(), a4.table_digest())
        self.assertEqual(a4.request("state")["runs"][0]["RunStatus"], "COMPLETE")

    def test_adding_workers_mid_run(self):
        agent, schema, run, units = self.make("add")
        stats = run_threads(agent.path, schema, 4, stagger=0.7)
        self.assertEqual(sum(s.units for s in stats), len(units))
        self.assertTrue(all(att == 1 for _, _, att in units_state(agent.path)))

    def test_lock_table_refusal(self):
        agent, *_ = self.make("lock")

        class SmallL(FakeAgent):
            def _op_hello(self, db):
                return dict(super()._op_hello(db), L=50_000)
        with self.assertRaises(launcher.LaunchError) as cm:
            launcher.preflight(SmallL(agent.path), 4, False, {"kind": "fake"})
        self.assertIn("--workers 4", str(cm.exception))


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stale_claim_is_reclaimed_and_old_worker_loses(self):
        agent, schema, run, units = fake_with_plan(self.tmp, customer_units=2)
        now = [1000.0]
        a = FakeAgent(agent.path, clock=lambda: now[0])
        u1 = a.request("claim", worker="h:1:1:0")["unit"]          # the only phase-0 unit (REFERENCE)
        self.assertEqual(u1["UnitKind"], "REFERENCE")
        # a fresh claim is protected: the phase is blocked for everyone else
        self.assertEqual(a.request("claim", worker="h:1:9:0")["reason"], "phase-blocked")
        now[0] += 200
        a.request("heartbeat", run=1, unitNo=u1["UnitNo"], worker="h:1:1:0")
        now[0] += 200                                                 # 200 s since the heartbeat: still fresh
        self.assertEqual(a.request("claim", worker="h:1:9:0")["reason"], "phase-blocked")
        now[0] += 150                                                 # 350 s since the heartbeat: stale
        reclaimed = a.request("claim", worker="h:1:9:0")["unit"]
        self.assertEqual(reclaimed["UnitNo"], u1["UnitNo"])
        self.assertEqual(reclaimed["Attempts"], 2)
        f = self.tmp / "u.json"
        f.write_text("{}")
        with self.assertRaises(Exception) as cm:
            a.request("load", run=1, unitNo=u1["UnitNo"], worker="h:1:1:0", file=str(f))
        self.assertIn("lost", str(cm.exception))

    def test_watermark_never_passes_an_unfinished_unit(self):
        agent, schema, run, units = fake_with_plan(self.tmp, customer_units=6)
        from pbgen.generate import generate_unit
        from pbgen.unitjson import write_unit
        from pbgen.worker import context_for_run
        ctx = context_for_run(schema, run)
        claimed = []
        while True:
            r = agent.request("claim", worker="h:1:1:0")
            if not r["unit"]:
                if r["reason"] == "phase-blocked":
                    # load what we hold so the next phase opens, in random order
                    pass
                else:
                    break
            else:
                claimed.append(r["unit"])
                continue
            random.Random(3).shuffle(claimed)
            for u in claimed:
                p = self.tmp / f"u{u['UnitNo']}.json"
                write_unit(p, generate_unit(u, ctx))
                agent.request("load", run=1, unitNo=u["UnitNo"], worker="h:1:1:0", file=str(p))
                agent.request("watermark", run=1)
                done = {x[0] for x in units_state(agent.path) if x[1] == "D"}
                prefix = 0
                while prefix + 1 in done:
                    prefix += 1
                limit = {}
                for pu in units[:prefix]:
                    first, cnt = _parse_map(pu["FirstIds"]), _parse_map(pu["RowCounts"])
                    for t, c in cnt.items():
                        limit[t] = max(limit.get(t, 0), first[t] + c - 1)
                for b in agent.request("state")["bti"]:
                    self.assertEqual(b["MaxId"], limit.get(b["TableName"], 0), b["TableName"])
            claimed = []
        self.assertEqual(agent.request("watermark", run=1)["complete"], True)

    def test_dead_local_worker_claims_are_released(self):
        agent, *_ = fake_with_plan(self.tmp, customer_units=2)
        dead = f"{socket.gethostname()}:999999999:1:0"
        agent.request("claim", worker=dead)
        pre = launcher.preflight(agent, 1, False, {"kind": "fake"})
        self.assertEqual(pre["released"], 1)
        self.assertEqual(agent.request("status")["claimed"], 0)


def _launch(fake, workers=3):
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, (str(ROOT), os.environ.get("PYTHONPATH")))))
    return subprocess.Popen([PY, "-u", "-m", "pbgen", "run", "--fake", str(fake), "--workers", str(workers)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
                            start_new_session=True)


@unittest.skipIf(os.name == "nt", "process-group kill test uses POSIX signals")
class KillResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_forced_kills_then_resume_gives_identical_data(self):
        ref_dir, kill_dir = self.tmp / "ref", self.tmp / "kill"
        ref_dir.mkdir()
        kill_dir.mkdir()
        ref, schema, *_ = fake_with_plan(ref_dir, customer_units=10)
        victim, *_ = fake_with_plan(kill_dir, customer_units=10)
        run_threads(ref.path, schema, 2)
        rng = random.Random(11)
        for _ in range(2):
            p = _launch(victim.path)
            time.sleep(rng.uniform(4, 7))
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
        # the killed workers' claims belong to dead local PIDs and are released by the next run
        p = _launch(victim.path)
        out, _ = p.communicate(timeout=600)
        self.assertEqual(p.returncode, 0, out)
        self.assertIn("COMPLETE", out)
        self.assertEqual(ref.table_digest(), victim.table_digest())

    def test_graceful_interrupt_exits_130_and_leaves_no_partial_units(self):
        agent, schema, run, units = fake_with_plan(self.tmp, customer_units=60)
        p = _launch(agent.path)
        seen = []
        for line in p.stdout:                      # wait until the workers are running
            seen.append(line)
            if line.startswith("Run 1"):
                break
        time.sleep(4)
        os.killpg(p.pid, signal.SIGINT)
        rest, _ = p.communicate(timeout=300)
        out = "".join(seen) + rest
        self.assertEqual(p.returncode, 130, out)
        done = {u for u, st, _ in units_state(agent.path) if st == "D"}
        expected = {}
        for u in units:
            if u["UnitNo"] in done:
                for t, c in _parse_map(u["RowCounts"]).items():
                    expected[t] = expected.get(t, 0) + c
        got = {t: len(agent.all_rows(t)) for t in expected}
        self.assertEqual(got, expected)
        status = agent.request("status")
        self.assertEqual(status["done"], len(done))


if __name__ == "__main__":
    unittest.main()
