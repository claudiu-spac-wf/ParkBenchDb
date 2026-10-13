"""Result shape and metrics edge cases."""

import unittest
import json

from pbwork.catalog import find_profile, load_catalog
from pbwork.metrics import RunMetrics
from pbwork.model import WorkloadRun
from pbwork.result import human_summary, make_result, redact


class ResultTests(unittest.TestCase):
    def test_zero_sample_latency_is_null(self):
        values = RunMetrics(sample_limit=8).latency()
        self.assertEqual(values["sample_count"], 0)
        self.assertIsNone(values["median"])
        self.assertIsNone(values["p95"])
        self.assertIsNone(values["p99"])

    def test_populated_latency_and_read_counters(self):
        metrics = RunMetrics(sample_limit=8)
        metrics.record("lookup", 1, {"status": "read", "rows_read": 2, "rows_written": 0, "elapsed_ms": 5})
        data = metrics.as_dict(1)
        self.assertEqual(data["completed"], 1)
        self.assertEqual(data["rows_written"], 0)
        self.assertEqual(data["latency_ms"]["median"], 5)

    def test_error_redaction(self):
        self.assertNotIn("hunter2", redact("password=hunter2"))

    def test_read_cardinality_and_modes(self):
        metrics = RunMetrics()
        metrics.record("nav", 1, {"status": "read", "rows_read": 0, "rows_written": 0,
                                   "requested_cardinality": 100, "traversal_depth": 4,
                                   "lob_mode": "clob", "elapsed_ms": 0.2})
        aggregate = metrics.as_dict(1)
        operation = metrics.by_operation(1)["nav"]
        for data in (aggregate, operation):
            self.assertEqual(data["empty_results"], 1)
            self.assertEqual(data["requested_rows"], 100)
            self.assertEqual(data["rows_read"], 0)
            self.assertEqual(data["traversal_depth"], 4)
            self.assertEqual(data["lob_modes"], ["clob"])

    def test_complete_read_result_contract(self):
        profile = find_profile(load_catalog(), "read-reference-point")
        run = WorkloadRun("fixture", profile.id, profile.version, "read", "fake", 1, 1, 1, None, "direct-read")
        for state in ("VALIDATING", "READY", "RUNNING", "STOPPING", "SUCCEEDED"):
            run.transition(state)
        metrics = RunMetrics()
        metrics.record("currency-by-id", 1, {"status": "read", "rows_read": 1, "rows_written": 0, "elapsed_ms": 1})
        result = make_result(run, profile, metrics, 1, errors=[{"operation_id": "x", "table": None,
                                                                  "error_class": "x", "message": "password=hunter2",
                                                                  "rolled_back": False}])
        self.assertEqual(result["schema_version"], 1)
        for key in ("run_id", "profile_id", "profile_version", "kind", "database_target", "working_database",
                    "seed", "workers", "operation_limit", "duration_seconds", "mode", "status",
                    "started_at", "ended_at", "cleanup_status"):
            self.assertIn(key, result["run"])
        for key in ("attempted", "completed", "failed", "retried", "committed", "rolled_back",
                    "rows_read", "rows_written", "latency_ms", "throughput_ops_per_second"):
            self.assertIn(key, result["metrics"])
        self.assertEqual(result["metrics"]["rows_written"], 0)
        self.assertNotIn("hunter2", str(result))
        self.assertIn("read-reference-point", human_summary(result))

    def test_write_error_never_serializes_raw_payload(self):
        profile = find_profile(load_catalog(), "write-narrow-append")
        run = WorkloadRun("fixture", profile.id, profile.version, "write", "fake", 1, 1, 1, None, "isolated")
        result = make_result(run, profile, RunMetrics(), 0, errors=[{"operation_id": "login-append", "table": "LoginEvent",
                                                                    "error_class": "Constraint", "message": "Faker sensitive payload",
                                                                    "rolled_back": True}])
        self.assertNotIn("Faker sensitive payload", str(result))

    def test_at_least_95_percent_of_completed_fixtures_have_contract_fields(self):
        fixtures = []
        for profile in load_catalog():
            if profile.kind != "read":
                continue
            for index in range(3):
                run = WorkloadRun(f"{profile.id}-{index}", profile.id, profile.version, "read", "fake",
                                  index, 1, 1, None, "direct-read")
                for state in ("VALIDATING", "READY", "RUNNING", "STOPPING", "SUCCEEDED"):
                    run.transition(state)
                metrics = RunMetrics()
                metrics.record(profile.operations[0].id, 1, {"status": "read", "rows_read": 1, "elapsed_ms": 1})
                fixtures.append(json.loads(json.dumps(make_result(run, profile, metrics, 1))))
        required_top = {"schema_version", "run", "coverage", "metrics", "by_operation", "environment", "errors"}
        required_run = {"run_id", "profile_id", "profile_version", "seed", "workers", "mode", "status", "cleanup_status"}
        required_metrics = {"attempted", "completed", "failed", "rows_read", "rows_written", "latency_ms"}
        complete = sum(required_top <= fixture.keys() and required_run <= fixture["run"].keys()
                       and required_metrics <= fixture["metrics"].keys() for fixture in fixtures)
        self.assertGreaterEqual(complete / len(fixtures), 0.95)
