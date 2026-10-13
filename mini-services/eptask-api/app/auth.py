"""app/auth.py -- optional API-key authentication layer (v2).

v1 performed no authentication at all (documented limitation #4). v2 adds a
lightweight, dependency-free identity gate sized for a research console:

* Set ``EPTASK_API_KEY`` to a non-empty string to REQUIRE that every
  ``/api/*`` request carries a matching key -- either the ``X-API-Key``
  header or an ``api_key`` query parameter (needed for ``<img>`` sources
  such as /api/figures, which cannot set headers).
* Leave it unset for local single-user mode: the gate is fully transparent
  and /api/meta reports ``auth_required: false``.
* /health, /docs and OpenAPI stay open in both modes so orchestrators and
  humans can see whether the service is alive.
* Comparison is constant-time (hmac.compare_digest) and failures are logged
  with the request id, never with the supplied key.
"""
from __future__ import annotations

import hmac
import logging
import os
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger("eptask-api.auth")

# Paths that never require a key (liveness + human docs).
OPEN_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json")


def api_key() -> str:
    """The configured key, read per-request so tests/deployment can toggle it
    without a process restart."""
    return os.environ.get("EPTASK_API_KEY", "").strip()


def auth_required() -> bool:
    return bool(api_key())


def _supplied(request: Request) -> str:
    key = request.headers.get("X-API-Key", "")
    if key:
        return key
    return request.query_params.get("api_key", "")


async def guard(request: Request, call_next):
    required = api_key()
    if required:
        path = request.url.path
        opened = any(path == p or path.startswith(p + "/") or path.startswith(p)
                     for p in OPEN_PREFIXES)
        if not opened:
            supplied = _supplied(request)
            if not supplied or not hmac.compare_digest(supplied.encode(), required.encode()):
                rid = uuid.uuid4().hex[:12]
                log.warning("401 rid=%s %s %s (missing or invalid API key)", rid,
                            request.method, path)
                return JSONResponse(
                    status_code=401,
                    content={"detail": "missing or invalid API key: send it in the "
                                       "X-API-Key header (or ?api_key= for image URLs). "
                                       "The key is configured via the EPTASK_API_KEY "
                                       "environment variable.",
                             "request_id": rid})
    return await call_next(request)
