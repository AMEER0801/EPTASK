#!/usr/bin/env bash
# ensure_and_run.sh -- boot-robust launcher for the eptask-api service.
# Used by the platform's mini-services flow (bun run dev). Picks the first
# Python that already has the service dependencies; on a fresh machine it
# creates a venv and installs requirements (first boot only, a few minutes
# because of the PyTorch CPU wheel). Start it manually with: bash run.sh
set -e
cd "$(dirname "$0")"

deps_ok() { "$1" -c "import fastapi, uvicorn, onnxruntime, networkx, numpy" 2>/dev/null; }

PY="${EPTASK_PYTHON:-}"
if [ -z "$PY" ] || ! deps_ok "$PY" 2>/dev/null; then
  PY=""
  for cand in /home/z/.venv/bin/python python3 python; do
    if command -v "$cand" >/dev/null 2>&1 && deps_ok "$cand"; then PY="$cand"; break; fi
  done
fi

if [ -z "$PY" ]; then
  echo "[eptask-api] no Python with the service deps found -- creating /home/z/.venv (first boot only)"
  python3 -m venv /home/z/.venv
  /home/z/.venv/bin/pip install --quiet -r requirements.txt
  PY=/home/z/.venv/bin/python
fi

echo "[eptask-api] starting with $($PY -V 2>&1) at $($PY -c 'import sys; print(sys.executable)')"
exec "$PY" -m uvicorn main:app --host 0.0.0.0 --port "${EPTASK_PORT:-8100}"
