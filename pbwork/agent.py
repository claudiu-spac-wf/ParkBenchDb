"""Persistent OpenEdge workload agent over the existing atomic JSON spool protocol."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from pbgen.agent import AgentClient as _BaseAgentClient
from pbgen.agent import AgentError as _BaseAgentError

from . import config
from .result import redact


class AgentError(_BaseAgentError):
    """Redacted workload agent failure."""


class AgentClient(_BaseAgentClient):
    """Launch pbwork_agent.p and exchange hello/validate/batch/sample/quit requests."""

    def start(self) -> None:
        if self.spool.exists() and any(self.spool.iterdir()):
            raise AgentError(f"workload spool already contains files: {self.spool}")
        self.spool.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            os.chmod(self.spool, 0o700)
        log = open(self.spool / "agent.log", "w", encoding="utf-8", errors="replace")
        cmd = [str(config.progres_exe()), "-b", *self.conn.connect_args(), "-rereadnolock",
               "-cpinternal", "UTF-8", "-cpstream", "UTF-8", "-p",
               str(config.ABL_DIR / "pbwork_agent.p"), "-param", str(self.spool)]
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        try:
            self.proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, cwd=str(self.spool),
                                         creationflags=flags, start_new_session=(os.name != "nt"))
        finally:
            log.close()

    def request(self, op: str, timeout: float = 900.0, **kw) -> dict:
        if op not in {"hello", "validate", "batch", "sample", "quit"}:
            raise AgentError(f"unsupported workload agent operation: {op}")
        try:
            return super().request(op, timeout=timeout, **kw)
        except _BaseAgentError as exc:
            raise AgentError(redact(str(exc)), exc.reply) from None

    def hello(self):
        return self.request("hello")

    def validate(self, profile: str, prerequisites: dict):
        return self.request("validate", profile=profile, prerequisites=prerequisites)

    def batch(self, operations: list[dict]):
        if not 1 <= len(operations) <= 256:
            raise AgentError("batch must contain 1 to 256 operations")
        return self.request("batch", operations=operations)

    def sample(self, tables: list[str]):
        return self.request("sample", tables=tables)
