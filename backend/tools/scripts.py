import subprocess
from pathlib import Path
from typing import Any, Dict, List

from backend.core.config import WORKSPACE_ROOT
from .base import Tool


ALLOWED_EXTENSIONS = {".py", ".sh"}


class ScriptTool(Tool):
    name = "scripts"
    description = "Run scripts within the allowed workspace"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "args": {"type": "array", "items": {"type": "string"}},
            "timeout": {"type": "integer", "description": "seconds"},
        },
        "required": ["path"],
    }

    def _resolve(self, path: str) -> Path:
        candidate = (WORKSPACE_ROOT / path).resolve()
        if WORKSPACE_ROOT not in candidate.parents and candidate != WORKSPACE_ROOT:
            raise ValueError("Path is outside allowed workspace")
        if candidate.suffix not in ALLOWED_EXTENSIONS:
            raise ValueError("Script type not allowed")
        if not candidate.exists():
            raise FileNotFoundError("Script not found")
        return candidate

    def run(self, **kwargs) -> Dict[str, Any]:
        path = kwargs.get("path", "")
        args: List[str] = kwargs.get("args") or []
        timeout = int(kwargs.get("timeout", 300))
        script_path = self._resolve(path)

        if script_path.suffix == ".py":
            cmd = ["python", str(script_path)] + args
        else:
            cmd = ["bash", str(script_path)] + args

        result = subprocess.run(
            cmd,
            cwd=str(script_path.parent),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "path": str(script_path.relative_to(WORKSPACE_ROOT)),
            "returncode": result.returncode,
            "stdout": result.stdout[-8000:],
            "stderr": result.stderr[-8000:],
        }

