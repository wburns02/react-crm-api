"""Tests for app.services.ai.anthropic_client.AnthropicClient.

The Anthropic SDK is mocked end-to-end — these tests verify:
  - cache_control is auto-applied to system block AND tool definitions
  - cost is computed from mocked usage tokens
  - tool_choice is forced for triage
  - empty/missing api_key raises ValueError
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.ai import anthropic_client as anthropic_client_module
from app.services.ai.anthropic_client import AnthropicClient


# ---------------------------------------------------------------------------
# Helpers — fake SDK responses.
# ---------------------------------------------------------------------------
def _make_fake_tool_response(
    tool_name: str = "record_interaction_analysis",
    tool_input: dict | None = None,
    input_tokens: int = 200,
    output_tokens: int = 150,
    cache_read: int = 5_000,
    cache_write: int = 0,
) -> SimpleNamespace:
    """Mimic an anthropic.types.Message with a forced tool_use block."""
    if tool_input is None:
        tool_input = {"intent": "request_quote", "hot_lead_score": 60}
    return SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                name=tool_name,
                id="toolu_test_1",
                input=tool_input,
            ),
        ],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_write,
        ),
        stop_reason="tool_use",
    )


def _make_fake_strategy_response(
    text: str = "## Weekly report\n\n1. ...",
    thinking: str = "Reasoning about ad copy patterns...",
    input_tokens: int = 50_000,
    output_tokens: int = 1_500,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking=thinking),
            SimpleNamespace(type="text", text=text),
        ],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        stop_reason="end_turn",
    )


# ---------------------------------------------------------------------------
# Construction / validation.
# ---------------------------------------------------------------------------
def test_empty_api_key_raises_value_error() -> None:
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicClient(api_key="")


def test_whitespace_api_key_raises_value_error() -> None:
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicClient(api_key="   ")


def test_valid_api_key_constructs() -> None:
    # Should not raise.
    client = AnthropicClient(api_key="sk-test-fake")
    assert client._client is not None  # noqa: SLF001 — internal access in test


# ---------------------------------------------------------------------------
# call_triage — cache_control + cost + tool_choice.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_call_triage_applies_cache_control_to_system_and_tools() -> None:
    client = AnthropicClient(api_key="sk-test-fake")
    fake_create = AsyncMock(return_value=_make_fake_tool_response())

    with patch.object(client._client.messages, "create", fake_create):  # noqa: SLF001
        await client.call_triage("user message")

    fake_create.assert_awaited_once()
    kwargs = fake_create.call_args.kwargs

    # System block has cache_control.
    system = kwargs["system"]
    assert isinstance(system, list)
    assert len(system) == 1
    assert system[0]["type"] == "text"
    assert system[0]["cache_control"] == {"type": "ephemeral"}

    # Tool definitions have cache_control auto-applied.
    tools = kwargs["tools"]
    assert isinstance(tools, list)
    assert len(tools) == 1
    assert tools[0]["cache_control"] == {"type": "ephemeral"}
    # Original schema preserved (not mutated by the wrapper).
    assert tools[0]["name"] == "record_interaction_analysis"
    assert "input_schema" in tools[0]


@pytest.mark.asyncio
async def test_call_triage_forces_tool_choice() -> None:
    client = AnthropicClient(api_key="sk-test-fake")
    fake_create = AsyncMock(return_value=_make_fake_tool_response())

    with patch.object(client._client.messages, "create", fake_create):  # noqa: SLF001
        await client.call_triage("user message")

    kwargs = fake_create.call_args.kwargs
    assert kwargs["tool_choice"] == {
        "type": "tool",
        "name": "record_interaction_analysis",
    }


@pytest.mark.asyncio
async def test_call_triage_uses_haiku_model() -> None:
    client = AnthropicClient(api_key="sk-test-fake")
    fake_create = AsyncMock(return_value=_make_fake_tool_response())

    with patch.object(client._client.messages, "create", fake_create):  # noqa: SLF001
        result = await client.call_triage("user message")

    kwargs = fake_create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5-20251001"
    assert kwargs["max_tokens"] == 1024
    assert result.model == "claude-haiku-4-5-20251001"
    assert result.prompt_version == "v1"


@pytest.mark.asyncio
async def test_call_triage_computes_cost_from_usage() -> None:
    """200 input + 150 output + 5000 cache_read on Haiku.

    200 * 1e-6 + 150 * 5e-6 + 5000 * 1e-6 * 0.10
      = 0.0002 + 0.00075 + 0.0005 = 0.001450
    """
    client = AnthropicClient(api_key="sk-test-fake")
    fake_create = AsyncMock(
        return_value=_make_fake_tool_response(
            input_tokens=200, output_tokens=150, cache_read=5_000
        )
    )

    with patch.object(client._client.messages, "create", fake_create):  # noqa: SLF001
        result = await client.call_triage("user message")

    assert result.cost_usd == Decimal("0.001450")
    assert result.input_tokens == 200
    assert result.output_tokens == 150
    assert result.cache_read_tokens == 5_000
    assert result.cache_write_tokens == 0


@pytest.mark.asyncio
async def test_call_triage_extracts_tool_input() -> None:
    client = AnthropicClient(api_key="sk-test-fake")
    fake_input = {
        "intent": "competitor_referral",
        "hot_lead_score": 0,
        "do_not_contact_signal": True,
    }
    fake_create = AsyncMock(
        return_value=_make_fake_tool_response(tool_input=fake_input)
    )

    with patch.object(client._client.messages, "create", fake_create):  # noqa: SLF001
        result = await client.call_triage("user message")

    assert result.tool_name == "record_interaction_analysis"
    assert result.tool_input == fake_input


# ---------------------------------------------------------------------------
# call_reply — cache_control + tool_choice + Sonnet model.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_call_reply_uses_sonnet_with_forced_tool_choice() -> None:
    client = AnthropicClient(api_key="sk-test-fake")
    fake_create = AsyncMock(
        return_value=_make_fake_tool_response(
            tool_name="draft_reply",
            tool_input={
                "reply": "Thanks for reaching out. — Will",
                "channel_format": "sms",
                "tone": "warm",
                "reason": "Returning customer.",
            },
        )
    )

    with patch.object(client._client.messages, "create", fake_create):  # noqa: SLF001
        result = await client.call_reply("user message")

    kwargs = fake_create.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert kwargs["tool_choice"] == {"type": "tool", "name": "draft_reply"}
    # System block + tool defs cached.
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["tools"][0]["cache_control"] == {"type": "ephemeral"}
    assert result.tool_input["reply"].startswith("Thanks")


# ---------------------------------------------------------------------------
# call_strategy — Opus + extended thinking + no tool_choice.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_call_strategy_uses_opus_with_extended_thinking() -> None:
    client = AnthropicClient(api_key="sk-test-fake")
    fake_create = AsyncMock(return_value=_make_fake_strategy_response())

    with patch.object(client._client.messages, "create", fake_create):  # noqa: SLF001
        result = await client.call_strategy("user message")

    kwargs = fake_create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-4-7"
    assert kwargs["max_tokens"] == 8192
    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 8000}
    # No tool_choice / tools on strategy calls.
    assert "tool_choice" not in kwargs or kwargs.get("tool_choice") is None
    assert "tools" not in kwargs or not kwargs.get("tools")

    # Surface text and thinking separately.
    assert result.text.startswith("## Weekly report")
    assert "ad copy patterns" in result.thinking
    assert result.model == "claude-opus-4-7"
    assert result.prompt_version == "v1"


# ---------------------------------------------------------------------------
# Module-level constants are stable.
# ---------------------------------------------------------------------------
def test_module_constants() -> None:
    assert anthropic_client_module.TRIAGE_MODEL == "claude-haiku-4-5-20251001"
    assert anthropic_client_module.REPLY_MODEL == "claude-sonnet-4-6"
    assert anthropic_client_module.STRATEGY_MODEL == "claude-opus-4-7"
