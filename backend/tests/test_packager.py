"""Unit test packager — state cuối → file theo file_convention + commit về repo (fake)."""

import json
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from app.engine.operations import CreateOp, Evidence, apply_operations
from app.engine.packager import Packager
from app.engine.state import MeetingState
from app.integrations.fakes import FakeRepoConnector
from app.integrations.registry import ConnectorRegistry
from tests.conftest import BACKEND_DIR


def make_state(profile_family) -> MeetingState:
    ops = [
        CreateOp(
            item_type="DECISION",
            subject_key="scope",
            core={"title": "Chốt scope", "rationale": "đủ cho MVP"},
            profile_fields={"impacts": "contract"},
            evidence=Evidence(quote="chốt scope", span=[0, 2]),
        ),
        CreateOp(
            item_type="ACTION",
            subject_key="tasks",
            core={"title": "Viết BRD"},
            profile_fields={"owner": "BE-Nam", "due": "2026-09-05"},
            evidence=Evidence(quote="giao BE-Nam", span=[0, 3]),
        ),
    ]
    items, _ = apply_operations(
        MeetingState(meeting_id=uuid4()), ops, nhip_id=1, profile=profile_family
    )
    return MeetingState(meeting_id=uuid4(), items=items, version=1)


async def test_package_renders_and_commits(profile_family):
    registry = ConnectorRegistry()
    repo = FakeRepoConnector()
    registry.register(repo)
    packager = Packager(registry, templates_dir=BACKEND_DIR / "templates")

    meeting = SimpleNamespace(started_at=datetime(2026, 8, 30, 9, 0))
    result = await packager.package(
        meeting=meeting, profile=profile_family, state=make_state(profile_family)
    )

    # 1) file theo file_convention + meeting-state.json
    assert "meetings/2026-08-30-family-package.md" in result.files
    assert "meeting-state.json" in result.files

    md = result.files["meetings/2026-08-30-family-package.md"]
    assert "Family Package — requirement/design" in md
    assert "**Chốt scope**" in md
    assert "impacts: contract" in md
    assert "owner: BE-Nam" in md
    assert "due: 2026-09-05" in md

    state_json = json.loads(result.files["meeting-state.json"])
    assert state_json["version"] == 1
    assert {it["type"] for it in state_json["items"]} == {"DECISION", "ACTION"}

    # 2) commit ghi vào connector (seam repo)
    assert len(repo.commits) == 1
    commit = repo.commits[0]
    assert commit["repo_url"] == "git@git.company:be/family-pkg.git"
    assert commit["commit"] == "fake-0001"
    assert "2026-08-30" in commit["message"]
    assert result.commit == "fake-0001"
