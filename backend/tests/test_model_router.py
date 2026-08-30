"""★ MODEL ROUTER (plan.md §10) — task→model đúng policy, escalation, fallback, audit."""

from pathlib import Path

import pytest
import yaml

from app.llm.providers.base import LLMError, ToolCall
from app.llm.providers.fake import FakeLLM
from app.llm.router import ListAuditSink, ModelRouter

BACKEND_POLICY = yaml.safe_load(
    Path(__file__)
    .resolve()
    .parent.parent.joinpath("config/model_policy.yaml")
    .read_text(encoding="utf-8")
)


def make_router(policy, fake: FakeLLM) -> ModelRouter:
    providers = {pid: fake for pid in ("fake", "anthropic", "openai", "gemini", "selfhosted")}
    return ModelRouter(policy, providers, audit=ListAuditSink())


async def test_task_to_model_đúng_policy(fake_llm):
    router = make_router(BACKEND_POLICY, fake_llm)
    fake_llm.enqueue(
        "state_edit",
        [
            ToolCall(
                name="create_item",
                args={"item_type": "DECISION", "subject_key": "x", "core": {"title": "t"}},
            )
        ],
    )
    fake_llm.enqueue("segment_confirm", [])

    await router.run("state_edit", system="", user="", tools=[])
    await router.run("segment_confirm", system="", user="", tools=[])

    records = router.audit.records  # type: ignore[union-attr]
    assert records[0]["task"] == "state_edit"
    assert records[0]["model"] == "claude-opus-5"
    assert records[0]["provider"] == "anthropic"
    assert records[1]["task"] == "segment_confirm"
    assert records[1]["model"] == "claude-haiku-4-5-20251001"


async def test_escalation_theo_hints(fake_llm):
    """state_edit mặc định sonnet; hints has_revision_cue → nâng opus (rule khai báo)."""
    policy = {
        "defaults": {"provider": "anthropic", "model": "claude-sonnet-5"},
        "tasks": {
            "state_edit": {
                "model": "claude-sonnet-5",
                "escalate": [{"if": "has_revision_cue", "model": "claude-opus-5"}],
            }
        },
    }
    router = make_router(policy, fake_llm)

    await router.run("state_edit", system="", user="", tools=[], hints={})
    assert router.audit.records[-1]["model"] == "claude-sonnet-5"  # type: ignore[union-attr]

    await router.run("state_edit", system="", user="", tools=[], hints={"has_revision_cue": True})
    assert router.audit.records[-1]["model"] == "claude-opus-5"  # type: ignore[union-attr]


async def test_fallback_khi_provider_loi(fake_llm):
    policy = {
        "defaults": {"provider": "anthropic", "model": "claude-sonnet-5"},
        "tasks": {
            "state_edit": {
                "model": "claude-opus-5",
                "fallback": [{"provider": "anthropic", "model": "claude-sonnet-5"}],
            }
        },
    }
    router = make_router(policy, fake_llm)
    fake_llm.fail_next_call("state_edit")  # lượt 1 lỗi → fallback lượt 2

    result = await router.run("state_edit", system="", user="", tools=[])
    assert result.tool_calls == []
    records = router.audit.records  # type: ignore[union-attr]
    assert len(records) == 1
    assert records[0]["model"] == "claude-sonnet-5"  # fallback model được dùng


async def test_toan_bo_chain_loi_raise(fake_llm):
    policy = {
        "defaults": {"provider": "anthropic", "model": "claude-opus-5"},
        "tasks": {
            "state_edit": {
                "model": "claude-opus-5",
                "fallback": [{"provider": "anthropic", "model": "claude-sonnet-5"}],
            }
        },
    }
    router = make_router(policy, fake_llm)
    fake_llm.fail_next_call("state_edit")
    fake_llm.fail_next_call("state_edit")
    with pytest.raises(LLMError):
        await router.run("state_edit", system="", user="", tools=[])
    assert router.audit.records == []  # type: ignore[union-attr]


async def test_provider_khong_dang_ky_thi_skip(fake_llm):
    policy = {
        "defaults": {"provider": "not-registered", "model": "claude-opus-5"},
        "tasks": {},
    }
    router = make_router(policy, fake_llm)
    with pytest.raises(LLMError):
        await router.run("state_edit", system="", user="", tools=[])
