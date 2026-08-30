"""Unit test operations.apply — quy tắc biên tập state (plan.md §8.3)."""

from uuid import uuid4

from app.engine.operations import (
    AmendOp,
    AnswerOp,
    CreateOp,
    Evidence,
    FlagOp,
    NewDecisionItem,
    SupersedeOp,
    apply_operations,
)
from app.engine.state import MeetingState


def make_state(items=None) -> MeetingState:
    return MeetingState(meeting_id=uuid4(), items=items or [], version=0)


def create_item(**kw) -> CreateOp:
    defaults = dict(
        item_type="DECISION",
        subject_key="topic",
        core={"title": "Chốt A"},
        evidence=Evidence(quote="chốt A", span=[0, 2]),
    )
    defaults.update(kw)
    return CreateOp(**defaults)


async def test_create():
    state = make_state()
    items, applied = apply_operations(state, [create_item()], nhip_id=1)
    assert len(items) == 1
    assert items[0].type == "DECISION"
    assert items[0].status == "active"
    assert items[0].created_nhip == 1
    assert items[0].provenance["nhip_id"] == 1
    assert items[0].provenance["quote"] == "chốt A"
    assert applied == [{"op_type": "create", "payload": items[0].model_dump(mode="json")}]


async def test_supersede_valid():
    state = make_state()
    items, _ = apply_operations(state, [create_item()], nhip_id=1)
    d1 = items[0]
    op = SupersedeOp(
        old_item_id=d1.id,
        new_item=NewDecisionItem(
            subject_key="topic",
            core={"title": "Chốt B"},
            profile_fields={"impacts": "contract"},
            evidence=Evidence(quote="đổi sang B", span=[0, 3]),
        ),
        reason="A không kịp deadline",
    )
    items2, applied = apply_operations(
        MeetingState(meeting_id=state.meeting_id, items=items), [op], nhip_id=3
    )
    d2 = items2[-1]
    old = next(i for i in items2 if i.id == d1.id)
    assert old.status == "superseded"
    assert old.superseded_by == d2.id
    assert d2.status == "active"
    assert d2.supersedes == d1.id
    assert d2.profile_fields == {"impacts": "contract"}
    assert applied[0]["op_type"] == "supersede"


async def test_supersede_invalid_missing_old():
    state = make_state()
    op = SupersedeOp(
        old_item_id=uuid4(),
        new_item=NewDecisionItem(subject_key="topic", core={"title": "B"}),
    )
    items, applied = apply_operations(state, [op], nhip_id=2)
    assert items == []
    assert applied == []  # op invalid → bỏ, KHÔNG crash


async def test_supersede_double_flip_rejected():
    """Item đã superseded không thể bị lật tiếp (tránh lật chồng)."""
    state = make_state()
    items, _ = apply_operations(state, [create_item()], nhip_id=1)
    d1 = items[0]
    op1 = SupersedeOp(
        old_item_id=d1.id, new_item=NewDecisionItem(subject_key="topic", core={"title": "B"})
    )
    items, _ = apply_operations(
        MeetingState(meeting_id=state.meeting_id, items=items), [op1], nhip_id=2
    )
    op2 = SupersedeOp(
        old_item_id=d1.id, new_item=NewDecisionItem(subject_key="topic", core={"title": "C"})
    )
    items2, applied = apply_operations(
        MeetingState(meeting_id=state.meeting_id, items=items), [op2], nhip_id=3
    )
    assert applied == []  # d1 không còn active → bỏ
    assert len(items2) == 2  # không tạo C


async def test_answer_with_decision():
    state = make_state()
    items, _ = apply_operations(
        state,
        [create_item(item_type="OPEN", subject_key="rate-limit", core={"title": "Rate limit?"})],
        nhip_id=1,
    )
    o1 = items[0]
    op = AnswerOp(
        open_item_id=o1.id,
        answer_decision=NewDecisionItem(
            subject_key="rate-limit",
            core={"title": "Rate limit = 100 req/s"},
        ),
        evidence=Evidence(quote="chốt 100 req/s", span=[0, 4]),
    )
    items2, applied = apply_operations(
        MeetingState(meeting_id=state.meeting_id, items=items), [op], nhip_id=4
    )
    o1_after = next(i for i in items2 if i.id == o1.id)
    d3 = items2[-1]
    assert o1_after.status == "answered"
    assert o1_after.answered_by == d3.id
    assert d3.type == "DECISION"
    assert d3.status == "active"


async def test_answer_text_only():
    state = make_state()
    items, _ = apply_operations(
        state,
        [create_item(item_type="OPEN", subject_key="q", core={"title": "Câu hỏi"})],
        nhip_id=1,
    )
    o1 = items[0]
    op = AnswerOp(open_item_id=o1.id, answer_text="1 tuần")
    items2, _ = apply_operations(
        MeetingState(meeting_id=state.meeting_id, items=items), [op], nhip_id=2
    )
    o1_after = next(i for i in items2 if i.id == o1.id)
    assert o1_after.status == "answered"
    assert o1_after.core["answer_text"] == "1 tuần"
    assert o1_after.answered_by is None
    assert len(items2) == 1  # không tạo DECISION mới


async def test_amend_known_field(profile_family):
    state = make_state()
    items, _ = apply_operations(
        state,
        [
            create_item(
                item_type="ACTION",
                subject_key="task",
                core={"title": "Làm X"},
                profile_fields={"owner": "Nam"},
            )
        ],
        nhip_id=1,
    )
    a1 = items[0]
    op = AmendOp(item_id=a1.id, field_changes={"owner": "Linh", "due": "2026-09-05"})
    # owner + due đều khai báo trong profile family-package ACTION schema → áp được
    items2, applied = apply_operations(
        MeetingState(meeting_id=state.meeting_id, items=items),
        [op],
        nhip_id=2,
        profile=profile_family,
    )
    a1_after = next(i for i in items2 if i.id == a1.id)
    assert a1_after.profile_fields == {"owner": "Linh", "due": "2026-09-05"}
    assert a1_after.updated_nhip == 2
    assert len(applied) == 1


async def test_amend_unknown_field_skipped(profile_family):
    """Field lạ trong profile → bỏ cả op (chống rác; model được dạy schema qua tools)."""
    state = make_state()
    items, _ = apply_operations(state, [create_item(core={"title": "X"})], nhip_id=1)
    op = AmendOp(item_id=items[0].id, field_changes={"khong_tontai": 1})
    items2, applied = apply_operations(
        MeetingState(meeting_id=state.meeting_id, items=items),
        [op],
        nhip_id=2,
        profile=profile_family,
    )
    assert applied == []  # field lạ → bỏ cả op
    assert items2[0].core == {"title": "X"}


async def test_flag_target_and_new():
    state = make_state()
    items, _ = apply_operations(state, [create_item()], nhip_id=1)
    d1 = items[0]
    # flag item có sẵn
    items, _ = apply_operations(
        MeetingState(meeting_id=state.meeting_id, items=items),
        [FlagOp(target_item_id=d1.id, reason="mơ hồ")],
        nhip_id=2,
    )
    d1_after = next(i for i in items if i.id == d1.id)
    assert d1_after.status == "flagged"
    # flag item mới (đề xuất)
    items, _ = apply_operations(
        MeetingState(meeting_id=state.meeting_id, items=items),
        [
            FlagOp(
                new_item=NewDecisionItem(subject_key="topic", core={"title": "Đề xuất B"}),
                reason="chưa rõ",
            )
        ],
        nhip_id=3,
    )
    assert items[-1].status == "flagged"
    assert items[-1].type == "DECISION"


async def test_empty_ops_no_change():
    state = make_state()
    items, applied = apply_operations(state, [], nhip_id=1)
    assert items == []
    assert applied == []
