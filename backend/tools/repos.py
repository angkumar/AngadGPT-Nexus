from pathlib import Path
from typing import Any, Dict, List

from backend.core.config import WORKSPACE_ROOT
from .base import Tool


class RepoScanTool(Tool):
    name = "repos"
    description = "List repositories and folders in the workspace root"
    input_schema = {
        "type": "object",
        "properties": {
            "include_non_git": {"type": "boolean"}
        },
    }

    def run(self, **kwargs) -> Dict[str, Any]:
        include_non_git = bool(kwargs.get("include_non_git", False))
        items: List[Dict[str, Any]] = []
        for entry in WORKSPACE_ROOT.iterdir():
            if not entry.is_dir():
                continue
            is_git = (entry / ".git").exists()
            if is_git or include_non_git:
                items.append({"name": entry.name, "is_git": is_git})
        return {"repos": sorted(items, key=lambda x: x["name"].lower())}

