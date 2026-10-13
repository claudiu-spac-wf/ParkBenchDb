"""Portable source hygiene and wrapper syntax checks."""

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "db" / "pbwork.sh",
    ROOT / "db" / "pbwork.bat",
    ROOT / "db" / "abl" / "pbwork_agent.p",
    ROOT / "ParkBench" / "docker" / "build-pasoe.sh",
    ROOT / "ParkBench" / "docker" / "build-pasoe.bat",
    ROOT / "ParkBench" / "docker" / "openedge-pasoe-parkbench" / "Dockerfile",
    ROOT / "ParkBench" / "docker" / "openedge-pasoe-parkbench" / "entrypoint.sh",
    ROOT / "ParkBench" / "docker" / "openedge-pasoe-parkbench" / "entrypoint.cmd",
]


class ScriptChecks(unittest.TestCase):
    def test_utf8_lf_no_tabs(self):
        for path in FILES:
            with self.subTest(path=path):
                raw = path.read_bytes()
                raw.decode("utf-8")
                self.assertNotIn(b"\r", raw)
                self.assertNotIn(b"\t", raw)

    def test_bash_syntax(self):
        for path in FILES:
            if path.suffix != ".sh":
                continue
            with self.subTest(path=path):
                subprocess.run(["bash", "-n", str(path)], check=True)
