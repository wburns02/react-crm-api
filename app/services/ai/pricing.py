"""Anthropic API pricing — single source of truth.

Sourced via the claude-api skill (cached 2026-04-15). Prices are USD per
1,000,000 tokens. Cache write tokens are billed at 1.25x input price; cache
read tokens at 0.10x input price (per docs/AI_INTERACTION_ANALYZER_BUILD_PROMPT
and confirmed by claude-api skill, shared/prompt-caching.md).

Thinking tokens are billed as output tokens.

If Anthropic publishes a price change, update this file. Tests in
tests/services/ai/test_pricing.py guard the math, not the prices themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


_TOKENS_PER_MTOK = Decimal("1000000")
_QUANTUM = Decimal("0.000001")  # 6 decimal places, matches NUMERIC(10,6) DB column

# Cache multipliers (applied to base input price).
CACHE_WRITE_MULTIPLIER = Decimal("1.25")
CACHE_READ_MULTIPLIER = Decimal("0.10")


@dataclass(frozen=True)
class ModelPricing:
    """Per-MTok pricing for a single Claude model."""

    input_per_mtok: Decimal
    output_per_mtok: Decimal


# Source of truth (USD per million tokens). Pulled via the claude-api skill.
# claude-haiku-4-5-20251001 — used for tier 1 (triage)
# claude-sonnet-4-6 — used for tier 2 (reply drafter)
# claude-opus-4-7 — used for tier 3 (weekly strategist; thinking enabled)
PRICING: dict[str, ModelPricing] = {
    "claude-haiku-4-5-20251001": ModelPricing(
        input_per_mtok=Decimal("1.00"),
        output_per_mtok=Decimal("5.00"),
    ),
    # Alias without the date suffix (some callers may use the alias).
    "claude-haiku-4-5": ModelPricing(
        input_per_mtok=Decimal("1.00"),
        output_per_mtok=Decimal("5.00"),
    ),
    "claude-sonnet-4-6": ModelPricing(
        input_per_mtok=Decimal("3.00"),
        output_per_mtok=Decimal("15.00"),
    ),
    "claude-opus-4-7": ModelPricing(
        input_per_mtok=Decimal("5.00"),
        output_per_mtok=Decimal("25.00"),
    ),
}


class UnknownModelError(ValueError):
    """Raised when compute_cost_usd is called with an unrecognized model id."""


def get_pricing(model: str) -> ModelPricing:
    """Return the pricing entry for `model`. Raises UnknownModelError."""
    pricing = PRICING.get(model)
    if pricing is None:
        raise UnknownModelError(
            f"No pricing configured for model {model!r}. "
            f"Add it to app/services/ai/pricing.py::PRICING."
        )
    return pricing


def compute_cost_usd(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    thinking_tokens: int = 0,
) -> Decimal:
    """Compute total USD cost for one Anthropic API call.

    Pricing model:
      - input_tokens         x base input price
      - output_tokens        x base output price
      - cache_read_tokens    x base input price x 0.10 (cache hit, cheap)
      - cache_write_tokens   x base input price x 1.25 (cache write premium)
      - thinking_tokens      x base output price (Opus extended thinking)

    The total is quantized to 6 decimal places to match the NUMERIC(10,6)
    column in interaction_analysis_runs.cost_usd.
    """
    pricing = get_pricing(model)
    input_unit = pricing.input_per_mtok / _TOKENS_PER_MTOK
    output_unit = pricing.output_per_mtok / _TOKENS_PER_MTOK

    cost = (
        Decimal(input_tokens) * input_unit
        + Decimal(output_tokens) * output_unit
        + Decimal(cache_read_tokens) * input_unit * CACHE_READ_MULTIPLIER
        + Decimal(cache_write_tokens) * input_unit * CACHE_WRITE_MULTIPLIER
        + Decimal(thinking_tokens) * output_unit
    )
    return cost.quantize(_QUANTUM, rounding=ROUND_HALF_UP)
