"""Voicemail flow triggered when AMD returns `machine_end_beep`.

Renders a templated message via Cartesia, then the WS handler streams it
to Twilio and hangs up. No LLM in the loop — voicemail content is fixed.
"""
import logging

import httpx

from app.config import settings


logger = logging.getLogger(__name__)


_VOICEMAIL_TEMPLATE = (
    "Hi {first_name}, this is Sarah from MAC Septic. I was following up on the "
    "estimate we sent you for {service_type}. Please give us a call back when you "
    "have a moment at six one five, three four five, two five four four. "
    "Thanks, and have a great day."
)


def render_text(prospect: dict, quote: dict) -> str:
    return _VOICEMAIL_TEMPLATE.format(
        first_name=prospect.get("first_name") or "there",
        service_type=quote.get("title") or "septic services",
    )


async def synthesize_voicemail_audio(prospect: dict, quote: dict) -> bytes | None:
    """Render Cartesia μ-law 8kHz audio. Returns None if Cartesia unconfigured."""
    if not settings.CARTESIA_API_KEY or not settings.CARTESIA_VOICE_ID:
        logger.warning("[Voicemail] Cartesia not configured — cannot synthesize")
        return None
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
    except Exception as exc:
        logger.exception(f"[Voicemail] Cartesia request failed: {exc}")
        return None

    if resp.status_code != 200:
        logger.error(f"[Voicemail] Cartesia returned {resp.status_code}: {resp.text[:200]}")
        return None
    return resp.content
