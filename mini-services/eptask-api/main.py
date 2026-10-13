"""eptask-api -- live backend for the EPtask operations console.

Serves the ORIGINAL notebook modules (core/) over HTTP: corridor.run_trial
road-scale simulations, env.VECEnv cell simulations driven by the shipped
ONNX policy exports, and the paired outage study. Assets come from the
notebook's own demo_bundle.

Run:  bash run.sh            (or: uvicorn main:app --host 0.0.0.0 --port 8100)
"""
from __future__ import annotations

import logging
import os
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth import auth_required
from app.routes import api
from app.state import STATE

logging.basicConfig(level=os.environ.get("EPTASK_LOG_LEVEL", "INFO"),
                    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("eptask-api")

app = FastAPI(
    title="EPtask API",
    version="2.0.0",
    description=("Live execution of the EPtask V7.1 notebook logic (corridor N1, VEC cell, "
                 "C3 outage study) plus v2 upgrades: real OpenStreetMap road graphs, "
                 "side-by-side warning-network comparison, persistent job history and an "
                 "optional API-key auth layer."),
)

# Same-origin in production (Caddy gateway); permissive CORS helps local dev.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], expose_headers=["X-Process-Time"])


@app.on_event("startup")
def _startup() -> None:
    t0 = time.time()
    STATE.load()
    from app import jobs
    log.info("notebook assets loaded in %.2fs (graph %d nodes, %d latency arms)",
             time.time() - t0, STATE.catalogue()["graph_nodes"], len(STATE.latency))
    log.info("auth: %s | job history: %s",
             "API-key required (EPTASK_API_KEY set)" if auth_required() else "disabled (local mode)",
             jobs.store_info())


@app.middleware("http")
async def _timing(request: Request, call_next):
    rid = uuid.uuid4().hex[:12]
    t0 = time.time()
    try:
        from app.auth import guard as auth_guard
        response = await auth_guard(request, call_next)
    except Exception as exc:  # noqa: BLE001
        log.error("%s %s rid=%s failed: %r", request.method, request.url.path, rid, exc)
        return JSONResponse(status_code=500, content={"detail": "internal error", "request_id": rid})
    response.headers["X-Process-Time"] = f"{(time.time() - t0) * 1000:.1f}ms"
    response.headers["X-Request-Id"] = rid
    return response


app.include_router(api)


@app.get("/health")
def root_health():
    return {"status": "ok", "service": "eptask-api", **STATE.catalogue()}
