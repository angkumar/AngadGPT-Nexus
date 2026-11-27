import asyncio
import hashlib
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.core.config import SCRIPTS_DIR, SCHEDULER_TIMEZONE
from backend.api.ws import WebSocketManager

logger = logging.getLogger("scheduler")

TRAINING_SCRIPT = "train_dummy.py"


def validate_cron(expression: str) -> None:
    """Raise ValueError when the expression is not a valid 5-field cron."""
    CronTrigger.from_crontab(expression, timezone=SCHEDULER_TIMEZONE)


@dataclass
class TaskStatus:
    id: str
    owner_id: str
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
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    @staticmethod
    def _task_key(task_id: str, owner_id: str) -> str:
        owner_key = hashlib.sha256(owner_id.encode("utf-8")).hexdigest()[:20]
        return f"{owner_key}:{task_id}"

    def schedule_training(self, task_id: str, cron: str, owner_id: str) -> None:
        validate_cron(cron)
        script_path = Path(SCRIPTS_DIR) / TRAINING_SCRIPT
        trigger = CronTrigger.from_crontab(cron, timezone=SCHEDULER_TIMEZONE)
        task_key = self._task_key(task_id, owner_id)
        self.tasks[task_key] = TaskStatus(
            id=task_id, owner_id=owner_id, name="dummy_train", schedule=cron
        )
        self.scheduler.add_job(
            lambda: asyncio.run(self._run_script(task_key, script_path)),
            trigger=trigger,
            id=task_key,
            replace_existing=True,
        )

    async def _run_script(self, task_key: str, script_path: Path) -> None:
        status = self.tasks.get(task_key)
        if not status:
            return
        task_id = status.id
        owner_id = status.owner_id
        status.last_status = "running"
        status.last_run = datetime.now(timezone.utc).isoformat()
        status.last_output = ""
        await self.ws_manager.broadcast(
            {"type": "task", "task_id": task_id, "status": "running"}, owner_id
        )

        exit_code = -1
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            if process.stdout:
                async for line in process.stdout:
                    text = line.decode("utf-8", errors="ignore")
                    status.last_output += text
                    await self.ws_manager.broadcast(
                        {"type": "log", "task_id": task_id, "line": text}, owner_id
                    )
            exit_code = await process.wait()
        except Exception as exc:  # Keep the task status truthful instead of crashing.
            logger.exception("Task %s failed to run", task_id)
            status.last_output += f"{exc}\n"
            await self.ws_manager.broadcast(
                {"type": "log", "task_id": task_id, "line": f"error: {exc}\n"}, owner_id
            )

        status.last_status = "success" if exit_code == 0 else "failed"
        await self.ws_manager.broadcast(
            {"type": "task", "task_id": task_id, "status": status.last_status}, owner_id
        )

    def start_now(self, task_id: str, owner_id: str) -> bool:
        """Queue a task on the running event loop without blocking the request."""
        task_key = self._task_key(task_id, owner_id)
        task = self.tasks.get(task_key)
        if not task:
            return False
        if task.last_status == "running":
            return True
        task.last_status = "running"
        task.last_run = datetime.now(timezone.utc).isoformat()
        asyncio.create_task(self._run_script(task_key, Path(SCRIPTS_DIR) / TRAINING_SCRIPT))
        return True

    def list_tasks(self, owner_id: str) -> Dict[str, TaskStatus]:
        return {
            task.id: task
            for task in self.tasks.values()
            if task.owner_id == owner_id
        }
