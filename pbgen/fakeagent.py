"""Offline stand-in for db/abl/pbgen_agent.p, used by the unit tests.

Same request() interface and semantics as AgentClient, backed by an SQLite file so that
several processes can share it and every op is one atomic transaction, like OpenEdge.
Behaviour changes to the ABL agent must be mirrored here (and vice versa).
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import time
from pathlib import Path

from pbgen.agent import AgentError

STALE_SECONDS = 300

SCHEMA = """
CREATE TABLE IF NOT EXISTS run (id INTEGER PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS unit (run INTEGER, unitno INTEGER, phase INTEGER, kind TEXT, status TEXT,
    seed TEXT, firstids TEXT, rowcounts TEXT, totalrows INTEGER, claimedby TEXT, heartbeat REAL,
    doneat REAL, attempts INTEGER, PRIMARY KEY (run, unitno));
CREATE TABLE IF NOT EXISTS row (tbl TEXT, id INTEGER, data TEXT, PRIMARY KEY (tbl, id));
CREATE TABLE IF NOT EXISTS bti (tbl TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS seq (tbl TEXT PRIMARY KEY, value INTEGER);
"""


def _map(text: str) -> dict[str, int]:
    return {k: int(v) for k, v in (e.split("=") for e in text.split(";") if e)}


def _lob_limits() -> dict[tuple[str, str], tuple[str, int]]:
    """LOB-SIZE limits from the schema, so the fake rejects oversized LOBs like OpenEdge (error 11322)."""
    from pbgen import config
    from tools import schema_model as m
    from tools.gen_db_files import lob_size_bytes
    schema = m.load_expanded(config.SCHEMA_FILE)
    return {(t.name, f.name): (f.type, lob_size_bytes(f.lob.maxSize)) for t in schema.tables for f in t.lob_fields}


class FakeAgent:
    def __init__(self, path: str | Path, clock=time.time):
        self.path = str(path)
        self.clock = clock
        self._limits = None
        with self._db() as db:
            db.executescript(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    # ------------------------------------------------------------------ interface
    def request(self, op: str, timeout: float = 900.0, **kw) -> dict:
        fn = getattr(self, "_op_" + op, None)
        if fn is None:
            raise AgentError(f"unknown op {op!r}")
        db = self._db()
        try:
            db.execute("BEGIN IMMEDIATE")
            reply = fn(db, **kw)
            db.execute("COMMIT")
        except AgentError:
            db.execute("ROLLBACK")
            raise
        except Exception as e:  # noqa: BLE001 - mirror the agent's CATCH-all
            db.execute("ROLLBACK")
            raise AgentError(str(e)) from e
        finally:
            db.close()
        reply["ok"] = True
        return reply

    def close(self, wait: float = 0) -> None:
        pass

    def kill(self) -> None:
        pass

    # ------------------------------------------------------------------ helpers
    def _runs(self, db) -> list[dict]:
        return [json.loads(r[0]) for r in db.execute("SELECT data FROM run ORDER BY id")]

    def _put_run(self, db, run: dict) -> None:
        db.execute("INSERT OR REPLACE INTO run VALUES (?, ?)", (run["LoaderRunId"], json.dumps(run)))

    def _unit_dict(self, r) -> dict:
        return {"LoaderRunId": r[0], "UnitNo": r[1], "Phase": r[2], "UnitKind": r[3], "UnitStatus": r[4],
                "UnitSeed": r[5], "FirstIds": r[6], "RowCounts": r[7], "TotalRows": r[8],
                "ClaimedBy": r[9] or "", "Attempts": r[12]}

    def _bti(self, db) -> list[dict]:
        return [json.loads(r[0]) for r in db.execute("SELECT data FROM bti ORDER BY tbl")]

    # ------------------------------------------------------------------ ops
    def _op_hello(self, db) -> dict:
        return {"db": "fake", "version": "0.1.0", "loaderTables": True, "tables": 32, "L": 10_000_000}

    def _op_quit(self, db) -> dict:
        return {}

    def _op_plan(self, db, file: str) -> dict:
        data = json.loads(Path(file).read_text(encoding="utf-8"))
        run = data["LoaderRun"][0]
        if db.execute("SELECT 1 FROM run WHERE id = ?", (run["LoaderRunId"],)).fetchone():
            raise AgentError("run already exists")
        if any(r["RunStatus"] != "COMPLETE" for r in self._runs(db)):
            raise AgentError("another run is not complete")
        self._put_run(db, run)
        for u in data["LoaderUnit"]:
            db.execute("INSERT INTO unit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (u["LoaderRunId"], u["UnitNo"], u["Phase"], u["UnitKind"], "P", u["UnitSeed"],
                        u["FirstIds"], u["RowCounts"], u["TotalRows"], "", None, None, 0))
        return {"rows": 1 + len(data["LoaderUnit"])}

    def _op_state(self, db) -> dict:
        return {"runs": self._runs(db), "bti": self._bti(db)}

    def _op_claim(self, db, worker: str) -> dict:
        runs = [r for r in self._runs(db) if r["RunStatus"] != "COMPLETE"]
        if not runs:
            return {"unit": None, "reason": "run-complete" if self._runs(db) else "no-run"}
        run = runs[0]
        rid = run["LoaderRunId"]
        phase = db.execute("SELECT MIN(phase) FROM unit WHERE run = ? AND status IN ('P','C')", (rid,)).fetchone()[0]
        if phase is None:
            return {"unit": None, "reason": "run-complete"}
        stale = self.clock() - STALE_SECONDS
        r = db.execute("SELECT * FROM unit WHERE run = ? AND phase = ? AND (status = 'P' OR (status = 'C' AND "
                       "heartbeat < ?)) ORDER BY unitno LIMIT 1", (rid, phase, stale)).fetchone()
        if r is None:
            return {"unit": None, "reason": "phase-blocked"}
        now = self.clock()
        db.execute("UPDATE unit SET status='C', claimedby=?, heartbeat=?, attempts=attempts+1 "
                   "WHERE run=? AND unitno=?", (worker, now, rid, r[1]))
        if run["RunStatus"] == "PLANNED":
            run["RunStatus"] = "RUNNING"
            self._put_run(db, run)
        r = db.execute("SELECT * FROM unit WHERE run=? AND unitno=?", (rid, r[1])).fetchone()
        return {"unit": self._unit_dict(r)}

    def _op_heartbeat(self, db, run: int, unitNo: int, worker: str) -> dict:
        r = db.execute("SELECT status, claimedby FROM unit WHERE run=? AND unitno=?", (run, unitNo)).fetchone()
        if r is None or r[0] != "C" or r[1] != worker:
            raise AgentError("lost")
        db.execute("UPDATE unit SET heartbeat=? WHERE run=? AND unitno=?", (self.clock(), run, unitNo))
        return {}

    def _op_load(self, db, run: int, unitNo: int, worker: str, file: str) -> dict:
        t0 = time.perf_counter()
        tables = json.loads(Path(file).read_text(encoding="utf-8"))
        r = db.execute("SELECT status, claimedby, totalrows FROM unit WHERE run=? AND unitno=?",
                       (run, unitNo)).fetchone()
        if r is None or r[0] != "C" or r[1] != worker:
            raise AgentError("lost")
        if self._limits is None:
            self._limits = _lob_limits()
        import base64
        for (tbl, fld), (ftype, limit) in self._limits.items():
            for row in tables.get(tbl, []):
                v = row.get(fld)
                if v is not None and len(base64.b64decode(v) if ftype == "BLOB" else v.encode("utf-8")) > limit:
                    raise AgentError(f"Could not update large object segment during copy. (11322) [{tbl}.{fld}]")
        n = 0
        for tbl, rows in tables.items():
            for row in rows:
                db.execute("INSERT INTO row VALUES (?,?,?)", (tbl, row[tbl + "Id"], json.dumps(row, sort_keys=True)))
                if tbl == "BenchmarkTableInfo":
                    db.execute("INSERT INTO bti VALUES (?,?)", (row["TableName"], json.dumps(row)))
                n += 1
        if n != r[2]:
            raise AgentError(f"unit {unitNo} has {n} rows, expected {r[2]}")
        db.execute("UPDATE unit SET status='D', doneat=? WHERE run=? AND unitno=?", (self.clock(), run, unitNo))
        return {"rows": n, "ms": int((time.perf_counter() - t0) * 1000)}

    def _op_watermark(self, db, run: int) -> dict:
        rr = json.loads(db.execute("SELECT data FROM run WHERE id=?", (run,)).fetchone()[0])
        pos = rr.get("UnitsDone", 0)
        maxima: dict[str, int] = {}
        for u in db.execute("SELECT unitno, status, firstids, rowcounts FROM unit WHERE run=? AND unitno>? "
                            "ORDER BY unitno", (run, pos)):
            if u[1] != "D":
                break
            pos = u[0]
            first = _map(u[2])
            for t, c in _map(u[3]).items():
                maxima[t] = max(maxima.get(t, 0), first[t] + c - 1)
        if pos > rr.get("UnitsDone", 0):
            for t, mx in maxima.items():
                b = db.execute("SELECT data FROM bti WHERE tbl=?", (t,)).fetchone()
                if b is None:
                    continue
                b = json.loads(b[0])
                if mx > b["MaxId"]:
                    b["MaxId"] = mx
                    b["TableRowCount"] = mx
                    db.execute("UPDATE bti SET data=? WHERE tbl=?", (json.dumps(b), t))
            rr["UnitsDone"] = pos
            self._put_run(db, rr)
        return {"unitsDone": rr["UnitsDone"], "unitCount": rr["UnitCount"],
                "complete": rr["UnitsDone"] >= rr["UnitCount"]}

    def _op_finalize(self, db, run: int, diskBytes: int = 0) -> dict:
        rr = json.loads(db.execute("SELECT data FROM run WHERE id=?", (run,)).fetchone()[0])
        if rr.get("UnitsDone", 0) < rr["UnitCount"]:
            raise AgentError("run is not complete")
        for b in self._bti(db):
            db.execute("INSERT OR REPLACE INTO seq VALUES (?,?)", (b["TableName"], b["MaxId"]))
            b["ScaleFactor"] = round(float(rr["TargetScale"]), 2)
            db.execute("UPDATE bti SET data=? WHERE tbl=?", (json.dumps(b), b["TableName"]))
        if rr["RunStatus"] != "COMPLETE":
            rr.update(RunStatus="COMPLETE", MeasuredDiskBytes=diskBytes,
                      CompletedAt=dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"))
            self._put_run(db, rr)
        return {"status": rr["RunStatus"]}

    def _op_release(self, db, run: int, workers: list[str] | None = None, olderThanSec: int | None = None) -> dict:
        n = 0
        cutoff = self.clock() - olderThanSec if olderThanSec is not None else None
        for u in db.execute("SELECT unitno, claimedby, heartbeat FROM unit WHERE run=? AND status='C'",
                            (run,)).fetchall():
            if (workers and u[1] in workers) or (cutoff is not None and u[2] < cutoff):
                db.execute("UPDATE unit SET status='P', claimedby='' WHERE run=? AND unitno=?", (run, u[0]))
                n += 1
        return {"released": n}

    def _op_status(self, db) -> dict:
        runs = self._runs(db)
        out = {"run": runs[-1]["LoaderRunId"] if runs else None, "pending": 0, "claimed": 0, "done": 0,
               "doneRows": 0, "recentUnits": 0, "recentRows": 0, "claims": [], "runs": runs, "bti": self._bti(db)}
        if runs:
            recent = self.clock() - 300
            for u in db.execute("SELECT unitno, status, claimedby, heartbeat, doneat, totalrows FROM unit WHERE run=?",
                                (out["run"],)):
                if u[1] == "P":
                    out["pending"] += 1
                elif u[1] == "C":
                    out["claimed"] += 1
                    out["claims"].append({"unitNo": u[0], "claimedBy": u[2], "heartbeatAt": u[3]})
                else:
                    out["done"] += 1
                    out["doneRows"] += u[5]
                    if u[4] >= recent:
                        out["recentUnits"] += 1
                        out["recentRows"] += u[5]
        return out

    def _op_sample(self, db, table: str, k: int, maxId: int | None = None) -> dict:
        rows = [json.loads(r[0]) for r in db.execute("SELECT data FROM row WHERE tbl=? ORDER BY id", (table,))]
        rows = [r for r in rows if r["RandomInt1000"] == k and (maxId is None or r[table + "Id"] <= maxId)]
        return {"data": rows, "rows": len(rows)}

    # ------------------------------------------------------------------ test helpers
    def all_rows(self, table: str) -> list[dict]:
        db = self._db()
        try:
            return [json.loads(r[0]) for r in db.execute("SELECT data FROM row WHERE tbl=? ORDER BY id", (table,))]
        finally:
            db.close()

    def table_digest(self) -> dict[str, str]:
        import hashlib
        db = self._db()
        try:
            out = {}
            for (tbl,) in db.execute("SELECT DISTINCT tbl FROM row ORDER BY tbl").fetchall():
                h = hashlib.sha256()
                for (data,) in db.execute("SELECT data FROM row WHERE tbl=? ORDER BY id", (tbl,)):
                    h.update(data.encode())
                out[tbl] = h.hexdigest()
            return out
        finally:
            db.close()

    def set_heartbeat(self, run: int, unit_no: int, when: float) -> None:
        db = self._db()
        try:
            db.execute("UPDATE unit SET heartbeat=? WHERE run=? AND unitno=?", (when, run, unit_no))
        finally:
            db.close()
