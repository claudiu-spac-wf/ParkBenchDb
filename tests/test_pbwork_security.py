"""Regression checks for non-executable catalogs and source-path safety."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pbwork.agent import AgentClient
from pbwork.model import BaselineManifest
from pbwork.catalog import find_profile, load_catalog
from pbwork.config import ConnectionConfig
from pbwork.runner import Runner
from pbwork.result import redact


class SecurityTests(unittest.TestCase):
    def test_common_secret_forms_are_redacted(self):
        self.assertNotIn("password=hunter2", redact("password=hunter2"))
        self.assertNotIn("token: abcdef", redact("token: abcdef"))

    def test_baseline_workdir_cannot_overlap_source(self):
        source = "/tmp/parkbench-source/parkbench"
        values = dict(run_id="x", source_database=source, source_schema_digest="x",
                      source_row_counts={}, source_benchmark_counts={}, source_sequences={},
                      dump_directory="/tmp/pbwork-dump", created_at="now")
        for work in (source, str(Path(source).parent), str(Path(source) / "nested")):
            with self.subTest(work=work), self.assertRaises(ValueError):
                BaselineManifest(working_directory=work, **values).validate_paths()

    def test_docker_context_excludes_local_env(self):
        text = (Path(__file__).resolve().parents[1] / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn("ParkBench/.env.local", text)

    def test_library_cannot_bypass_write_isolation_gate(self):
        profile = find_profile(load_catalog(), "write-narrow-append")
        runner = Runner(ConnectionConfig("fake"), profile, agent_factory=lambda *_: self.fail("agent started"))
        with self.assertRaisesRegex(RuntimeError, "disabled until isolated-copy"):
            runner.execute(operations=1, duration=None, seed=1, workers=1, mode="isolated")

    def test_payload_spool_is_private_on_posix(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent"
            agent = AgentClient(ConnectionConfig("fake"), path, start=False)
            with patch("pbwork.agent.config.progres_exe", return_value=Path("/bin/true")), \
                    patch("pbwork.agent.subprocess.Popen"):
                agent.start()
            self.assertTrue((path / "agent.log").is_file())
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o700)

    def test_abl_rejects_unallowlisted_tables_and_free_form_predicates(self):
        text = (Path(__file__).resolve().parents[1] / "db" / "abl" / "pbwork_agent.p").read_text(encoding="utf-8")
        self.assertIn("FUNCTION allowedTable", text)
        self.assertIn('LOOKUP(cIndexed, "RandomInt10,RandomInt100,RandomInt1000")', text)
        self.assertIn('LOOKUP(cHandler, "point_lookup,indexed_selective,range_scan,table_scan,relationship_navigation,lob_fetch")', text)
        self.assertNotIn('oOp:GetCharacter("where")', text)
        self.assertNotIn('oOp:GetCharacter("query")', text)
