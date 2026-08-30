from __future__ import annotations

import json
import logging
import re
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


# Nhãn người nói: "A:", "B (KD):", "BA-Ha:", "E (Finance, vào):" — tên ngắn, cho phép
# một cụm ngoặc mô tả vai. Cắt hơi thừa thì vô hại (nhịp gom lại được); cắt thiếu mới
# chết, vì nhịp KHÔNG BAO GIỜ nhỏ hơn chunk.
_SPEAKER = re.compile(
    r"(?=(?<![^\s])[A-ZĐÀ-Ỹ][\wÀ-ỹ.\- ]{0,20}(?:\([^)]{0,40}\))?\s*:\s)"
)
_SENTENCE = re.compile(r"(?<=[.!?…])\s+")
# Dưới ngưỡng này coi là mảnh vụn, không đáng đứng riêng một chunk.
_MIN_TURN_WORDS = 4


def split_turns(text: str, max_words: int) -> list[str]:
    """Tách một chunk quá dài thành nhiều lượt nói.

    Chunk là hạt nguyên tử của pipeline: nhịp không thể nhỏ hơn chunk. Dán cả buổi
    họp vào một lần => buffer_full ngay => đúng MỘT nhịp => state_edit chạy một lượt
    và mất sạch khả năng revision-aware. Hàm này bịt đúng chỗ đó.

    Thứ tự ưu tiên ranh giới: nhãn người nói > hết câu > cắt cứng theo max_words.
    """
    if not text.strip():
        return []

    # Tách theo NHÃN NGƯỜI NÓI bất kể dài ngắn: một chunk phải là một lượt nói.
    # Ngưỡng max_words là cỡ NHỊP, không phải cỡ lượt — buộc điều kiện tách vào nó
    # thì transcript 150 từ có 12 lượt vẫn thành 1 chunk = 1 nhịp = mất revision-aware.
    parts = [p.strip() for p in _SPEAKER.split(text) if p.strip()]
    if len(parts) <= 1:
        # Không có nhãn (mic gửi từng câu, STT một lượt) → chỉ cắt khi vượt cỡ nhịp.
        if len(text.split()) <= max_words:
            return [text]
        parts = [p.strip() for p in _SENTENCE.split(text) if p.strip()]

    out: list[str] = []
    for part in parts:
        words = part.split()
        if len(words) <= max_words:
            out.append(part)
            continue
        # lượt nói vẫn quá dài -> thử theo câu, cuối cùng cắt cứng
        for sent in [s.strip() for s in _SENTENCE.split(part) if s.strip()] or [part]:
            sw = sent.split()
            if len(sw) <= max_words:
                out.append(sent)
            else:
                for i in range(0, len(sw), max_words):
                    out.append(" ".join(sw[i : i + max_words]))

    # Regex nhãn người nói đôi khi cắt ra mảnh vụn ("D:", "ở con số.") — gộp ngược
    # vào lượt trước để chunk nào cũng là một lượt nói có nghĩa.
    merged: list[str] = []
    for piece in out:
        if merged and len(piece.split()) < _MIN_TURN_WORDS:
            merged[-1] = f"{merged[-1]} {piece}"
        else:
            merged.append(piece)
    return merged or [text]


def parse_json_response(text: str) -> dict:
    """Lấy JSON object ĐẦU TIÊN trong response text.

    Model hay bọc ```json và/hoặc viết thêm lời giải thích SAU khối JSON. Gỡ fence
    thôi là chưa đủ — json.loads sẽ ném "Extra data" vì phần văn xuôi phía sau, và
    confirm_close nuốt lỗi thành False khiến nhịp không bao giờ đóng. raw_decode dừng
    ngay khi hết object nên miễn nhiễm với mọi thứ đứng sau.
    """
    start = text.find("{")
    if start == -1:
        raise ValueError("response không chứa JSON object")
    data, _ = json.JSONDecoder().raw_decode(text[start:])
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
