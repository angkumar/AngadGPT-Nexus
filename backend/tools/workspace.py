from pathlib import Path
from typing import Any, Dict
import difflib

from backend.core.config import WORKSPACE_ROOT
from .base import Tool


class WorkspaceTool(Tool):
    name = "workspace"
    description = "Create folders, read, write, append, or diff files within the workspace root"
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "read", "write", "append", "mkdir", "diff"]},
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["action", "path"],
    }

    def _resolve(self, path: str) -> Path:
        candidate = (WORKSPACE_ROOT / path).resolve()
        if WORKSPACE_ROOT not in candidate.parents and candidate != WORKSPACE_ROOT:
            raise ValueError("Path is outside allowed workspace")
        return candidate

    def run(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action")
        path = kwargs.get("path", "")
        target = self._resolve(path)

        if action == "list":
            items = [p.name for p in target.iterdir()]
            return {"items": items}

        if action == "read":
            content = target.read_text(encoding="utf-8")
            return {"path": str(target.relative_to(WORKSPACE_ROOT)), "content": content}

        if action == "write":
            content = kwargs.get("content", "")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {"path": str(target.relative_to(WORKSPACE_ROOT)), "written": True}

        if action == "append":
            content = kwargs.get("content", "")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as handle:
                handle.write(content)
            return {"path": str(target.relative_to(WORKSPACE_ROOT)), "appended": True}

        if action == "mkdir":
            target.mkdir(parents=True, exist_ok=True)
            return {"path": str(target.relative_to(WORKSPACE_ROOT)), "created": True}

        if action == "diff":
            content = kwargs.get("content", "")
            if target.exists():
                before = target.read_text(encoding="utf-8").splitlines()
            else:
                before = []
            after = content.splitlines()
            diff = "\n".join(
                difflib.unified_diff(
                    before,
                    after,
                    fromfile=str(target),
                    tofile=str(target),
                    lineterm="",
                )
            )
            return {"path": str(target.relative_to(WORKSPACE_ROOT)), "diff": diff}

        return {"error": "Unsupported action"}

