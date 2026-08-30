"""MeetingService — dàn nhịp toàn bộ luồng họp (plan.md §12):
ingest (idempotent) → cắt nhịp (heuristic + LLM confirm) → state-edit pass → op_log + snapshot;
routing calendar khi mở họp; assign/end/package. HEADLESS: FE tắt, mọi thứ chạy qua service."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from ..db import repos
from ..db.models import Beat, Meeting
from ..engine.packager import Packager, PackageResult
from ..engine.profile_loader import Profile, load_profile_file, load_profile_yaml
from ..engine.segmenter import Segmenter, heuristic_segment, split_turns
from ..engine.state import MeetingState
from ..engine.state_editor import StateEditor
from ..integrations.registry import ConnectorRegistry
from ..llm.router import ModelRouter

logger = logging.getLogger(__name__)


class BusinessError(Exception):
    """Lỗi nghiệp vụ — API map sang 4xx."""


def _spread_ts(
    pieces: list[str], ts_start: float | None, ts_end: float | None
) -> list[tuple[str, float | None, float | None]]:
    """Rải mốc thời gian của chunk gốc lên các lượt đã tách, theo tỉ lệ số từ.

    Chunk dán tay không có thông tin khoảng lặng thật, nên các lượt nằm liền nhau
    (gap ~ 0): segmenter sẽ cắt nhịp theo cue đóng và buffer_full thay vì theo im lặng.
    """
    if ts_start is None or ts_end is None or ts_end <= ts_start:
        return [(p, None, None) for p in pieces]
    counts = [max(1, len(p.split())) for p in pieces]
    total = sum(counts)
    span = ts_end - ts_start
    out: list[tuple[str, float | None, float | None]] = []
    cursor = ts_start
    for piece, n in zip(pieces, counts, strict=True):
        nxt = cursor + span * n / total
        out.append((piece, round(cursor, 2), round(nxt, 2)))
        cursor = nxt
    return out


class MeetingService:
    """Dependency graph: router(LLM) + connectors(thế giới ngoài) + profiles(config).
    Không trạng thái ngoài khóa/lock."""

    def __init__(
        self,
        *,
        session_factory,
        router: ModelRouter,
        connectors: ConnectorRegistry,
        profiles_dir: Path,
        templates_dir: Path,
    ) -> None:
        self.session_factory = session_factory
        self.connectors = connectors
        self.profiles_dir = profiles_dir
        self.editor = StateEditor(router)
        self.segmenter = Segmenter(router)
        self.packager = Packager(connectors, templates_dir)
        self._locks: dict[UUID, asyncio.Lock] = {}
        # in-memory: seq chunk MỞ nhịp hiện tại (để tính beat_sec theo ts của chunk).
        # Reset khi restart — tham số calibrate, chấp nhận cho bản đầu.
        self._beat_anchor_seq: dict[UUID, int] = {}

    def _lock(self, meeting_id: UUID) -> asyncio.Lock:
        return self._locks.setdefault(meeting_id, asyncio.Lock())

    # ---------------------------------------------------------------- profile

    def _load_profile_file(self, key: str) -> Profile:
        path = self.profiles_dir / f"{key}.yaml"
        if not path.exists():
            logger.warning("profile '%s' không có file — fallback generic", key)
            path = self.profiles_dir / "generic.yaml"
        return load_profile_file(path)

    async def _profile_for(self, session, meeting: Meeting) -> Profile:
        """Profile nguồn: project đã gán → yaml lưu trong DB; chưa gán → file theo profile_key."""
        if meeting.project_id is not None:
            project = await repos.get_project(session, meeting.project_id)
            if project is not None:
                return load_profile_yaml(project.profile_yaml)
        return self._load_profile_file(meeting.profile_key)

    # ---------------------------------------------------------------- create / routing

    async def create_meeting(
        self,
        *,
        event_id: str | None = None,
        calendar_source: str = "google",
        project_slug: str | None = None,
    ) -> Meeting:
        """Mở họp: gán project trực tiếp (project_slug) HOẶC route từ calendar event.
        Không khớp event → unassigned (vẫn dùng generic profile, không mất dữ liệu)."""
        async with self.session_factory() as session:
            meeting = Meeting(
                profile_key="generic",
                status="unassigned",
                calendar_source=calendar_source,
                calendar_event_id=event_id,
            )
            if project_slug is not None:
                project = await repos.get_project_by_slug(session, project_slug)
                if project is None:
                    raise BusinessError(f"project '{project_slug}' chưa tồn tại")
                meeting.project_id = project.id
                meeting.profile_key = project.slug
                meeting.status = "live"
            elif event_id:
                key = await self._route_event(session, event_id)
                if key is not None:
                    project = await repos.get_project_by_slug(session, key)
                    if project is not None:
                        meeting.project_id = project.id
                    meeting.profile_key = key
                    meeting.status = "live"
            session.add(meeting)
            await session.commit()
            await session.refresh(meeting)
            return meeting

    async def _route_event(self, session, event_id: str) -> str | None:
        """Event → slug project (khớp routing.calendar_tags trong profile). None → unassigned."""
        connector = self.connectors.get("calendar-google")
        out = await connector.call("resolve_event", {"event_id": event_id})
        event = out.get("event") or {}
        projects = await repos.list_projects(session)
        profiles = [load_profile_yaml(p.profile_yaml).model_dump(mode="json") for p in projects]
        matched = await connector.call("match_project", {"event": event, "profiles": profiles})
        return matched.get("matched_project") or matched.get("project")

    # ---------------------------------------------------------------- ingest pipeline

    async def ingest(
        self,
        *,
        meeting_id: UUID,
        chunk_id: str,
        seq: int,
        speaker: str | None,
        text: str,
        ts_start: float | None,
        ts_end: float | None,
    ) -> dict:
        """Nhận chunk; chunk quá dài thì tách thành nhiều lượt nói rồi chạy tuần tự.

        Nhịp KHÔNG BAO GIỜ nhỏ hơn chunk, nên một chunk ôm cả buổi họp sẽ thành đúng
        một nhịp và state-edit chỉ chạy một lượt — mất sạch revision-aware. Tách ở đây
        bịt cả đường paste lẫn đường STT/bot gửi chunk to.
        """
        async with self._lock(meeting_id):
            async with self.session_factory() as session:
                meeting = await repos.get_meeting(session, meeting_id)
                if meeting is None:
                    raise BusinessError(f"meeting {meeting_id} không tồn tại")
                profile = await self._profile_for(session, meeting)
                pieces = split_turns(text, profile.segmenter.max_beat_words)
                base_seq = await repos.max_seq(session, meeting_id)

            if len(pieces) <= 1:
                return await self._ingest_one(
                    meeting_id=meeting_id,
                    chunk_id=chunk_id,
                    seq=seq,
                    speaker=speaker,
                    text=text,
                    ts_start=ts_start,
                    ts_end=ts_end,
                )

            logger.info(
                "chunk %s dài %s từ → tách %s lượt", chunk_id, len(text.split()), len(pieces)
            )
            results = [
                await self._ingest_one(
                    meeting_id=meeting_id,
                    chunk_id=f"{chunk_id}#{i + 1}",
                    seq=base_seq + i + 1,
                    speaker=speaker,
                    text=piece,
                    ts_start=ts0,
                    ts_end=ts1,
                )
                for i, (piece, ts0, ts1) in enumerate(_spread_ts(pieces, ts_start, ts_end))
            ]
            changed = [r for r in results if r["state_changed"]]
            return {
                "status": "ok" if any(r["status"] == "ok" for r in results) else "duplicate",
                "beat": results[-1]["beat"],
                "state_changed": bool(changed),
                "version": changed[-1]["version"] if changed else None,
            }

    async def _ingest_one(
        self,
        *,
        meeting_id: UUID,
        chunk_id: str,
        seq: int,
        speaker: str | None,
        text: str,
        ts_start: float | None,
        ts_end: float | None,
    ) -> dict:
        """Một lượt nói → beat mở → heuristic cắt nhịp → (close → state-edit)."""
        async with self.session_factory() as session:
            meeting = await repos.get_meeting(session, meeting_id)
            if meeting is None:
                raise BusinessError(f"meeting {meeting_id} không tồn tại")
            inserted = await repos.insert_chunk_dedup(
                session,
                meeting_id=meeting_id,
                chunk_id=chunk_id,
                seq=seq,
                speaker=speaker,
                text=text,
                ts_start=ts_start,
                ts_end=ts_end,
            )
            if not inserted:
                await session.commit()
                return {
                    "status": "duplicate",
                    "beat": None,
                    "state_changed": False,
                    "version": None,
                }

            beat = await repos.get_open_beat(session, meeting_id)
            if beat is None:
                beat = await repos.create_beat(
                    session, meeting_id, (await repos.max_nhip(session, meeting_id)) + 1
                )
                self._beat_anchor_seq[meeting_id] = seq
            beat.transcript = (beat.transcript + "\n" if beat.transcript else "") + text

            profile = await self._profile_for(session, meeting)
            decision = await self._segment_decision(
                session, meeting_id, beat, seq, text, ts_start, ts_end, profile
            )

            if decision == "certain":
                await session.commit()  # release transaction trước LLM (sqlite 1 connection)
                return await self._close_beat(session, meeting_id, beat.nhip_id, profile)
            if decision == "weak":
                closed = await self.segmenter.confirm_close(
                    meeting_id=meeting_id, beat_text=beat.transcript
                )
                if closed:
                    await session.commit()
                    return await self._close_beat(session, meeting_id, beat.nhip_id, profile)
            await session.commit()
            return {
                "status": "ok",
                "beat": beat.nhip_id,
                "state_changed": False,
                "version": None,
            }

    async def _segment_decision(
        self, session, meeting_id, beat: Beat, seq, text, ts_start, ts_end, profile
    ) -> str | None:
        """Heuristic cắt nhịp — trả 'certain' | 'weak' | None (plan.md §8.4)."""
        prev = await repos.get_chunk_by_seq(session, meeting_id, seq - 1)
        gap = (
            ts_start - prev.ts_end
            if prev is not None and ts_start is not None and prev.ts_end is not None
            else None
        )
        cue = any(c in text.lower() for c in profile.segmenter.closing_cues)
        beat_words = len(beat.transcript.split())
        anchor = await repos.get_chunk_by_seq(
            session, meeting_id, self._beat_anchor_seq.get(meeting_id, seq)
        )
        beat_sec = (
            ts_end - anchor.ts_start
            if anchor is not None and anchor.ts_start is not None and ts_end is not None
            else None
        )
        return heuristic_segment(
            gap=gap, cue=cue, beat_words=beat_words, beat_sec=beat_sec, cfg=profile.segmenter
        )

    async def _close_beat(self, session, meeting_id: UUID, nhip_id: int, profile: Profile) -> dict:
        """Đóng nhịp → state-edit pass (plan.md §8.3). Snapshot version+1 CHỈ khi state đổi."""
        await repos.close_beat(session, meeting_id, nhip_id)
        beat = await repos.get_beat(session, meeting_id, nhip_id)
        state, version = await repos.load_state(session, meeting_id)
        await (
            session.commit()
        )  # session rảnh → LLM + audit (session riêng) chạy trên connection duy nhất

        result = await self.editor.edit(
            meeting_id=meeting_id,
            state=state,
            nhip_id=nhip_id,
            beat_text=beat.transcript if beat else "",
            profile=profile,
        )
        new_version = version
        if result.applied:
            new_version = version + 1
            new_state = MeetingState(meeting_id=meeting_id, items=result.items, version=new_version)
            await repos.save_state(session, new_state)
            await repos.append_op_log(session, meeting_id, nhip_id, result.applied)
        await session.commit()
        return {
            "status": "ok",
            "beat": nhip_id,
            "state_changed": bool(result.applied),
            "version": new_version,
        }

    # ---------------------------------------------------------------- read / lifecycle

    async def get_meetings(self) -> list[dict]:
        """Danh sách họp cho FE (không kèm transcript — chỉ metadata + summary nhanh)."""
        async with self.session_factory() as session:
            rows = await repos.list_meetings(session)
            out = []
            for m in rows:
                state, version = await repos.load_state(session, m.id)
                out.append(
                    {
                        "id": str(m.id),
                        "status": m.status,
                        "profile_key": m.profile_key,
                        "project_id": str(m.project_id) if m.project_id else None,
                        "calendar_event_id": m.calendar_event_id,
                        "started_at": m.started_at.isoformat() if m.started_at else None,
                        "ended_at": m.ended_at.isoformat() if m.ended_at else None,
                        "version": version,
                        "summary": state.summary(),
                    }
                )
            return out

    async def get_state(self, *, meeting_id: UUID) -> dict:
        async with self.session_factory() as session:
            meeting = await repos.get_meeting(session, meeting_id)
            if meeting is None:
                raise BusinessError(f"meeting {meeting_id} không tồn tại")
            state, version = await repos.load_state(session, meeting_id)
            return {
                "meeting_id": str(meeting_id),
                "status": meeting.status,
                "profile_key": meeting.profile_key,
                "version": version,
                "items": [it.model_dump(mode="json") for it in state.items],
                "summary": state.summary(),
            }

    async def get_transcript(self, *, meeting_id: UUID) -> dict:
        """Transcript thô + timeline nhịp cho portal (không phải nguồn cho engine).

        Privacy (brief): chỉ qua auth (deps) mới trả; không log payload ở đây.
        """
        async with self.session_factory() as session:
            meeting = await repos.get_meeting(session, meeting_id)
            if meeting is None:
                raise BusinessError(f"meeting {meeting_id} không tồn tại")
            chunks = await repos.list_chunks(session, meeting_id)
            beats = await repos.list_beats(session, meeting_id)
            return {
                "meeting_id": str(meeting_id),
                "status": meeting.status,
                "chunks": [
                    {
                        "chunk_id": c.chunk_id,
                        "seq": c.seq,
                        "speaker": c.speaker,
                        "text": c.text,
                        "ts_start": c.ts_start,
                        "ts_end": c.ts_end,
                    }
                    for c in chunks
                ],
                "beats": [
                    {
                        "nhip_id": b.nhip_id,
                        "status": b.status,
                        "transcript": b.transcript,
                        "started_at": b.started_at.isoformat() if b.started_at else None,
                        "closed_at": b.closed_at.isoformat() if b.closed_at else None,
                    }
                    for b in beats
                ],
            }

    async def get_oplog(self, *, meeting_id: UUID) -> list[dict]:
        async with self.session_factory() as session:
            if await repos.get_meeting(session, meeting_id) is None:
                raise BusinessError(f"meeting {meeting_id} không tồn tại")
            rows = await repos.list_oplog(session, meeting_id)
            return [
                {
                    "id": row.id,
                    "nhip_id": row.nhip_id,
                    "op_type": row.op_type,
                    "payload": row.payload,
                    "applied_at": row.applied_at.isoformat() if row.applied_at else None,
                }
                for row in rows
            ]

    async def assign_project(self, *, meeting_id: UUID, project_slug: str) -> Meeting:
        """Fallback routing: BA gán project sau họp (HITL). State re-map theo profile thật."""
        async with self.session_factory() as session:
            meeting = await repos.get_meeting(session, meeting_id)
            if meeting is None:
                raise BusinessError(f"meeting {meeting_id} không tồn tại")
            project = await repos.get_project_by_slug(session, project_slug)
            if project is None:
                raise BusinessError(f"project '{project_slug}' chưa tồn tại")
            await repos.set_meeting_project(session, meeting_id, project)
            await session.commit()
            await session.refresh(meeting)
            return meeting

    async def end_meeting(self, *, meeting_id: UUID) -> Meeting:
        """Kết thúc họp: đóng nhịp cuối còn mở (plan.md §12) rồi status=ended.

        Không flush thì transcript của nhịp cuối không bao giờ qua state-edit — mất trắng.
        """
        async with self._lock(meeting_id):
            async with self.session_factory() as session:
                meeting = await repos.get_meeting(session, meeting_id)
                if meeting is None:
                    raise BusinessError(f"meeting {meeting_id} không tồn tại")

                beat = await repos.get_open_beat(session, meeting_id)
                if beat is not None and (beat.transcript or "").strip():
                    profile = await self._profile_for(session, meeting)
                    nhip_id = beat.nhip_id
                    await session.commit()
                    await self._close_beat(session, meeting_id, nhip_id, profile)

                await repos.set_meeting_status(session, meeting_id, "ended")
                await session.commit()
                await session.refresh(meeting)
                return meeting

    async def package(self, *, meeting_id: UUID) -> PackageResult:
        """Đóng gói state cuối → file theo file_convention → commit về repo (chỉ khi đã end)."""
        async with self._lock(meeting_id):
            async with self.session_factory() as session:
                meeting = await repos.get_meeting(session, meeting_id)
                if meeting is None:
                    raise BusinessError(f"meeting {meeting_id} không tồn tại")
                if meeting.status != "ended":
                    raise BusinessError(f"meeting {meeting_id} chưa end — package chỉ sau khi end")
                profile = await self._profile_for(session, meeting)
                state, version = await repos.load_state(session, meeting_id)
                await session.commit()
                result = await self.packager.package(meeting=meeting, profile=profile, state=state)
                await repos.set_meeting_status(session, meeting_id, "packaged")
                await session.commit()
                return result
