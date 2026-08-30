from __future__ import annotations

import os

from ..protocol import Connector, ConnectorError


def match_project(event: dict, profiles: list[dict]) -> str | None:
    """Khớp event với project: profile có nhiều calendar tag trùng nhất (tie → profile đầu tiên)."""
    parts = [
        str(event.get("title", "")),
        str(event.get("description", "")),
        str(event.get("tags", "")),
    ]
    text = " ".join(parts).lower()
    best_key: str | None = None
    best_hits = 0
    for profile in profiles:
        hits = 0
        for tag in (profile.get("routing") or {}).get("calendar_tags") or []:
            lowered = tag.lower()
            if lowered in text or lowered.lstrip("#") in text:
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best_key = profile.get("project")
    return best_key


class CalendarGoogleConnector(Connector):
    """Connector Google Calendar (direct): resolve_event + match_project."""

    def __init__(self, name: str = "calendar-google", config: dict | None = None) -> None:
        self.name = name
        self.config = config or {}

    async def list_tools(self) -> list[dict]:
        """Khai báo tool mà engine có thể gọi trên connector này."""
        return [
            {
                "name": "resolve_event",
                "description": "Lấy chi tiết một event từ Google Calendar theo event_id.",
            },
            {
                "name": "match_project",
                "description": "Khớp event với project dựa trên calendar tags trong profile.",
            },
        ]

    async def call(self, tool: str, args: dict) -> dict:
        """Gọi tool; resolve_event cần credentials_file hoặc GOOGLE_APPLICATION_CREDENTIALS."""
        if tool == "resolve_event":
            return await self._resolve_event(args)
        if tool == "match_project":
            return {"matched_project": match_project(args["event"], args.get("profiles") or [])}
        raise ConnectorError(f"tool '{tool}' không được hỗ trợ bởi {self.name}")

    async def _resolve_event(self, args: dict) -> dict:
        creds_file = self.config.get("credentials_file") or os.environ.get(
            "GOOGLE_APPLICATION_CREDENTIALS"
        )
        if not creds_file:
            raise ConnectorError(
                f"{self.name}: thiếu credentials_file trong config"
                " hoặc GOOGLE_APPLICATION_CREDENTIALS"
            )
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_file(
            creds_file, scopes=["https://www.googleapis.com/auth/calendar.readonly"]
        )
        service = build("calendar", "v3", credentials=credentials)
        calendar_id = (self.config.get("calendar_ids") or ["primary"])[0]
        event = service.events().get(calendarId=calendar_id, eventId=args["event_id"]).execute()
        start = event.get("start") or {}
        return {
            "event": {
                "id": event.get("id"),
                "title": event.get("summary"),
                "description": event.get("description") or "",
                "start": start.get("dateTime") or start.get("date"),
            }
        }
