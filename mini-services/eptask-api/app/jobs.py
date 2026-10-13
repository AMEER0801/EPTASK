"""app/jobs.py -- async job runner with persistent history (v2).

Every simulation endpoint submits a job and returns a job id; the client
polls GET /api/jobs/{id}. Jobs run on a 2-worker thread pool (the sims are
numpy-bound). v1 kept the history in an in-memory LRU; v2 mirrors every job
into a SQLite store (app/jobstore.py) so history -- including full results --
survives restarts. The in-memory dict stays the hot cache for running and
recently finished jobs; older jobs are served from the store.
"""
from __future__ import annotations

import itertools
import threading
import time
import traceback
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from .jobstore import JobStore

_LOCK = threading.Lock()
_JOBS: "OrderedDict[str, dict]" = OrderedDict()
_EXEC = ThreadPoolExecutor(max_workers=2, thread_name_prefix="eptask-sim")
_SEQ = itertools.count(1)
_MEMORY_JOBS = 40          # hot cache size for full payloads
_LAST_WRITE: dict[str, float] = {}   # job id -> last progress write (throttle)

STORE = JobStore()


def _gc() -> None:
    while len(_JOBS) > _MEMORY_JOBS:
        jid, _ = _JOBS.popitem(last=False)
        _LAST_WRITE.pop(jid, None)


def submit(kind: str, params: dict, fn) -> str:
    jid = f"j{next(_SEQ):05d}-{int(time.time())}"
    job = dict(id=jid, kind=kind, params=params, status="queued", progress=0.0,
               stage="queued", result=None, error=None, created=time.time(),
               started=None, finished=None)
    with _LOCK:
        _JOBS[jid] = job
        _gc()
    try:
        STORE.insert(job)
    except Exception:  # noqa: BLE001 -- persistence must never kill a run
        pass

    def run():
        with _LOCK:
            job["status"], job["started"] = "running", time.time()
        STORE.update(jid, status="running", started=job["started"])
        try:
            res = fn(lambda f, s=None: _progress(jid, f, s))
            with _LOCK:
                job["result"] = res
                job["status"], job["progress"], job["stage"] = "done", 1.0, "done"
            STORE.update(jid, status="done", progress=1.0, stage="done",
                         finished=time.time())
            STORE.store_result(jid, res)
        except Exception as exc:  # noqa: BLE001 -- surfaced verbatim to the client
            with _LOCK:
                job["status"] = "error"
                job["error"] = f"{type(exc).__name__}: {exc}"
                job["trace"] = traceback.format_exc(limit=6)
            STORE.update(jid, status="error", error=job["error"], trace=job["trace"],
                         finished=time.time())
        finally:
            with _LOCK:
                job["finished"] = time.time()

    _EXEC.submit(run)
    return jid


def _progress(jid: str, frac: float, stage: str | None) -> None:
    db_write = None
    with _LOCK:
        job = _JOBS.get(jid)
        if job and job["status"] == "running":
            job["progress"] = max(0.0, min(1.0, float(frac)))
            if stage:
                job["stage"] = stage
            # throttle DB progress writes to ~1/s
            now = time.time()
            if now - _LAST_WRITE.get(jid, 0.0) >= 1.0:
                _LAST_WRITE[jid] = now
                db_write = (job["progress"], job["stage"])
            else:
                db_write = None
    if db_write:
        STORE.update(jid, progress=db_write[0], stage=db_write[1])


def get(jid: str) -> dict | None:
    with _LOCK:
        if jid in _JOBS:
            return dict(_JOBS[jid])
    return STORE.get(jid)          # None if unknown everywhere


def listing() -> list[dict]:
    strip = lambda j: {k: v for k, v in j.items() if k not in ("result", "trace")}
    with _LOCK:
        mem = [strip(dict(j)) for j in reversed(list(_JOBS.values()))]
    hist = [strip(j) for j in STORE.listing(limit=100)]
    seen, merged = set(), []
    for j in mem + hist:            # memory first (fresher), then persisted rows
        if j["id"] in seen:
            continue
        seen.add(j["id"])
        merged.append(j)
    return merged


def store_info() -> dict:
    return STORE.info()
