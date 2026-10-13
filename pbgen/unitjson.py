"""Unit JSON encoding (specs/003-data-generation/data-model.md §3).

A unit file is a JSON object {"<Table>": [row, ...], ...} read by the ABL agent with
DATASET:READ-JSON into temp-tables created LIKE each table.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
from decimal import Decimal


def fmt_date(d: dt.date) -> str:
    return d.isoformat()


def fmt_datetime(t: dt.datetime) -> str:
    """DATETIME (no zone): YYYY-MM-DDTHH:MM:SS.mmm"""
    return t.replace(tzinfo=None).isoformat(timespec="milliseconds")


def fmt_datetime_tz(t: dt.datetime) -> str:
    """DATETIME-TZ: YYYY-MM-DDTHH:MM:SS.mmm+HH:MM"""
    if t.tzinfo is None:
        raise ValueError("DATETIME-TZ value needs a time zone")
    return t.isoformat(timespec="milliseconds")


def encode_value(ftype: str, value, decimals: int | None = None):
    """Encode one Python value for a field of the given OpenEdge type."""
    if value is None:
        return None
    if ftype == "DATE":
        return fmt_date(value)
    if ftype == "DATETIME":
        return fmt_datetime(value)
    if ftype == "DATETIME-TZ":
        return fmt_datetime_tz(value)
    if ftype == "LOGICAL":
        return bool(value)
    if ftype == "DECIMAL":
        if isinstance(value, Decimal):
            value = float(value)
        return round(float(value), decimals if decimals is not None else 10)
    if ftype == "BLOB":
        return base64.b64encode(bytes(value)).decode("ascii")
    if ftype in ("INTEGER", "INT64"):
        return int(value)
    return str(value)  # CHARACTER, CLOB


def write_unit(path: str | os.PathLike, tables: dict[str, list[dict]]) -> int:
    """Write the unit atomically (tmp file + rename). Returns the byte size written."""
    path = os.fspath(path)
    tmp = path + ".tmp"
    data = json.dumps(tables, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
    return len(data)


def write_json_atomic(path: str | os.PathLike, obj) -> None:
    path = os.fspath(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)
    os.replace(tmp, path)
