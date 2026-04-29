"""Cost-math tests for app.services.ai.pricing.

Pricing values themselves are guarded by inspection (not by these tests) — the
tests check that the multipliers and quantization are right.
"""
from decimal import Decimal

import pytest

from app.services.ai import pricing


# All asserted costs are quantized to 6dp (matches NUMERIC(10,6) DB column).
_QUANTUM = Decimal("0.000001")


def _q(value: str) -> Decimal:
    return Decimal(value).quantize(_QUANTUM)


def test_haiku_no_cache_input_and_output_only() -> None:
    """1k input + 1k output on Haiku 4.5 = $0.001 + $0.005 = $0.006."""
    cost = pricing.compute_cost_usd(
        "claude-haiku-4-5-20251001",
        input_tokens=1_000,
        output_tokens=1_000,
    )
    assert cost == _q("0.006000")
    # Quantized to 6 decimal places.
    assert cost.as_tuple().exponent == -6


def test_haiku_cache_read_is_one_tenth_input() -> None:
    """10k cache_read tokens on Haiku at $1/MTok x 0.10 = $0.001."""
    cost = pricing.compute_cost_usd(
        "claude-haiku-4-5-20251001",
        cache_read_tokens=10_000,
    )
    assert cost == _q("0.001000")


def test_haiku_cache_write_is_125_percent_input() -> None:
    """1M cache_write tokens on Haiku at $1/MTok x 1.25 = $1.25."""
    cost = pricing.compute_cost_usd(
        "claude-haiku-4-5-20251001",
        cache_write_tokens=1_000_000,
    )
    assert cost == _q("1.250000")


def test_sonnet_4_6_standard() -> None:
    """1k input + 1k output on Sonnet 4.6 = $0.003 + $0.015 = $0.018."""
    cost = pricing.compute_cost_usd(
        "claude-sonnet-4-6",
        input_tokens=1_000,
        output_tokens=1_000,
    )
    assert cost == _q("0.018000")


def test_opus_4_7_standard() -> None:
    """1k input + 1k output on Opus 4.7 = $0.005 + $0.025 = $0.030."""
    cost = pricing.compute_cost_usd(
        "claude-opus-4-7",
        input_tokens=1_000,
        output_tokens=1_000,
    )
    assert cost == _q("0.030000")


def test_opus_4_7_with_thinking_tokens_priced_as_output() -> None:
    """Thinking tokens are billed at the output rate.

    1k thinking tokens on Opus 4.7 ($25/MTok output) = $0.025.
    """
    cost = pricing.compute_cost_usd(
        "claude-opus-4-7",
        thinking_tokens=1_000,
    )
    assert cost == _q("0.025000")


def test_zero_tokens_returns_zero_cost() -> None:
    """Edge case: all-zero usage → exactly $0.000000."""
    cost = pricing.compute_cost_usd("claude-haiku-4-5-20251001")
    assert cost == _q("0.000000")
    assert cost == Decimal("0")


def test_unknown_model_raises() -> None:
    """Bogus model id must raise UnknownModelError, not silently default."""
    with pytest.raises(pricing.UnknownModelError):
        pricing.compute_cost_usd("claude-fictional-99", input_tokens=10)


def test_combined_realistic_haiku_call() -> None:
    """Realistic mix: 200 input + 150 output + 5000 cache_read.

    200 * 1e-6 + 150 * 5e-6 + 5000 * 1e-6 * 0.10
      = 0.0002 + 0.00075 + 0.0005 = 0.001450
    """
    cost = pricing.compute_cost_usd(
        "claude-haiku-4-5-20251001",
        input_tokens=200,
        output_tokens=150,
        cache_read_tokens=5_000,
    )
    assert cost == _q("0.001450")


def test_haiku_alias_matches_dated_id() -> None:
    """The alias claude-haiku-4-5 should match claude-haiku-4-5-20251001."""
    a = pricing.compute_cost_usd(
        "claude-haiku-4-5", input_tokens=1_000, output_tokens=1_000
    )
    b = pricing.compute_cost_usd(
        "claude-haiku-4-5-20251001", input_tokens=1_000, output_tokens=1_000
    )
    assert a == b
