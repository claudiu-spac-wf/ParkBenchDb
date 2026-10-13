"""Offline PASOE image-selection and opt-in Docker checks."""

import os
import shutil
import subprocess
import tempfile
import time
import unittest
from uuid import uuid4
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "ParkBench" / "docker" / "build-pasoe.sh"
DEFAULT = ROOT / "ParkBench" / "docker" / "openedge-pasoe-parkbench"


class PasoeSelectionTests(unittest.TestCase):
    def run_build(self, *args, context=None):
        env = dict(os.environ)
        env.pop("PASOE_BASE_IMAGE", None)
        if context is not None:
            env["PARKBENCH_PASOE_BUILD_CONTEXT"] = str(context)
        else:
            env.pop("PARKBENCH_PASOE_BUILD_CONTEXT", None)
        return subprocess.run([str(BUILD), *args], cwd=ROOT, env=env, capture_output=True, text=True)

    def test_missing_context_fails_before_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "absent"
            result = self.run_build("--base-image", "approved.example/pasoe:tag", context=missing)
            self.assertEqual(result.returncode, 2)
            self.assertIn("not found", result.stderr)

    def test_missing_support_file_fails_before_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "Dockerfile").touch()
            result = self.run_build("--base-image", "approved.example/pasoe:tag", context=directory)
            self.assertEqual(result.returncode, 2)
            self.assertIn("requirements.txt", result.stderr)

    def test_cli_context_overrides_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_build("--context", str(DEFAULT), "--base-image", "", context=Path(directory) / "absent")
            self.assertEqual(result.returncode, 2)
            self.assertIn("PASOE base image must not be empty", result.stderr)
            self.assertNotIn("not found", result.stderr)

    def test_empty_base_is_rejected(self):
        result = self.run_build("--base-image", "")
        self.assertEqual(result.returncode, 2)
        self.assertIn("PASOE base image must not be empty", result.stderr)

    def test_definition_contains_no_credentials(self):
        for path in DEFAULT.iterdir():
            self.assertNotIn("password=", path.read_text(encoding="utf-8").lower())

    def test_selected_path_and_tag_are_reported_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_docker = Path(directory) / "docker"
            fake_docker.write_text("#!/bin/sh\nprintf 'docker invoked\\n'\n", encoding="utf-8")
            fake_docker.chmod(0o755)
            env = dict(os.environ)
            env["PATH"] = directory + os.pathsep + env.get("PATH", "")
            env["PARKBENCH_PASOE_BUILD_CONTEXT"] = str(DEFAULT)
            result = subprocess.run([str(BUILD), "--base-image", "approved.example/pasoe:tag", "--tag", "pbwork:test"],
                                    cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"PASOE context: {DEFAULT}", result.stdout)
            self.assertIn("Image tag: pbwork:test", result.stdout)
            self.assertIn("docker invoked", result.stdout)

    def test_default_context_and_approved_base(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_docker = Path(directory) / "docker"
            fake_docker.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
            fake_docker.chmod(0o755)
            env = dict(os.environ)
            env.pop("PASOE_BASE_IMAGE", None)
            env.pop("PARKBENCH_PASOE_BUILD_CONTEXT", None)
            env["PATH"] = directory + os.pathsep + env.get("PATH", "")
            result = subprocess.run([str(BUILD)], cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"PASOE context: {DEFAULT}", result.stdout)
            self.assertIn("PASOE_BASE_IMAGE=parkbench/openedge-pasoe:dev", result.stdout)

    def test_alternate_valid_definition_is_forwarded_to_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            alternate = Path(directory) / "definition"
            shutil.copytree(DEFAULT, alternate)
            fake_docker = Path(directory) / "docker"
            fake_docker.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
            fake_docker.chmod(0o755)
            env = dict(os.environ)
            env["PATH"] = directory + os.pathsep + env.get("PATH", "")
            env["PARKBENCH_PASOE_BUILD_CONTEXT"] = str(alternate)
            result = subprocess.run([str(BUILD), "--base-image", "approved.example/pasoe:tag"],
                                    cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"parkbench_definition={alternate}", result.stdout)
            self.assertIn(str(alternate / "Dockerfile"), result.stdout)


@unittest.skipUnless(os.environ.get("PARKBENCH_DOCKER_TESTS") == "1", "Docker test opt-in")
class DockerSmokeTests(unittest.TestCase):
    def test_build_start_and_smoke(self):
        base = os.environ.get("PASOE_BASE_IMAGE", "parkbench/openedge-pasoe:dev")
        unique = uuid4().hex[:12]
        tag = f"parkbench-pasoe:workloads-test-{unique}"
        container = f"pbwork-pasoe-test-{unique}"
        started = False
        try:
            subprocess.run([str(BUILD), "--base-image", base, "--tag", tag], cwd=ROOT, check=True, timeout=1200)
            subprocess.run(["docker", "run", "--rm", "--entrypoint", "parkbench-pasoe-smoke", tag],
                           check=True, timeout=120)
            inspect = subprocess.run(["docker", "image", "inspect", tag,
                                      "--format", "{{.Config.User}} {{json .Config.Entrypoint}}"],
                                     capture_output=True, text=True, check=True)
            self.assertIn("pscadmin", inspect.stdout)
            self.assertIn("parkbench-pasoe-entrypoint.sh", inspect.stdout)
            subprocess.run(["docker", "run", "--rm", "--detach", "--name", container,
                            "--env", "PASOE_DB_CONNECTION=", tag], check=True, timeout=60)
            started = True
            deadline = time.monotonic() + 150
            while time.monotonic() < deadline:
                probe = subprocess.run(["docker", "exec", container, "curl", "--silent", "--output", "/dev/null",
                                        "--write-out", "%{http_code}", "http://127.0.0.1:8810/"],
                                       capture_output=True, text=True)
                if probe.returncode == 0 and probe.stdout == "200":
                    break
                time.sleep(2)
            else:
                logs = subprocess.run(["docker", "logs", "--tail", "80", container], capture_output=True, text=True)
                self.fail(f"PASOE did not return HTTP 200: {logs.stdout}\n{logs.stderr}")
        finally:
            if started:
                subprocess.run(["docker", "stop", container], capture_output=True, text=True, timeout=90)
            subprocess.run(["docker", "image", "rm", tag], capture_output=True, text=True, timeout=90)

    def test_alternate_context_and_invalid_base(self):
        unique = uuid4().hex[:12]
        tag = f"parkbench-pasoe:alternate-test-{unique}"
        with tempfile.TemporaryDirectory(prefix="pbwork-definition-") as directory:
            alternate = Path(directory) / "definition"
            shutil.copytree(DEFAULT, alternate)
            try:
                subprocess.run([str(BUILD), "--context", str(alternate), "--tag", tag],
                               cwd=ROOT, check=True, timeout=1200)
            finally:
                subprocess.run(["docker", "image", "rm", tag], capture_output=True, text=True, timeout=90)
        invalid = subprocess.run([str(BUILD), "--base-image", "invalid@@@", "--tag", tag],
                                 cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertNotEqual(invalid.returncode, 0)
