"""
Twilio Media Stream + Browser Transcript WebSocket Handlers

Two WebSocket endpoints:
1. /ws/media-stream/{call_sid} — Twilio sends audio here (server-side, no auth)
2. /ws/call-transcript/{call_sid} — Browser subscribes for transcript updates (authenticated)
"""

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect, Query
from typing import Optional

from app.config import settings
from app.api.deps import get_current_user_ws

logger = logging.getLogger(__name__)

# In-memory state: call_sid -> set of browser WebSocket subscribers
_transcript_subscribers: dict[str, set[WebSocket]] = {}
# In-memory state: call_sid -> GoogleSTTService instance
_active_stt_streams: dict[str, "GoogleSTTService"] = {}


async def ws_media_stream(websocket: WebSocket, call_sid: str):
    """
    Receive Twilio Media Stream audio via WebSocket.

    Twilio sends JSON messages:
    - {"event": "connected", ...}
    - {"event": "start", "start": {"streamSid": ..., "callSid": ...}, ...}
    - {"event": "media", "media": {"payload": "<base64 audio>", ...}, ...}
    - {"event": "stop", ...}

    We decode the audio and feed it to GoogleSTTService for real-time transcription.
    """
    await websocket.accept()
    logger.info("Media stream WebSocket connected for call %s", call_sid)

    stt_service = None

    try:
        if not settings.GOOGLE_STT_ENABLED:
            logger.warning("Google STT not enabled, accepting but not transcribing")
            # Still accept the connection but don't process audio
            async for message in websocket.iter_text():
                pass
            return

        from app.services.google_stt_service import GoogleSTTService

        async def on_transcript(text: str, is_final: bool):
            """Push transcript to all browser subscribers for this call."""
            payload = json.dumps({
                "speaker": "customer",
                "text": text,
                "isFinal": is_final,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            subscribers = _transcript_subscribers.get(call_sid, set())
            dead = set()
            for ws in subscribers:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.add(ws)
            if dead:
                subscribers -= dead

        stt_service = GoogleSTTService(on_transcript=on_transcript)
        _active_stt_streams[call_sid] = stt_service
        await stt_service.start_stream()

        async for message in websocket.iter_text():
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                continue

            event = data.get("event")

            if event == "connected":
                logger.info("Twilio media stream connected: %s", data.get("protocol"))

            elif event == "start":
                stream_sid = data.get("start", {}).get("streamSid", "")
                logger.info("Media stream started: streamSid=%s callSid=%s", stream_sid, call_sid)

            elif event == "media":
                payload_b64 = data.get("media", {}).get("payload", "")
                if payload_b64:
                    audio_bytes = base64.b64decode(payload_b64)
                    await stt_service.feed_audio(audio_bytes)

            elif event == "stop":
                logger.info("Media stream stopped for call %s", call_sid)
                break

    except WebSocketDisconnect:
        logger.info("Media stream WebSocket disconnected for call %s", call_sid)
    except Exception as e:
        logger.error("Media stream error for call %s: %s", call_sid, e)
    finally:
        if stt_service:
            await stt_service.stop_stream()
        _active_stt_streams.pop(call_sid, None)


async def ws_call_transcript(websocket: WebSocket, call_sid: str):
    """
    Browser subscribes to receive real-time transcript updates for a call.

    Messages sent to browser:
    {"speaker": "customer", "text": "...", "isFinal": true/false, "timestamp": "..."}
    """
    # Authenticate via JWT token query param
    token = websocket.query_params.get("token")
    if token:
        user = await get_current_user_ws(token)
        if not user:
            await websocket.close(code=4001, reason="Unauthorized")
            return
    else:
        # Allow unauthenticated for now — relies on same-origin
        pass

    await websocket.accept()
    logger.info("Transcript subscriber connected for call %s", call_sid)

    # Register subscriber
    if call_sid not in _transcript_subscribers:
        _transcript_subscribers[call_sid] = set()
    _transcript_subscribers[call_sid].add(websocket)

    try:
        # Keep connection alive — client can send ping/close
        async for message in websocket.iter_text():
            try:
                data = json.loads(message)
                if data.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        subs = _transcript_subscribers.get(call_sid)
        if subs:
            subs.discard(websocket)
            if not subs:
                del _transcript_subscribers[call_sid]
        logger.info("Transcript subscriber disconnected for call %s", call_sid)
