"""
API endpoints for the AI Outbound Sales Agent.

Handles:
- Campaign management (start/stop/pause/status)
- Twilio voice webhook (TwiML for media streams)
- Twilio status callback
- Media stream WebSocket (audio in/out, streaming STT with barge-in)
- Live transcript SSE endpoint
- Call persistence to CallLog
"""

import asyncio
import base64
import json
import logging
import uuid
from datetime import datetime, date
from typing import Optional

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Response, Depends
from fastapi.responses import PlainTextResponse, StreamingResponse

from app.config import settings
from app.database import async_session_maker
from app.models.call_log import CallLog
from app.services.deepgram_stream import DeepgramStream
from app.services.outbound_agent import OutboundAgentSession
from app.services.campaign_dialer import (
    campaign, active_sessions, start_campaign, stop_campaign,
    pause_campaign, resume_campaign, get_prospect_queue,
    get_pending_call_data, remove_pending_call_data,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outbound-agent", tags=["outbound-agent"])


# ── Live Transcript Pub/Sub ────────────────────────────────────────

_transcript_listeners: dict[str, list[asyncio.Queue]] = {}


def _broadcast_transcript(call_sid: str, speaker: str, text: str) -> None:
    """Push a transcript line to all SSE subscribers for this call."""
    listeners = _transcript_listeners.get(call_sid)
    if not listeners:
        return
    payload = {"call_sid": call_sid, "speaker": speaker, "text": text, "ts": datetime.utcnow().isoformat()}
    for q in listeners:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


def _subscribe_transcript(call_sid: str) -> asyncio.Queue:
    """Register a new SSE subscriber for this call. Returns its queue."""
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _transcript_listeners.setdefault(call_sid, []).append(q)
    return q


def _unsubscribe_transcript(call_sid: str, q: asyncio.Queue) -> None:
    """Remove a subscriber queue."""
    listeners = _transcript_listeners.get(call_sid)
    if listeners:
        try:
            listeners.remove(q)
        except ValueError:
            pass
        if not listeners:
            _transcript_listeners.pop(call_sid, None)


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


# ── Live Transcript SSE ────────────────────────────────────────────

@router.get("/live-transcript/{call_sid}")
async def api_live_transcript(call_sid: str):
    """
    Server-Sent Events stream for the live call transcript.

    Yields data: {json}\\n\\n lines for each transcript event.
    Sends a keepalive comment every 30 seconds.
    """
    q = _subscribe_transcript(call_sid)

    async def event_generator():
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # keepalive
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _unsubscribe_transcript(call_sid, q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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
        logger.info(f"Voicemail detected for {to_number} — starting media stream for Cartesia TTS voicemail")

        # Start a media stream so we can use Cartesia TTS for the voicemail
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

        # Create a voicemail session flagged so the WS handler knows to leave a message
        prospect = call_data["prospect"]
        quote = call_data["quote"]

        session = OutboundAgentSession(
            call_sid=call_sid,
            prospect=prospect,
            quote=quote,
        )
        session._voicemail_mode = True
        active_sessions[call_sid] = session

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
    Sends mu-law 8kHz audio back (agent speech via Cartesia/ElevenLabs TTS).

    Uses streaming Deepgram STT with barge-in support:
    - Interim results accumulate in pending_speech
    - Final results trigger session.handle_speech()
    - If agent is speaking and a final transcript arrives, audio is cancelled
    """
    await websocket.accept()
    logger.info(f"Outbound agent media stream connected: {call_sid}")

    session = active_sessions.get(call_sid)
    if not session:
        logger.warning(f"No session found for {call_sid}")
        await websocket.close()
        return

    stream_sid: Optional[str] = None

    # Barge-in state
    agent_is_speaking = False
    tts_cancel: asyncio.Event = asyncio.Event()

    # Streaming STT state
    pending_speech = ""

    # ── Deepgram callbacks ──────────────────────────────────────────

    async def on_transcript(text: str, is_final: bool) -> None:
        nonlocal pending_speech, agent_is_speaking, stream_sid

        if is_final:
            full_text = (pending_speech + " " + text).strip()
            pending_speech = ""

            if full_text:
                # Barge-in: cancel agent TTS if speaking
                if agent_is_speaking:
                    logger.info(f"[Agent:{call_sid[:8]}] Barge-in detected — cancelling TTS")
                    agent_is_speaking = False
                    tts_cancel.set()
                    # Flush Twilio audio buffer
                    if stream_sid:
                        try:
                            clear_msg = json.dumps({"event": "clear", "streamSid": stream_sid})
                            await websocket.send_text(clear_msg)
                        except Exception as e:
                            logger.warning(f"Failed to send clear message: {e}")

                # Broadcast customer speech to SSE listeners
                _broadcast_transcript(call_sid, "customer", full_text)

                # Send to agent conversation engine
                await session.handle_speech(full_text)
        else:
            # Accumulate interim results
            pending_speech = (pending_speech + " " + text).strip()

    async def on_utterance_end() -> None:
        """Flush any pending interim speech when Deepgram signals end of utterance."""
        nonlocal pending_speech

        if pending_speech.strip():
            flushed = pending_speech.strip()
            pending_speech = ""
            logger.info(f"[Agent:{call_sid[:8]}] Utterance-end flush: {flushed!r}")

            if agent_is_speaking:
                pass  # Don't interrupt for flush — final transcript handles barge-in

            _broadcast_transcript(call_sid, "customer", flushed)
            await session.handle_speech(flushed)

    # ── TTS speak callback ──────────────────────────────────────────

    async def speak(text: str) -> None:
        """Convert text to speech and send to Twilio in 400ms chunks, respecting barge-in."""
        nonlocal agent_is_speaking, stream_sid

        if not stream_sid:
            return

        # Broadcast agent speech to SSE listeners
        _broadcast_transcript(call_sid, "agent", text)

        try:
            audio_data = await _text_to_speech(text)
            if not audio_data:
                return

            agent_is_speaking = True
            tts_cancel.clear()

            # Send audio in 3200-byte chunks (~400ms of mu-law 8kHz audio)
            chunk_size = 3200
            offset = 0
            while offset < len(audio_data):
                # Check for barge-in cancellation between chunks
                if tts_cancel.is_set():
                    logger.info(f"[Agent:{call_sid[:8]}] TTS cancelled mid-stream (barge-in)")
                    break

                chunk = audio_data[offset:offset + chunk_size]
                offset += chunk_size

                payload = base64.b64encode(chunk).decode()
                media_msg = json.dumps({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload}
                })
                try:
                    await websocket.send_text(media_msg)
                except Exception as e:
                    logger.error(f"TTS send error: {e}")
                    break

                # 50ms pacing between chunks
                await asyncio.sleep(0.05)

        except Exception as e:
            logger.error(f"TTS/speak error: {e}")
        finally:
            if not tts_cancel.is_set():
                agent_is_speaking = False

    # ── Other session callbacks ─────────────────────────────────────

    async def end_call() -> None:
        """Signal Twilio to end the call."""
        try:
            if TWILIO_AVAILABLE and settings.TWILIO_ACCOUNT_SID:
                from twilio.rest import Client
                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                client.calls(call_sid).update(status="completed")
        except Exception as e:
            logger.error(f"Failed to end call {call_sid}: {e}")

    async def transfer(number: str) -> None:
        """Transfer the call."""
        try:
            if TWILIO_AVAILABLE and settings.TWILIO_ACCOUNT_SID:
                from twilio.rest import Client
                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                twiml = f'<Response><Dial>{number}</Dial></Response>'
                client.calls(call_sid).update(twiml=twiml)
        except Exception as e:
            logger.error(f"Failed to transfer call {call_sid}: {e}")

    session.on_speak = speak
    session.on_end_call = end_call
    session.on_transfer = transfer

    # ── Connect Deepgram streaming STT ─────────────────────────────

    dg = DeepgramStream(
        on_transcript=on_transcript,
        on_utterance_end=on_utterance_end,
    )

    try:
        await dg.connect()
    except Exception as e:
        logger.error(f"Failed to connect Deepgram for {call_sid}: {e}")
        await websocket.close()
        return

    # ── Main WebSocket loop ─────────────────────────────────────────

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

                if getattr(session, '_voicemail_mode', False):
                    # Voicemail path: wait for beep, then speak via Cartesia TTS
                    await asyncio.sleep(2)  # Wait for the voicemail beep
                    p = session.prospect
                    q = session.quote
                    line_items = q.get("line_items", [])
                    service = line_items[0].get("service", "septic service") if line_items else "septic service"
                    vm_text = (
                        f"Hi {p.get('first_name', '')}, this is MAC Septic following up "
                        f"on the estimate we sent for {service} at your property. "
                        f"Give us a call back at 615-345-2544 when you get a chance. Thanks!"
                    )
                    logger.info(f"[Agent:{call_sid[:8]}] Leaving voicemail: {vm_text!r}")
                    await speak(vm_text)
                    session.disposition = "voicemail_left"
                    session.transcript.append({
                        "speaker": "agent",
                        "text": vm_text,
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    await asyncio.sleep(2)  # Let audio finish before hanging up
                    await end_call()
                else:
                    # Normal human-answered path: send greeting after brief pause
                    await asyncio.sleep(1)
                    await session.start_greeting()

            elif event == "media":
                # Receive customer audio (mu-law 8kHz) and stream to Deepgram
                payload = msg.get("media", {}).get("payload", "")
                if payload:
                    audio_bytes = base64.b64decode(payload)
                    dg.send_audio(audio_bytes)

            elif event == "stop":
                logger.info(f"Media stream stopped for {call_sid}")
                break

    except WebSocketDisconnect:
        logger.info(f"Media stream disconnected for {call_sid}")
    except Exception as e:
        logger.error(f"Media stream error for {call_sid}: {e}")
    finally:
        # Shut down Deepgram
        try:
            await dg.close()
        except Exception as e:
            logger.warning(f"Deepgram close error for {call_sid}: {e}")

        session.ended = True
        summary = session.get_summary()
        logger.info(f"Call {call_sid} ended. Disposition: {summary['disposition']}")

        # Persist call to database
        try:
            await _persist_call(session)
        except Exception as e:
            logger.error(f"Failed to persist call {call_sid}: {e}")

        # Clean up SSE listeners
        _transcript_listeners.pop(call_sid, None)


# ── Call Persistence ───────────────────────────────────────────────

async def _generate_call_summary(session: OutboundAgentSession) -> Optional[str]:
    """Generate a 2-3 sentence AI summary of the call using Claude Haiku."""
    if not settings.ANTHROPIC_API_KEY:
        return None
    if not session.transcript:
        return None

    transcript_text = "\n".join(
        f"{t['speaker'].upper()}: {t['text']}"
        for t in session.transcript
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 200,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "Summarize this outbound sales call in 2-3 sentences. "
                                "Include the outcome and any next steps.\n\n"
                                f"{transcript_text}"
                            ),
                        }
                    ],
                },
            )

        if resp.status_code == 200:
            data = resp.json()
            blocks = data.get("content", [])
            parts = [b["text"] for b in blocks if b.get("type") == "text"]
            return " ".join(parts).strip() or None
        else:
            logger.warning(f"Claude summary error: {resp.status_code}")
            return None

    except Exception as e:
        logger.warning(f"_generate_call_summary error: {e}")
        return None


async def _persist_call(session: OutboundAgentSession) -> None:
    """Save the completed call to the call_logs table."""
    p = session.prospect

    # Build timestamped transcript string  [MM:SS] Speaker: text
    lines = []
    for entry in session.transcript:
        ts_str = entry.get("timestamp", "")
        speaker = entry.get("speaker", "unknown")
        text = entry.get("text", "")
        try:
            ts_dt = datetime.fromisoformat(ts_str)
            elapsed = (ts_dt - session.started_at).total_seconds()
            elapsed = max(0, elapsed)
            mm = int(elapsed // 60)
            ss = int(elapsed % 60)
            time_label = f"[{mm:02d}:{ss:02d}]"
        except (ValueError, TypeError):
            time_label = "[??:??]"
        lines.append(f"{time_label} {speaker.upper()}: {text}")

    transcript_text = "\n".join(lines)
    duration = int((datetime.utcnow() - session.started_at).total_seconds())

    # Infer sentiment from disposition
    positive_dispositions = {"appointment_set", "callback_requested"}
    negative_dispositions = {"not_interested", "service_completed_elsewhere", "do_not_call"}
    disp = session.disposition or ""
    if disp in positive_dispositions:
        sentiment = "positive"
    elif disp in negative_dispositions:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    # Generate AI summary
    ai_summary = await _generate_call_summary(session)

    # Resolve customer_id
    customer_id_raw = p.get("id")
    customer_uuid = None
    if customer_id_raw:
        try:
            customer_uuid = uuid.UUID(str(customer_id_raw))
        except (ValueError, TypeError):
            pass

    # Caller/called numbers
    caller_number = settings.OUTBOUND_AGENT_FROM_NUMBER or settings.TWILIO_PHONE_NUMBER or ""
    called_number = p.get("phone", "")

    # Recording URL from session if set
    recording_url = getattr(session, "_recording_url", None)

    now = datetime.utcnow()

    try:
        async with async_session_maker() as db:
            call_log = CallLog(
                id=uuid.uuid4(),
                direction="outbound",
                call_type="voice",
                caller_number=caller_number,
                called_number=called_number,
                customer_id=customer_uuid,
                call_disposition=disp or "unknown",
                call_date=now.date(),
                call_time=now.time(),
                duration_seconds=duration,
                recording_url=recording_url,
                transcription=transcript_text,
                transcription_status="completed" if transcript_text else "failed",
                ai_summary=ai_summary,
                sentiment=sentiment,
                notes=session.disposition_notes or "",
                assigned_to="ai_outbound_agent",
                external_system="outbound_agent",
                user_id="1",
            )
            db.add(call_log)
            await db.commit()
            logger.info(f"Call {session.call_sid} persisted to call_logs (duration={duration}s, disposition={disp})")
    except Exception as e:
        logger.error(f"_persist_call DB error for {session.call_sid}: {e}")
        raise


# ── STT (legacy batch — kept for potential fallback use) ───────────

async def _speech_to_text(audio_bytes: bytes) -> Optional[str]:
    """Transcribe mu-law audio using Deepgram Nova-3 (batch mode)."""
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


# ── TTS (Cartesia Sonic) ───────────────────────────────────────────

async def _text_to_speech(text: str) -> Optional[bytes]:
    """Convert text to speech using Cartesia Sonic, returns mu-law audio for Twilio."""
    if settings.TTS_PROVIDER == "cartesia":
        return await _cartesia_tts(text)
    elif settings.TTS_PROVIDER == "elevenlabs":
        return await _elevenlabs_tts(text)
    else:
        logger.error(f"Unknown TTS provider: {settings.TTS_PROVIDER}")
        return None


async def _cartesia_tts(text: str) -> Optional[bytes]:
    """Cartesia Sonic TTS — fast, cheap, great quality."""
    if not settings.CARTESIA_API_KEY:
        logger.warning("CARTESIA_API_KEY not set")
        return None

    voice_id = settings.CARTESIA_VOICE_ID or "a0e99841-438c-4a64-b679-ae501e7d6091"  # Default: Barbershop Man

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.cartesia.ai/tts/bytes",
                headers={
                    "X-API-Key": settings.CARTESIA_API_KEY,
                    "Cartesia-Version": "2025-04-16",
                    "Content-Type": "application/json",
                },
                json={
                    "model_id": "sonic-3",
                    "transcript": text,
                    "voice": {"mode": "id", "id": voice_id},
                    "output_format": {
                        "container": "raw",
                        "encoding": "pcm_mulaw",
                        "sample_rate": 8000,
                    },
                    "language": "en",
                    "speed": "normal",
                },
            )

            if resp.status_code == 200:
                return resp.content
            else:
                logger.error(f"Cartesia error: {resp.status_code} {resp.text[:200]}")
                return None

    except Exception as e:
        logger.error(f"Cartesia TTS error: {e}")
        return None


async def _elevenlabs_tts(text: str) -> Optional[bytes]:
    """ElevenLabs TTS fallback."""
    if not settings.ELEVENLABS_API_KEY:
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
                    "output_format": "ulaw_8000",
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
        logger.error(f"ElevenLabs TTS error: {e}")
        return None


try:
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
# Outbound agent v2.0 — streaming STT + barge-in + call persistence + live transcript SSE
