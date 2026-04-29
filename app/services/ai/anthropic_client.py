"""Thin async wrapper around the Anthropic SDK.

Responsibilities:
  - Auto-applies cache_control to the system block AND tool definitions
    (per docs/AI_INTERACTION_ANALYZER_BUILD_PROMPT.md, "Anthropic SDK setup").
  - Reads usage.cache_read_input_tokens, usage.cache_creation_input_tokens,
    usage.input_tokens, usage.output_tokens.
  - Computes cost_usd via app.services.ai.pricing.compute_cost_usd().
  - Forces tool_choice for triage and reply (structured output).
  - Strategy uses extended thinking (budget_tokens=8000).

Models:
  - Triage   = claude-haiku-4-5-20251001
  - Reply    = claude-sonnet-4-6
  - Strategy = claude-opus-4-7
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from anthropic import AsyncAnthropic

from app.services.ai.pricing import compute_cost_usd
from app.services.ai.prompts import (
    REPLY_SYSTEM_V1,
    REPLY_TOOL_V1,
    REPLY_VERSION,
    STRATEGY_SYSTEM_V1,
    STRATEGY_VERSION,
    TRIAGE_SYSTEM_V1,
    TRIAGE_TOOL_V1,
    TRIAGE_VERSION,
)


# Model IDs (single source of truth — must match pricing.PRICING keys).
TRIAGE_MODEL = "claude-haiku-4-5-20251001"
REPLY_MODEL = "claude-sonnet-4-6"
STRATEGY_MODEL = "claude-opus-4-7"

# Default max_tokens by tier.
TRIAGE_MAX_TOKENS = 1024
REPLY_MAX_TOKENS = 1024
STRATEGY_MAX_TOKENS = 8192
STRATEGY_THINKING_BUDGET_TOKENS = 8000


# ---------------------------------------------------------------------------
# Result dataclasses — what each call returns.
# ---------------------------------------------------------------------------
@dataclass
class _BaseResult:
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: Decimal
    duration_ms: int
    raw: Any = field(repr=False)


@dataclass
class TriageResult(_BaseResult):
    """Tier 1 (Haiku): forced tool call → structured JSON in `tool_input`."""

    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReplyResult(_BaseResult):
    """Tier 2 (Sonnet): forced tool call → drafted reply in `tool_input`."""

    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyResult(_BaseResult):
    """Tier 3 (Opus): markdown text + extended thinking content."""

    text: str = ""
    thinking: str = ""
    thinking_tokens: int = 0


# ---------------------------------------------------------------------------
# Client.
# ---------------------------------------------------------------------------
class AnthropicClient:
    """Async wrapper. Construct from settings.ANTHROPIC_API_KEY."""

    def __init__(self, api_key: str) -> None:
        if not api_key or not api_key.strip():
            raise ValueError(
                "ANTHROPIC_API_KEY is required. Set it via Railway env vars."
            )
        self._client = AsyncAnthropic(api_key=api_key)

    # -- public methods -----------------------------------------------------
    async def call_triage(
        self,
        user_message: str,
        max_tokens: int = TRIAGE_MAX_TOKENS,
    ) -> TriageResult:
        """Tier 1: Haiku 4.5 forced-tool triage. Returns structured analysis."""
        system_blocks = self._cached_system(TRIAGE_SYSTEM_V1)
        tools = self._cached_tools([TRIAGE_TOOL_V1])

        start = time.perf_counter()
        response = await self._client.messages.create(
            model=TRIAGE_MODEL,
            max_tokens=max_tokens,
            system=system_blocks,
            tools=tools,
            tool_choice={"type": "tool", "name": TRIAGE_TOOL_V1["name"]},
            messages=[{"role": "user", "content": user_message}],
        )
        duration_ms = int((time.perf_counter() - start) * 1000)

        usage = self._extract_usage(response)
        tool_name, tool_input = self._extract_tool_call(response)

        cost = compute_cost_usd(
            TRIAGE_MODEL,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            cache_write_tokens=usage["cache_write_tokens"],
        )
        return TriageResult(
            model=TRIAGE_MODEL,
            prompt_version=TRIAGE_VERSION,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            cache_write_tokens=usage["cache_write_tokens"],
            cost_usd=cost,
            duration_ms=duration_ms,
            raw=response,
            tool_name=tool_name,
            tool_input=tool_input,
        )

    async def call_reply(
        self,
        user_message: str,
        max_tokens: int = REPLY_MAX_TOKENS,
    ) -> ReplyResult:
        """Tier 2: Sonnet 4.6 forced-tool reply drafter."""
        system_blocks = self._cached_system(REPLY_SYSTEM_V1)
        tools = self._cached_tools([REPLY_TOOL_V1])

        start = time.perf_counter()
        response = await self._client.messages.create(
            model=REPLY_MODEL,
            max_tokens=max_tokens,
            system=system_blocks,
            tools=tools,
            tool_choice={"type": "tool", "name": REPLY_TOOL_V1["name"]},
            messages=[{"role": "user", "content": user_message}],
        )
        duration_ms = int((time.perf_counter() - start) * 1000)

        usage = self._extract_usage(response)
        tool_name, tool_input = self._extract_tool_call(response)

        cost = compute_cost_usd(
            REPLY_MODEL,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            cache_write_tokens=usage["cache_write_tokens"],
        )
        return ReplyResult(
            model=REPLY_MODEL,
            prompt_version=REPLY_VERSION,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            cache_write_tokens=usage["cache_write_tokens"],
            cost_usd=cost,
            duration_ms=duration_ms,
            raw=response,
            tool_name=tool_name,
            tool_input=tool_input,
        )

    async def call_strategy(
        self,
        user_message: str,
        max_tokens: int = STRATEGY_MAX_TOKENS,
        thinking_budget_tokens: int = STRATEGY_THINKING_BUDGET_TOKENS,
    ) -> StrategyResult:
        """Tier 3: Opus 4.7 weekly strategist with extended thinking."""
        system_blocks = self._cached_system(STRATEGY_SYSTEM_V1)

        start = time.perf_counter()
        response = await self._client.messages.create(
            model=STRATEGY_MODEL,
            max_tokens=max_tokens,
            system=system_blocks,
            thinking={
                "type": "enabled",
                "budget_tokens": thinking_budget_tokens,
            },
            messages=[{"role": "user", "content": user_message}],
        )
        duration_ms = int((time.perf_counter() - start) * 1000)

        usage = self._extract_usage(response)
        text, thinking_text = self._extract_strategy_content(response)

        # Extended thinking tokens are billed as output tokens. Anthropic SDK
        # reports them as part of `output_tokens`, so we don't double-count
        # here — pass thinking_tokens=0 to compute_cost_usd. We surface the
        # thinking text length only as a separate field for observability.
        cost = compute_cost_usd(
            STRATEGY_MODEL,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            cache_write_tokens=usage["cache_write_tokens"],
        )
        return StrategyResult(
            model=STRATEGY_MODEL,
            prompt_version=STRATEGY_VERSION,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            cache_write_tokens=usage["cache_write_tokens"],
            cost_usd=cost,
            duration_ms=duration_ms,
            raw=response,
            text=text,
            thinking=thinking_text,
            thinking_tokens=len(thinking_text.split()) if thinking_text else 0,
        )

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _cached_system(text: str) -> list[dict[str, Any]]:
        """Build a system block list with cache_control on the text block."""
        return [
            {
                "type": "text",
                "text": text,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    @staticmethod
    def _cached_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deep-copy tool defs and apply cache_control to each (per spec)."""
        out: list[dict[str, Any]] = []
        for tool in tools:
            cloned = copy.deepcopy(tool)
            cloned["cache_control"] = {"type": "ephemeral"}
            out.append(cloned)
        return out

    @staticmethod
    def _extract_usage(response: Any) -> dict[str, int]:
        """Read token counts off response.usage. Defaults to 0 when absent."""
        usage = getattr(response, "usage", None)
        return {
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            "cache_read_tokens": int(
                getattr(usage, "cache_read_input_tokens", 0) or 0
            ),
            "cache_write_tokens": int(
                getattr(usage, "cache_creation_input_tokens", 0) or 0
            ),
        }

    @staticmethod
    def _extract_tool_call(response: Any) -> tuple[str, dict[str, Any]]:
        """Pull the first tool_use block from the response. Returns (name, input)."""
        content = getattr(response, "content", []) or []
        for block in content:
            block_type = getattr(block, "type", None)
            if block_type == "tool_use":
                return (
                    str(getattr(block, "name", "")),
                    dict(getattr(block, "input", {}) or {}),
                )
        return ("", {})

    @staticmethod
    def _extract_strategy_content(response: Any) -> tuple[str, str]:
        """Pull (text, thinking) from a strategy response."""
        content = getattr(response, "content", []) or []
        text_parts: list[str] = []
        thinking_parts: list[str] = []
        for block in content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(str(getattr(block, "text", "") or ""))
            elif block_type == "thinking":
                thinking_parts.append(
                    str(getattr(block, "thinking", "") or "")
                )
        return ("".join(text_parts), "".join(thinking_parts))


__all__ = [
    "AnthropicClient",
    "TriageResult",
    "ReplyResult",
    "StrategyResult",
    "TRIAGE_MODEL",
    "REPLY_MODEL",
    "STRATEGY_MODEL",
]
