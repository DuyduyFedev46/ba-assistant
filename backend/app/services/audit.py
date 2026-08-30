"""AuditSink → bảng llm_calls. Chỉ metadata (task/model/tokens/latency).

KHÔNG bao giờ log prompt/transcript (privacy).
"""

from __future__ import annotations

from ..db.models import LLMCall
from ..llm.router import AuditSink


class DBAuditSink(AuditSink):
    """Ghi mỗi LLM call vào llm_calls (session riêng — KHÔNG dính transaction của pipeline)."""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def record(self, *, meeting_id, task, provider, model, result) -> None:
        async with self.session_factory() as session:
            session.add(
                LLMCall(
                    meeting_id=meeting_id,
                    task=str(task),
                    provider=provider,
                    model=model,
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    latency_ms=result.usage.latency_ms,
                )
            )
            await session.commit()
