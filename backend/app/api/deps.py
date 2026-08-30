"""Dependencies chung cho API layer — session DB, service, auth (Firebase ID token)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import repos
from ..services.meeting_service import MeetingService

logger = logging.getLogger(__name__)

_FIREBASE_ISSUER = "https://securetoken.google.com/"
_FIREBASE_CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
)


async def verify_firebase_id_token(token: str, firebase_project_id: str) -> str:
    """Verify Firebase ID token (RS256, certs Google) → user_id (sub). 401 nếu sai/expired."""
    try:
        claims = await run_in_threadpool(
            id_token.verify_oauth2_token,
            token,
            google_requests.Request(),
            audience=firebase_project_id,
            certs_url=_FIREBASE_CERTS_URL,
        )
    except Exception as exc:
        logger.warning("auth: token không verify được: %s", exc)
        raise HTTPException(status_code=401, detail="token không hợp lệ") from exc
    if claims.get("iss") != _FIREBASE_ISSUER + firebase_project_id:
        raise HTTPException(status_code=401, detail="issuer không khớp")
    return str(claims.get("sub") or "unknown")


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Session DB mỗi request từ app.state.session_factory."""
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_service(request: Request) -> MeetingService:
    return request.app.state.service


async def get_current_user(request: Request) -> str:
    """auth_disabled (dev) → 'dev-user'; ngược lại verify Firebase ID token (Bearer JWT).

    Chưa cấu hình FIREBASE_PROJECT_ID → 501 (tránh chạy prod không auth vô tình).
    """
    settings = request.app.state.settings
    if settings.auth_disabled:
        return "dev-user"
    if not settings.firebase_project_id:
        raise HTTPException(
            status_code=501,
            detail="Auth chưa cấu hình — set FIREBASE_PROJECT_ID",
        )
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="thiếu Authorization: Bearer <token>")
    return await verify_firebase_id_token(auth[7:], settings.firebase_project_id)


async def require_project_access(user_id: str, project_id: UUID, session: AsyncSession) -> None:
    """RBAC: dev-user hoặc member (project_members rỗng = mở). Không đủ quyền → 403."""
    if user_id == "dev-user":
        return
    if not await repos.is_project_member(session, project_id, user_id):
        raise HTTPException(status_code=403, detail="không thuộc project")
