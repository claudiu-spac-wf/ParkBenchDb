"""Shared opt-in gates for workload integration tests."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def requires_openedge(test):
    return unittest.skipUnless(os.environ.get("PARKBENCH_OE_TESTS") == "1", "set PARKBENCH_OE_TESTS=1")(test)


def requires_docker(test):
    return unittest.skipUnless(os.environ.get("PARKBENCH_DOCKER_TESTS") == "1", "set PARKBENCH_DOCKER_TESTS=1")(test)


def temporary_workdir():
    return tempfile.TemporaryDirectory(prefix="pbwork-test-")


def run_program(*args: str, cwd: Path = REPO):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
