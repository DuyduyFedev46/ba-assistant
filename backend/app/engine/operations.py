from __future__ import annotations

import logging
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .state import MeetingState, StateItem

logger = logging.getLogger(__name__)

# core là trừu tượng CỐ ĐỊNH — amend chỉ đụng được các field này
VALID_CORE_KEYS = {"title", "body", "rationale"}


def _allowed_profile_keys(profile) -> dict[str, set[str]] | None:
    """Field hợp lệ cho profile_fields theo loại item (khai báo trong profile)."""
    if profile is None:
        return None
    return {
        t: {f.name for f in profile.item_schemas.get(t).fields}
        if profile.item_schemas.get(t)
        else set()
        for t in ("DECISION", "OPEN", "ACTION")
    }


class Evidence(BaseModel):
    quote: str = ""
    span: list[int] = Field(default_factory=list)


class NewDecisionItem(BaseModel):
    subject_key: str
    core: dict = Field(default_factory=dict)
    profile_fields: dict = Field(default_factory=dict)
    evidence: Evidence = Field(default_factory=Evidence)


class CreateOp(BaseModel):
    op: Literal["create"] = "create"
    item_type: Literal["DECISION", "OPEN", "ACTION"]
    subject_key: str
    core: dict = Field(default_factory=dict)
    profile_fields: dict = Field(default_factory=dict)
    evidence: Evidence = Field(default_factory=Evidence)


class SupersedeOp(BaseModel):
    op: Literal["supersede"] = "supersede"
    old_item_id: UUID
    new_item: NewDecisionItem
    reason: str = ""


class AnswerOp(BaseModel):
    op: Literal["answer"] = "answer"
    open_item_id: UUID
    answer_text: str | None = None
    answer_decision: NewDecisionItem | None = None
    evidence: Evidence = Field(default_factory=Evidence)


class AmendOp(BaseModel):
    op: Literal["amend"] = "amend"
    item_id: UUID
    field_changes: dict = Field(default_factory=dict)
    reason: str = ""
    evidence: Evidence = Field(default_factory=Evidence)


class FlagOp(BaseModel):
    op: Literal["flag"] = "flag"
    target_item_id: UUID | None = None
    new_item: NewDecisionItem | None = None
    reason: str = ""


Operation = Annotated[
    CreateOp | SupersedeOp | AnswerOp | AmendOp | FlagOp,
    Field(discriminator="op"),
]


def _provenance(nhip_id: int, evidence: Evidence) -> dict:
    return {"nhip_id": nhip_id, "span": evidence.span, "quote": evidence.quote}


def apply_operations(
    state: MeetingState,
    ops: list[Operation],
    nhip_id: int,
    profile=None,
) -> tuple[list[StateItem], list[dict]]:
    """Áp patch từng op vào state (thuần Python). Op invalid → bỏ + warning, KHÔNG crash beat.

    Trả về (items mới, op_log entries đã áp). op invalid KHÔNG vào op_log.
    profile (tuỳ chọn): ràng buộc amend chỉ đụng field khai báo trong profile.
    """
    items = list(state.items)
    applied: list[dict] = []
    allowed = _allowed_profile_keys(profile)

    for op in ops:
        try:
            result = _apply_one(items, op, nhip_id, allowed)
        except Exception:  # defensive — engine không được chết vì 1 op lỗi
            logger.warning("apply_operations: op bị bỏ do lỗi: %s", op, exc_info=True)
            continue
        if result is None:
            continue
        items, entry = result
        applied.append(entry)

    return items, applied


def _apply_one(
    items: list[StateItem],
    op: Operation,
    nhip_id: int,
    allowed: dict[str, set[str]] | None = None,
) -> tuple[list[StateItem], dict] | None:

    if op.op == "create":
        item = StateItem(
            id=uuid4(),
            type=op.item_type,
            subject_key=op.subject_key,
            core=dict(op.core),
            profile_fields=dict(op.profile_fields),
            provenance=_provenance(nhip_id, op.evidence),
            created_nhip=nhip_id,
            updated_nhip=nhip_id,
        )
        items.append(item)
        return items, {"op_type": "create", "payload": item.model_dump(mode="json")}

    if op.op == "supersede":
        old = _find(items, op.old_item_id)
        if old is None or old.type != "DECISION" or old.status != "active":
            logger.warning(
                "supersede bỏ: old_item_id=%s không phải DECISION active", op.old_item_id
            )
            return None
        if old.subject_key != op.new_item.subject_key:
            logger.warning(
                "supersede: subject_key không khớp (old=%s new=%s) — vẫn áp vì old_id do model "
                "chỉ định",
                old.subject_key,
                op.new_item.subject_key,
            )
        new_id = uuid4()
        new_item = StateItem(
            id=new_id,
            type="DECISION",
            subject_key=op.new_item.subject_key,
            core=dict(op.new_item.core),
            profile_fields=dict(op.new_item.profile_fields),
            provenance=_provenance(nhip_id, op.new_item.evidence),
            supersedes=old.id,
            created_nhip=nhip_id,
            updated_nhip=nhip_id,
        )
        old_updated = old.model_copy(
            update={"status": "superseded", "superseded_by": new_id, "updated_nhip": nhip_id}
        )
        idx = next(i for i, it in enumerate(items) if it.id == old.id)
        items[idx] = old_updated
        items.append(new_item)
        return items, {
            "op_type": "supersede",
            "payload": {"old_item_id": str(old.id), "new_item_id": str(new_id)},
        }

    if op.op == "answer":
        open_item = _find(items, op.open_item_id)
        if open_item is None or open_item.type != "OPEN" or open_item.status != "active":
            logger.warning("answer bỏ: open_item_id=%s không phải OPEN active", op.open_item_id)
            return None
        answered_by: UUID | None = None
        new_core = dict(open_item.core)
        if op.answer_decision is not None:
            new_item = StateItem(
                id=uuid4(),
                type="DECISION",
                subject_key=op.answer_decision.subject_key,
                core=dict(op.answer_decision.core),
                profile_fields=dict(op.answer_decision.profile_fields),
                provenance=_provenance(nhip_id, op.answer_decision.evidence),
                created_nhip=nhip_id,
                updated_nhip=nhip_id,
            )
            answered_by = new_item.id
            items.append(new_item)
        elif op.answer_text:
            if not new_core.get("body"):
                new_core["body"] = op.answer_text
            new_core["answer_text"] = op.answer_text
        idx = next(i for i, it in enumerate(items) if it.id == open_item.id)
        items[idx] = open_item.model_copy(
            update={
                "status": "answered",
                "answered_by": answered_by,
                "updated_nhip": nhip_id,
                "core": new_core,
            }
        )
        return items, {
            "op_type": "answer",
            "payload": {
                "open_item_id": str(open_item.id),
                "answered_by": str(answered_by) if answered_by else None,
            },
        }

    if op.op == "amend":
        item = _find(items, op.item_id)
        if item is None or item.status not in ("active", "flagged"):
            logger.warning(
                "amend bỏ: item_id=%s không sửa được (status=%s)",
                op.item_id,
                item.status if item else None,
            )
            return None
        core = dict(item.core)
        profile_fields = dict(item.profile_fields)
        changed = False
        for key, value in op.field_changes.items():
            if key in VALID_CORE_KEYS:
                core[key] = value
                changed = True
            elif allowed is not None:
                allowed_keys = allowed.get(item.type, set())
                if key in allowed_keys:
                    profile_fields[key] = value
                    changed = True
                else:
                    logger.warning(
                        "amend bỏ field không khai báo trong profile: %s (item %s)", key, item.id
                    )
            else:
                profile_fields[key] = value
                changed = True
        if not changed:
            logger.warning(
                "amend bỏ: field_changes rỗng hoặc không có gì thay đổi (item %s)", item.id
            )
            return None
        idx = next(i for i, it in enumerate(items) if it.id == item.id)
        items[idx] = item.model_copy(
            update={"core": core, "profile_fields": profile_fields, "updated_nhip": nhip_id}
        )
        return items, {"op_type": "amend", "payload": {"item_id": str(item.id)}}

    if op.op == "flag":
        if op.target_item_id is not None:
            item = _find(items, op.target_item_id)
            if item is None or item.status != "active":
                logger.warning("flag bỏ: target=%s không active", op.target_item_id)
                return None
            idx = next(i for i, it in enumerate(items) if it.id == item.id)
            items[idx] = item.model_copy(update={"status": "flagged", "updated_nhip": nhip_id})
            payload = {"target_item_id": str(item.id), "new_item_id": None}
        elif op.new_item is not None:
            new_item = StateItem(
                id=uuid4(),
                type="DECISION",
                subject_key=op.new_item.subject_key,
                core=dict(op.new_item.core),
                profile_fields=dict(op.new_item.profile_fields),
                provenance=_provenance(nhip_id, op.new_item.evidence),
                status="flagged",
                created_nhip=nhip_id,
                updated_nhip=nhip_id,
            )
            items.append(new_item)
            payload = {"target_item_id": None, "new_item_id": str(new_item.id)}
        else:
            logger.warning("flag bỏ: không có target_item_id lẫn new_item")
            return None
        return items, {"op_type": "flag", "payload": payload}

    logger.warning("op không nhận diện: %s", op)
    return None


def _find(items: list[StateItem], item_id: UUID) -> StateItem | None:
    return next((it for it in items if it.id == item_id), None)
