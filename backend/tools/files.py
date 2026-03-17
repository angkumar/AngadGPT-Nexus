from pathlib import Path
from typing import Any, Dict, List

from backend.core.config import WORKSPACE_ROOT
from .base import Tool


class FileTool(Tool):
    name = "files"
    description = "Read or list files within the workspace"
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "read"]},
            "path": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["action"],
    }

    def _resolve(self, path: str) -> Path:
        candidate = (WORKSPACE_ROOT / path).resolve()
        if WORKSPACE_ROOT not in candidate.parents and candidate != WORKSPACE_ROOT:
            raise ValueError("Path is outside allowed workspace")
        return candidate

    def run(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action")
        if action == "list":
            target = self._resolve(kwargs.get("path", "."))
            items = [str(p.relative_to(WORKSPACE_ROOT)) for p in target.iterdir()]
            return {"items": items}
        if action == "read":
            target = self._resolve(kwargs.get("path", ""))
            limit = int(kwargs.get("limit", 5000))
            content = target.read_text(encoding="utf-8")[:limit]
            return {"path": str(target.relative_to(WORKSPACE_ROOT)), "content": content}
        return {"error": "Unsupported action"}
