#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x ".venv311/bin/python" ]; then
  echo "Missing .venv311. Create it and install backend dependencies first:" >&2
  echo "  python3 -m venv .venv311" >&2
  echo "  .venv311/bin/python -m pip install -r backend/requirements.txt" >&2
  exit 1
fi

exec .venv311/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
