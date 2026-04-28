"""Pre-TTS guard that catches unsupported tool claims in LLM output.

Maps regex patterns to the tool calls that would justify them. If a claim is
found in the assistant's text but no matching tool_use block was generated in
the same turn, we rewrite the offending sentence to a soft alternative
("Let me check on that") before it reaches TTS, log the original/rewritten
pair for the call_logs.hallucinations field, and signal the session to inject
a self-correction nudge into Claude's next turn.
"""
import re
from dataclasses import dataclass, field
from typing import Any


# (pattern_name, compiled_regex, justifying_tool_names)
_PATTERNS: list[tuple[str, re.Pattern, set[str]]] = [
    (
        "sms",
        re.compile(
            r"\bI(?:'ve| just|'ll| will)?\s*(?:sent|sending|send|text(?:ed|ing)?|message(?:d|ing)?)\s+(?:you\s+)?(?:a|the|that)?\s*(?:text|message|email|sms)?",
            re.IGNORECASE,
        ),
        {"send_followup_sms"},
    ),
    (
        "booking",
        re.compile(
            r"\bI(?:'ve| just|'ll| will|'m)?\s*(?:book(?:ed|ing)?|schedul(?:ed|ing|e))\s+(?:you|an?|the)",
            re.IGNORECASE,
        ),
        {"book_appointment", "create_callback"},
    ),
    (
        "transfer",
        re.compile(
            r"\b(?:let me\s+)?transfer(?:ring)?\s+you",
            re.IGNORECASE,
        ),
        {"transfer_call"},
    ),
]


_SOFT_REWRITE = "Let me check on that for you."


@dataclass
class GuardResult:
    rewritten_text: str
    hallucinations: list[dict[str, str]] = field(default_factory=list)


class HallucinationGuard:
    """Stateless checker; one instance per session is fine."""

    def check(self, text: str, tool_calls: list[dict[str, Any]]) -> GuardResult:
        called_tool_names = {tc.get("name") for tc in tool_calls}
        sentences = self._split_sentences(text)
        rewritten_sentences: list[str] = []
        caught: list[dict[str, str]] = []

        for sentence in sentences:
            offending_pattern = self._find_unsupported_claim(sentence, called_tool_names)
            if offending_pattern is None:
                rewritten_sentences.append(sentence)
                continue
            caught.append(
                {
                    "pattern": offending_pattern,
                    "original": sentence.strip(),
                    "rewritten": _SOFT_REWRITE,
                }
            )
            rewritten_sentences.append(_SOFT_REWRITE)

        return GuardResult(
            rewritten_text=" ".join(s.strip() for s in rewritten_sentences if s.strip()),
            hallucinations=caught,
        )

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        # Lightweight splitter: split on . ! ? followed by whitespace, keeping the punctuation.
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return [p for p in parts if p]

    @staticmethod
    def _find_unsupported_claim(sentence: str, called_tool_names: set[str]) -> str | None:
        for pattern_name, regex, justifying_tools in _PATTERNS:
            if regex.search(sentence) and not (justifying_tools & called_tool_names):
                return pattern_name
        return None
