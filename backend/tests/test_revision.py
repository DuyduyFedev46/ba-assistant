"""★ ACCEPTANCE QUAN TRỌNG NHẤT — kịch bản revision (plan.md §15.1).

Chốt A (nhịp 1) → treo rate-limit (nhịp 2) → LẬT sang B (nhịp 3) → trả lời treo (nhịp 4).
Output phải là ĐÚNG PHIÊN BẢN CUỐI: chỉ B active, A superseded (KHÔNG song song),
OPEN đã answered, rời panel "còn treo". FakeLLM script deterministic — test này kiểm
chứng ENGINE (apply + parse + state), không kiểm chứng model.
"""

from uuid import uuid4

from app.engine.operations import Evidence, NewDecisionItem
from app.engine.state import MeetingState
from app.llm.providers.base import ToolCall

BEATS = [
    # nhip 1 — chốt A
    "BE-Nam: phần thanh toán thì em thấy phương án A ổn. "
    "BA-Ha: ok vậy chốt phương án A cho luồng thanh toán nhé.",
    # nhip 2 — treo rate-limit
    "BA-Ha: còn rate limit thì mình tính thế nào nhỉ? "
    "Ecom-Tuan: chưa rõ, phụ thuộc hạ tầng. "
    "BA-Ha: vậy để mở, mai hỏi thêm bên platform.",
    # nhip 3 — LẬT: A → B
    "BE-Nam: thôi đổi sang phương án B đi, A không kịp deadline tuần sau. "
    "BA-Ha: ok, vậy chốt B, bỏ A.",
    # nhip 4 — trả lời treo
    "BA-Ha: rate limit chốt 100 req/s nhé. Ecom-Tuan: ok.",
]


def _create(item_type, subject_key, title, quote) -> ToolCall:
    return ToolCall(
        name="create_item",
        args={
            "item_type": item_type,
            "subject_key": subject_key,
            "core": {"title": title},
            "evidence": {"quote": quote, "span": [0, len(quote)]},
        },
    )


async def test_revision_lat_dap_treo(state_editor, fake_llm, profile_family):
    state = MeetingState(meeting_id=uuid4())

    # ---- nhịp 1: chốt A
    fake_llm.enqueue(
        "state_edit",
        [
            _create(
                "DECISION",
                "payment-flow",
                "Dùng phương án A cho luồng thanh toán",
                "ok vậy chốt phương án A cho luồng thanh toán nhé.",
            )
        ],
    )
    r1 = await state_editor.edit(
        meeting_id=state.meeting_id,
        state=state,
        nhip_id=1,
        beat_text=BEATS[0],
        profile=profile_family,
    )
    d1 = r1.items[0]
    assert d1.type == "DECISION" and d1.status == "active"
    assert d1.subject_key == "payment-flow"
    state = MeetingState(meeting_id=state.meeting_id, items=r1.items, version=1)

    # ---- nhịp 2: treo
    fake_llm.enqueue(
        "state_edit",
        [
            _create(
                "OPEN",
                "rate-limit",
                "Rate limit tính thế nào?",
                "còn rate limit thì mình tính thế nào nhỉ?",
            )
        ],
    )
    r2 = await state_editor.edit(
        meeting_id=state.meeting_id,
        state=state,
        nhip_id=2,
        beat_text=BEATS[1],
        profile=profile_family,
    )
    o1 = r2.items[-1]
    assert o1.type == "OPEN" and o1.status == "active"
    state = MeetingState(meeting_id=state.meeting_id, items=r2.items, version=2)

    # ---- nhịp 3: LẬT A → B
    fake_llm.enqueue(
        "state_edit",
        [
            ToolCall(
                name="supersede_item",
                args={
                    "old_item_id": str(d1.id),
                    "new_item": NewDecisionItem(
                        subject_key="payment-flow",
                        core={
                            "title": "Dùng phương án B cho luồng thanh toán",
                            "rationale": "A không kịp deadline",
                        },
                        profile_fields={"replaces_decision": str(d1.id), "impacts": "contract"},
                        evidence=Evidence(quote="vậy chốt B, bỏ A", span=[0, 6]),
                    ).model_dump(),
                    "reason": "A không kịp deadline",
                },
            )
        ],
    )
    r3 = await state_editor.edit(
        meeting_id=state.meeting_id,
        state=state,
        nhip_id=3,
        beat_text=BEATS[2],
        profile=profile_family,
    )
    d2 = next(i for i in r3.items if i.supersedes == d1.id)
    d1_after = next(i for i in r3.items if i.id == d1.id)
    assert d1_after.status == "superseded"
    assert d1_after.superseded_by == d2.id
    assert d2.status == "active"
    assert d2.supersedes == d1.id
    assert d2.profile_fields["impacts"] == "contract"
    state = MeetingState(meeting_id=state.meeting_id, items=r3.items, version=3)

    # ---- nhịp 4: trả lời treo rate-limit
    fake_llm.enqueue(
        "state_edit",
        [
            ToolCall(
                name="answer_open",
                args={
                    "open_item_id": str(o1.id),
                    "answer_decision": NewDecisionItem(
                        subject_key="rate-limit",
                        core={"title": "Rate limit = 100 req/s"},
                        evidence=Evidence(quote="rate limit chốt 100 req/s nhé", span=[0, 8]),
                    ).model_dump(),
                    "evidence": {"quote": "rate limit chốt 100 req/s nhé", "span": [0, 8]},
                },
            )
        ],
    )
    r4 = await state_editor.edit(
        meeting_id=state.meeting_id,
        state=state,
        nhip_id=4,
        beat_text=BEATS[3],
        profile=profile_family,
    )
    d3 = next(i for i in r4.items if i.type == "DECISION" and i.id != d1.id and i.id != d2.id)
    o1_after = next(i for i in r4.items if i.id == o1.id)
    assert o1_after.status == "answered"
    assert o1_after.answered_by == d3.id
    assert d3.subject_key == "rate-limit"

    final_state = MeetingState(meeting_id=state.meeting_id, items=r4.items, version=4)

    # ================= ASSERTIONS CUỐI (plan.md §15.1) =================
    # 1. Chỉ B active — KHÔNG có 2 DECISION active cùng subject_key "payment-flow"
    active_payment = [
        i
        for i in final_state.items
        if i.type == "DECISION" and i.status == "active" and i.subject_key == "payment-flow"
    ]
    assert len(active_payment) == 1
    assert active_payment[0].id == d2.id

    # 2. A vẫn tồn tại ở trạng thái superseded (giữ lịch sử, không xoá)
    assert any(i.id == d1.id and i.status == "superseded" for i in final_state.items)

    # 3. OPEN đã rời panel "còn treo"
    assert final_state.summary()["open_count"] == 0

    # 4. op_log: đúng 4 op theo thứ tự create/create/supersede/answer
    op_log = r1.applied + r2.applied + r3.applied + r4.applied
    assert [e["op_type"] for e in op_log] == ["create", "create", "supersede", "answer"]

    # 5. snapshot version == 4 (mỗi nhịp đổi state 1 lần)
    assert final_state.version == 4


async def test_revision_nothing_actionable_no_push(state_editor, fake_llm, profile_family):
    """Nhịp không có gì đáng ghi → KHÔNG đổi state (version không tăng, FE không nhận push)."""
    state = MeetingState(meeting_id=uuid4())
    fake_llm.enqueue("state_edit", [])  # model trả rỗng
    r = await state_editor.edit(
        meeting_id=state.meeting_id,
        state=state,
        nhip_id=1,
        beat_text="BA-Ha: chào mọi người, hôm nay mình họp về gói Family Package.",
        profile=profile_family,
    )
    assert r.state_changed is False
    assert r.items == []
    assert state.version == 0
