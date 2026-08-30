from __future__ import annotations

import logging
from uuid import UUID

from pydantic import ValidationError

from ..llm.providers.base import ToolCall
from ..llm.tasks import TaskId
from .operations import (
    AmendOp,
    AnswerOp,
    CreateOp,
    Evidence,
    FlagOp,
    NewDecisionItem,
    Operation,
    SupersedeOp,
    apply_operations,
)
from .profile_loader import Profile, build_tools
from .prompts import SYSTEM_STATE_EDIT, build_state_edit_user
from .state import MeetingState, StateItem

logger = logging.getLogger(__name__)


class StateEditResult:
    def __init__(
        self,
        operations: list[Operation],
        applied: list[dict],
        items: list[StateItem],
        state_changed: bool,
    ):
        self.operations = operations
        self.applied = applied
        self.items = items
        self.state_changed = state_changed


class StateEditor:
    """PASS state-edit: state hiện tại + nhịp mới → operations (qua ModelRouter) → apply."""

    def __init__(self, router):
        self.router = router

    async def edit(
        self,
        *,
        meeting_id: UUID,
        state: MeetingState,
        nhip_id: int,
        beat_text: str,
        profile: Profile,
        hints: dict | None = None,
    ) -> StateEditResult:
        tools = build_tools(profile)
        system = SYSTEM_STATE_EDIT
        user = build_state_edit_user(
            state_json=state.compact(nhip_id),
            nhip_id=nhip_id,
            beat_text=beat_text,
            profile=profile.model_dump(),
            prev_nhip=nhip_id - 1,
        )
        result = await self.router.run(
            TaskId.STATE_EDIT,
            system=system,
            user=user,
            tools=tools,
            hints=hints,
            meeting_id=meeting_id,
        )
        ops = parse_tool_calls(result.tool_calls)
        items, applied = apply_operations(state, ops, nhip_id, profile=profile)
        return StateEditResult(
            operations=ops,
            applied=applied,
            items=items,
            state_changed=bool(applied),
        )


def parse_tool_calls(tool_calls: list[ToolCall]) -> list[Operation]:
    """Map tool calls (theo thứ tự) → operations. Tool call lỗi → bỏ + warning."""
    ops: list[Operation] = []
    for call in tool_calls:
        op = _parse_one(call)
        if op is not None:
            ops.append(op)
    return ops


def _parse_one(call: ToolCall) -> Operation | None:
    name = call.name
    args = call.args or {}
    try:
        if name == "create_item":
            return CreateOp(
                item_type=args["item_type"],
                subject_key=args["subject_key"],
                core=args.get("core") or {},
                profile_fields=args.get("profile_fields") or {},
                evidence=_evidence(args.get("evidence")),
            )
        if name == "supersede_item":
            return SupersedeOp(
                old_item_id=UUID(args["old_item_id"]),
                new_item=NewDecisionItem.model_validate(args["new_item"]),
                reason=args.get("reason", ""),
            )
        if name == "answer_open":
            return AnswerOp(
                open_item_id=UUID(args["open_item_id"]),
                answer_text=args.get("answer_text"),
                answer_decision=(
                    NewDecisionItem.model_validate(args["answer_decision"])
                    if args.get("answer_decision") is not None
                    else None
                ),
                evidence=_evidence(args.get("evidence")),
            )
        if name == "amend_item":
            return AmendOp(
                item_id=UUID(args["item_id"]),
                field_changes=args.get("field_changes") or {},
                reason=args.get("reason", ""),
                evidence=_evidence(args.get("evidence")),
            )
        if name == "flag_item":
            return FlagOp(
                target_item_id=UUID(args["target_item_id"]) if args.get("target_item_id") else None,
                new_item=(
                    NewDecisionItem.model_validate(args["new_item"])
                    if args.get("new_item") is not None
                    else None
                ),
                reason=args.get("reason", ""),
            )
    except (KeyError, ValidationError, ValueError) as exc:
        logger.warning("tool call bỏ do parse lỗi: %s (%s)", call, exc)
        return None
    logger.warning("tool call không nhận diện: %s", name)
    return None


def _evidence(raw: dict | None) -> Evidence:
    raw = raw or {}
    return Evidence(quote=raw.get("quote", ""), span=raw.get("span") or [])
