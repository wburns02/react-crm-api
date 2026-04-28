"""Hallucination guard catches unsupported tool claims and rewrites them."""
import pytest

from app.services.voice_agent.hallucination_guard import (
    HallucinationGuard,
    GuardResult,
)


def test_pass_through_when_no_pattern_match():
    guard = HallucinationGuard()
    result = guard.check(
        text="That's a great question about pricing.",
        tool_calls=[],
    )
    assert result.rewritten_text == "That's a great question about pricing."
    assert result.hallucinations == []


def test_catches_sms_claim_without_tool_call():
    guard = HallucinationGuard()
    result = guard.check(
        text="Great — I just sent you a text with the details.",
        tool_calls=[],
    )
    assert result.hallucinations
    assert result.hallucinations[0]["pattern"] == "sms"
    # Rewritten text must not still claim the SMS was sent
    assert "sent you a text" not in result.rewritten_text.lower()
    assert "let me check" in result.rewritten_text.lower() or "follow up" in result.rewritten_text.lower()


def test_passes_sms_claim_when_tool_was_called():
    guard = HallucinationGuard()
    result = guard.check(
        text="Great — I just sent you a text with the details.",
        tool_calls=[{"name": "send_followup_sms", "input": {"message": "..."}}],
    )
    assert result.hallucinations == []
    assert result.rewritten_text == "Great — I just sent you a text with the details."


def test_catches_booking_claim_without_tool_call():
    guard = HallucinationGuard()
    result = guard.check(
        text="I'll book you for Tuesday morning at 10.",
        tool_calls=[],
    )
    assert result.hallucinations
    assert "book" not in result.rewritten_text.lower() or "let me" in result.rewritten_text.lower()


def test_passes_booking_claim_when_book_appointment_called():
    guard = HallucinationGuard()
    result = guard.check(
        text="I just booked you for Tuesday at 10.",
        tool_calls=[{"name": "book_appointment", "input": {"scheduled_date": "2026-04-30"}}],
    )
    assert result.hallucinations == []


def test_passes_booking_claim_when_create_callback_called():
    guard = HallucinationGuard()
    result = guard.check(
        text="I'll schedule you for a callback tomorrow.",
        tool_calls=[{"name": "create_callback", "input": {"callback_time": "tomorrow"}}],
    )
    assert result.hallucinations == []


def test_catches_transfer_claim_without_tool_call():
    guard = HallucinationGuard()
    result = guard.check(
        text="Let me transfer you to the office.",
        tool_calls=[],
    )
    assert result.hallucinations


def test_multiple_sentences_only_offending_one_rewritten():
    guard = HallucinationGuard()
    result = guard.check(
        text="I understand your concern. I just sent you a text. Let me know if you need anything else.",
        tool_calls=[],
    )
    assert "I understand your concern." in result.rewritten_text
    assert "Let me know if you need anything else." in result.rewritten_text
    assert "sent you a text" not in result.rewritten_text.lower()


def test_guard_result_carries_original_for_audit():
    guard = HallucinationGuard()
    result = guard.check(
        text="I just sent you a text.",
        tool_calls=[],
    )
    assert result.hallucinations[0]["original"] == "I just sent you a text."
    assert result.hallucinations[0]["rewritten"] != "I just sent you a text."
