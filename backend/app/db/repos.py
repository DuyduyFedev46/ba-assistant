"""Repo layer — mọi truy cập DB tập trung ở đây (plan.md §6.2).
Session async, portable sqlite/postgres."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..engine.state import MeetingState, StateItem
from .models import (
    Beat,
    IngestChunk,
    Meeting,
    MeetingStateSnapshot,
    OpLog,
    Project,
    StateItemRow,
)

# ---------------------------------------------------------------- projects / meetings


async def get_project(session: AsyncSession, project_id: UUID) -> Project | None:
    return await session.get(Project, project_id)


async def get_project_by_slug(session: AsyncSession, slug: str) -> Project | None:
    stmt = select(Project).where(Project.slug == slug)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_projects(session: AsyncSession) -> list[Project]:
    stmt = select(Project).order_by(Project.created_at)
    return list((await session.execute(stmt)).scalars().all())


async def create_project(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    profile_yaml: str,
    repo_url: str | None = None,
) -> Project:
    project = Project(slug=slug, name=name, profile_yaml=profile_yaml, repo_url=repo_url)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def is_project_member(session: AsyncSession, project_id: UUID, user_id: str) -> bool:
    """RBAC: user có trong project_members? Không có member nào → ai cũng được (dev)."""
    from .models import ProjectMember

    stmt = select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
    members = set((await session.execute(stmt)).scalars().all())
    return not members or user_id in members


async def get_meeting(session: AsyncSession, meeting_id: UUID) -> Meeting | None:
    return await session.get(Meeting, meeting_id)


async def list_meetings(session: AsyncSession) -> list[Meeting]:
    stmt = select(Meeting).order_by(Meeting.started_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def set_meeting_project(session: AsyncSession, meeting_id: UUID, project: Project) -> None:
    meeting = await get_meeting(session, meeting_id)
    if meeting is None:
        raise LookupError(f"meeting {meeting_id} không tồn tại")
    meeting.project_id = project.id
    meeting.profile_key = project.slug
    meeting.status = "live"


async def set_meeting_status(session: AsyncSession, meeting_id: UUID, status: str) -> None:
    meeting = await get_meeting(session, meeting_id)
    if meeting is None:
        raise LookupError(f"meeting {meeting_id} không tồn tại")
    meeting.status = status
    if status == "ended":
        meeting.ended_at = datetime.now(UTC)


# ---------------------------------------------------------------- chunks / beats


def _insert_for(session: AsyncSession):
    """INSERT theo dialect của session — ON CONFLICT của sqlite và postgres không tương thích."""
    return pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert


async def insert_chunk_dedup(
    session: AsyncSession,
    *,
    meeting_id: UUID,
    chunk_id: str,
    seq: int,
    speaker: str | None,
    text: str,
    ts_start: float | None,
    ts_end: float | None,
) -> bool:
    """Chunk idempotent — ON CONFLICT DO NOTHING trên (meeting_id, chunk_id). True nếu chunk MỚI."""
    stmt = (
        _insert_for(session)(IngestChunk)
        .values(
            meeting_id=meeting_id,
            chunk_id=chunk_id,
            seq=seq,
            speaker=speaker,
            text=text,
            ts_start=ts_start,
            ts_end=ts_end,
        )
        .on_conflict_do_nothing(index_elements=[IngestChunk.meeting_id, IngestChunk.chunk_id])
    )
    res = await session.execute(stmt)
    return res.rowcount > 0


async def get_chunk_by_seq(session: AsyncSession, meeting_id: UUID, seq: int) -> IngestChunk | None:
    stmt = (
        select(IngestChunk)
        .where(IngestChunk.meeting_id == meeting_id, IngestChunk.seq == seq)
        .order_by(IngestChunk.created_at.desc())
    )
    return (await session.execute(stmt)).scalars().first()


async def max_nhip(session: AsyncSession, meeting_id: UUID) -> int:
    stmt = select(func.max(Beat.nhip_id)).where(Beat.meeting_id == meeting_id)
    return (await session.execute(stmt)).scalar() or 0


async def get_open_beat(session: AsyncSession, meeting_id: UUID) -> Beat | None:
    stmt = (
        select(Beat)
        .where(Beat.meeting_id == meeting_id, Beat.status == "open")
        .order_by(Beat.nhip_id.desc())
    )
    return (await session.execute(stmt)).scalars().first()


async def get_beat(session: AsyncSession, meeting_id: UUID, nhip_id: int) -> Beat | None:
    return await session.get(Beat, (meeting_id, nhip_id))


async def create_beat(session: AsyncSession, meeting_id: UUID, nhip_id: int) -> Beat:
    beat = Beat(meeting_id=meeting_id, nhip_id=nhip_id)
    session.add(beat)
    return beat


async def close_beat(session: AsyncSession, meeting_id: UUID, nhip_id: int) -> None:
    beat = await get_beat(session, meeting_id, nhip_id)
    if beat is None:
        return
    beat.status = "closed"
    beat.closed_at = datetime.now(UTC)


async def list_chunks(session: AsyncSession, meeting_id: UUID) -> list[IngestChunk]:
    """Transcript thô theo thứ tự seq — chỉ phục vụ hiển thị live, không dùng cho engine."""
    stmt = (
        select(IngestChunk)
        .where(IngestChunk.meeting_id == meeting_id)
        .order_by(IngestChunk.seq)
    )
    return list((await session.execute(stmt)).scalars())


async def list_beats(session: AsyncSession, meeting_id: UUID) -> list[Beat]:
    """Timeline nhịp (mở/khép) cho portal."""
    stmt = select(Beat).where(Beat.meeting_id == meeting_id).order_by(Beat.nhip_id)
    return list((await session.execute(stmt)).scalars())


# ---------------------------------------------------------------- state


def row_to_item(row: StateItemRow) -> StateItem:
    return StateItem(
        id=row.id,
        type=row.type,
        status=row.status,
        subject_key=row.subject_key,
        core=dict(row.core or {}),
        profile_fields=dict(row.profile_fields or {}),
        provenance=dict(row.provenance or {}),
        supersedes=row.supersedes,
        superseded_by=row.superseded_by,
        answered_by=row.answered_by,
        created_nhip=row.created_nhip,
        updated_nhip=row.updated_nhip,
    )


def item_to_row(meeting_id: UUID, it: StateItem) -> StateItemRow:
    return StateItemRow(
        id=it.id,
        meeting_id=meeting_id,
        type=it.type,
        status=it.status,
        subject_key=it.subject_key,
        core=it.core,
        profile_fields=it.profile_fields,
        provenance=it.provenance,
        supersedes=it.supersedes,
        superseded_by=it.superseded_by,
        answered_by=it.answered_by,
        created_nhip=it.created_nhip,
        updated_nhip=it.updated_nhip,
    )


async def load_state(session: AsyncSession, meeting_id: UUID) -> tuple[MeetingState, int]:
    """Items từ state_items + version từ snapshot. State rỗng nếu chưa có nhịp nào."""
    stmt = (
        select(StateItemRow)
        .where(StateItemRow.meeting_id == meeting_id)
        .order_by(StateItemRow.created_nhip)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    snap = await session.get(MeetingStateSnapshot, meeting_id)
    version = snap.version if snap is not None else 0
    return MeetingState(
        meeting_id=meeting_id, items=[row_to_item(r) for r in rows], version=version
    ), version


async def save_state(session: AsyncSession, state: MeetingState) -> None:
    """Thay toàn bộ items + upsert snapshot. Commit do caller (transaction duy nhất)."""
    await session.execute(delete(StateItemRow).where(StateItemRow.meeting_id == state.meeting_id))
    for it in state.items:
        session.add(item_to_row(state.meeting_id, it))
    snap = await session.get(MeetingStateSnapshot, state.meeting_id)
    dump = state.model_dump(mode="json")
    if snap is None:
        session.add(
            MeetingStateSnapshot(meeting_id=state.meeting_id, version=state.version, snapshot=dump)
        )
    else:
        snap.version = state.version
        snap.snapshot = dump
        snap.updated_at = datetime.now(UTC)


# ---------------------------------------------------------------- op_log / audit


async def append_op_log(
    session: AsyncSession, meeting_id: UUID, nhip_id: int, entries: list[dict]
) -> None:
    """entries = [{op_type, payload}] — chính là `applied` từ apply_operations."""
    for e in entries:
        session.add(
            OpLog(
                meeting_id=meeting_id,
                nhip_id=nhip_id,
                op_type=e["op_type"],
                payload=e.get("payload") or {},
            )
        )


async def list_oplog(session: AsyncSession, meeting_id: UUID) -> list[OpLog]:
    stmt = select(OpLog).where(OpLog.meeting_id == meeting_id).order_by(OpLog.id)
    return list((await session.execute(stmt)).scalars().all())
