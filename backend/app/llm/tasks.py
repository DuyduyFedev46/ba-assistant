from __future__ import annotations

from enum import StrEnum


class TaskId(StrEnum):
    """Task của engine — policy config quyết định task nào dùng model nào."""

    SEGMENT_CONFIRM = "segment_confirm"
    BEAT_ROUTER = "beat_router"
    STATE_EDIT = "state_edit"
    PROFILE_MAP = "profile_map"
    FINAL_DOC = "final_doc"
    REDACT = "redact"
