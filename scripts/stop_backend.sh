#!/usr/bin/env bash
set -euo pipefail

PIDS="$(lsof -ti tcp:8000 -sTCP:LISTEN || true)"

if [ -z "$PIDS" ]; then
  echo "No process is listening on port 8000."
  exit 0
fi

echo "Stopping process(es) listening on port 8000:"
lsof -nP -iTCP:8000 -sTCP:LISTEN || true

kill $PIDS
echo "Stopped backend port 8000."
