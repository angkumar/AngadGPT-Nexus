import subprocess
from pathlib import Path
from typing import Any, Dict, List

from backend.core.config import WORKSPACE_ROOT
from .base import Tool


class SearchTool(Tool):
    name = "search"
    description = "Search text within the workspace using ripgrep"
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string"},
            "max_results": {"type": "integer"},
        },
        "required": ["pattern"],
    }

    def _resolve(self, path: str) -> Path:
        candidate = (WORKSPACE_ROOT / path).resolve()
        if WORKSPACE_ROOT not in candidate.parents and candidate != WORKSPACE_ROOT:
            raise ValueError("Path is outside allowed workspace")
        return candidate

    def run(self, **kwargs) -> Dict[str, Any]:
        pattern = kwargs.get("pattern", "")
        path = kwargs.get("path", ".")
        max_results = int(kwargs.get("max_results", 200))
        target = self._resolve(path)

        cmd = [
            "rg",
            "-n",
            "--no-heading",
            "--max-count",
            str(max_results),
            pattern,
            str(target),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode not in (0, 1):
            return {"error": result.stderr.strip()}
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        return {"matches": lines}

