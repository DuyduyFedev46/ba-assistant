"""Meetings — vòng đời họp: mở, state, oplog, assign, end, package (headless qua service)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..integrations.protocol import ConnectorError
from ..services.meeting_service import BusinessError, MeetingService
from .deps import get_service

router = APIRouter(tags=["meetings"])


class MeetingCreate(BaseModel):
    project_slug: str | None = None
    event_id: str | None = None
    calendar_source: str = "google"


class AssignBody(BaseModel):
    project_slug: str


def as_http(exc: Exception) -> HTTPException:
    """Map lỗi service → HTTP: BusinessError → 404, ConnectorError → 502, khác → 500."""
    if isinstance(exc, BusinessError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ConnectorError):
        return HTTPException(status_code=502, detail="nguồn dữ liệu ngoài lỗi")
    return HTTPException(status_code=500, detail="lỗi nội bộ")


def _meeting_out(meeting) -> dict:
    return {
        "id": str(meeting.id),
        "status": meeting.status,
        "profile_key": meeting.profile_key,
        "project_id": str(meeting.project_id) if meeting.project_id else None,
        "calendar_event_id": meeting.calendar_event_id,
    }


@router.post("/meetings", status_code=201)
async def create_meeting(
    body: MeetingCreate,
    service: Annotated[MeetingService, Depends(get_service)],
) -> dict:
    """Mở họp: gán project (project_slug) hoặc route từ calendar event — 201 + meeting info."""
    try:
        meeting = await service.create_meeting(
            project_slug=body.project_slug,
            event_id=body.event_id,
            calendar_source=body.calendar_source,
        )
    except Exception as exc:
        raise as_http(exc) from exc
    return _meeting_out(meeting)


@router.get("/meetings")
async def list_meetings(
    service: Annotated[MeetingService, Depends(get_service)],
) -> dict:
    """Danh sách họp (metadata + summary) cho FE — mới nhất trước."""
    try:
        return {"items": await service.get_meetings()}
    except Exception as exc:
        raise as_http(exc) from exc


@router.get("/meetings/{meeting_id}/transcript")
async def get_transcript(
    meeting_id: UUID,
    service: Annotated[MeetingService, Depends(get_service)],
) -> dict:
    """Transcript thô + timeline nhịp cho portal (auth bắt buộc khi auth bật).

    Không log payload — chunk chỉ trả về cho client đã xác thực.
    """
    try:
        return await service.get_transcript(meeting_id=meeting_id)
    except Exception as exc:
        raise as_http(exc) from exc


@router.get("/meetings/{meeting_id}")
@router.get("/meetings/{meeting_id}/state")
async def get_state(
    meeting_id: UUID,
    service: Annotated[MeetingService, Depends(get_service)],
) -> dict:
    """State hiện tại (items + version + summary) — 404 nếu meeting không tồn tại."""
    try:
        return await service.get_state(meeting_id=meeting_id)
    except Exception as exc:
        raise as_http(exc) from exc


@router.get("/meetings/{meeting_id}/oplog")
async def get_oplog(
    meeting_id: UUID,
    service: Annotated[MeetingService, Depends(get_service)],
) -> dict:
    """Op log mọi biên tập theo nhịp — 404 nếu meeting không tồn tại."""
    try:
        return {"items": await service.get_oplog(meeting_id=meeting_id)}
    except Exception as exc:
        raise as_http(exc) from exc


@router.post("/meetings/{meeting_id}/assign")
async def assign_project(
    meeting_id: UUID,
    body: AssignBody,
    service: Annotated[MeetingService, Depends(get_service)],
) -> dict:
    """Fallback routing: BA gán project sau họp — 404 nếu meeting/project không tồn tại."""
    try:
        meeting = await service.assign_project(
            meeting_id=meeting_id, project_slug=body.project_slug
        )
    except Exception as exc:
        raise as_http(exc) from exc
    return {
        "id": str(meeting.id),
        "status": meeting.status,
        "profile_key": meeting.profile_key,
        "project_id": str(meeting.project_id),
    }


@router.post("/meetings/{meeting_id}/end")
async def end_meeting(
    meeting_id: UUID,
    service: Annotated[MeetingService, Depends(get_service)],
) -> dict:
    """Kết thúc họp — mở đường cho package — 404 nếu meeting không tồn tại."""
    try:
        meeting = await service.end_meeting(meeting_id=meeting_id)
    except Exception as exc:
        raise as_http(exc) from exc
    return {
        "id": str(meeting.id),
        "status": meeting.status,
        "ended_at": meeting.ended_at.isoformat() if meeting.ended_at else None,
    }


@router.post("/meetings/{meeting_id}/package")
async def package(
    meeting_id: UUID,
    service: Annotated[MeetingService, Depends(get_service)],
) -> dict:
    """Đóng gói state cuối → file + commit repo (chỉ khi đã end) — 502 nếu connector lỗi."""
    try:
        result = await service.package(meeting_id=meeting_id)
    except Exception as exc:
        raise as_http(exc) from exc
    return {"files": result.files, "commit": result.commit, "repo": result.repo}
