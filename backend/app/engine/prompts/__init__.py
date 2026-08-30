"""Prompts AI (thư mục riêng — giống design/prompts của LC_Care).

Mỗi prompt là 1 file .md trong thư mục này; module chỉ load + render.
Nội dung prompt verbatim — muốn chỉnh prompt thì sửa file .md, không sửa code.
"""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import BaseLoader, Environment, StrictUndefined

_PROMPTS_DIR = Path(__file__).parent

_env = Environment(loader=BaseLoader(), undefined=StrictUndefined, autoescape=False)


def _render(name: str, **ctx: object) -> str:
    """Render template .md bằng jinja2 — nội dung biến (JSON...) không bị parse lại."""
    src = (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    return _env.from_string(src).render(**ctx)


# ---------------------------------------------------------------- SYSTEM prompts

SYSTEM_STATE_EDIT = (_PROMPTS_DIR / "state_edit_system.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------- USER prompt builders


def build_state_edit_user(
    state_json: dict,
    nhip_id: int,
    beat_text: str,
    profile: dict,
    prev_nhip: int,
) -> str:
    """USER prompt cho task state_edit (điền placeholder theo plan.md §9.2)."""
    schemas = profile.get("item_schemas", {})
    fields = {
        "DECISION": [f["name"] for f in schemas.get("DECISION", {}).get("fields", [])],
        "ACTION": [f["name"] for f in schemas.get("ACTION", {}).get("fields", [])],
    }
    ctx = {
        "display_name": profile.get("display_name", profile.get("project", "")),
        "participants": profile.get("vocabulary", {}).get("participants", []),
        "aliases": profile.get("vocabulary", {}).get("aliases", {}),
        "decision_fields": fields["DECISION"],
        "action_fields": fields["ACTION"],
    }
    return _render(
        "state_edit_user",
        prev_nhip=prev_nhip,
        nhip_id=nhip_id,
        beat_text=beat_text,
        state_json=json.dumps(state_json, ensure_ascii=False),
        ctx_json=json.dumps(ctx, ensure_ascii=False),
    )


def build_beat_router_user(beat_text: str) -> str:
    return _render("beat_router_user", beat_text=beat_text)


def build_segment_confirm_user(beat_text: str) -> str:
    return _render("segment_confirm_user", beat_text=beat_text)
