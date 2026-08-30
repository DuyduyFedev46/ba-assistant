from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.config import Settings
from app.engine.profile_loader import load_profile_file
from app.engine.state_editor import StateEditor
from app.llm.providers.fake import FakeLLM
from app.llm.router import ListAuditSink, ModelRouter

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def router(fake_llm: FakeLLM) -> ModelRouter:
    policy = yaml.safe_load((BACKEND_DIR / "config/model_policy.yaml").read_text(encoding="utf-8"))
    providers = {pid: fake_llm for pid in ("fake", "anthropic", "openai", "gemini", "selfhosted")}
    return ModelRouter(policy, providers, audit=ListAuditSink())


@pytest.fixture
def audit(router: ModelRouter) -> ListAuditSink:
    assert isinstance(router.audit, ListAuditSink)
    return router.audit


@pytest.fixture
def state_editor(router: ModelRouter) -> StateEditor:
    return StateEditor(router)


def load_profile(project: str):
    return load_profile_file(BACKEND_DIR / "profiles" / f"{project}.yaml")


@pytest.fixture
def profile_family():
    return load_profile("family-package")


@pytest.fixture
def profile_ux():
    return load_profile("ux")


@pytest.fixture
def profile_generic():
    return load_profile("generic")


@pytest.fixture
def settings_offline() -> Settings:
    return Settings(
        model_policy_path="config/model_policy.yaml",
        connectors_path="config/connectors.yaml",
        profiles_dir="profiles",
        llm_fake=True,
        auth_disabled=True,
        database_url="sqlite+aiosqlite:///:memory:",
    )


@pytest.fixture
async def db_factory():
    """Session factory sqlite :memory: với schema đã tạo (StaticPool — 1 connection chia nhau)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db.engine import create_db_engine
    from app.db.models import Base

    engine = create_db_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()
