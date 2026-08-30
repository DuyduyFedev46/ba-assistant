from __future__ import annotations

import json
import logging
from uuid import UUID

from ..llm.tasks import TaskId
from .profile_loader import SegmenterCfg
from .prompts import build_segment_confirm_user

logger = logging.getLogger(__name__)


def heuristic_segment(
    *,
    gap: float | None,
    cue: bool,
    beat_words: int,
    beat_sec: float | None,
    cfg: SegmenterCfg,
) -> str | None:
    """'certain' | 'weak' | None.
    - 'certain': (gap >= cfg.silence_gap_sec AND cue) OR buffer full
      (beat_words >= cfg.max_beat_words OR (beat_sec is not None and beat_sec >= cfg.max_beat_sec))
    - 'weak': only cue, or only gap (>= silence_gap_sec) — cần LLM xác nhận
    - None: không phải ranh giới nhịp
    """
    buffer_full = beat_words >= cfg.max_beat_words or (
        beat_sec is not None and beat_sec >= cfg.max_beat_sec
    )
    if buffer_full:
        return "certain"
    gap_ok = gap is not None and gap >= cfg.silence_gap_sec
    if gap_ok and cue:
        return "certain"
    if cue or gap_ok:
        return "weak"
    return None


def parse_json_response(text: str) -> dict:
    """Parse JSON từ response text; model hay bọc trong ```json ... ``` nên gỡ fence trước."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        cleaned = cleaned.removesuffix("```").strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError(f"response không phải JSON object: {type(data).__name__}")
    return data


class Segmenter:
    """Tier-2 phân đoạn: heuristic chỉ 'weak' → LLM xác nhận đóng nhịp (headless, không crash)."""

    SYSTEM_SEGMENT_CONFIRM = """\
You decide whether a meeting beat has reached a natural closing point. A beat should close when the
current discussion thread is complete: a topic was wrapped up (committed decision, answered
question, or the thread ended), a clear closing cue was spoken, or the buffer is full and continuing
would mix topics.
Return ONLY JSON:
{"closed": bool, "reason": "silence"|"topic_shift"|"closing_cue"|"buffer_full"|null}
closed=false unless the transcript shows a natural end of the current discussion thread."""

    def __init__(self, router) -> None:
        self.router = router

    async def confirm_close(self, *, meeting_id: UUID, beat_text: str) -> bool:
        """Hỏi LLM xác nhận đóng nhịp; parse lỗi/LLM lỗi → warning + False (giữ nhịp mở)."""
        try:
            result = await self.router.run(
                TaskId.SEGMENT_CONFIRM,
                system=self.SYSTEM_SEGMENT_CONFIRM,
                user=build_segment_confirm_user(beat_text),
                tools=[],
                hints={},
                meeting_id=meeting_id,
            )
            data = parse_json_response(result.text)
            return bool(data.get("closed"))
        except Exception:
            logger.warning("confirm_close: LLM/parse lỗi — giữ nhịp mở, không crash", exc_info=True)
            return False
