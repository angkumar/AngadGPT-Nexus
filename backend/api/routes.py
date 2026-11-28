import re
import threading
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from backend.agent.agent import Agent
from backend.agent.llm import LLMProviderError
from backend.core.auth import authenticate_token, require_auth
from backend.core.config import USER_DATA_DIR
from backend.api.ws import WebSocketManager
from backend.scheduler.runner import TaskRunner, validate_cron
from backend.tools.calendar import CalendarTool

router = APIRouter()

ws_manager = WebSocketManager()
task_runner = TaskRunner(ws_manager)

# Each account gets its own memory, calendar and workspace under USER_DATA_DIR.
_agents: Dict[str, Agent] = {}
_agents_lock = threading.Lock()


def _user_dir(user_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", user_id) or "unknown"
    return USER_DATA_DIR / safe_id


def get_agent(user_id: str) -> Agent:
    with _agents_lock:
        cached = _agents.get(user_id)
        if cached is not None:
            return cached

        user_dir = _user_dir(user_id)
        workspace = user_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        memory_db = str(user_dir / "memory.sqlite3")
        agent = Agent(
            memory_db_path=memory_db,
            workspace_root=workspace,
            calendar_db_path=memory_db,
        )
        _agents[user_id] = agent
        return agent


def get_calendar_tool(user_id: str) -> CalendarTool:
    tool = get_agent(user_id).tools.get("calendar")
    if tool is None:
        raise HTTPException(status_code=500, detail="Calendar tool is unavailable.")
    return tool


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    images: List[str] = Field(default_factory=list)


# Groq accepts at most three images per request, each capped at 20MB.
MAX_IMAGES = 3
MAX_IMAGE_CHARS = 20 * 1024 * 1024
IMAGE_DATA_URL = re.compile(r"^data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+")


def _validate_images(images: List[str]) -> None:
    if len(images) > MAX_IMAGES:
        raise HTTPException(
            status_code=400, detail=f"Attach at most {MAX_IMAGES} images per message."
        )
    for image in images:
        if not IMAGE_DATA_URL.match(image or ""):
            raise HTTPException(
                status_code=400,
                detail="Images must be base64 data URLs such as data:image/png;base64,...",
            )
        if len(image) > MAX_IMAGE_CHARS:
            raise HTTPException(
                status_code=400, detail="Each image must be smaller than 20MB."
            )


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok"}


# Sync handlers run in FastAPI's threadpool, so the blocking model call no
# longer freezes the event loop for the whole app.
@router.post("/agent/step")
def agent_step(payload: AgentRequest, user_id: str = Depends(require_auth)) -> Dict[str, Any]:
    _validate_images(payload.images)
    try:
        return get_agent(user_id).step(payload.message, images=payload.images)
    except LLMProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/memory")
def memory(user_id: str = Depends(require_auth)) -> Dict[str, Any]:
    current = get_agent(user_id)
    return {
        "summary": current.memory.get_summary(),
        "messages": [m.__dict__ for m in current.memory.list_messages(100)],
    }


@router.post("/memory/reset")
def reset_memory(user_id: str = Depends(require_auth)) -> Dict[str, bool]:
    get_agent(user_id).reset_conversation()
    return {"reset": True}


@router.post("/calendar")
def calendar(
    payload: Dict[str, Any], user_id: str = Depends(require_auth)
) -> Dict[str, Any]:
    if not payload.get("action"):
        raise HTTPException(status_code=400, detail="`action` is required.")
    try:
        return get_calendar_tool(user_id).run(**payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Calendar error: {exc}") from exc


@router.get("/tasks")
def tasks(user_id: str = Depends(require_auth)) -> Dict[str, Any]:
    return {
        "tasks": {
            task_id: {
                "id": task.id,
                "name": task.name,
                "schedule": task.schedule,
                "last_run": task.last_run,
                "last_status": task.last_status,
                "last_output": task.last_output,
            }
            for task_id, task in task_runner.list_tasks(user_id).items()
        }
    }


@router.get("/tools")
def tools(user_id: str = Depends(require_auth)) -> Dict[str, Any]:
    current = get_agent(user_id)
    return {
        "tools": {
            name: {
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for name, tool in current.tools.items()
        }
    }


@router.post("/tasks/schedule")
def schedule_task(
    payload: Dict[str, Any], user_id: str = Depends(require_auth)
) -> Dict[str, Any]:
    task_id = payload.get("task_id", "overnight_train")
    cron = payload.get("cron", "0 2 * * *")
    try:
        validate_cron(cron)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid cron expression: {exc}"
        ) from exc
    task_runner.schedule_training(task_id, cron, user_id)
    return {"scheduled": True, "task_id": task_id, "cron": cron}


@router.post("/tasks/run")
async def run_task(
    payload: Dict[str, Any], user_id: str = Depends(require_auth)
) -> Dict[str, Any]:
    task_id = payload.get("task_id", "overnight_train")
    if not task_runner.start_now(task_id, user_id):
        raise HTTPException(status_code=404, detail=f"Unknown task: {task_id}")
    return {"started": True, "task_id": task_id}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    try:
        user_id = authenticate_token(websocket.query_params.get("token"))
    except HTTPException:
        await websocket.close(code=4401)
        return
    await ws_manager.connect(websocket, user_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket, user_id)


def start_scheduler() -> None:
    task_runner.start()
    if "overnight_train" not in task_runner.list_tasks("system"):
        task_runner.schedule_training("overnight_train", "0 2 * * *", "system")


def stop_scheduler() -> None:
    task_runner.shutdown()
