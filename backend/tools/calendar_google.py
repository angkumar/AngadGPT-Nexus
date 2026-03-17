from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from backend.core.config import (
    GOOGLE_CALENDAR_ID,
    GOOGLE_CREDENTIALS_PATH,
    GOOGLE_TOKEN_PATH,
)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def _load_credentials() -> Credentials:
    creds: Optional[Credentials] = None
    try:
        creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_PATH, SCOPES)
    except Exception:
        creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                GOOGLE_CREDENTIALS_PATH, SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open(GOOGLE_TOKEN_PATH, "w", encoding="utf-8") as handle:
            handle.write(creds.to_json())
    return creds


def _service():
    creds = _load_credentials()
    return build("calendar", "v3", credentials=creds)


def _to_event_dict(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": event.get("id"),
        "title": event.get("summary", ""),
        "start_time": event.get("start", {}).get("dateTime")
        or event.get("start", {}).get("date"),
        "end_time": event.get("end", {}).get("dateTime")
        or event.get("end", {}).get("date"),
        "description": event.get("description", ""),
        "location": event.get("location", ""),
    }


class GoogleCalendarProvider:
    def __init__(self, calendar_id: str = GOOGLE_CALENDAR_ID) -> None:
        self.calendar_id = calendar_id

    def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
    ) -> Dict[str, Any]:
        service = _service()
        body = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": start_time},
            "end": {"dateTime": end_time},
        }
        event = (
            service.events()
            .insert(calendarId=self.calendar_id, body=body)
            .execute()
        )
        return _to_event_dict(event)

    def list_events(self, start_after: Optional[str] = None) -> List[Dict[str, Any]]:
        service = _service()
        time_min = start_after or dt.datetime.utcnow().isoformat() + "Z"
        events_result = (
            service.events()
            .list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                maxResults=50,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        return [_to_event_dict(e) for e in events]

    def update_event(self, event_id: str, **updates: Any) -> Optional[Dict[str, Any]]:
        service = _service()
        event = (
            service.events()
            .get(calendarId=self.calendar_id, eventId=event_id)
            .execute()
        )
        if not event:
            return None
        if "title" in updates and updates["title"] is not None:
            event["summary"] = updates["title"]
        if "description" in updates and updates["description"] is not None:
            event["description"] = updates["description"]
        if "location" in updates and updates["location"] is not None:
            event["location"] = updates["location"]
        if "start_time" in updates and updates["start_time"] is not None:
            event.setdefault("start", {})["dateTime"] = updates["start_time"]
        if "end_time" in updates and updates["end_time"] is not None:
            event.setdefault("end", {})["dateTime"] = updates["end_time"]
        updated = (
            service.events()
            .update(calendarId=self.calendar_id, eventId=event_id, body=event)
            .execute()
        )
        return _to_event_dict(updated)

    def delete_event(self, event_id: str) -> bool:
        service = _service()
        service.events().delete(calendarId=self.calendar_id, eventId=event_id).execute()
        return True
