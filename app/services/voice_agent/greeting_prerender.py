"""Render the greeting TTS at dial time so the customer hears Sarah within
~150ms of Twilio Media Stream connect, instead of waiting 5–8s for the LLM
+ TTS round trip on every call.

Buffer is held in memory keyed by call_sid. Released on Stream connect once
AMD has confirmed the answerer is human.
"""
import logging

import httpx

from app.config import settings


logger = logging.getLogger(__name__)


_GREETING_TEMPLATE = "Hey {first_name}, this is Phil from MAC Septic — got a sec?"


# call_sid -> raw audio bytes (μ-law 8kHz, ready to ship to Twilio)
_buffers: dict[str, bytes] = {}


def render_text(prospect: dict, quote: dict) -> str:
    return _GREETING_TEMPLATE.format(
        first_name=prospect.get("first_name") or "there",
        service_type=quote.get("title") or "septic services",
    )


async def prerender_greeting(call_sid: str, prospect: dict, quote: dict) -> None:
    """Synthesize greeting via Cartesia and stash bytes in `_buffers`.

    Called by campaign_dialer immediately after Twilio.calls.create returns.
    Failures are non-fatal — if Cartesia is down or unconfigured, we just
    fall back to the LLM-generated greeting (slower, but works).
    """
    if not settings.CARTESIA_API_KEY or not settings.CARTESIA_VOICE_ID:
        logger.warning(f"[Prerender:{call_sid[:8]}] Cartesia not configured — skipping prerender")
        return

    text = render_text(prospect, quote)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.cartesia.ai/tts/bytes",
                headers={
                    "X-API-Key": settings.CARTESIA_API_KEY,
                    "Cartesia-Version": "2024-11-13",
                    "Content-Type": "application/json",
                },
                json={
                    "model_id": "sonic-3",
                    "transcript": text,
                    "voice": {"mode": "id", "id": settings.CARTESIA_VOICE_ID},
                    "output_format": {
                        "container": "raw",
                        "encoding": "pcm_mulaw",
                        "sample_rate": 8000,
                    },
                },
            )
        if resp.status_code != 200:
            logger.error(
                f"[Prerender:{call_sid[:8]}] Cartesia returned "
                f"{resp.status_code}: {resp.text[:200]}"
            )
            return
        _buffers[call_sid] = resp.content
        logger.info(
            f"[Prerender:{call_sid[:8]}] greeting buffered "
            f"({len(resp.content)} bytes, ~{len(resp.content)/8000:.1f}s of audio)"
        )
    except Exception as exc:
        logger.exception(f"[Prerender:{call_sid[:8]}] error: {exc}")


def take_buffer(call_sid: str) -> bytes | None:
    """Pop and return the prerendered audio for a call_sid (None if not ready)."""
    return _buffers.pop(call_sid, None)


def discard(call_sid: str) -> None:
    """Drop a buffered greeting (e.g., on AMD = machine_end_beep)."""
    _buffers.pop(call_sid, None)
