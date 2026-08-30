from __future__ import annotations

from types import SimpleNamespace

from .profile_loader import Profile
from .state import MeetingState, StateItem


def map_item(item: StateItem, profile: Profile) -> dict:
    """StateItem generic → dict theo profile (core/profile_fields giữ NESTED dict cho template)."""
    return {
        "id": str(item.id),
        "type": item.type,
        "status": item.status,
        "subject_key": item.subject_key,
        "core": dict(item.core),
        "profile_fields": dict(item.profile_fields),
        "supersedes": str(item.supersedes) if item.supersedes else None,
        "superseded_by": str(item.superseded_by) if item.superseded_by else None,
        "answered_by": str(item.answered_by) if item.answered_by else None,
        "created_nhip": item.created_nhip,
        "updated_nhip": item.updated_nhip,
        "provenance": dict(item.provenance),
    }


def map_state(state: MeetingState, profile: Profile) -> dict:
    """Toàn bộ state → dict profile-representation (meeting_id, version, items đã map)."""
    return {
        "meeting_id": str(state.meeting_id),
        "version": state.version,
        "items": [map_item(it, profile) for it in state.items],
    }


def build_doc_context(*, state: MeetingState, profile: Profile, date: str) -> dict:
    """Context render final doc — khớp templates/brd_family.md.j2 (project, date, state).

    `state` là namespace chứ KHÔNG phải dict: template dùng `state.items` — với dict,
    Jinja sẽ resolve nhầm sang method `dict.items`.
    """
    return {
        "project": profile.model_dump(mode="json"),
        "date": date,
        "state": SimpleNamespace(
            meeting_id=str(state.meeting_id),
            version=state.version,
            items=[map_item(it, profile) for it in state.items],
        ),
    }
