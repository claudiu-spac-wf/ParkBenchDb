"""Client for the persistent ABL agent (db/abl/pbgen_agent.p) over the spool-file protocol.

data-model.md §4: Python writes req-<n>.json atomically, the agent answers resp-<n>.json.
Ops that return bulk data (state, status, sample) point at data files; this client reads
them so callers always get plain dicts:  resp["runs"], resp["bti"], resp["data"].
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from pbgen import config
from pbgen.unitjson import write_json_atomic


class AgentError(Exception):
    """The agent replied ok:false, died, or timed out."""

    def __init__(self, message: str, reply: dict | None = None):
        super().__init__(message)
        self.reply = reply or {}

    @property
    def lost(self) -> bool:
        return "lost" in str(self)


def _read_json_file(path: str | None):
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8-sig").strip()
    try:
        p.unlink()
    except OSError:
        pass
    if not text:
        return []
    data = json.loads(text)
    if isinstance(data, dict):  # a temp-table written with its outer object
        values = list(data.values())
        data = values[0] if len(values) == 1 else values
    return data


class AgentClient:
    """Starts one `_progres -b` agent and exchanges requests with it (thread-safe)."""

    def __init__(self, conn: config.ConnectionConfig, spool_dir: str | os.PathLike, *, start: bool = True):
        self.conn = conn
        self.spool = Path(spool_dir)
        self.seq = 0
        self.proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        if start:
            self.start()

    def start(self) -> None:
        if self.spool.exists():
            shutil.rmtree(self.spool, ignore_errors=True)
        self.spool.mkdir(parents=True, exist_ok=True)
        log = open(self.spool / "agent.log", "w", encoding="utf-8", errors="replace")
        # -rereadnolock: long-lived agents must never see stale NO-LOCK copies of rows other agents changed
        cmd = [str(config.progres_exe()), "-b", *self.conn.connect_args(), "-rereadnolock",
               "-cpinternal", "UTF-8", "-cpstream", "UTF-8",
               "-p", str(config.ABL_DIR / "pbgen_agent.p"), "-param", str(self.spool)]
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     cwd=str(self.spool), creationflags=flags,
                                     start_new_session=(os.name != "nt"))

    def agent_log(self, lines: int = 20) -> str:
        p = self.spool / "agent.log"
        if not p.exists():
            return ""
        return "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])

    def request(self, op: str, timeout: float = 900.0, **kw) -> dict:
        with self._lock:
            self.seq += 1
            req = self.spool / f"req-{self.seq}.json"
            resp = self.spool / f"resp-{self.seq}.json"
            write_json_atomic(req, {"op": op, **kw})
            deadline = time.monotonic() + timeout
            delay = 0.002
            while not resp.exists():
                if self.proc is not None and self.proc.poll() is not None:
                    raise AgentError(f"agent exited (code {self.proc.returncode}) during {op}:\n{self.agent_log()}")
                if time.monotonic() > deadline:
                    raise AgentError(f"agent timed out after {timeout:.0f}s on {op}")
                time.sleep(delay)
                delay = min(delay * 2, 0.05)
            reply = None
            for attempt in range(100):  # Windows: the file can still be held open briefly after the rename
                try:
                    reply = json.loads(resp.read_text(encoding="utf-8-sig"))
                    resp.unlink()
                    break
                except (PermissionError, json.JSONDecodeError):
                    if attempt == 99:
                        raise
                    time.sleep(0.02)
        if not reply.get("ok"):
            raise AgentError(reply.get("error", "unknown agent error"), reply)
        if "runsFile" in reply:
            reply["runs"] = _read_json_file(reply.pop("runsFile"))
        if "btiFile" in reply:
            reply["bti"] = _read_json_file(reply.pop("btiFile"))
        if op == "sample" and "file" in reply:
            reply["data"] = _read_json_file(reply.pop("file"))
        return reply

    def close(self, wait: float = 30.0) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        try:
            self.request("quit", timeout=wait)
        except AgentError:
            pass
        try:
            self.proc.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def kill(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def run_oneshot(conn: config.ConnectionConfig, program: str, param: str, cwd: str | os.PathLike,
                timeout: float = 3600.0) -> tuple[int, str]:
    """Runs one ABL program in batch mode on the connection; returns (exit code, output)."""
    cmd = [str(config.progres_exe()), "-b", *conn.connect_args(), "-cpinternal", "UTF-8", "-cpstream", "UTF-8",
           "-p", str(config.ABL_DIR / program), "-param", param]
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, errors="replace", timeout=timeout,
                       stdin=subprocess.DEVNULL)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


NOT_SERVED_HINT = ("the database is not being served (or is open single-user). Start it first, e.g.:\n"
                   "  db/server.sh start <db-path> --workers <N>      (Windows: db\\server.bat ...)")
