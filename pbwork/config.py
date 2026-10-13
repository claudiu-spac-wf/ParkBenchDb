"""Connection and workload argument validation."""

import math
from pathlib import Path

from pbgen.config import ABL_DIR, REPO, ConfigError, ConnectionConfig, progres_exe
from pbgen.agent import NOT_SERVED_HINT


def connection(db: str | None, host: str | None, port: int | None) -> ConnectionConfig:
    if not db:
        raise ConfigError("--db is required")
    if (host is None) != (port is None):
        raise ConfigError("--host and --port must be provided together")
    if port is not None and not 1 <= port <= 65535:
        raise ConfigError("--port must be between 1 and 65535")
    return ConnectionConfig(db=db, host=host, port=port)


def limits(operations: int | None, duration: float | None, workers: int):
    if (operations is None) == (duration is None):
        raise ConfigError("specify exactly one of --operations or --duration")
    if operations is not None and operations < 1:
        raise ConfigError("--operations must be positive")
    if duration is not None and (not math.isfinite(duration) or duration <= 0):
        raise ConfigError("--duration must be positive")
    if workers < 1:
        raise ConfigError("--workers must be positive")


def spool_root(conn: ConnectionConfig, override: str | None = None) -> Path:
    return Path(override).resolve() if override else (conn.db_dir() if conn.self_service else Path.cwd()) / "pbwork-spool"


def validate_seed(seed: int) -> int:
    if not -(2 ** 63) <= seed < 2 ** 63:
        raise ConfigError("--seed must be a signed 64-bit integer")
    return seed


def validate_output_path(value: str | None, option: str) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser().resolve()
    if path.exists() and path.is_dir() and option == "--result":
        raise ConfigError("--result must name a file")
    if path.exists() and path.is_file() and option == "--spool":
        raise ConfigError("--spool must name a directory")
    if not path.parent.exists():
        raise ConfigError(f"{option} parent directory does not exist: {path.parent}")
    return path
