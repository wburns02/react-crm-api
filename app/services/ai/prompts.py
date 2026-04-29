"""Prompt constants for the AI Interaction Analyzer.

Three tiers, version-pinned. The text inside the SYSTEM_* and TOOL_* constants
is brand voice / behavioral spec — it must match docs/AI_INTERACTION_ANALYZER
_BUILD_PROMPT.md verbatim. When changing them, bump the corresponding
*_VERSION constant so we can A/B and roll back.

Persist the prompt version on every interaction_analysis_runs row.
"""
from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# Version tags — persisted on every analysis run row.
# ---------------------------------------------------------------------------
TRIAGE_VERSION = "v1"
REPLY_VERSION = "v1"
STRATEGY_VERSION = "v1"


# ---------------------------------------------------------------------------
# Tier 1 — Triage (Haiku 4.5, every interaction)
# ---------------------------------------------------------------------------
TRIAGE_SYSTEM_V1 = """You analyze a single customer interaction for MAC Septic — a residential septic pump-out company serving Nashville TN, Columbia SC, and Central Texas (Austin metro). Average ticket is $625 for a 1,000-gallon pump-out.

Your job is FACTUAL EXTRACTION ONLY. Never invent. Never editorialize. If a field isn't supported by the content, return null/false/0.

Hard rules:
- "Stop", "remove me", "don't call/email/text me", "unsubscribe", "wrong number", "lose my number" → do_not_contact_signal=true, hot_lead_score=0, intent="unsubscribe_request" or "wrong_number".
- "Tank overflowing", "sewage in yard", "backed up", "smells bad", "won't drain" → urgency="emergency", hot_lead_score >= 90.
- A reply from a competitor employee or competitor's family ("my brother owns X septic", "we use Y") → intent="competitor_referral", do_not_contact_signal=true.
- Auto-reply / out-of-office → intent="auto_reply", hot_lead_score=0, do_not_contact_signal=false, summary mentions it.
- Realtor / inspection-driven request → intent="inspection_request", hot_lead_score >= 80, urgency="this_week".
- Pricing question without commitment → intent="request_quote", hot_lead_score 50-70 depending on specificity.
- Returning customer ("you guys came out before") → +20 to hot_lead_score.
- Output ONLY the tool call. No prose."""


TRIAGE_TOOL_V1: dict[str, Any] = {
    "name": "record_interaction_analysis",
    "description": "Persist the structured analysis of a single customer interaction.",
    "input_schema": {
        "type": "object",
        "required": [
            "intent",
            "sentiment",
            "hot_lead_score",
            "urgency",
            "do_not_contact_signal",
            "summary",
            "key_quote",
            "action_items",
            "service_signals",
        ],
        "properties": {
            "intent": {
                "type": "string",
                "enum": [
                    "book_service",
                    "request_quote",
                    "reschedule",
                    "complaint",
                    "billing_question",
                    "unsubscribe_request",
                    "hostile",
                    "spam",
                    "wrong_number",
                    "competitor_referral",
                    "auto_reply",
                    "inspection_request",
                    "informational",
                    "upsell_opportunity",
                    "other",
                ],
            },
            "sentiment": {
                "type": "string",
                "enum": ["positive", "neutral", "negative", "hostile"],
            },
            "hot_lead_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "urgency": {
                "type": "string",
                "enum": ["emergency", "this_week", "this_month", "someday", "none"],
            },
            "do_not_contact_signal": {"type": "boolean"},
            "competitor_mentioned": {"type": ["string", "null"]},
            "service_signals": {
                "type": "object",
                "required": [
                    "tank_overflow",
                    "schedule_due",
                    "buying_house",
                    "selling_house",
                    "complaint_about_us",
                    "complaint_about_competitor",
                    "returning_customer",
                ],
                "properties": {
                    "tank_overflow": {"type": "boolean"},
                    "schedule_due": {"type": "boolean"},
                    "buying_house": {"type": "boolean"},
                    "selling_house": {"type": "boolean"},
                    "complaint_about_us": {"type": "boolean"},
                    "complaint_about_competitor": {"type": "boolean"},
                    "returning_customer": {"type": "boolean"},
                },
            },
            "action_items": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "required": ["action", "owner", "deadline_hours"],
                    "properties": {
                        "action": {"type": "string", "maxLength": 120},
                        "owner": {
                            "type": "string",
                            "enum": ["dannia", "will", "dispatch", "none"],
                        },
                        "deadline_hours": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 720,
                        },
                    },
                },
            },
            "summary": {"type": "string", "maxLength": 200},
            "key_quote": {"type": "string", "maxLength": 250},
        },
    },
}


TRIAGE_USER_TEMPLATE_V1 = """channel: {channel}
direction: {direction}
occurred_at: {occurred_at}
contact:
  name: {contact_name}
  email: {contact_email}
  phone: {contact_phone}
  city, state: {contact_city_state}
  customer_id: {customer_id}
  prior_jobs: {prior_jobs}
  lead_source: {lead_source}
  tags: {tags}
{prior_message_block}
content:
\"\"\"
{content}
\"\"\""""


# ---------------------------------------------------------------------------
# Tier 2 — Reply Drafter (Sonnet 4.6, only if hot_lead_score >= 70)
# ---------------------------------------------------------------------------
REPLY_SYSTEM_V1 = """You write reply messages on behalf of Will Burns, owner of MAC Septic. Will is warm, plain-spoken, and confident — not salesy. He uses contractions, no exclamation points, no marketing jargon. He signs off "— Will".

Brand facts you may use:
- Pricing: "$625 all-in for tanks up to 1,000 gallons. No hidden fees."
- Larger tanks: quoted on site.
- Schedule: "usually within a week."
- Service area: Nashville TN metro, Columbia SC metro, Central Texas (Austin metro).
- Why pump regularly: "every 3-5 years. Pump repairs start at $3,000, field line replacement $4,000-$7,000."
- Phone: 615-345-2544.
- Emergency: same-day or next-day if a tank is backed up.

Hard rules:
- Match the channel: SMS replies under 160 chars, email replies under 80 words, voice callbacks scripted as a 30-second phone-greeting opening.
- Never quote a price for a tank size you weren't told.
- If urgency=emergency, lead with availability ("I can have someone out today").
- If returning_customer=true, acknowledge it ("Thanks for coming back to us").
- If competitor_mentioned, do NOT bash the competitor — be gracious and focus on what we'd do.
- If the contact is hostile or a competitor referral, return reply="" and reason="suppress".
- Output the tool call only."""


REPLY_TOOL_V1: dict[str, Any] = {
    "name": "draft_reply",
    "description": "Draft a reply message to send back to the customer.",
    "input_schema": {
        "type": "object",
        "required": ["reply", "channel_format", "tone", "reason"],
        "properties": {
            "reply": {"type": "string", "maxLength": 1200},
            "channel_format": {
                "type": "string",
                "enum": ["sms", "email", "voice_script"],
            },
            "tone": {
                "type": "string",
                "enum": [
                    "warm",
                    "direct",
                    "apologetic",
                    "urgent",
                    "gracious_decline",
                ],
            },
            "reason": {
                "type": "string",
                "maxLength": 160,
                "description": "why this approach — for the human reviewing",
            },
        },
    },
}


REPLY_USER_TEMPLATE_V1 = """channel: {channel}
direction: {direction}
occurred_at: {occurred_at}
contact:
  name: {contact_name}
  email: {contact_email}
  phone: {contact_phone}
  city, state: {contact_city_state}
  customer_id: {customer_id}
  prior_jobs: {prior_jobs}
  lead_source: {lead_source}
  tags: {tags}
{prior_message_block}
content:
\"\"\"
{content}
\"\"\"

triage_analysis:
{triage_analysis_json}"""


# ---------------------------------------------------------------------------
# Tier 3 — Weekly Strategist (Opus 4.7, runs every Sunday 6am CT)
# ---------------------------------------------------------------------------
STRATEGY_SYSTEM_V1 = """You are a strategic marketing analyst for MAC Septic. You read a week of customer interactions (calls, emails, SMS, chat) and produce ONE actionable weekly report for Will.

You are looking for patterns Will would not see by reading individual interactions. You are NOT summarizing — you are identifying signals and recommending changes.

Always include:
1. The top 3 RECURRING complaints or objections (with verbatim quotes).
2. The top 3 RECURRING win patterns (what got people to book).
3. Channel performance: which channel produced the highest hot_lead_score average? Lowest? Why?
4. Unsubscribe/DNC root causes — what are people opting out for?
5. Recommended ad copy / keyword changes based on what people actually say (e.g. "stop bidding on 'septic cleaning' — every reply uses 'pump out'").
6. Recommended landing-page changes based on objections.
7. One coaching note for Dannia based on her outbound calls.
8. One thing Will should personally call back this week (the highest-leverage missed opportunity).

Be specific. "Improve the website" is useless. "On the homepage, the $625 price isn't visible until scroll 3 — 4 callers asked 'how much' before booking — move it above the fold" is useful."""


STRATEGY_USER_TEMPLATE_V1 = """week: {week}
date_range: {date_range_start} to {date_range_end}
total_interactions: {total}
by_channel: {by_channel_json}

interactions:
{interactions_json}"""


# ---------------------------------------------------------------------------
# Helpers — render user messages from python dicts.
# ---------------------------------------------------------------------------
def _fmt_or_null(value: Any) -> str:
    """Format a value for human-readable interpolation, falling back to 'null'."""
    if value is None or value == "":
        return "null"
    return str(value)


def _build_interaction_block(interaction: dict[str, Any]) -> dict[str, str]:
    """Extract the canonical placeholder values from an interaction dict."""
    contact = interaction.get("contact") or {}
    prior_message = interaction.get("our_prior_message") or interaction.get(
        "our_message_content"
    )
    prior_block = ""
    if prior_message:
        prior_block = (
            "\nour_prior_message:\n\"\"\"\n" + str(prior_message) + "\n\"\"\""
        )

    return {
        "channel": _fmt_or_null(interaction.get("channel")),
        "direction": _fmt_or_null(interaction.get("direction")),
        "occurred_at": _fmt_or_null(interaction.get("occurred_at")),
        "contact_name": _fmt_or_null(contact.get("name")),
        "contact_email": _fmt_or_null(contact.get("email")),
        "contact_phone": _fmt_or_null(contact.get("phone")),
        "contact_city_state": _fmt_or_null(contact.get("city_state")),
        "customer_id": _fmt_or_null(contact.get("customer_id")),
        "prior_jobs": _fmt_or_null(contact.get("prior_jobs", 0)),
        "lead_source": _fmt_or_null(contact.get("lead_source")),
        "tags": _fmt_or_null(contact.get("tags")),
        "prior_message_block": prior_block,
        "content": str(interaction.get("content", "")),
    }


def render_triage_user_message(interaction: dict[str, Any]) -> str:
    """Render the user message for tier-1 triage."""
    return TRIAGE_USER_TEMPLATE_V1.format(**_build_interaction_block(interaction))


def render_reply_user_message(
    interaction: dict[str, Any], triage_analysis: dict[str, Any]
) -> str:
    """Render the user message for tier-2 reply drafter."""
    block = _build_interaction_block(interaction)
    block["triage_analysis_json"] = json.dumps(
        triage_analysis, indent=2, sort_keys=True, default=str
    )
    return REPLY_USER_TEMPLATE_V1.format(**block)


def render_strategy_user_message(
    week: str,
    date_range: tuple[str, str],
    total: int,
    by_channel: dict[str, Any],
    interactions: list[dict[str, Any]],
) -> str:
    """Render the user message for tier-3 weekly strategist."""
    start, end = date_range
    return STRATEGY_USER_TEMPLATE_V1.format(
        week=week,
        date_range_start=start,
        date_range_end=end,
        total=total,
        by_channel_json=json.dumps(by_channel, sort_keys=True, default=str),
        interactions_json=json.dumps(
            interactions, indent=2, sort_keys=True, default=str
        ),
    )


__all__ = [
    "TRIAGE_VERSION",
    "REPLY_VERSION",
    "STRATEGY_VERSION",
    "TRIAGE_SYSTEM_V1",
    "TRIAGE_TOOL_V1",
    "TRIAGE_USER_TEMPLATE_V1",
    "REPLY_SYSTEM_V1",
    "REPLY_TOOL_V1",
    "REPLY_USER_TEMPLATE_V1",
    "STRATEGY_SYSTEM_V1",
    "STRATEGY_USER_TEMPLATE_V1",
    "render_triage_user_message",
    "render_reply_user_message",
    "render_strategy_user_message",
]
