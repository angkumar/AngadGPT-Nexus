from typing import Any, Dict

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.agent.agent import Agent
from backend.core.auth import require_auth
from backend.api.ws import WebSocketManager
from backend.scheduler.runner import TaskRunner
from backend.tools.calendar import CalendarTool

router = APIRouter()

ws_manager = WebSocketManager()
agent: Agent | None = None
task_runner = TaskRunner(ws_manager)


def get_agent() -> Agent:
    global agent
    if agent is None:
        agent = Agent()
    return agent


def get_calendar_tool() -> CalendarTool:
    return get_agent().tools.get("calendar", CalendarTool())


class AgentRequest(BaseModel):
    message: str


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok"}


@router.post("/agent/step", dependencies=[Depends(require_auth)])
async def agent_step(payload: AgentRequest) -> Dict[str, Any]:
    return get_agent().step(payload.message)


@router.get("/memory", dependencies=[Depends(require_auth)])
async def memory() -> Dict[str, Any]:
    agent = get_agent()
    return {
        "summary": agent.memory.get_summary(),
        "messages": [m.__dict__ for m in agent.memory.list_messages(100)],
    }


@router.post("/calendar", dependencies=[Depends(require_auth)])
async def calendar(payload: Dict[str, Any]) -> Dict[str, Any]:
    return get_calendar_tool().run(**payload)


@router.get("/tasks", dependencies=[Depends(require_auth)])
async def tasks() -> Dict[str, Any]:
    return {
        "tasks": {task_id: task.__dict__ for task_id, task in task_runner.list_tasks().items()}
    }

@router.get("/tools", dependencies=[Depends(require_auth)])
async def tools() -> Dict[str, Any]:
    agent = get_agent()
    return {
        "tools": {
            name: {
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for name, tool in agent.tools.items()
        }
    }


@router.post("/tasks/schedule", dependencies=[Depends(require_auth)])
async def schedule_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    task_id = payload.get("task_id", "overnight_train")
    cron = payload.get("cron", "0 2 * * *")
    task_runner.schedule_training(task_id, cron)
    return {"scheduled": True, "task_id": task_id, "cron": cron}

@router.post("/tasks/run", dependencies=[Depends(require_auth)])
async def run_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    task_id = payload.get("task_id", "overnight_train")
    task_runner.run_now(task_id)
    return {"started": True, "task_id": task_id}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


def start_scheduler() -> None:
    task_runner.start()
    if "overnight_train" not in task_runner.list_tasks():
        task_runner.schedule_training("overnight_train", "0 2 * * *")
