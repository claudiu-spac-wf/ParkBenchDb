"""Repeatable, hardware-independent comparison fixture for workload results."""

import json
import tempfile
import unittest
from pathlib import Path

from pbwork.catalog import find_profile, load_catalog
from pbwork.config import ConnectionConfig
from pbwork.runner import Runner
from tests.test_pbwork_cli import LocalFakeAgent


class ComparativeHarness(unittest.TestCase):
    def test_records_comparable_throughput_and_latency(self):
        profile = find_profile(load_catalog(), "read-reference-point")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            summaries = []
            for workers in (1, 4):
                result = Runner(ConnectionConfig("fake"), profile, agent_factory=LocalFakeAgent,
                                spool=path / f"spool-{workers}").execute(
                                    operations=100, duration=None, seed=20260929,
                                    workers=workers, mode="direct-read")
                metrics = result["metrics"]
                summaries.append({"profile_id": profile.id, "profile_version": profile.version,
                                  "workers": workers, "database_scale": "fake-100-ops",
                                  "operation_throughput": metrics["throughput_ops_per_second"],
                                  "row_throughput": metrics["throughput_rows_per_second"],
                                  "latency_ms": metrics["latency_ms"]})
            target = path / "comparison.json"
            target.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
            loaded = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual([row["workers"] for row in loaded], [1, 4])
            for row in loaded:
                self.assertGreaterEqual(row["operation_throughput"], 0)
                self.assertGreaterEqual(row["row_throughput"], 0)
                for key in ("median", "p95", "p99", "sample_count", "sample_limit"):
                    self.assertIn(key, row["latency_ms"])
