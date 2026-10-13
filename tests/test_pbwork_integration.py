"""Opt-in OpenEdge read integration gate for the workload agent."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from pbwork.agent import AgentClient
from pbwork.catalog import load_catalog
from pbwork.config import ConnectionConfig

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("PARKBENCH_OE_TESTS") == "1", "OpenEdge test opt-in")
class RealReadWorkloads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = os.environ.get("PARKBENCH_OE_DB")
        if not cls.database:
            raise AssertionError("PARKBENCH_OE_DB must name a served, populated test database")
        cls.operations = int(os.environ.get("PARKBENCH_OE_OPERATIONS", "1000"))
        if cls.operations < 1:
            raise AssertionError("PARKBENCH_OE_OPERATIONS must be positive")
        cls.wrapper = ROOT / "db" / ("pbwork.bat" if os.name == "nt" else "pbwork.sh")
        cls.generator = ROOT / "db" / ("pbgen.bat" if os.name == "nt" else "pbgen.sh")

    def test_all_read_families_and_source_check(self):
        with tempfile.TemporaryDirectory(prefix="pbwork-read-integration-") as directory:
            for profile in load_catalog():
                if profile.kind != "read":
                    continue
                with self.subTest(profile=profile.id):
                    path = Path(directory) / f"{profile.id}.json"
                    result = subprocess.run([str(self.wrapper), "run", "--db", self.database,
                                             "--profile", profile.id, "--operations", str(self.operations), "--workers", "2",
                                             "--seed", "20260929", "--spool", str(Path(directory) / "spool"),
                                             "--result", str(path), "--json"],
                                            cwd=ROOT, capture_output=True, text=True, timeout=3600)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    data = json.loads(path.read_text(encoding="utf-8"))
                    self.assertGreaterEqual(data["metrics"]["completed"], int(self.operations * 0.99))
                    self.assertEqual(data["metrics"]["rows_written"], 0)
                    self.assertEqual(data["metrics"]["committed"], 0)
            check = subprocess.run([str(self.generator), "check", "--db", self.database],
                                   cwd=ROOT, capture_output=True, text=True, timeout=3600)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_valid_empty_selective_result_is_not_an_error(self):
        with tempfile.TemporaryDirectory(prefix="pbwork-empty-selective-") as directory:
            with AgentClient(ConnectionConfig(self.database), Path(directory) / "agent") as agent:
                agent.hello()
                descriptors = [{"ordinal": index, "operation_id": "currency-empty-selective",
                                "handler": "indexed_selective", "table": "Currency", "field": "RandomInt1000",
                                "predicate_value": index, "limit": 100}
                               for index in range(1, 1001)]
                observed = []
                for start in range(0, len(descriptors), 256):
                    observed.extend(agent.batch(descriptors[start:start + 256])["operations"])
                self.assertTrue(any(item["rows_read"] == 0 and item["status"] == "read"
                                    and item["rows_written"] == 0 for item in observed))
