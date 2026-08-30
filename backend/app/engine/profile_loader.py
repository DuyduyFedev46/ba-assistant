from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ProfileField(BaseModel):
    name: str
    type: str  # ref | enum | person | date | text
    values: list[str] | None = None
    description: str = ""


class ItemSchema(BaseModel):
    fields: list[ProfileField] = Field(default_factory=list)


class RoutingCfg(BaseModel):
    connector: str = "calendar-google"
    calendar_tags: list[str] = Field(default_factory=list)
    repo: str = ""
    file_convention: str = "meetings/{date}-{slug}.md"


class SegmenterCfg(BaseModel):
    silence_gap_sec: float = 8.0
    closing_cues: list[str] = Field(
        default_factory=lambda: [
            "ok chốt",
            "chốt vậy",
            "quyết định vậy",
            "vậy quyết",
            "chuyển sang",
            "sang phần",
            "tiếp theo",
        ]
    )
    max_beat_words: int = 400
    max_beat_sec: float = 180.0


class FinalDocCfg(BaseModel):
    enabled: bool = False
    template: str = ""


class Profile(BaseModel):
    """Profile dự án — config khai báo, KHÔNG phải code. Engine không đổi khi thêm profile mới."""

    project: str
    display_name: str = ""
    vocabulary: dict = Field(default_factory=dict)
    routing: RoutingCfg = Field(default_factory=RoutingCfg)
    item_schemas: dict[str, ItemSchema] = Field(default_factory=dict)
    final_doc: FinalDocCfg = Field(default_factory=FinalDocCfg)
    segmenter: SegmenterCfg = Field(default_factory=SegmenterCfg)


# ---------------------------------------------------------------- loaders


def load_profile_yaml(text: str) -> Profile:
    data = yaml.safe_load(text) or {}
    return Profile.model_validate(data)


def load_profile_file(path: Path) -> Profile:
    return load_profile_yaml(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- JSON schema


def field_to_json_schema(f: ProfileField) -> dict:
    if f.type == "enum":
        schema: dict = {"type": "string", "enum": f.values or []}
    elif f.type == "ref":
        schema = {"type": "string", "description": "item id"}
    elif f.type == "person":
        schema = {"type": "string"}
    elif f.type == "date":
        schema = {"type": "string", "description": "YYYY-MM-DD"}
    else:  # text
        schema = {"type": "string"}
    if f.description:
        schema["description"] = f.description
    return schema


def build_profile_fields_schema(schema: ItemSchema | None) -> dict:
    """Object schema từ field khai báo; rỗng nếu không có field."""
    if schema is None or not schema.fields:
        return {"type": "object", "properties": {}, "additionalProperties": False}
    return {
        "type": "object",
        "properties": {f.name: field_to_json_schema(f) for f in schema.fields},
        "additionalProperties": False,
    }


_CORE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Tiêu đề ngắn gọn của mục"},
        "body": {"type": "string", "description": "Nội dung chi tiết (nếu có)"},
        "rationale": {"type": "string", "description": "Lý do/chốt cứng nếu có"},
    },
    "required": ["title"],
}


def _evidence_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "quote": {"type": "string", "description": "Trích nguyên văn từ nhịp (ngôn ngữ gốc)"},
            "span": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "[start, end] index của quote trong transcript nhịp",
            },
        },
    }


# ---------------------------------------------------------------- tools (5 cố định)


def build_tools(profile: Profile) -> list[dict]:
    """Dựng động danh sách tool (Anthropic tool-use format) cho pass state-edit.
    Tên tool CỐ ĐỊNH; chỉ schema profile_fields đổi theo profile."""
    decision_schema = build_profile_fields_schema(profile.item_schemas.get("DECISION"))
    open_schema = build_profile_fields_schema(profile.item_schemas.get("OPEN"))
    action_schema = build_profile_fields_schema(profile.item_schemas.get("ACTION"))

    new_decision = {
        "type": "object",
        "properties": {
            "subject_key": {"type": "string", "description": "Slug chủ đề ổn định, tiếng Anh"},
            "core": _CORE_SCHEMA,
            "profile_fields": decision_schema,
            "evidence": _evidence_schema(),
        },
        "required": ["subject_key", "core"],
    }

    return [
        {
            "name": "create_item",
            "description": (
                "Tạo mục MỚI trong state (DECISION/OPEN/ACTION). Chỉ khi phát biểu ĐÃ cam kết "
                "(cue: 'chốt', 'ok vậy', 'quyết định', 'thống nhất', 'vậy làm'). Không tạo cho "
                "phương án đang cân nhắc."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "item_type": {"type": "string", "enum": ["DECISION", "OPEN", "ACTION"]},
                    "subject_key": {
                        "type": "string",
                        "description": "Slug chủ đề ổn định, tiếng Anh",
                    },
                    "core": _CORE_SCHEMA,
                    "profile_fields": {
                        "oneOf": [
                            {"title": "DECISION", **decision_schema},
                            {"title": "OPEN", **open_schema},
                            {"title": "ACTION", **action_schema},
                        ],
                        "description": "Field riêng theo loại mục (khai báo trong profile)",
                    },
                    "evidence": _evidence_schema(),
                },
                "required": ["item_type", "subject_key", "core"],
            },
        },
        {
            "name": "supersede_item",
            "description": (
                "LẬT một quyết định: CHỈ khi (a) phương án mới ĐÃ cam kết, VÀ (b) nó mâu thuẫn "
                "trực tiếp một DECISION active cùng subject_key. Chỉ đang bàn thêm → KHÔNG dùng; "
                "mơ hồ → flag_item."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "old_item_id": {
                        "type": "string",
                        "description": "id của DECISION active bị thay",
                    },
                    "new_item": new_decision,
                    "reason": {"type": "string"},
                },
                "required": ["old_item_id", "new_item"],
            },
        },
        {
            "name": "answer_open",
            "description": (
                "Trả lời một câu hỏi TREO (OPEN). Chỉ khi nhịp này đưa câu trả lời ĐÃ cam kết. "
                "Nếu câu trả lời là một quyết định → truyền answer_decision; ngược lại → answer_text."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "open_item_id": {"type": "string"},
                    "answer_text": {"type": "string"},
                    "answer_decision": new_decision,
                    "evidence": _evidence_schema(),
                },
                "required": ["open_item_id"],
            },
        },
        {
            "name": "amend_item",
            "description": "Hiệu chỉnh field của item đã có khi nhịp làm rõ/bổ sung nội dung mà KHÔNG mâu thuẫn nó.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "field_changes": {
                        "type": "object",
                        "description": "Map field → giá trị mới (chỉ field đã tồn tại trong core hoặc profile_fields)",
                    },
                    "reason": {"type": "string"},
                    "evidence": _evidence_schema(),
                },
                "required": ["item_id", "field_changes"],
            },
        },
        {
            "name": "flag_item",
            "description": (
                "Lật MƠ HỒ: nghi ngờ mâu thuẫn nhưng chưa rõ đã cam kết — KHÔNG supersede. "
                "Host xác nhận sau họp. Truyền target_item_id (đánh dấu item) HOẶC new_item (đề xuất mới)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_item_id": {"type": "string"},
                    "new_item": new_decision,
                    "reason": {"type": "string"},
                },
                "required": ["reason"],
            },
        },
    ]
