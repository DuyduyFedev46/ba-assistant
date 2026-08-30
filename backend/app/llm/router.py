from __future__ import annotations

import logging
from uuid import UUID

import yaml

from ..config import Settings, get_settings
from .providers.base import LLMError, LLMProvider, LLMResult

logger = logging.getLogger(__name__)


class AuditSink:
    """Ghi nhận LLM call (task, model, cost...) — plug DB repo ở Phase 3."""

    async def record(
        self,
        *,
        meeting_id: UUID | None,
        task: str,
        provider: str,
        model: str,
        result: LLMResult,
    ) -> None:  # pragma: no cover — interface
        ...


class ListAuditSink(AuditSink):
    """Audit trong-memory cho test."""

    def __init__(self) -> None:
        self.records: list[dict] = []

    async def record(self, *, meeting_id, task, provider, model, result) -> None:
        self.records.append(
            {
                "meeting_id": meeting_id,
                "task": task,
                "provider": provider,
                "model": model,
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "latency_ms": result.usage.latency_ms,
            }
        )


class ModelRouter:
    """Task nào → model nào: policy config (YAML), escalation theo hints, fallback chain, audit."""

    def __init__(
        self,
        policy: dict,
        providers: dict[str, LLMProvider],
        audit: AuditSink | None = None,
    ) -> None:
        self.policy = policy
        self.providers = providers
        self.audit = audit
        self.defaults: dict = policy.get("defaults", {})

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        providers: dict[str, LLMProvider] | None = None,
        audit: AuditSink | None = None,
    ) -> ModelRouter:
        settings = settings or get_settings()
        policy = yaml.safe_load(settings.model_policy_file.read_text(encoding="utf-8")) or {}
        if providers is None:
            providers = cls._build_providers(settings)
        return cls(policy, providers, audit)

    @staticmethod
    def _build_providers(settings: Settings) -> dict[str, LLMProvider]:
        from .providers.fake import FakeLLM

        if settings.llm_fake:
            fake = FakeLLM()
            return {pid: fake for pid in ("fake", "anthropic", "openai", "gemini", "selfhosted")}

        from .providers.anthropic import AnthropicProvider

        return {"anthropic": AnthropicProvider(settings.anthropic_api_key)}

    async def run(
        self,
        task: str,
        *,
        system: str,
        user: str,
        tools: list[dict],
        hints: dict | None = None,
        meeting_id: UUID | None = None,
    ) -> LLMResult:
        task_cfg = self.policy.get("tasks", {}).get(task, {})
        provider_id = task_cfg.get("provider") or self.defaults.get("provider")
        model = task_cfg.get("model") or self.defaults.get("model")
        if not provider_id or not model:
            raise LLMError(f"model_policy thiếu cấu hình cho task {task}")

        # escalation: nhịp phức tạp → model mạnh hơn (rules khai báo, engine không đổi)
        if hints and task_cfg.get("escalate"):
            for rule in task_cfg["escalate"]:
                if hints.get(rule["if"]):
                    model = rule["model"]
                    break

        # fallback chain: [(provider, model), ...] — primary trước, fallback theo sau
        chain = [(provider_id, model)]
        for fb in task_cfg.get("fallback", []):
            chain.append((fb.get("provider") or provider_id, fb["model"]))

        last_error: Exception | None = None
        for fb_provider_id, fb_model in chain:
            provider = self.providers.get(fb_provider_id)
            if provider is None:
                last_error = LLMError(f"provider {fb_provider_id} chưa đăng ký")
                continue
            try:
                result = await provider.complete(
                    task=str(task), model=fb_model, system=system, user=user, tools=tools
                )
            except LLMError as exc:
                last_error = exc
                logger.warning(
                    "model %s (%s) lỗi cho task %s — thử fallback", fb_model, fb_provider_id, task
                )
                continue
            if self.audit is not None:
                await self.audit.record(
                    meeting_id=meeting_id,
                    task=str(task),
                    provider=fb_provider_id,
                    model=fb_model,
                    result=result,
                )
            return result

        raise LLMError(f"toàn bộ model chain thất bại cho task {task}: {last_error}")
