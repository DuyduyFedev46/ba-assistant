"""Unit test segmenter — heuristic cắt nhịp (plan.md §8.4) + LLM confirm."""

import json

from app.engine.profile_loader import SegmenterCfg
from app.engine.segmenter import Segmenter, heuristic_segment, split_turns


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


# ---------------------------------------------------------------- tách chunk quá dài
# Nhịp không bao giờ nhỏ hơn chunk: dán cả buổi họp vào một chunk thì buffer_full đóng
# ngay thành ĐÚNG một nhịp, state-edit chạy một lượt và mất hết khả năng revision-aware.

TURNS = (
    "A (BA): Xin chào mọi người, hôm nay ta thống nhất phạm vi dự án. "
    "B (KD): Mục tiêu cuối cùng vẫn là tăng doanh thu cho công ty. "
    "D (Ops): Không được, bỏ bớt xác minh là vi phạm quy định. "
    "C (Product): Tôi nghĩ trọng tâm phải là cải thiện chỉ số NPS."
)


def test_split_giu_nguyen_khi_ngan():
    """Dưới ngưỡng → trả nguyên văn, không đụng vào (đường ingest thường)."""
    assert split_turns("ok vậy chốt phương án A", 400) == ["ok vậy chốt phương án A"]


def test_split_rong_tra_list_rong():
    assert split_turns("   ", 400) == []


def test_split_theo_nhan_nguoi_noi():
    """Quá ngưỡng → tách theo nhãn người nói, mỗi lượt một chunk."""
    parts = split_turns(TURNS, 12)
    assert len(parts) >= 4
    assert parts[0].startswith("A (BA):")
    assert any(p.startswith("D (Ops):") for p in parts)


def test_split_khong_mat_chu():
    """Bất biến quan trọng nhất: tách xong không được rơi chữ nào."""
    parts = split_turns(TURNS, 12)
    assert sum(len(p.split()) for p in parts) == len(TURNS.split())


def test_split_khong_co_nhan_thi_theo_cau():
    """Văn bản không có nhãn người nói → lùi về ranh giới câu."""
    text = "Câu một dài ơi là dài. Câu hai cũng dài không kém. Câu ba khép lại."
    parts = split_turns(text, 6)
    assert len(parts) >= 2
    assert sum(len(p.split()) for p in parts) == len(text.split())


def test_split_mot_luot_dai_bi_cat_cung():
    """Một lượt nói dài hơn max_words vẫn phải bị cắt, không được vượt ngưỡng."""
    text = " ".join(f"tu{i}" for i in range(50))
    parts = split_turns(text, 10)
    assert all(len(p.split()) <= 10 for p in parts)
    assert sum(len(p.split()) for p in parts) == 50


def test_split_luon_tach_theo_luot_du_ngan():
    """Regression: transcript NGẮN nhưng nhiều lượt vẫn phải tách.

    Buộc điều kiện tách vào max_beat_words (cỡ nhịp) là sai: bộ 10 test case họp thật
    chỉ 126-198 từ, dưới ngưỡng 400, nên cả 10 ra đúng 1 nhịp và engine không sinh nổi
    một op supersede nào.
    """
    text = "A: Chốt Integer nhé. C: Khoan, hay dùng Boolean? B: Em vẫn giữ Integer."
    parts = split_turns(text, 400)  # tổng chỉ 13 từ, xa ngưỡng
    assert len(parts) == 3
    assert parts[0].startswith("A:") and parts[2].startswith("B:")


def test_split_mot_luot_tu_mic_giu_nguyen():
    """Mic/STT gửi từng lượt kèm nhãn — chỉ một nhãn thì không được tách nhỏ thêm."""
    assert split_turns("BA-Ha: ok vậy chốt phương án A.", 400) == [
        "BA-Ha: ok vậy chốt phương án A."
    ]


async def test_confirm_close_bo_qua_van_xuoi_sau_json(fake_llm, router):
    """Regression: Claude trả JSON trong ```fence RỒI giải thích thêm phía sau.

    Gỡ fence không đủ — json.loads ném "Extra data", confirm_close nuốt thành False,
    hệ quả là KHÔNG nhịp nào đóng được. Phát hiện khi chạy bộ 10 test case họp thật:
    segment_confirm gọi 16 lần, đóng 0 nhịp, dù model đều trả closed=true.
    """
    fake_llm.enqueue_text(
        "segment_confirm",
        '```json\n{"closed": true, "reason": "closing_cue"}\n```\n\n'
        "The discussion reached a natural closing point because the decision was made.",
    )
    seg = Segmenter(router)
    assert await seg.confirm_close(meeting_id=None, beat_text="đoạn nhịp") is True


def test_parse_json_response_cac_dang():
    from app.engine.segmenter import parse_json_response

    assert parse_json_response('{"closed": true}') == {"closed": True}
    assert parse_json_response('```json\n{"closed": true}\n```') == {"closed": True}
    assert parse_json_response('Kết quả:\n{"closed": false}\nGiải thích thêm.') == {
        "closed": False
    }
