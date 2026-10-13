"""Workload catalog and CLI contract tests."""

import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import subprocess
import sys

from pbwork import cli
from pbwork.agent import AgentClient
from pbwork.config import ConnectionConfig
from pbwork.catalog import load_catalog
from pbwork.runner import Runner


class LocalFakeAgent(AgentClient):
    calls = []

    def start(self):
        self.spool.mkdir(parents=True, exist_ok=False)
        self.proc = subprocess.Popen([sys.executable, str(Path(__file__).with_name("fake_pbwork_agent.py")), str(self.spool)])

    def request(self, op, timeout=900.0, **kwargs):
        self.calls.append((op, kwargs))
        return super().request(op, timeout=timeout, **kwargs)


class MissingRowsAgent(LocalFakeAgent):
    def validate(self, profile, prerequisites):
        from pbwork.agent import AgentError
        raise AgentError("minimumRows not met for Currency")


class CliContractTests(unittest.TestCase):
    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_catalog_lists_all_canonical_profiles(self):
        code, out, _ = self.invoke("catalog", "--json")
        self.assertEqual(code, 0)
        profiles = json.loads(out)["profiles"]
        self.assertEqual(len(profiles), 15)
        self.assertIn("read-reference-point", {p["id"] for p in profiles})

    def test_invalid_profile_rejected_before_agent(self):
        code, _, err = self.invoke("validate", "--db", "unused", "--profile", "unknown")
        self.assertEqual(code, 2)
        self.assertIn("unknown", err)

    def test_limits_are_exclusive(self):
        code, _, _ = self.invoke("run", "--db", "unused", "--profile", "read-reference-point", "--operations", "1", "--duration", "1")
        self.assertEqual(code, 2)
        code, _, _ = self.invoke("run", "--db", "unused", "--profile", "read-reference-point", "--duration", "nan")
        self.assertEqual(code, 2)

    def test_catalog_validates_unavailable_profile(self):
        code, _, err = self.invoke("validate", "--db", "unused", "--profile", "write-wide-update", "--operations", "1")
        self.assertEqual(code, 2)
        self.assertTrue(err)

    def test_1000_reference_reads_write_structured_result(self):
        LocalFakeAgent.calls = []
        with TemporaryDirectory() as directory, patch.object(cli, "AgentClient", LocalFakeAgent), patch.object(cli, "Runner") as runner_type:
            from pbwork.runner import Runner
            runner_type.side_effect = lambda conn, profile, **kwargs: Runner(conn, profile, agent_factory=LocalFakeAgent, **kwargs)
            result_path = Path(directory) / "result.json"
            code, out, err = self.invoke("run", "--db", "fake", "--profile", "read-reference-point",
                                         "--operations", "1000", "--workers", "4", "--seed", "20260929",
                                         "--spool", str(Path(directory) / "spool"), "--result", str(result_path), "--json")
            self.assertEqual(code, 0, err)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["metrics"]["completed"], 1000)
            self.assertEqual(result["metrics"]["rows_written"], 0)
            self.assertEqual(result["run"]["profile_id"], "read-reference-point")
            self.assertEqual(json.loads(out), result)
            self.assertEqual({op for op, _ in LocalFakeAgent.calls}, {"hello", "validate", "batch", "quit"})
            self.assertTrue(all(item["handler"] == "point_lookup"
                                for op, kwargs in LocalFakeAgent.calls if op == "batch"
                                for item in kwargs["operations"]))

    def test_validation_is_dry_run_and_repeatable(self):
        LocalFakeAgent.calls = []
        with TemporaryDirectory() as directory, patch.object(cli, "AgentClient", LocalFakeAgent), patch.object(cli, "spool_root", return_value=Path(directory)):
            for _ in range(2):
                code, out, err = self.invoke("validate", "--db", "fake", "--profile", "read-reference-point")
                self.assertEqual(code, 0, err)
                self.assertIn("ready", out)
        self.assertEqual({op for op, _ in LocalFakeAgent.calls}, {"hello", "validate", "quit"})

    def test_quickstart_mvp_checkpoint_and_result_path(self):
        """The documented catalog/validate/run sequence works without OpenEdge."""
        LocalFakeAgent.calls = []
        with TemporaryDirectory() as directory, patch.object(cli, "AgentClient", LocalFakeAgent), patch.object(cli, "Runner") as runner_type, patch.object(cli, "spool_root", return_value=Path(directory) / "validate-spool"):
            runner_type.side_effect = lambda conn, profile, **kwargs: Runner(conn, profile, agent_factory=LocalFakeAgent, **kwargs)
            code, catalog_text, err = self.invoke("catalog", "--json")
            self.assertEqual(code, 0, err)
            self.assertEqual(len(json.loads(catalog_text)["profiles"]), 15)
            code, ready_text, err = self.invoke("validate", "--db", "fake", "--profile", "read-reference-point", "--operations", "1000", "--seed", "20260929")
            self.assertEqual(code, 0, err)
            self.assertIn("ready", ready_text)
            self.assertFalse(any(op == "batch" for op, _ in LocalFakeAgent.calls))
            path = Path(directory) / "read-reference.json"
            code, _, err = self.invoke("run", "--db", "fake", "--profile", "read-reference-point",
                                       "--operations", "1000", "--seed", "20260929", "--workers", "2",
                                       "--spool", str(Path(directory) / "run-spool"), "--result", str(path))
            self.assertEqual(code, 0, err)
            self.assertTrue(path.is_file())
            result = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(result["metrics"]["completed"], 1000)
            self.assertEqual(result["metrics"]["rows_written"], 0)

    def test_all_eight_read_profiles_complete_without_writes(self):
        with TemporaryDirectory() as directory:
            for profile in load_catalog():
                if profile.kind != "read":
                    continue
                with self.subTest(profile=profile.id):
                    result = Runner(ConnectionConfig("fake"), profile, agent_factory=LocalFakeAgent,
                                    spool=Path(directory) / profile.id).execute(
                                        operations=100, duration=None, seed=20260929,
                                        workers=2, mode="direct-read")
                    self.assertEqual(result["run"]["status"], "SUCCEEDED", result["errors"])
                    self.assertEqual(result["metrics"]["completed"], 100)
                    self.assertEqual(result["metrics"]["rows_written"], 0)

    def test_missing_rows_rejects_before_batch(self):
        LocalFakeAgent.calls = []
        with TemporaryDirectory() as directory, patch.object(cli, "AgentClient", MissingRowsAgent), patch.object(cli, "spool_root", return_value=Path(directory)):
            code, _, err = self.invoke("validate", "--db", "fake", "--profile", "read-reference-point")
        self.assertEqual(code, 1)
        self.assertIn("Currency", err)
        self.assertFalse(any(op == "batch" for op, _ in LocalFakeAgent.calls))

    def test_compare_profile_version_gate(self):
        with TemporaryDirectory() as directory:
            first, second = Path(directory) / "a.json", Path(directory) / "b.json"
            value = {"run": {"profile_id": "read-reference-point", "profile_version": 1, "workers": 1},
                     "metrics": {"completed": 1, "latency_ms": {"median": 1}}}
            first.write_text(json.dumps(value), encoding="utf-8")
            second.write_text(json.dumps(value), encoding="utf-8")
            code, out, _ = self.invoke("compare", str(first), str(second), "--json")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["profiles"], ["read-reference-point"] * 2)
            value["run"]["profile_version"] = 2
            second.write_text(json.dumps(value), encoding="utf-8")
            code, _, err = self.invoke("compare", str(first), str(second))
            self.assertEqual(code, 2)
            self.assertIn("versions differ", err)

    def test_unserved_database_hint(self):
        from pbwork.agent import AgentError
        with patch.object(cli, "AgentClient", side_effect=AgentError("agent exited (1423): no server")):
            code, _, err = self.invoke("validate", "--db", "fake", "--profile", "read-reference-point")
        self.assertEqual(code, 2)
        self.assertIn("database is not being served", err)

    def test_run_exit_codes_failed_and_interrupted(self):
        with TemporaryDirectory() as directory, patch.object(cli, "Runner") as runner_type:
            fake = runner_type.return_value
            common = ("run", "--db", "fake", "--profile", "read-reference-point",
                      "--operations", "1", "--spool", directory, "--json")
            for status, expected in (("FAILED", 1), ("INTERRUPTED", 130)):
                fake.execute.return_value = {"run": {"run_id": status.lower(), "status": status}, "metrics": {}}
                code, _, err = self.invoke(*common)
                self.assertEqual(code, expected, err)

    def test_invalid_profile_parameter_rejected_before_agent(self):
        with patch.object(cli, "AgentClient") as agent_type:
            code, _, err = self.invoke("validate", "--db", "fake", "--profile", "read-reference-point",
                                       "--param", "bogus=2")
        self.assertEqual(code, 2)
        self.assertIn("unknown parameter", err)
        agent_type.assert_not_called()
