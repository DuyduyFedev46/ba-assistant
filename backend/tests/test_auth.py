"""Auth API: auth_disabled → dev-user; bật auth (FIREBASE_PROJECT_ID) → 401 khi thiếu token;
chưa cấu hình → 501. Token thật (RS256) không test offline — verify qua google-auth certs."""

import httpx
import pytest
from httpx import ASGITransport

from app.main import create_app


@pytest.fixture
async def api_offline(settings_offline):
    app = create_app(settings_offline)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client


async def test_auth_disabled_returns_dev_user(api_offline):
    """Chế độ dev (AUTH_DISABLED=1): GET /projects không cần token."""
    r = await api_offline.get("/projects")
    assert r.status_code == 200


async def test_auth_missing_config_returns_501(settings_offline):
    """Bật auth nhưng chưa cấu hình FIREBASE_PROJECT_ID → 501 (không chạy prod hở)."""
    settings = settings_offline.model_copy(
        update={"auth_disabled": False, "firebase_project_id": ""}
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/projects")
            assert r.status_code == 501
            assert "FIREBASE_PROJECT_ID" in r.json()["detail"]


async def test_auth_requires_bearer(settings_offline):
    """Có cấu hình project id (giả) → mọi request phải kèm Bearer token."""
    settings = settings_offline.model_copy(
        update={"auth_disabled": False, "firebase_project_id": "ba-assistant-portal"}
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/projects")
            assert r.status_code == 401
            assert "Bearer" in r.json()["detail"]
