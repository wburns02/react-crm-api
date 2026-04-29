"""Prompt-rendering and tool-schema tests."""
from __future__ import annotations

import jsonschema
import pytest

from app.services.ai import prompts


# ---------------------------------------------------------------------------
# render_triage_user_message
# ---------------------------------------------------------------------------
def test_render_triage_includes_canonical_fields() -> None:
    interaction = {
        "channel": "sms",
        "direction": "inbound",
        "occurred_at": "2026-04-25T15:30:00Z",
        "contact": {
            "name": "Scott England",
            "email": "sengland@realtracs.com",
            "phone": "+16155551212",
            "city_state": "Brentwood, TN",
            "customer_id": "abc-123",
            "prior_jobs": 0,
            "lead_source": "website",
            "tags": "realtor,permit-blast",
        },
        "content": "My brother owns England Septic.",
    }
    rendered = prompts.render_triage_user_message(interaction)

    # Channel + direction surface in the header.
    assert "channel: sms" in rendered
    assert "direction: inbound" in rendered

    # Contact block fields are interpolated.
    assert "name: Scott England" in rendered
    assert "email: sengland@realtracs.com" in rendered
    assert "phone: +16155551212" in rendered
    assert "Brentwood, TN" in rendered
    assert "lead_source: website" in rendered
    assert "tags: realtor,permit-blast" in rendered

    # Content is wrapped in triple quotes.
    assert "My brother owns England Septic." in rendered
    assert '"""' in rendered


def test_render_triage_uses_null_for_missing_contact_fields() -> None:
    interaction = {
        "channel": "email",
        "direction": "outbound",
        "occurred_at": "2026-04-26T09:00:00Z",
        "contact": {"name": "unknown"},
        "content": "Out of office until April 30.",
    }
    rendered = prompts.render_triage_user_message(interaction)
    assert "email: null" in rendered
    assert "phone: null" in rendered
    assert "customer_id: null" in rendered


def test_render_triage_includes_prior_message_when_present() -> None:
    interaction = {
        "channel": "email",
        "direction": "inbound",
        "occurred_at": "2026-04-26T09:00:00Z",
        "contact": {},
        "content": "Sounds good, what's the price?",
        "our_prior_message": "Hi! Quick reminder your tank is due.",
    }
    rendered = prompts.render_triage_user_message(interaction)
    assert "our_prior_message:" in rendered
    assert "Hi! Quick reminder your tank is due." in rendered


def test_render_triage_omits_prior_message_when_absent() -> None:
    interaction = {
        "channel": "sms",
        "direction": "inbound",
        "occurred_at": "2026-04-26T09:00:00Z",
        "contact": {},
        "content": "Need a pump-out.",
    }
    rendered = prompts.render_triage_user_message(interaction)
    assert "our_prior_message" not in rendered


# ---------------------------------------------------------------------------
# render_reply_user_message
# ---------------------------------------------------------------------------
def test_render_reply_includes_triage_analysis_json() -> None:
    interaction = {
        "channel": "sms",
        "direction": "inbound",
        "occurred_at": "2026-04-26T09:00:00Z",
        "contact": {"name": "Pat"},
        "content": "How much for a 1000gal pumpout?",
    }
    triage = {
        "intent": "request_quote",
        "hot_lead_score": 65,
        "urgency": "this_month",
    }
    rendered = prompts.render_reply_user_message(interaction, triage)
    assert "triage_analysis:" in rendered
    assert '"intent": "request_quote"' in rendered
    assert '"hot_lead_score": 65' in rendered


# ---------------------------------------------------------------------------
# render_strategy_user_message
# ---------------------------------------------------------------------------
def test_render_strategy_renders_week_and_breakdown() -> None:
    rendered = prompts.render_strategy_user_message(
        week="2026-W17",
        date_range=("2026-04-20", "2026-04-26"),
        total=42,
        by_channel={"call": 18, "sms": 12, "email": 10, "chat": 2},
        interactions=[
            {"id": "ix-1", "channel": "call", "transcript": "..."},
        ],
    )
    assert "week: 2026-W17" in rendered
    assert "date_range: 2026-04-20 to 2026-04-26" in rendered
    assert "total_interactions: 42" in rendered
    assert '"call"' in rendered
    assert '"id": "ix-1"' in rendered


# ---------------------------------------------------------------------------
# Tool-schema validation: a known-good triage tool-call payload.
# ---------------------------------------------------------------------------
def test_triage_tool_schema_validates_minimal_known_good_payload() -> None:
    """Spec example: a Scott-England-style competitor_referral analysis."""
    payload = {
        "intent": "competitor_referral",
        "sentiment": "neutral",
        "hot_lead_score": 0,
        "urgency": "none",
        "do_not_contact_signal": True,
        "competitor_mentioned": "England Septic",
        "service_signals": {
            "tank_overflow": False,
            "schedule_due": False,
            "buying_house": False,
            "selling_house": False,
            "complaint_about_us": False,
            "complaint_about_competitor": False,
            "returning_customer": False,
        },
        "action_items": [
            {
                "action": "Add to suppression lists",
                "owner": "none",
                "deadline_hours": 0,
            }
        ],
        "summary": "Reply from competitor's family member; suppress.",
        "key_quote": "My brother owns England Septic.",
    }
    # Must not raise.
    jsonschema.validate(payload, prompts.TRIAGE_TOOL_V1["input_schema"])


def test_triage_tool_schema_rejects_invalid_intent() -> None:
    payload = {
        "intent": "fake_intent_not_in_enum",
        "sentiment": "neutral",
        "hot_lead_score": 50,
        "urgency": "none",
        "do_not_contact_signal": False,
        "service_signals": {
            "tank_overflow": False,
            "schedule_due": False,
            "buying_house": False,
            "selling_house": False,
            "complaint_about_us": False,
            "complaint_about_competitor": False,
            "returning_customer": False,
        },
        "action_items": [],
        "summary": "x",
        "key_quote": "x",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, prompts.TRIAGE_TOOL_V1["input_schema"])


def test_reply_tool_schema_validates_known_good_payload() -> None:
    payload = {
        "reply": "Thanks for reaching out. We can usually get out within a week. — Will",
        "channel_format": "sms",
        "tone": "warm",
        "reason": "Returning customer asking about timing; lead with availability.",
    }
    jsonschema.validate(payload, prompts.REPLY_TOOL_V1["input_schema"])


# ---------------------------------------------------------------------------
# Version constants are wired up.
# ---------------------------------------------------------------------------
def test_version_constants_are_v1() -> None:
    assert prompts.TRIAGE_VERSION == "v1"
    assert prompts.REPLY_VERSION == "v1"
    assert prompts.STRATEGY_VERSION == "v1"
