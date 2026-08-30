from __future__ import annotations

import logging
import time

from .base import LLMError, LLMResult, ToolCall, Usage

logger = logging.getLogger(__name__)

# Task nào bắt buộc gọi tool (structured output) — còn lại để model tự do (text JSON)
_FORCE_TOOL = {"state_edit"}


class AnthropicProvider:
    """Provider Claude (Anthropic SDK). KHÔNG log payload — chỉ log metadata (privacy)."""

    provider_id = "anthropic"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        from anthropic import AsyncAnthropic

        self.client = (
            AsyncAnthropic(api_key=api_key, base_url=base_url)
            if base_url
            else AsyncAnthropic(api_key=api_key)
        )

    async def complete(
        self,
        *,
        task: str,
        model: str,
        system: str,
        user: str,
        tools: list[dict],
    ) -> LLMResult:
        started = time.monotonic()
        kwargs: dict = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if tools:
            kwargs["tools"] = tools
            if task in _FORCE_TOOL:
                kwargs["tool_choice"] = {"type": "any"}

        try:
            resp = await self.client.messages.create(**kwargs)
        except Exception as exc:  # rate limit / network / model lỗi
            logger.warning("anthropic call lỗi (task=%s model=%s): %s", task, model, exc)
            raise LLMError(str(exc)) from exc

        tool_calls: list[ToolCall] = []
        text = ""
        for block in resp.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(name=block.name, args=block.input or {}))
            elif block.type == "text":
                text += block.text

        usage = Usage(
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        logger.info(
            "anthropic ok (task=%s model=%s in=%s out=%s)",
            task,
            model,
            usage.input_tokens,
            usage.output_tokens,
        )
        return LLMResult(tool_calls=tool_calls, text=text, usage=usage)
