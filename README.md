# AngadGPT Nexus

A local, high-performance agentic web app powered by a local ai (swappable), with scheduling, memory, tools, and a modern dashboard.

## Features
- Agentic loop: input → LLM → tool → feedback → next action
- Memory persistence with SQLite + summarization
- Modular tool system with JSON schemas
- Calendar tool (local by default, swappable to Google Calendar)
- File tool for workspace file listing/reading (safe path sandbox)
- Cron-style scheduling (overnight training)
- Real-time log streaming via WebSocket
- Optional auth token

## Project Layout
- `backend/` FastAPI app, agent core, tools, scheduler
- `frontend/` Vite + React + Tailwind UI
- `scripts/` training and batch tasks
- `memory/` SQLite DB and exported logs

## Backend Setup
1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

2. Create a `.env` file (see `.env.example`).
3. Run the API:

```bash
scripts/dev_backend.sh
```

The API runs at `http://localhost:8000` with routes under `/api`.

Use the script instead of a bare `uvicorn ...` command. It pins execution to
the repo virtual environment, so Homebrew or system Python installs cannot take
over accidentally.

## Frontend Setup
1. Install dependencies:

```bash
cd frontend
npm install
```

2. Run the dev server:

```bash
npm run dev
```

The UI runs at `http://localhost:5173` on the backend machine and is also
available to devices on the same Wi-Fi at `http://<backend-machine-ip>:5173`.
It calls the API at `/api` by default.

To run both backend and frontend from the repo root:

```bash
scripts/dev.sh
```

## TinyLLM
- Set `TINYLLM_MODEL_PATH` in `.env` to your local model file.
- Install your TinyLLM Python package or swap the provider in `backend/agent/llm.py`.

## LM Studio (OpenAI-Compatible API)
If you run LM Studio’s local server, set:
- `LMSTUDIO_BASE_URL` (default `http://127.0.0.1:1234`)
- `LMSTUDIO_MODEL` (e.g. `gemma-3-4b`)

## Scheduling
The overnight training task is scheduled by default at `2:00 AM` in `America/Detroit`.
You can reschedule via `POST /api/tasks/schedule`.

## Calendar Integration
The default calendar provider is local SQLite, fully functional. To swap to Google Calendar:
- Place your OAuth `credentials.json` at `memory/credentials.json`.
- Set `ANGADGPT_CALENDAR_PROVIDER=google` in `.env`.
- Optional: set `ANGADGPT_GOOGLE_CALENDAR_ID` (default `primary`).
- First use will open a browser for OAuth consent and store `memory/token.json`.

## File Tool
Use `POST /api/tools` to inspect schemas and `POST /api/agent/step` to ask the agent to read or summarize files.
Set `ANGADGPT_WORKSPACE_ROOT` in `.env` to restrict file access to a single folder.

## Script Tool
The `scripts` tool can run `.py` or `.sh` scripts inside the workspace root only.
Example tool call:
```json
{"action":"tool","tool_name":"scripts","args":{"path":"myrepo/scripts/train.py","args":["--epochs","1"]}}
```

## Search + Repo Scan
- `repos` tool lists git repositories in the workspace root.
- `search` tool wraps ripgrep (`rg`) for fast text search.
Examples:
```json
{"action":"tool","tool_name":"repos","args":{"include_non_git":false}}
{"action":"tool","tool_name":"search","args":{"pattern":"TODO","path":"myrepo"}}
```

## Workspace Tool (Create/Write)
The `workspace` tool can create folders and write files within the workspace root.
Examples:
```json
{"action":"tool","tool_name":"workspace","args":{"action":"mkdir","path":"NewRepo"}}\n{"action":"tool","tool_name":"workspace","args":{"action":"write","path":"NewRepo/README.md","content":"# NewRepo\\n"}}\n```

## Auth
Set `ANGADGPT_AUTH_TOKEN` in `.env` to require a Bearer token for API access.

## Notes
- Logs stream to the UI via WebSocket at `/api/ws`.
- The mock LLM fallback is used if TinyLLM is not available.
