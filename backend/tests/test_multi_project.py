"""★ ACCEPTANCE ĐA-DỰ-ÁN (plan.md §15.2) — thêm profile mới = 0 dòng engine sửa.

Cùng code state_editor/profile_loader, profile khác → schema tool khác →
profile_fields của item khác. Không branch theo project trong engine.
"""

from uuid import uuid4

from app.engine.state import MeetingState


async def test_ux_profile_fields_khac_family(state_editor, fake_llm, profile_ux, profile_family):
    # ux: DECISION có field affects_flow + edge_cases, KHÔNG có impacts
    fake_llm.set_echo(True)
    state = MeetingState(meeting_id=uuid4())
    r = await state_editor.edit(
        meeting_id=state.meeting_id,
        state=state,
        nhip_id=1,
        beat_text="UX: quyết định chuyển checkout sang 1 trang.",
        profile=profile_ux,
    )
    ux_item = r.items[0]
    assert ux_item.type == "DECISION"
    assert "affects_flow" in ux_item.profile_fields
    assert "edge_cases" in ux_item.profile_fields
    assert "impacts" not in ux_item.profile_fields

    # family: DECISION có impacts, KHÔNG có affects_flow
    fake_llm.set_echo(True)
    state2 = MeetingState(meeting_id=uuid4())
    r2 = await state_editor.edit(
        meeting_id=state2.meeting_id,
        state=state2,
        nhip_id=1,
        beat_text="BA: chốt tier mới cho gói GĐ.",
        profile=profile_family,
    )
    fam_item = r2.items[0]
    assert "impacts" in fam_item.profile_fields
    assert "affects_flow" not in fam_item.profile_fields


async def test_profile_loader_schema_dong(profile_ux, profile_family):
    from app.engine.profile_loader import build_tools

    tools_ux = build_tools(profile_ux)
    tools_fam = build_tools(profile_family)

    def decision_fields(tools) -> set[str]:
        for tool in tools:
            if tool["name"] == "create_item":
                for variant in tool["input_schema"]["properties"]["profile_fields"]["oneOf"]:
                    if variant["title"] == "DECISION":
                        return set(variant.get("properties", {}).keys())
        return set()

    assert decision_fields(tools_ux) == {"affects_flow", "edge_cases"}
    assert decision_fields(tools_fam) == {"replaces_decision", "impacts"}
