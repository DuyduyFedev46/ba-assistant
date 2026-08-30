from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ItemType = Literal["DECISION", "OPEN", "ACTION"]
ItemStatus = Literal["active", "superseded", "answered", "flagged"]


class StateItem(BaseModel):
    """Một mục sống trong state — có ID ổn định, revision-aware."""

    id: UUID
    type: ItemType
    status: ItemStatus = "active"
    subject_key: str
    core: dict = Field(default_factory=dict)
    profile_fields: dict = Field(default_factory=dict)
    provenance: dict = Field(default_factory=dict)
    supersedes: UUID | None = None
    superseded_by: UUID | None = None
    answered_by: UUID | None = None
    created_nhip: int
    updated_nhip: int


class MeetingState(BaseModel):
    """State = MỘT tài liệu sống (tập StateItem có ID) — KHÔNG phải list bản tóm nối đuôi."""

    meeting_id: UUID
    items: list[StateItem] = Field(default_factory=list)
    version: int = 0

    def get(self, item_id: UUID) -> StateItem | None:
        return next((it for it in self.items if it.id == item_id), None)

    def active_items(self, item_type: ItemType | None = None) -> list[StateItem]:
        return [
            it
            for it in self.items
            if it.status == "active" and (item_type is None or it.type == item_type)
        ]

    def compact(self, current_nhip: int, keep_recent: int = 5) -> dict:
        """Trạng thái gửi LLM: items active đầy đủ; items phi-active chỉ giữ nếu mới gần."""
        out = []
        for it in self.items:
            if it.status == "active" or it.updated_nhip >= current_nhip - keep_recent:
                out.append(it.model_dump(mode="json"))
        return {"version": self.version, "items": out}

    def summary(self) -> dict:
        open_items = [
            it for it in self.items if it.type == "OPEN" and it.status in ("active", "flagged")
        ]
        active_decisions = self.active_items("DECISION")
        actions = self.active_items("ACTION")
        unassigned = [str(it.id) for it in actions if not it.profile_fields.get("owner")]
        return {
            "open_count": len(open_items),
            "flagged_count": len([it for it in self.items if it.status == "flagged"]),
            "decision_count": len(active_decisions),
            "action_unassigned": unassigned,
        }
