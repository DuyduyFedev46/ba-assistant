from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


class ToolCall(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)


class LLMResult(BaseModel):
    tool_calls: list[ToolCall] = Field(default_factory=list)
    text: str = ""
    usage: Usage = Field(default_factory=Usage)


class LLMError(Exception):
    """Lỗi khi gọi provider (network, rate limit, model lỗi...)."""


class LLMProvider(Protocol):
    """Một provider LLM (Claude / OpenAI / Gemini / self-host / fake)."""

    provider_id: str

    async def complete(
        self,
        *,
        task: str,
        model: str,
        system: str,
        user: str,
        tools: list[dict],
    ) -> LLMResult:
        """Gọi model, trả tool calls (theo thứ tự). Provider phải đo latency.
        Raise LLMError khi lỗi."""
        ...
