"""Tests for voice_agent.tools — schema validation + adapter delegation."""
import pytest

from app.services.voice_agent import tools


def test_agent_tools_has_all_eight_definitions():
    names = {t["name"] for t in tools.AGENT_TOOLS}
    assert names == {
        "check_availability",
        "book_appointment",
        "transfer_call",
        "create_callback",
        "set_disposition",
        "leave_voicemail",
        "end_call",
        "send_followup_sms",
    }


def test_each_tool_has_anthropic_schema_shape():
    for t in tools.AGENT_TOOLS:
        assert "name" in t
        assert "description" in t
        assert "input_schema" in t
        assert t["input_schema"]["type"] == "object"
        assert "properties" in t["input_schema"]


def test_set_disposition_enum_matches_legacy():
    spec = next(t for t in tools.AGENT_TOOLS if t["name"] == "set_disposition")
    enum_vals = set(spec["input_schema"]["properties"]["disposition"]["enum"])
    assert enum_vals == {
        "appointment_set", "callback_requested", "transferred_to_sales",
        "not_interested", "service_completed_elsewhere", "voicemail_left",
        "no_answer", "wrong_number", "do_not_call",
    }


@pytest.mark.asyncio
async def test_handle_tool_call_delegates_to_session(mocker):
    """Adapter should forward to the OutboundAgentSession instance method."""
    fake_session = mocker.MagicMock()
    fake_session._handle_tool_call = mocker.AsyncMock(return_value={"ok": True})

    result = await tools.handle_tool_call(
        session=fake_session,
        name="set_disposition",
        tool_id="t_1",
        args={"disposition": "callback_requested", "notes": "test"},
    )

    fake_session._handle_tool_call.assert_awaited_once_with(
        "set_disposition", "t_1", {"disposition": "callback_requested", "notes": "test"}
    )
    assert result == {"ok": True}
