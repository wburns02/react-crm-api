"""Tool schema + dispatch adapter for the Pipecat voice agent.

The schema is the single source of truth for what tools the LLM can call.
The adapter delegates to OutboundAgentSession._handle_tool_call which contains
the existing, tested implementations (Twilio SMS, work order creation, etc.).

``AGENT_TOOLS`` is the human-readable Anthropic-shaped definition list. The
canonical Pipecat representation is built by ``get_tools_schema()`` below,
which Pipecat 0.0.108's ``LLMContext`` accepts directly. Anthropic's adapter
inside Pipecat takes care of cache-control markers on system + tools at send
time (see ``pipecat.adapters.services.anthropic_adapter``).
"""
from typing import Any

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema


AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "check_availability",
        "description": "Check available appointment slots for the next 7 days in the prospect's service area.",
        "input_schema": {
            "type": "object",
            "properties": {
                "preferred_date": {
                    "type": "string",
                    "description": "Preferred date in YYYY-MM-DD format, or 'next_available'",
                }
            },
            "required": [],
        },
    },
    {
        "name": "book_appointment",
        "description": "Book a service appointment for the prospect. Creates a work order in the CRM.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scheduled_date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "time_window": {"type": "string", "description": "morning, afternoon, or specific time like 10:00"},
                "service_type": {"type": "string", "description": "pumping, inspection, repair, etc."},
                "notes": {"type": "string", "description": "Any special instructions from the customer"},
            },
            "required": ["scheduled_date", "service_type"],
        },
    },
    {
        "name": "transfer_call",
        "description": "Transfer the call to MAC Septic office for human assistance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the customer wants to talk to someone"}
            },
            "required": ["reason"],
        },
    },
    {
        "name": "create_callback",
        "description": "Schedule a callback at a specific time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "callback_time": {"type": "string", "description": "When to call back, e.g. 'tomorrow morning' or '2026-04-30 14:00'"},
                "notes": {"type": "string", "description": "Context for the callback"},
            },
            "required": ["callback_time"],
        },
    },
    {
        "name": "set_disposition",
        "description": "Set the call outcome/disposition. Call this before ending the conversation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "disposition": {
                    "type": "string",
                    "enum": [
                        "appointment_set", "callback_requested", "transferred_to_sales",
                        "not_interested", "service_completed_elsewhere", "voicemail_left",
                        "no_answer", "wrong_number", "do_not_call",
                    ],
                },
                "notes": {"type": "string", "description": "Brief summary of the call"},
            },
            "required": ["disposition"],
        },
    },
    {
        "name": "leave_voicemail",
        "description": "Leave a voicemail message. Use when you detect voicemail/answering machine.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "end_call",
        "description": "End the phone call. Always set_disposition before calling this.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "send_followup_sms",
        "description": "Send a follow-up text message to the prospect after the call.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Text message content"}
            },
            "required": ["message"],
        },
    },
]


def _build_function_schemas() -> list[FunctionSchema]:
    """Translate AGENT_TOOLS dicts into Pipecat ``FunctionSchema`` instances."""
    schemas: list[FunctionSchema] = []
    for t in AGENT_TOOLS:
        input_schema = t.get("input_schema") or {}
        schemas.append(
            FunctionSchema(
                name=t["name"],
                description=t["description"],
                properties=input_schema.get("properties", {}),
                required=input_schema.get("required", []),
            )
        )
    return schemas


def get_tools_schema() -> ToolsSchema:
    """Return AGENT_TOOLS as a Pipecat ``ToolsSchema``.

    Pipecat 0.0.108's universal ``LLMContext`` requires a ``ToolsSchema``
    (or ``NOT_GIVEN``) — raw dict lists are not accepted. The Anthropic LLM
    service adapter converts the schema into Anthropic-shaped tool dicts and
    applies prompt-cache markers at send time.
    """
    return ToolsSchema(standard_tools=_build_function_schemas())


async def handle_tool_call(session, name: str, tool_id: str, args: dict) -> dict:
    """Forward a tool invocation to the active OutboundAgentSession.

    The session class owns the actual side effects (Twilio SMS, DB writes,
    transfer flagging). This adapter exists so the Pipecat pipeline doesn't
    need to import the session class directly — keeps the pipeline factory
    swappable with mocks in tests.
    """
    return await session._handle_tool_call(name, tool_id, args)
