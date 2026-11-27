from pathlib import Path
from typing import Dict

from .base import Tool
from backend.core.config import CALENDAR_PROVIDER
from .calendar import CalendarTool, LocalCalendarProvider
from .files import FileTool
from .repos import RepoScanTool
from .search import SearchTool
from .scripts import ScriptTool
from .workspace import WorkspaceTool


def default_tools(workspace_root: Path | None = None, calendar_db_path: str | None = None) -> Dict[str, Tool]:
    if CALENDAR_PROVIDER == "google":
        from .calendar_google import GoogleCalendarProvider

        calendar_provider = GoogleCalendarProvider()
    else:
        calendar_provider = LocalCalendarProvider(calendar_db_path) if calendar_db_path else LocalCalendarProvider()
    kwargs = {"workspace_root": workspace_root} if workspace_root else {}
    calendar = CalendarTool(provider=calendar_provider)
    files = FileTool(**kwargs)
    repos = RepoScanTool(**kwargs)
    search = SearchTool(**kwargs)
    scripts = ScriptTool(**kwargs)
    workspace = WorkspaceTool(**kwargs)
    return {
        calendar.name: calendar,
        files.name: files,
        repos.name: repos,
        search.name: search,
        scripts.name: scripts,
        workspace.name: workspace,
    }
