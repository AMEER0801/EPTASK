#!/usr/bin/env bash
# Start the eptask-api service on port 8100 (auto-restart on file change via --reload in dev)
cd "$(dirname "$0")"
PORT="${EPTASK_PORT:-8100}"
if [ "${EPTASK_DEV:-0}" = "1" ]; then
  exec python3 -m uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload
fi
exec python3 -m uvicorn main:app --host 0.0.0.0 --port "$PORT" --workers 1
