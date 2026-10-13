"""app/jobstore.py -- SQLite-backed persistent job history (v2).

v1 kept finished jobs in an in-memory OrderedDict: a service restart wiped
the run history. v2 persists every job row -- including the full result
payload, zlib-compressed -- to a single SQLite file, so history survives
restarts and can be inspected across sessions.

Design notes
------------
* `sqlite3` from the standard library: no new dependency.
* One connection guarded by a lock (write volume is tiny: a few rows per
  simulation, progress writes throttled to >= 1 s).
* Results are stored compressed (zlib, level 6); corridor traces are the
  largest payloads (a few MB uncompressed, mostly repetitive coordinate
  arrays that compress >10x).
* Row budget: the table is pruned to the newest `max_rows` (default 500)
  jobs on every insert.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import zlib
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id       TEXT PRIMARY KEY,
    kind     TEXT NOT NULL,
    params   TEXT,
    status   TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    stage    TEXT,
    error    TEXT,
    trace    TEXT,
    result   BLOB,
    created  REAL,
    started  REAL,
    finished REAL
);
CREATE INDEX IF NOT EXISTS jobs_created_idx ON jobs(created DESC);
"""


def default_db_path() -> Path:
    """`EPTASK_DB` wins; otherwise `<service>/data/jobs.db`."""
    env = os.environ.get("EPTASK_DB", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "data" / "jobs.db"


class JobStore:
    def __init__(self, path: str | os.PathLike | None = None, max_rows: int = 500) -> None:
        self.path = Path(path) if path else default_db_path()
        self.max_rows = max_rows
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None

    # ---------------------------------------------------------------- connection
    def _conn(self) -> sqlite3.Connection:
        if self._db is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(str(self.path), check_same_thread=False)
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(_SCHEMA)
            self._db = db
        return self._db

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None

    # ---------------------------------------------------------------- writes
    def insert(self, job: dict) -> None:
        with self._lock:
            self._conn().execute(
                "INSERT OR REPLACE INTO jobs (id, kind, params, status, progress, stage, error, trace,"
                " result, created, started, finished) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (job["id"], job["kind"], json.dumps(job.get("params")), job["status"],
                 float(job.get("progress") or 0), job.get("stage"), job.get("error"),
                 job.get("trace"), None, job.get("created"), job.get("started"), job.get("finished")),
            )
            self._conn().commit()
            self._prune()

    def update(self, jid: str, **fields) -> None:
        if not fields:
            return
        cols, vals = [], []
        for k in ("status", "progress", "stage", "error", "trace", "started", "finished"):
            if k in fields:
                cols.append(f"{k} = ?")
                vals.append(fields[k])
        if not cols:
            return
        vals.append(jid)
        with self._lock:
            self._conn().execute(f"UPDATE jobs SET {', '.join(cols)} WHERE id = ?", vals)
            self._conn().commit()

    def store_result(self, jid: str, result) -> None:
        blob = zlib.compress(json.dumps(result, allow_nan=False, default=str).encode("utf-8"), 6)
        with self._lock:
            self._conn().execute(
                "UPDATE jobs SET result = ? WHERE id = ?", (sqlite3.Binary(blob), jid))
            self._conn().commit()

    def _prune(self) -> None:
        self._conn().execute(
            "DELETE FROM jobs WHERE id NOT IN "
            "(SELECT id FROM jobs ORDER BY created DESC LIMIT ?)", (self.max_rows,))

    # ---------------------------------------------------------------- reads
    def get(self, jid: str) -> dict | None:
        with self._lock:
            row = self._conn().execute(
                "SELECT id, kind, params, status, progress, stage, error, trace, result,"
                " created, started, finished FROM jobs WHERE id = ?", (jid,)).fetchone()
        if row is None:
            return None
        return self._row_to_job(row, with_result=True)

    def listing(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn().execute(
                "SELECT id, kind, params, status, progress, stage, error, trace, NULL,"
                " created, started, finished FROM jobs ORDER BY created DESC LIMIT ?",
                (limit,)).fetchall()
        return [self._row_to_job(r, with_result=False) for r in rows]

    def count(self) -> int:
        with self._lock:
            return int(self._conn().execute("SELECT COUNT(*) FROM jobs").fetchone()[0])

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _row_to_job(row: tuple, with_result: bool) -> dict:
        (jid, kind, params, status, progress, stage, error, trace, result,
         created, started, finished) = row
        out = dict(id=jid, kind=kind, params=json.loads(params) if params else None,
                   status=status, progress=progress, stage=stage, error=error,
                   created=created, started=started, finished=finished)
        if not with_result:
            out["result"] = None
            out["trace"] = None
            return out
        if result is not None:
            try:
                out["result"] = json.loads(zlib.decompress(bytes(result)).decode("utf-8"))
            except Exception:  # noqa: BLE001 -- a corrupt blob must not 500 the read
                out["result"] = None
                out["error"] = out["error"] or "stored result could not be decoded"
        else:
            out["result"] = None
        return out

    def info(self) -> dict:
        try:
            return {"path": str(self.path), "jobs_stored": self.count(),
                    "size_bytes": self.path.stat().st_size if self.path.exists() else 0}
        except Exception as exc:  # noqa: BLE001
            return {"path": str(self.path), "error": repr(exc)}
