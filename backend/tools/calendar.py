import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.core.config import MEMORY_DB_PATH
from .base import Tool


@dataclass
class CalendarEvent:
    id: int
    title: str
    start_time: str
    end_time: str
    description: str
    location: str


class LocalCalendarProvider:
    def __init__(self, db_path: str = MEMORY_DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    description TEXT NOT NULL,
                    location TEXT NOT NULL
                )
                """
            )

    def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
    ) -> CalendarEvent:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO calendar_events (title, start_time, end_time, description, location)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, start_time, end_time, description, location),
            )
            event_id = cursor.lastrowid
        return CalendarEvent(
            id=int(event_id),
            title=title,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
        )

    def list_events(self, start_after: Optional[str] = None) -> List[CalendarEvent]:
        query = "SELECT id, title, start_time, end_time, description, location FROM calendar_events"
        params: List[Any] = []
        if start_after:
            query += " WHERE start_time >= ?"
            params.append(start_after)
        query += " ORDER BY start_time ASC"
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [CalendarEvent(*row) for row in rows]

    def update_event(self, event_id: int, **updates: Any) -> Optional[CalendarEvent]:
        allowed = {"title", "start_time", "end_time", "description", "location"}
        fields = [k for k in updates.keys() if k in allowed]
        if not fields:
            return self.get_event(event_id)
        assignments = ", ".join([f"{field} = ?" for field in fields])
        values = [updates[field] for field in fields]
        values.append(event_id)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE calendar_events SET {assignments} WHERE id = ?",
                values,
            )
        return self.get_event(event_id)

    def delete_event(self, event_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM calendar_events WHERE id = ?",
                (event_id,),
            )
        return cursor.rowcount > 0

    def get_event(self, event_id: int) -> Optional[CalendarEvent]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, title, start_time, end_time, description, location FROM calendar_events WHERE id = ?",
                (event_id,),
            ).fetchone()
        return CalendarEvent(*row) if row else None


class CalendarTool(Tool):
    name = "calendar"
    description = "Create, update, delete, and list calendar events"
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "list", "update", "delete"]},
            "event_id": {"type": "integer"},
            "title": {"type": "string"},
            "start_time": {"type": "string", "description": "ISO-8601"},
            "end_time": {"type": "string", "description": "ISO-8601"},
            "description": {"type": "string"},
            "location": {"type": "string"},
        },
        "required": ["action"],
    }

    def __init__(self, provider: Optional[LocalCalendarProvider] = None) -> None:
        self.provider = provider or LocalCalendarProvider()

    def run(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action")
        if action == "create":
            event = self.provider.create_event(
                title=kwargs.get("title", "Untitled"),
                start_time=kwargs.get("start_time", datetime.utcnow().isoformat()),
                end_time=kwargs.get("end_time", datetime.utcnow().isoformat()),
                description=kwargs.get("description", ""),
                location=kwargs.get("location", ""),
            )
            return {"event": event.__dict__}
        if action == "list":
            events = self.provider.list_events(start_after=kwargs.get("start_after"))
            return {"events": [e.__dict__ for e in events]}
        if action == "update":
            event = self.provider.update_event(
                kwargs.get("event_id"),
                title=kwargs.get("title"),
                start_time=kwargs.get("start_time"),
                end_time=kwargs.get("end_time"),
                description=kwargs.get("description"),
                location=kwargs.get("location"),
            )
            return {"event": event.__dict__ if event else None}
        if action == "delete":
            success = self.provider.delete_event(kwargs.get("event_id"))
            return {"deleted": success}
        return {"error": "Unsupported action"}

