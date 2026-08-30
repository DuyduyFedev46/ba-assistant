from __future__ import annotations

from .adapters.calendar_google import CalendarGoogleConnector, match_project
from .protocol import Connector, ConnectorError


class FakeCalendarConnector(Connector):
    """Fake connector calendar cho offline dev/test (LLM_FAKE=1) — event trong memory."""

    def __init__(
        self, name: str = "calendar-google", events: dict[str, dict] | None = None
    ) -> None:
        self.name = name
        self.events = events or {
            "evt-family": {
                "id": "evt-family",
                "title": "Họp Family Package #fp",
                "description": "",
                "start": "2026-08-30T09:00:00Z",
            },
            "evt-plain": {
                "id": "evt-plain",
                "title": "Họp chung",
                "description": "",
                "start": "2026-08-30T10:00:00Z",
            },
        }

    async def list_tools(self) -> list[dict]:
        """Khai báo tool giống CalendarGoogleConnector."""
        return await CalendarGoogleConnector(self.name).list_tools()

    async def call(self, tool: str, args: dict) -> dict:
        """resolve_event từ dict trong memory; match_project dùng hàm thuần từ adapter."""
        if tool == "resolve_event":
            event = self.events.get(args["event_id"])
            if event is None:
                raise ConnectorError(f"event_id '{args['event_id']}' không có trong fake calendar")
            return {"event": event}
        if tool == "match_project":
            return {"matched_project": match_project(args["event"], args.get("profiles") or [])}
        raise ConnectorError(f"tool '{tool}' không được hỗ trợ bởi {self.name}")


class FakeRepoConnector(Connector):
    """Fake connector git repo cho offline dev/test — không đụng filesystem/git."""

    def __init__(self, name: str = "repo-github") -> None:
        self.name = name
        self.commits: list[dict] = []

    async def list_tools(self) -> list[dict]:
        """Khai báo tool commit_files."""
        return [
            {
                "name": "commit_files",
                "description": "Fake commit: ghi nhận vào self.commits, không đụng git.",
            }
        ]

    async def call(self, tool: str, args: dict) -> dict:
        """commit_files → append vào self.commits và trả commit id fake."""
        if tool != "commit_files":
            raise ConnectorError(f"tool '{tool}' không được hỗ trợ bởi {self.name}")
        commit = f"fake-{len(self.commits) + 1:04d}"
        self.commits.append(
            {
                "repo_url": args["repo_url"],
                "files": dict(args.get("files") or {}),
                "message": args.get("message") or "",
                "commit": commit,
            }
        )
        return {"commit": commit}
