"""Offline agent protocol and fake response tests."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pbwork.agent import AgentClient, AgentError
from pbwork.config import ConnectionConfig
from tests.fake_pbwork_agent import process
from pbwork.catalog import load_catalog
from pbwork.operations import read_descriptor
from pbwork.metrics import RunMetrics


class FakeAgentTests(unittest.TestCase):
    def test_hello_and_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = AgentClient(ConnectionConfig("fake"), directory, start=False)
            agent.proc = subprocess.Popen([sys.executable, str(Path(__file__).with_name("fake_pbwork_agent.py")), directory])
            try:
                self.assertTrue(agent.hello()["ok"])
                self.assertEqual(agent.batch([{"ordinal": 1, "operation_id": "lookup", "handler": "point_lookup"}])["operations"][0]["status"], "read")
            finally:
                agent.close()

    def test_rejects_unexpected_protocol_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = AgentClient(ConnectionConfig("fake"), directory, start=False)
            with self.assertRaises(AgentError):
                agent.request("arbitrary-abl")

    def test_transaction_failure_has_no_written_rows(self):
        result = process({"op": "batch", "operations": [{"ordinal": 2, "operation_id": "batch", "handler": "transaction_batch", "inject_failure": "constraint"}]})
        self.assertEqual(result["operations"][0]["status"], "rolled_back")
        self.assertEqual(result["operations"][0]["rows_written"], 0)

    def test_multi_row_commit_and_partial_failure_are_atomic(self):
        requests = [
            {"ordinal": 1, "operation_id": "batch-good", "handler": "transaction_batch"},
            {"ordinal": 2, "operation_id": "batch-bad", "handler": "transaction_batch",
             "inject_failure": "constraint", "inject_failure_after": 2},
        ]
        results = process({"op": "batch", "operations": requests})["operations"]
        self.assertEqual([(row["status"], row["rows_written"]) for row in results],
                         [("committed", 3), ("rolled_back", 0)])
        metrics = RunMetrics()
        for row in results:
            metrics.record(row["operation_id"], row["ordinal"], row)
        self.assertEqual(metrics.counts["committed"], 1)
        self.assertEqual(metrics.counts["rolled_back"], 1)
        self.assertEqual(metrics.counts["rows_written"], 3)

    def test_deadlock_timeout_retry_and_error_redaction(self):
        from pbwork.result import redact
        requests = [
            {"ordinal": 1, "operation_id": "hot-deadlock", "handler": "update_wide",
             "inject_failure": "deadlock", "retries": 2, "payload": {"password": "secret-value"}},
            {"ordinal": 2, "operation_id": "hot-timeout", "handler": "update_wide",
             "inject_failure": "lock-timeout", "retries": 1},
        ]
        results = process({"op": "batch", "operations": requests})["operations"]
        metrics = RunMetrics()
        for row in results:
            metrics.record(row["operation_id"], row["ordinal"], row)
        self.assertEqual(metrics.counts["retried"], 3)
        self.assertEqual(metrics.counts["deadlocks"], 1)
        self.assertEqual(metrics.counts["timeouts"], 1)
        self.assertEqual(metrics.counts["contention_events"], 2)
        self.assertTrue(all(row["rows_written"] == 0 for row in results))
        self.assertNotIn("secret-value", str(results))
        self.assertNotIn("secret-value", redact("password=secret-value"))

    def test_stale_agent_and_bounded_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = AgentClient(ConnectionConfig("fake"), directory, start=False)
            with self.assertRaises(AgentError):
                agent.batch([])
            with self.assertRaises(AgentError):
                agent.batch([{"ordinal": i} for i in range(257)])
            agent.proc = subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"])
            with self.assertRaises(AgentError):
                agent.hello()

    def test_sample_is_deterministic(self):
        req = {"op": "sample", "tables": ["Currency", "Branch"]}
        self.assertEqual(process(req), process(req))

    def test_all_read_handlers_are_read_only_over_fake_protocol(self):
        for profile in load_catalog():
            if profile.kind != "read":
                continue
            counts = {table: 10000 for table in profile.tables}
            for operation in profile.operations:
                descriptor = read_descriptor(1, profile.version, 1, operation, counts)
                reply = process({"op": "batch", "operations": [descriptor]})["operations"][0]
                self.assertEqual(reply["status"], "read")
                self.assertEqual(reply["rows_written"], 0)

    def test_range_scan_navigation_lob_and_empty_selective_responses(self):
        profiles = [profile for profile in load_catalog() if profile.kind == "read"]
        descriptors = []
        for profile in profiles:
            counts = {table: 10000 for table in profile.tables}
            for operation in profile.operations:
                if operation.handler in {"range_scan", "table_scan", "relationship_navigation", "lob_fetch", "indexed_selective"}:
                    descriptors.append(read_descriptor(7, profile.version, len(descriptors) + 1, operation, counts))
        selective = next(row for row in descriptors if row["handler"] == "indexed_selective")
        selective["empty_result"] = True
        reply = process({"op": "batch", "operations": descriptors})["operations"]
        self.assertEqual(len(reply), len(descriptors))
        self.assertEqual({row["status"] for row in reply}, {"read"})
        self.assertTrue(all(row["rows_written"] == 0 for row in reply))
        self.assertTrue(all(row.get("error_class") is None for row in reply))
        self.assertEqual(next(row for row in reply if row["ordinal"] == selective["ordinal"])["rows_read"], 0)
        self.assertTrue(any(row["traversal_depth"] for row in reply))
        self.assertEqual({row["lob_mode"] for row in reply if row["lob_mode"]}, {"clob", "blob", "both", "scalarOnly"})
