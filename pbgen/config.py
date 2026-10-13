"""Connection options, OpenEdge discovery and paths shared by every pbgen command."""

from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ABL_DIR = REPO / "db" / "abl"
SCHEMA_FILE = REPO / "schema" / "parkbench-schema.yaml"
LOADER_DF = REPO / "db" / "parkbench_loader.df"


class ConfigError(Exception):
    """A configuration problem the user must fix (exit code 2)."""


@dataclass(frozen=True)
class ConnectionConfig:
    db: str                    # database path (self-service) or logical name (with host/port)
    host: str | None = None
    port: int | None = None

    @property
    def self_service(self) -> bool:
        return self.host is None

    def connect_args(self) -> list[str]:
        if self.self_service:
            return ["-db", self.db]
        return ["-db", self.db, "-H", self.host, "-S", str(self.port)]

    def db_dir(self) -> Path:
        """Directory holding the database files (self-service only)."""
        return Path(self.db).resolve().parent

    def db_files(self) -> list[Path]:
        """Extent files of the database, for size reporting (self-service only)."""
        if not self.self_service:
            return []
        base = Path(self.db)
        stem = base.name[:-3] if base.name.endswith(".db") else base.name
        d = base.parent if str(base.parent) else Path(".")
        return sorted(p for p in d.glob(f"{stem}*") if p.suffix[:2] in (".d", ".b") and p.suffix[2:].isdigit())


def dlc() -> Path:
    value = os.environ.get("DLC")
    if not value:
        raise ConfigError("DLC is not set; point it at the OpenEdge 12.8 installation")
    path = Path(value)
    if not any((path / "bin" / exe).exists() for exe in ("_progres.exe", "_progres")):
        raise ConfigError(f"{path}/bin/_progres not found; DLC does not look like an OpenEdge installation")
    return path


def progres_exe() -> Path:
    bin_dir = dlc() / "bin"
    for exe in ("_progres.exe", "_progres"):
        if (bin_dir / exe).exists():
            return bin_dir / exe
    raise ConfigError(f"{bin_dir}/_progres not found")


def spool_root(conn: ConnectionConfig, override: str | None = None) -> Path:
    if override:
        return Path(override)
    if conn.self_service:
        return conn.db_dir() / "pbgen-spool"
    return Path.cwd() / "pbgen-spool"


def worker_id(worker_no: int) -> str:
    """host:pid:worker-no:start-epoch (stored in LoaderUnit.ClaimedBy)."""
    return f"{socket.gethostname()}:{os.getpid()}:{worker_no}:{int(time.time())}"


def parse_worker_id(value: str) -> tuple[str, int, int, int] | None:
    parts = (value or "").split(":")
    if len(parts) != 4 or not all(p.isdigit() for p in parts[1:]):
        return None
    return parts[0], int(parts[1]), int(parts[2]), int(parts[3])


def pid_alive(pid: int) -> bool:
    """True if a process with this PID exists on this host."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
