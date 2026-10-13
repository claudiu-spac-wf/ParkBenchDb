"""Opt-in integration test against a real OpenEdge 12.8 install (Windows side, reached through cmd.exe).

Runs db/build_db.bat for real, then dumps the loaded schema with OpenEdge's own prodict/dump_df.p and
checks it is identical, block for block, to db/parkbench.df.

Enable with:  PARKBENCH_OE_TESTS=1 python3 -m unittest tests.test_openedge_integration -v
The OpenEdge install is taken from PARKBENCH_OE_DLC (a Windows path) or from DLC in the Windows environment.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

CMD = next((c for c in (shutil.which("cmd.exe"), "/mnt/c/Windows/System32/cmd.exe") if c and Path(c).exists()), None)


def win_dlc() -> str | None:
    if os.environ.get("PARKBENCH_OE_DLC"):
        return os.environ["PARKBENCH_OE_DLC"]
    if not CMD:
        return None
    out = subprocess.run([CMD, "/d", "/c", "echo %DLC%"], capture_output=True, text=True).stdout.strip()
    return None if not out or out == "%DLC%" else out


def to_wsl(p: str) -> Path:
    return Path(subprocess.run(["wslpath", "-u", p], capture_output=True, text=True, check=True).stdout.strip())


def to_win(p: Path) -> str:
    return subprocess.run(["wslpath", "-w", str(p)], capture_output=True, text=True, check=True).stdout.strip()


def df_blocks(path: Path) -> dict[str, list[str]]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = text[: text.index("\n.\nPSC\n")]
    return {c.split("\n")[0].rstrip(): [x.strip() for x in c.split("\n")[1:] if x.strip()]
            for c in text.strip("\n").split("\n\n")}


DLC = win_dlc() if os.environ.get("PARKBENCH_OE_TESTS") == "1" else None


@unittest.skipUnless(DLC and (to_wsl(DLC) / "bin" / "_progres.exe").exists(),
                     "set PARKBENCH_OE_TESTS=1 with a real OpenEdge 12.8 DLC to run")
class RealOpenEdgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / ".tmp").mkdir(exist_ok=True)
        cls.tmp = Path(tempfile.mkdtemp(dir=ROOT / ".tmp", prefix="oe_"))
        cls.target = cls.tmp / "db"
        env = dict(os.environ, DLC=DLC, WSLENV="DLC")
        r = subprocess.run([CMD, "/d", "/c", to_win(ROOT / "db" / "build_db.bat"), to_win(cls.tmp) + "\\db"],
                           capture_output=True, env=env, cwd=cls.tmp)
        cls.build_rc = r.returncode
        cls.build_out = r.stdout.decode("utf-8", "replace").replace("\r\n", "\n")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_build_and_verify(self):
        self.assertEqual(self.build_rc, 0, self.build_out)
        self.assertIn("VERIFY OK", self.build_out)
        self.assertNotIn("FAIL", self.build_out)
        self.assertFalse((self.target / "parkbench.e").exists())

    def test_dump_round_trip_matches_generated_df(self):
        self.assertEqual(self.build_rc, 0, self.build_out)
        (self.target / "dump.p").write_text('RUN prodict/dump_df.p (INPUT "ALL", INPUT "roundtrip.df", INPUT "").\n'
                                            "QUIT.\n")
        subprocess.run([CMD, "/d", "/c", f"{DLC}\\bin\\_progres.exe", "-b", "-1", "-db", "parkbench",
                        "-cpinternal", "UTF-8", "-cpstream", "UTF-8", "-p", "dump.p"],
                       capture_output=True, cwd=self.target, check=False)
        ours = df_blocks(ROOT / "db" / "parkbench.df")
        dumped = df_blocks(self.target / "roundtrip.df")
        self.assertEqual(sorted(ours), sorted(dumped))
        mismatched = [k for k in ours if ours[k] != dumped[k]]
        self.assertEqual(mismatched, [], f"{len(mismatched)} block(s) differ, e.g. {mismatched[:3]}")

    def test_bi_options(self):
        """spec 003 US6: a non-default before-image block and cluster size are applied and verified."""
        env = dict(os.environ, DLC=DLC, WSLENV="DLC")
        r = subprocess.run([CMD, "/d", "/c", to_win(ROOT / "db" / "build_db.bat"), to_win(self.tmp) + "\\bi8",
                            "--bi-block-size", "8", "--bi-cluster-size", "32"],
                           capture_output=True, env=env, cwd=self.tmp)
        out = r.stdout.decode("utf-8", "replace").replace("\r\n", "\n")
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("CHECK before-image block size: ok (8192)", out)
        self.assertIn("CHECK before-image cluster size: ok (33554432)", out)
        self.assertIn("VERIFY OK", out)


if __name__ == "__main__":
    unittest.main()
