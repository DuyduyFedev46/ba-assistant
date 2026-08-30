"""★ Test-headless (plan §14): toàn bộ luồng ingest → cắt nhịp → state sống → package
chạy qua HTTP API, FE tắt, LLM fake (echo_schema). Bằng chứng: API-first, không đụng tay."""

import httpx
import pytest
from httpx import ASGITransport

from app.main import create_app
from tests.conftest import BACKEND_DIR


@pytest.fixture
async def api(settings_offline):
    app = create_app(settings_offline)
    async with app.router.lifespan_context(app):
        fake = app.state.router.providers["fake"]
        fake.set_echo(True)  # mỗi state-edit sinh 1 DECISION deterministic — không cần script
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client


async def seed_project(api):
    yaml_text = (BACKEND_DIR / "profiles/family-package.yaml").read_text(encoding="utf-8")
    r = await api.post(
        "/projects",
        json={"slug": "family-package", "name": "Family Package", "profile_yaml": yaml_text},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def ingest(api, meeting_id, chunk_id, seq, text, ts_start, ts_end):
    r = await api.post(
        f"/meetings/{meeting_id}/ingest",
        json={
            "chunk_id": chunk_id,
            "seq": seq,
            "speaker": "BA",
            "text": text,
            "ts_start": ts_start,
            "ts_end": ts_end,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_headless_live_flow(api):
    await seed_project(api)
    r = await api.post("/meetings", json={"event_id": "evt-family"})
    assert r.status_code == 201, r.text
    meeting = r.json()
    assert meeting["status"] == "live"
    assert meeting["profile_key"] == "family-package"
    assert meeting["project_id"] is not None

    # ---- nhịp 1: mở (không có tín hiệu đóng)
    assert await ingest(api, meeting["id"], "c1", 1, "Bàn về phạm vi gói cơ bản.", 0.0, 2.0) == {
        "status": "ok",
        "beat": 1,
        "state_changed": False,
        "version": None,
    }
    # ---- nhịp 1 đóng: gap 10s ≥ 8 + cue "ok chốt" → certain → state-edit
    r = await ingest(api, meeting["id"], "c2", 2, "ok chốt phạm vi gói cơ bản.", 12.0, 14.0)
    assert r == {"status": "ok", "beat": 1, "state_changed": True, "version": 1}

    # ---- nhịp 2 mở + đóng ("chốt vậy")
    await ingest(api, meeting["id"], "c3", 3, "Thảo luận gói nâng cao.", 16.0, 18.0)
    r = await ingest(api, meeting["id"], "c4", 4, "chốt vậy thêm gói nâng cao.", 28.0, 30.0)
    assert r == {"status": "ok", "beat": 2, "state_changed": True, "version": 2}

    # ---- nhịp 3: mở, chưa đóng (gap nhỏ, không cue)
    await ingest(api, meeting["id"], "c5", 5, "Bàn về lộ trình triển khai.", 31.0, 33.0)
    await ingest(api, meeting["id"], "c6", 6, "để tuần sau quyết.", 33.5, 35.0)

    # ---- state sống: 2 quyết định, version 2, nhịp 3 vẫn mở
    r = await api.get(f"/meetings/{meeting['id']}/state")
    assert r.status_code == 200
    state = r.json()
    assert state["version"] == 2
    assert state["summary"]["decision_count"] == 2
    assert all(it["status"] == "active" for it in state["items"])

    # ---- idempotent: chunk gửi lại → duplicate, không đổi state
    r = await ingest(api, meeting["id"], "c4", 4, "chốt vậy thêm gói nâng cao.", 28.0, 30.0)
    assert r["status"] == "duplicate"

    # ---- end → package → file về repo (fake) + meeting-state.json
    r = await api.post(f"/meetings/{meeting['id']}/end")
    assert r.status_code == 200
    assert r.json()["status"] == "ended"

    r = await api.post(f"/meetings/{meeting['id']}/package")
    assert r.status_code == 200, r.text
    pkg = r.json()
    assert pkg["commit"] == "fake-0001"
    md_path = "meetings/2026-08-30-family-package.md"
    assert md_path in pkg["files"]
    assert "**Echo item**" in pkg["files"][md_path]
    assert pkg["files"]["meeting-state.json"].startswith("{")

    # ---- op_log: 3 ops create — nhịp 1, 2 đóng khi ingest; nhịp 3 còn mở nên
    # /end phải flush nó (plan.md §12: "đóng nhịp cuối + status=ended").
    # Thiếu flush = transcript nhịp cuối không bao giờ qua state-edit, mất trắng.
    r = await api.get(f"/meetings/{meeting['id']}/oplog")
    assert r.status_code == 200
    entries = r.json()["items"]
    assert [e["op_type"] for e in entries] == ["create", "create", "create"]
    assert [e["nhip_id"] for e in entries] == [1, 2, 3]

    # nhịp cuối phải ở trạng thái closed sau /end, không còn bỏ ngỏ
    r = await api.get(f"/meetings/{meeting['id']}/transcript")
    assert r.status_code == 200
    assert [b["status"] for b in r.json()["beats"]] == ["closed", "closed", "closed"]


async def test_headless_unassigned_route(api):
    """Event không khớp tag → unassigned (vẫn chạy generic)."""
    r = await api.post("/meetings", json={"event_id": "evt-plain"})
    assert r.status_code == 201
    meeting = r.json()
    assert meeting["status"] == "unassigned"
    assert meeting["profile_key"] == "generic"
    assert meeting["project_id"] is None

    r = await api.get(f"/meetings/{meeting['id']}/state")
    assert r.status_code == 200
    assert r.json()["version"] == 0


async def test_project_not_found(api):
    r = await api.post("/meetings", json={"project_slug": "khong-ton-tai"})
    assert r.status_code == 404


async def test_list_meetings(api):
    """GET /meetings — FE cần list có summary, không kèm transcript (privacy)."""
    r = await api.get("/meetings")
    assert r.status_code == 200
    assert r.json() == {"items": []}

    await seed_project(api)
    r = await api.post("/meetings", json={"event_id": "evt-family"})
    meeting_id = r.json()["id"]
    await ingest(api, meeting_id, "c1", 1, "Bàn về gói cơ bản.", 0.0, 2.0)
    await ingest(api, meeting_id, "c2", 2, "ok chốt gói cơ bản.", 12.0, 14.0)  # gap 10s > 8s + cue

    r = await api.get("/meetings")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    m = items[0]
    assert m["id"] == meeting_id
    assert m["status"] == "live"
    assert m["profile_key"] == "family-package"
    assert m["version"] >= 1
    assert "summary" in m
    assert "transcript" not in m  # metadata only — không rò nội dung nhạy cảm
    assert "text" not in m


async def test_khong_dung_tay(api):
    """§15.4 — engine tự cắt nhịp: KHÔNG có endpoint 'đóng nhịp'/'phân loại' (HITL bắt buộc)."""
    spec = (await api.get("/openapi.json")).json()
    paths = set(spec["paths"])
    assert not any("close" in p or "classify" in p or "segment" in p for p in paths)
    assert "/meetings/{meeting_id}/ingest" in paths  # nguồn duy nhất để đưa dữ liệu vào


async def test_transcript_endpoint(api):
    """Portal xem chữ thô: GET /meetings/{id}/transcript trả chunks theo seq + timeline nhịp.
    Chỉ trả qua endpoint riêng có auth — không rò trong danh sách họp (test trên)."""
    await seed_project(api)
    r = await api.post("/meetings", json={"event_id": "evt-family"})
    meeting_id = r.json()["id"]
    await ingest(api, meeting_id, "c1", 1, "Bàn về gói cơ bản.", 0.0, 2.0)
    await ingest(api, meeting_id, "c2", 2, "ok chốt gói cơ bản.", 12.0, 14.0)  # gap 10s + cue

    r = await api.get(f"/meetings/{meeting_id}/transcript")
    assert r.status_code == 200
    data = r.json()
    assert data["meeting_id"] == meeting_id
    assert [c["seq"] for c in data["chunks"]] == [1, 2]
    assert data["chunks"][1]["text"] == "ok chốt gói cơ bản."
    assert data["chunks"][1]["speaker"] == "BA"
    # chunk 2 (gap 10s + cue) đóng nhịp 1 → 1 beat closed, transcript gom cả 2 chunk
    assert len(data["beats"]) == 1
    assert data["beats"][0]["status"] == "closed"
    assert data["beats"][0]["transcript"] == "Bàn về gói cơ bản.\nok chốt gói cơ bản."

    # 404 khi không tồn tại
    missing = "/meetings/00000000-0000-0000-0000-000000000000/transcript"
    assert (await api.get(missing)).status_code == 404
