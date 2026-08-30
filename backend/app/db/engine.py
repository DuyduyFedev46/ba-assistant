from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


def create_db_engine(url: str) -> AsyncEngine:
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool  # mọi connection chia 1 db trong bộ nhớ
    return create_async_engine(url, **kwargs)


def create_session_factory(url: str) -> async_sessionmaker:
    return async_sessionmaker(create_db_engine(url), expire_on_commit=False)
