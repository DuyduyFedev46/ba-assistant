"""Connector swap seam + luồng service headless: routing calendar (fake) → state-edit →
assign (fallback) → end → package (fake repo). Không cần FE, không cần creds."""

from pathlib import Path

from app.db import repos
from app.integrations.fakes import FakeCalendarConnector, FakeRepoConnector
from app.integrations.registry import ConnectorRegistry
from app.llm.providers.base import ToolCall
from app.services.meeting_service import MeetingService
from tests.conftest import BACKEND_DIR


def make_service(
    db_factory,
    router,
    calendar: FakeCalendarConnector | None = None,
    repo: FakeRepoConnector | None = None,
) -> MeetingService:
    connectors = ConnectorRegistry()
    connectors.register(calendar or FakeCalendarConnector())
    connectors.register(repo or FakeRepoConnector())
    return MeetingService(
        session_factory=db_factory,
        router=router,
        connectors=connectors,
        profiles_dir=Path(BACKEND_DIR) / "profiles",
        templates_dir=Path(BACKEND_DIR) / "templates",
    )


async def seed_family_project(db_factory):
    yaml_text = (BACKEND_DIR / "profiles/family-package.yaml").read_text(encoding="utf-8")
    async with db_factory() as session:
        return await repos.create_project(
            session, slug="family-package", name="Family Package", profile_yaml=yaml_text
        )


async def test_calendar_routing_assigns_project(db_factory, router):
    """Event khớp calendar_tags → meeting gán đúng project (không cần user bấm)."""
    await seed_family_project(db_factory)
    service = make_service(db_factory, router)

    meeting = await service.create_meeting(event_id="evt-family")
    assert meeting.status == "live"
    assert meeting.profile_key == "family-package"
    assert meeting.project_id is not None

    plain = await service.create_meeting(event_id="evt-plain")
    assert plain.status == "unassigned"
    assert plain.profile_key == "generic"
    assert plain.project_id is None


async def test_unassigned_meeting_still_processes_beats(db_factory, router, fake_llm):
    """Meeting chưa gán dự án → vẫn state-edit bằng generic profile (không mất dữ liệu)."""
    service = make_service(db_factory, router)
    meeting = await service.create_meeting(event_id="evt-plain")
    assert meeting.status == "unassigned"

    fake_llm.enqueue_text("segment_confirm", '{"closed": true, "reason": "closing_cue"}')
    fake_llm.enqueue(
        "state_edit",
        [
            ToolCall(
                name="create_item",
                args={
                    "item_type": "DECISION",
                    "subject_key": "scope",
                    "core": {"title": "Chốt generic"},
                    "evidence": {"quote": "chốt vậy", "span": [0, 3]},
                },
            )
        ],
    )
    r = await service.ingest(
        meeting_id=meeting.id,
        chunk_id="c1",
        seq=1,
        speaker="BA",
        text="Chốt vậy phạm vi.",
        ts_start=0.0,
        ts_end=2.0,
    )
    assert r == {"status": "ok", "beat": 1, "state_changed": True, "version": 1}

    state = await service.get_state(meeting_id=meeting.id)
    assert state["version"] == 1
    assert state["summary"]["decision_count"] == 1
    assert state["items"][0]["core"]["title"] == "Chốt generic"


async def test_duplicate_chunk_idempotent(db_factory, router, fake_llm):
    """Chunk gửi lại (reconnect) → duplicate, không đổi state."""
    service = make_service(db_factory, router)
    meeting = await service.create_meeting(event_id="evt-plain")

    fake_llm.enqueue_text("segment_confirm", '{"closed": true}')
    fake_llm.enqueue(
        "state_edit",
        [
            ToolCall(
                name="create_item",
                args={"item_type": "DECISION", "subject_key": "a", "core": {"title": "A"}},
            )
        ],
    )
    await service.ingest(
        meeting_id=meeting.id,
        chunk_id="c1",
        seq=1,
        speaker="BA",
        text="Chốt vậy A.",
        ts_start=0.0,
        ts_end=2.0,
    )

    r = await service.ingest(
        meeting_id=meeting.id,
        chunk_id="c1",
        seq=1,
        speaker="BA",
        text="Chốt vậy A.",
        ts_start=0.0,
        ts_end=2.0,
    )
    assert r["status"] == "duplicate"
    state = await service.get_state(meeting_id=meeting.id)
    assert state["version"] == 1  # không nhân đôi


async def test_assign_end_package_full_flow(db_factory, router, fake_llm):
    """Unassigned → ingest (generic) → assign family-package → end → package về fake repo."""
    await seed_family_project(db_factory)
    service = make_service(db_factory, router)
    meeting = await service.create_meeting(event_id="evt-plain")

    fake_llm.enqueue_text("segment_confirm", '{"closed": true}')
    fake_llm.enqueue(
        "state_edit",
        [
            ToolCall(
                name="create_item",
                args={
                    "item_type": "DECISION",
                    "subject_key": "scope",
                    "core": {"title": "Chốt scope"},
                },
            )
        ],
    )
    await service.ingest(
        meeting_id=meeting.id,
        chunk_id="c1",
        seq=1,
        speaker="BA",
        text="Chốt vậy scope.",
        ts_start=0.0,
        ts_end=2.0,
    )

    meeting = await service.assign_project(meeting_id=meeting.id, project_slug="family-package")
    assert meeting.status == "live"
    assert meeting.profile_key == "family-package"

    meeting = await service.end_meeting(meeting_id=meeting.id)
    assert meeting.status == "ended"

    result = await service.package(meeting_id=meeting.id)
    assert result.commit == "fake-0001"
    assert "meetings/2026-08-30-family-package.md" in result.files
    assert "Chốt scope" in result.files["meetings/2026-08-30-family-package.md"]

    state = await service.get_state(meeting_id=meeting.id)
    assert state["status"] == "packaged"
