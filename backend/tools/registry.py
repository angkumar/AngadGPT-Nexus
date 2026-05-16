from typing import Dict

from .base import Tool
from backend.core.config import CALENDAR_PROVIDER
from .calendar import CalendarTool, LocalCalendarProvider
from .files import FileTool
from .repos import RepoScanTool
from .search import SearchTool
from .scripts import ScriptTool
from .workspace import WorkspaceTool


def default_tools() -> Dict[str, Tool]:
    if CALENDAR_PROVIDER == "google":
        from .calendar_google import GoogleCalendarProvider

        calendar_provider = GoogleCalendarProvider()
    else:
        calendar_provider = LocalCalendarProvider()
    calendar = CalendarTool(provider=calendar_provider)
    files = FileTool()
    repos = RepoScanTool()
    search = SearchTool()
    scripts = ScriptTool()
    workspace = WorkspaceTool()
    return {
        calendar.name: calendar,
        files.name: files,
        repos.name: repos,
        search.name: search,
        scripts.name: scripts,
        workspace.name: workspace,
    }
