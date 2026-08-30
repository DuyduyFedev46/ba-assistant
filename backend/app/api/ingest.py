"""Ingest — nhận chunk transcript từ FE/STT, chạy pipeline cắt nhịp (idempotent theo chunk_id)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..services.meeting_service import BusinessError, MeetingService
from .deps import get_service

router = APIRouter(tags=["ingest"])


class ChunkIn(BaseModel):
    chunk_id: str
    seq: int
    speaker: str | None = None
    text: str
    ts_start: float | None = None
    ts_end: float | None = None


@router.post("/meetings/{meeting_id}/ingest")
async def ingest_chunk(
    meeting_id: UUID,
    body: ChunkIn,
    service: Annotated[MeetingService, Depends(get_service)],
) -> dict:
    """Chunk → pipeline cắt nhịp. Trả dict service (status/beat/state_changed/version)."""
    try:
        return await service.ingest(
            meeting_id=meeting_id,
            chunk_id=body.chunk_id,
            seq=body.seq,
            speaker=body.speaker,
            text=body.text,
            ts_start=body.ts_start,
            ts_end=body.ts_end,
        )
    except BusinessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
