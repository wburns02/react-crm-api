"""
API endpoints for the AI Outbound Sales Agent.

Handles:
- Campaign management (start/stop/pause/status)
- Twilio voice webhook (TwiML for media streams)
- Twilio status callback
- Media stream WebSocket (audio in/out)
- Queue management
"""

import asyncio
import base64
import json
import logging
import struct
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Response, Depends
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.services.outbound_agent import OutboundAgentSession
from app.services.campaign_dialer import (
    campaign, active_sessions, start_campaign, stop_campaign,
    pause_campaign, resume_campaign, get_prospect_queue,
    get_pending_call_data, remove_pending_call_data,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outbound-agent", tags=["outbound-agent"])


# ── Campaign Management Endpoints ──────────────────────────────────

@router.post("/campaign/start")
async def api_start_campaign():
    """Start the outbound calling campaign."""
    result = await start_campaign()
    return result


@router.post("/campaign/stop")
async def api_stop_campaign():
    """Stop the campaign."""
    result = await stop_campaign()
    return result


@router.post("/campaign/pause")
async def api_pause_campaign():
    """Pause the campaign."""
    result = await pause_campaign()
    return result


@router.post("/campaign/resume")
async def api_resume_campaign():
    """Resume the campaign."""
    result = await resume_campaign()
    return result


@router.get("/campaign/status")
async def api_campaign_status():
    """Get current campaign status."""
    return campaign.to_dict()


@router.get("/queue")
async def api_get_queue():
    """Get the prospect queue."""
    queue = await get_prospect_queue(limit=20)
    return {
        "queue": [
            {
                "name": f"{e['prospect']['first_name']} {e['prospect']['last_name']}",
                "phone": e["prospect"]["phone"],
                "quote_number": e["quote"]["quote_number"],
                "quote_total": e["quote"]["total"],
                "sent_at": e["quote"]["sent_at"],
                "service": (e["quote"]["line_items"][0]["service"]
                           if e["quote"].get("line_items") else "septic service"),
            }
            for e in queue
        ],
        "total": len(queue),
    }


@router.get("/active-calls")
async def api_active_calls():
    """Get active call sessions."""
    return {
        "calls": [
            {
                "call_sid": sid,
                "prospect": f"{s.prospect.get('first_name', '')} {s.prospect.get('last_name', '')}",
                "duration": (datetime.utcnow() - s.started_at).total_seconds(),
                "disposition": s.disposition,
                "transcript_length": len(s.transcript),
            }
            for sid, s in active_sessions.items()
        ]
    }


@router.get("/call-log/{call_sid}")
async def api_call_log(call_sid: str):
    """Get transcript and details for a specific call."""
    session = active_sessions.get(call_sid)
    if session:
        return session.get_summary()
    return {"error": "Call not found"}


# ── Twilio Voice Webhook ───────────────────────────────────────────

@router.post("/voice")
async def twilio_voice_webhook(request: Request):
    """
    Twilio hits this URL when the outbound call connects.
    Returns TwiML that starts a media stream for real-time audio.
    """
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    to_number = form.get("To", "")
    call_status = form.get("CallStatus", "")
    answered_by = form.get("AnsweredBy", "")

    logger.info(
        f"Outbound voice webhook: SID={call_sid} To={to_number} "
        f"Status={call_status} AnsweredBy={answered_by}"
    )

    # Get the stored prospect data
    call_data = get_pending_call_data(to_number)
    if not call_data:
        logger.warning(f"No pending call data for {to_number}")
        twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Sorry, there was an error.</Say><Hangup/></Response>'
        return PlainTextResponse(twiml, media_type="text/xml")

    # Check if it went to voicemail via AMD
    if answered_by in ("machine_start", "machine_end_beep", "machine_end_silence"):
        logger.info(f"Voicemail detected for {to_number}")
        # Leave a voicemail via TTS
        p = call_data["prospect"]
        q = call_data["quote"]
        line_items = q.get("line_items", [])
        service = line_items[0].get("service", "septic service") if line_items else "septic service"
        vm_text = (
            f"Hi {p.get('first_name', '')}, this is MAC Septic following up "
            f"on the estimate we sent for {service} at your property. "
            f"Give us a call back at 615-345-2544 when you get a chance. Thanks!"
        )
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            f'<Say voice="Polly.Matthew">{vm_text}</Say>'
            '<Hangup/>'
            '</Response>'
        )
        remove_pending_call_data(to_number)
        return PlainTextResponse(twiml, media_type="text/xml")

    # Human answered — start media stream for AI conversation
    # Build the WebSocket URL for media streams
    ws_host = request.headers.get("host", "react-crm-api-production.up.railway.app")
    ws_url = f"wss://{ws_host}/ws/outbound-agent/{call_sid}"

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        '<Connect>'
        f'<Stream url="{ws_url}" />'
        '</Connect>'
        '</Response>'
    )

    # Create the agent session
    prospect = call_data["prospect"]
    quote = call_data["quote"]

    session = OutboundAgentSession(
        call_sid=call_sid,
        prospect=prospect,
        quote=quote,
    )
    active_sessions[call_sid] = session

    remove_pending_call_data(to_number)

    return PlainTextResponse(twiml, media_type="text/xml")


@router.post("/status")
async def twilio_status_callback(request: Request):
    """Twilio call status callback."""
    form = await request.form()
    call_sid = form.get("CallSid", "")
    status = form.get("CallStatus", "")

    logger.info(f"Outbound call status: SID={call_sid} Status={status}")

    if status in ("completed", "busy", "no-answer", "failed", "canceled"):
        session = active_sessions.get(call_sid)
        if session:
            if not session.disposition:
                if status == "no-answer":
                    session.disposition = "no_answer"
                elif status == "busy":
                    session.disposition = "no_answer"
                elif status == "failed":
                    session.disposition = "no_answer"
            session.ended = True

    return PlainTextResponse("OK")


# ── Media Stream WebSocket ─────────────────────────────────────────
# This is mounted on the main app router, not under /api/v2

media_ws_router = APIRouter()


@media_ws_router.websocket("/ws/outbound-agent/{call_sid}")
async def ws_outbound_agent_media(websocket: WebSocket, call_sid: str):
    """
    Twilio Media Streams WebSocket for the outbound AI agent.

    Receives mu-law 8kHz audio from the customer.
    Sends mu-law 8kHz audio back (agent speech from ElevenLabs TTS).
    """
    await websocket.accept()
    logger.info(f"Outbound agent media stream connected: {call_sid}")

    session = active_sessions.get(call_sid)
    if not session:
        logger.warning(f"No session found for {call_sid}")
        await websocket.close()
        return

    stream_sid = None
    stt_buffer = bytearray()
    stt_task = None
    speech_accumulator = ""
    silence_counter = 0
    last_speech_time = datetime.utcnow()

    # Wire up the speak callback for TTS
    async def speak(text: str):
        """Convert text to speech via ElevenLabs and send to Twilio."""
        nonlocal stream_sid
        if not stream_sid:
            return

        try:
            audio_data = await _text_to_speech(text)
            if audio_data:
                # ElevenLabs returns mp3/pcm. We need mu-law for Twilio.
                # For now, use Twilio's <Say> as a fallback since mu-law
                # conversion requires additional processing.
                # Send audio payload as base64 mu-law
                payload = base64.b64encode(audio_data).decode()
                media_msg = json.dumps({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload}
                })
                await websocket.send_text(media_msg)
        except Exception as e:
            logger.error(f"TTS/send error: {e}")

    session.on_speak = speak

    async def end_call():
        """Signal Twilio to end the call."""
        try:
            if TWILIO_AVAILABLE and settings.TWILIO_ACCOUNT_SID:
                from twilio.rest import Client
                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                client.calls(call_sid).update(status="completed")
        except Exception as e:
            logger.error(f"Failed to end call {call_sid}: {e}")

    session.on_end_call = end_call

    async def transfer(number: str):
        """Transfer the call."""
        try:
            if TWILIO_AVAILABLE and settings.TWILIO_ACCOUNT_SID:
                from twilio.rest import Client
                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                twiml = f'<Response><Dial>{number}</Dial></Response>'
                client.calls(call_sid).update(twiml=twiml)
        except Exception as e:
            logger.error(f"Failed to transfer call {call_sid}: {e}")

    session.on_transfer = transfer

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event = msg.get("event")

            if event == "connected":
                logger.info(f"Media stream connected for {call_sid}")

            elif event == "start":
                stream_sid = msg.get("start", {}).get("streamSid")
                logger.info(f"Media stream started: streamSid={stream_sid}")
                # Send greeting after a brief pause
                await asyncio.sleep(1)
                await session.start_greeting()

            elif event == "media":
                # Receive customer audio (mu-law 8kHz)
                payload = msg.get("media", {}).get("payload", "")
                if payload:
                    audio_bytes = base64.b64decode(payload)
                    stt_buffer.extend(audio_bytes)

                    # Process STT every ~1 second of audio (8000 bytes at 8kHz mu-law)
                    if len(stt_buffer) >= 8000:
                        chunk = bytes(stt_buffer)
                        stt_buffer.clear()

                        # Simple energy-based VAD
                        energy = sum(abs(b - 128) for b in chunk) / len(chunk)
                        if energy > 10:  # Speech detected
                            silence_counter = 0
                            last_speech_time = datetime.utcnow()
                            # Send to STT
                            text = await _speech_to_text(chunk)
                            if text:
                                speech_accumulator += " " + text
                        else:
                            silence_counter += 1
                            # After ~2 seconds of silence, process accumulated speech
                            if silence_counter >= 2 and speech_accumulator.strip():
                                accumulated = speech_accumulator.strip()
                                speech_accumulator = ""
                                silence_counter = 0
                                await session.handle_speech(accumulated)

            elif event == "stop":
                logger.info(f"Media stream stopped for {call_sid}")
                break

    except WebSocketDisconnect:
        logger.info(f"Media stream disconnected for {call_sid}")
    except Exception as e:
        logger.error(f"Media stream error for {call_sid}: {e}")
    finally:
        session.ended = True
        summary = session.get_summary()
        logger.info(f"Call {call_sid} ended. Disposition: {summary['disposition']}")


# ── STT (Deepgram) ─────────────────────────────────────────────────

async def _speech_to_text(audio_bytes: bytes) -> Optional[str]:
    """Transcribe mu-law audio using Deepgram Nova-3."""
    if not settings.DEEPGRAM_API_KEY:
        return None

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                "https://api.deepgram.com/v1/listen",
                headers={
                    "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
                    "Content-Type": "audio/mulaw",
                },
                params={
                    "model": "nova-3",
                    "encoding": "mulaw",
                    "sample_rate": "8000",
                    "channels": "1",
                    "smart_format": "true",
                    "no_delay": "true",
                },
                content=audio_bytes,
            )

            if resp.status_code == 200:
                data = resp.json()
                transcript = (
                    data.get("results", {})
                    .get("channels", [{}])[0]
                    .get("alternatives", [{}])[0]
                    .get("transcript", "")
                )
                return transcript if transcript.strip() else None
            else:
                logger.error(f"Deepgram error: {resp.status_code}")
                return None

    except Exception as e:
        logger.error(f"STT error: {e}")
        return None


# ── TTS (ElevenLabs) ───────────────────────────────────────────────

async def _text_to_speech(text: str) -> Optional[bytes]:
    """Convert text to speech using ElevenLabs, returns mu-law audio."""
    if not settings.ELEVENLABS_API_KEY:
        logger.warning("ElevenLabs API key not set")
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{settings.ELEVENLABS_VOICE_ID}",
                headers={
                    "xi-api-key": settings.ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_turbo_v2_5",
                    "output_format": "ulaw_8000",  # mu-law for Twilio
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                        "speed": 1.0,
                    },
                },
            )

            if resp.status_code == 200:
                return resp.content
            else:
                logger.error(f"ElevenLabs error: {resp.status_code} {resp.text[:200]}")
                return None

    except Exception as e:
        logger.error(f"TTS error: {e}")
        return None


# Need httpx for API calls
import httpx

try:
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
