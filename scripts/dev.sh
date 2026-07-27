#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

backend_is_healthy() {
  curl -fsS --max-time 1 http://127.0.0.1:8000/api/health >/dev/null 2>&1
}

backend_is_listening() {
  lsof -ti tcp:8000 -sTCP:LISTEN >/dev/null 2>&1
}

show_backend_listener() {
  lsof -nP -iTCP:8000 -sTCP:LISTEN >&2 || true
}

cleanup() {
  if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID"
  fi
}
trap cleanup EXIT INT TERM

if backend_is_healthy; then
  echo "Backend already running at http://127.0.0.1:8000"
elif backend_is_listening; then
  echo "Port 8000 is already in use, but the backend health check is failing." >&2
  show_backend_listener
  echo "Run ./scripts/stop_backend.sh, then run ./scripts/dev.sh again." >&2
  exit 1
else
  scripts/dev_backend.sh &
  BACKEND_PID=$!

  echo "Waiting for backend at http://127.0.0.1:8000..."
  BACKEND_READY=false
  for _ in {1..30}; do
    if backend_is_healthy; then
      BACKEND_READY=true
      break
    fi

    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
      echo "Backend exited before it became ready." >&2
      wait "$BACKEND_PID"
      exit 1
    fi

    sleep 1
  done

  if [ "$BACKEND_READY" != true ]; then
    echo "Backend did not become ready within 30 seconds." >&2
    exit 1
  fi
fi

echo "Backend ready. Starting frontend..."
cd frontend
npm run dev -- --open
