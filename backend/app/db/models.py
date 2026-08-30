"""Bảng theo plan.md §6.1 — map 1:1. Portable sqlite/postgres (dùng JSON, không JSONB)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    repo_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id"))
    status: Mapped[str] = mapped_column(
        String(20), default="live"
    )  # live|unassigned|ended|packaged
    calendar_event_id: Mapped[str | None] = mapped_column(String(255))
    calendar_source: Mapped[str | None] = mapped_column(String(20))
    profile_key: Mapped[str] = mapped_column(String(120), default="generic")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Beat(Base):
    __tablename__ = "beats"
    __table_args__ = (UniqueConstraint("meeting_id", "nhip_id"),)

    meeting_id: Mapped[UUID] = mapped_column(ForeignKey("meetings.id"), primary_key=True)
    nhip_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open|closed
    transcript: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestChunk(Base):
    __tablename__ = "ingest_chunks"
    __table_args__ = (UniqueConstraint("meeting_id", "chunk_id"),)  # dedup cứng

    meeting_id: Mapped[UUID] = mapped_column(ForeignKey("meetings.id"), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str | None] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    ts_start: Mapped[float | None] = mapped_column()
    ts_end: Mapped[float | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StateItemRow(Base):
    __tablename__ = "state_items"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    meeting_id: Mapped[UUID] = mapped_column(ForeignKey("meetings.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # DECISION|OPEN|ACTION
    status: Mapped[str] = mapped_column(String(12), default="active")
    subject_key: Mapped[str] = mapped_column(String(120), nullable=False)
    core: Mapped[dict] = mapped_column(JSON, default=dict)
    profile_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    supersedes: Mapped[UUID | None] = mapped_column()
    superseded_by: Mapped[UUID | None] = mapped_column()
    answered_by: Mapped[UUID | None] = mapped_column()
    created_nhip: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_nhip: Mapped[int] = mapped_column(Integer, nullable=False)


class MeetingStateSnapshot(Base):
    __tablename__ = "meeting_state_snapshot"

    meeting_id: Mapped[UUID] = mapped_column(ForeignKey("meetings.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OpLog(Base):
    __tablename__ = "op_log"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    meeting_id: Mapped[UUID] = mapped_column(ForeignKey("meetings.id"), nullable=False, index=True)
    nhip_id: Mapped[int] = mapped_column(Integer, nullable=False)
    op_type: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    meeting_id: Mapped[UUID | None] = mapped_column(ForeignKey("meetings.id"))
    task: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_est: Mapped[float | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectMember(Base):
    __tablename__ = "project_members"

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(120), primary_key=True)  # supabase auth uid
