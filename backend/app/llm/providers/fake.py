from __future__ import annotations

import os
from collections import defaultdict, deque

from .base import LLMError, LLMResult, ToolCall


class FakeLLM:
    """Provider giả cho dev/test offline (LLM_FAKE=1) — script theo task, deterministic.

    - `enqueue(task, calls)`: thêm 1 lượt tool calls cho task (FIFO).
    - `set_echo(True)`: tự sinh create_item theo schema tools (test đa-dự-án).
    - `fail_next(task)`: lượt kế tiếp của task sẽ raise LLMError (test fallback).
    """

    provider_id = "fake"

    def __init__(self) -> None:
        self.script: dict[str, deque[list[ToolCall]]] = defaultdict(deque)
        self.fail_next: dict[str, int] = defaultdict(int)
        # LLM_FAKE_ECHO=1 → tự sinh create_item (demo headless không cần script)
        self.echo_schema = os.environ.get("LLM_FAKE_ECHO", "") == "1"

    def enqueue(self, task: str, calls: list[ToolCall]) -> None:
        self.script[task].append(list(calls))

    def enqueue_text(self, task: str, text: str) -> None:
        """Enqueue 1 lượt response TEXT (JSON) — segment_confirm/beat_router trả JSON text."""
        self.script[task].append(LLMResult(text=text))

    def fail_next_call(self, task: str) -> None:
        self.fail_next[task] += 1

    def set_echo(self, on: bool) -> None:
        self.echo_schema = on

    async def complete(
        self, *, task: str, model: str, system: str, user: str, tools: list[dict]
    ) -> LLMResult:
        if self.fail_next[task] > 0:
            self.fail_next[task] -= 1
            raise LLMError(f"fake: lỗi cố ý cho task {task}")

        if self.echo_schema and task == "state_edit":
            return LLMResult(tool_calls=[self._echo_call(tools)])

        queue = self.script.get(task)
        if queue:
            item = queue.popleft()
            if isinstance(item, LLMResult):
                return item  # response text (segment_confirm/beat_router)
            return LLMResult(tool_calls=item)
        return LLMResult()

    def _echo_call(self, tools: list[dict]) -> ToolCall:
        """Sinh create_item DECISION với profile_fields đúng schema DECISION của tools."""
        schema: dict = {}
        for tool in tools:
            if tool.get("name") == "create_item":
                one_of = (
                    tool.get("input_schema", {})
                    .get("properties", {})
                    .get("profile_fields", {})
                    .get("oneOf", [])
                )
                for variant in one_of:
                    if variant.get("title") == "DECISION":
                        schema = variant.get("properties", {})
                        break
                break
        fields = {name: "sample" for name in schema}
        return ToolCall(
            name="create_item",
            args={
                "item_type": "DECISION",
                "subject_key": "echo-topic",
                "core": {"title": "Echo item"},
                "profile_fields": fields,
            },
        )
