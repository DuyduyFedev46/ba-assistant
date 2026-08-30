"""App factory — mount routers + wire dependencies (engine headless, mọi thứ qua HTTP)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker

from .api import ingest, meetings, projects
from .config import Settings, get_settings
from .db.engine import create_db_engine
from .db.models import Base
from .integrations.registry import ConnectorRegistry
from .llm.router import ModelRouter
from .services.audit import DBAuditSink
from .services.meeting_service import MeetingService


def create_app(settings: Settings | None = None) -> FastAPI:
    """App factory — tham số hoá để test (sqlite memory + LLM fake) và prod dùng chung."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_db_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        audit = DBAuditSink(session_factory)
        router = ModelRouter.from_settings(settings, audit=audit)
        connectors = ConnectorRegistry.from_settings(settings)
        service = MeetingService(
            session_factory=session_factory,
            router=router,
            connectors=connectors,
            profiles_dir=settings.profiles_dir_path,
            templates_dir=settings.resolve("templates"),
        )
        app.state.settings = settings
        app.state.session_factory = session_factory
        app.state.router = router
        app.state.connectors = connectors
        app.state.service = service
        yield
        await engine.dispose()

    app = FastAPI(
        title="BA Assistant — Platform hiểu-họp theo nhịp",
        version="0.1.0",
        lifespan=lifespan,
    )
    # FE dev (Next.js :3000) gọi API :8000 — chỉ mở khi khác origin, không kèm credentials.
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(projects.router)
    app.include_router(meetings.router)
    app.include_router(ingest.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
