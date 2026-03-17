import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.core.config import SCRIPTS_DIR, SCHEDULER_TIMEZONE
from backend.api.ws import WebSocketManager

logger = logging.getLogger("scheduler")


@dataclass
class TaskStatus:
    id: str
    name: str
    schedule: str
    last_run: Optional[str] = None
    last_status: Optional[str] = None
    last_output: str = ""


class TaskRunner:
    def __init__(self, ws_manager: WebSocketManager) -> None:
        self.ws_manager = ws_manager
        self.scheduler = BackgroundScheduler(timezone=SCHEDULER_TIMEZONE)
        self.tasks: Dict[str, TaskStatus] = {}

    def start(self) -> None:
        self.scheduler.start()

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)

    def schedule_training(self, task_id: str, cron: str) -> None:
        script_path = Path(SCRIPTS_DIR) / "train_dummy.py"
        trigger = CronTrigger.from_crontab(cron, timezone=SCHEDULER_TIMEZONE)
        self.tasks[task_id] = TaskStatus(id=task_id, name="dummy_train", schedule=cron)
        self.scheduler.add_job(
            lambda: asyncio.run(self._run_script(task_id, script_path)),
            trigger=trigger,
            id=task_id,
            replace_existing=True,
        )

    async def _run_script(self, task_id: str, script_path: Path) -> None:
        status = self.tasks.get(task_id)
        if not status:
            return
        status.last_status = "running"
        status.last_output = ""
        await self.ws_manager.broadcast(
            {"type": "task", "task_id": task_id, "status": "running"}
        )

        process = await asyncio.create_subprocess_exec(
            "python",
            str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        assert process.stdout
        async for line in process.stdout:
            text = line.decode("utf-8", errors="ignore")
            status.last_output += text
            await self.ws_manager.broadcast(
                {
                    "type": "log",
                    "task_id": task_id,
                    "line": text,
                }
            )

        code = await process.wait()
        status.last_status = "success" if code == 0 else "failed"
        await self.ws_manager.broadcast(
            {
                "type": "task",
                "task_id": task_id,
                "status": status.last_status,
            }
        )

    def list_tasks(self) -> Dict[str, TaskStatus]:
        return self.tasks

    def run_now(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if not task:
            return
        script_path = Path(SCRIPTS_DIR) / "train_dummy.py"
        asyncio.run(self._run_script(task_id, script_path))
