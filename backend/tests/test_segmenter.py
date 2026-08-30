"""Unit test segmenter — heuristic cắt nhịp (plan.md §8.4) + LLM confirm."""

import json

from app.engine.profile_loader import SegmenterCfg
from app.engine.segmenter import Segmenter, heuristic_segment


def cfg(**kw) -> SegmenterCfg:
    defaults = dict(
        silence_gap_sec=8.0,
        closing_cues=["ok chốt", "chốt vậy"],
        max_beat_words=400,
        max_beat_sec=180.0,
    )
    defaults.update(kw)
    return SegmenterCfg(**defaults)


def test_certain_gap_and_cue():
    """Khoảng lặng ≥ ngưỡng + cue đóng → certain, đóng nhịp không cần LLM."""
    assert (
        heuristic_segment(gap=10.0, cue=True, beat_words=50, beat_sec=30.0, cfg=cfg()) == "certain"
    )


def test_weak_cue_only():
    """Chỉ cue, gap nhỏ → weak (cần LLM xác nhận)."""
    assert heuristic_segment(gap=2.0, cue=True, beat_words=50, beat_sec=30.0, cfg=cfg()) == "weak"


def test_weak_gap_only():
    """Chỉ khoảng lặng dài → weak (cần LLM xác nhận)."""
    assert heuristic_segment(gap=10.0, cue=False, beat_words=50, beat_sec=30.0, cfg=cfg()) == "weak"


def test_none_no_signal():
    assert heuristic_segment(gap=1.0, cue=False, beat_words=50, beat_sec=30.0, cfg=cfg()) is None


def test_certain_buffer_full_words():
    """Nhịp vượt max_beat_words → chốt cứng."""
    assert (
        heuristic_segment(gap=0.0, cue=False, beat_words=400, beat_sec=10.0, cfg=cfg()) == "certain"
    )


def test_certain_buffer_full_sec():
    """Nhịp vượt max_beat_sec → chốt cứng."""
    assert (
        heuristic_segment(gap=0.0, cue=False, beat_words=10, beat_sec=180.0, cfg=cfg()) == "certain"
    )


def test_beat_sec_none_not_force_closed():
    """Thiếu ts (beat_sec=None) → không force-close vì giới hạn thời gian."""
    assert heuristic_segment(gap=0.0, cue=False, beat_words=10, beat_sec=None, cfg=cfg()) is None


async def test_confirm_close_true(fake_llm, router):
    fake_llm.enqueue_text("segment_confirm", json.dumps({"closed": True, "reason": "silence"}))
    seg = Segmenter(router)
    assert await seg.confirm_close(meeting_id=None, beat_text="đoạn nhịp") is True


async def test_confirm_close_false(fake_llm, router):
    fake_llm.enqueue_text("segment_confirm", json.dumps({"closed": False}))
    seg = Segmenter(router)
    assert await seg.confirm_close(meeting_id=None, beat_text="đoạn nhịp") is False


async def test_confirm_close_bad_json_falls_back_false(fake_llm, router):
    fake_llm.enqueue_text("segment_confirm", "{oops")
    seg = Segmenter(router)
    assert await seg.confirm_close(meeting_id=None, beat_text="đoạn nhịp") is False  # không crash
