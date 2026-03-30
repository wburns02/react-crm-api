"""
WebSocket endpoints for real-time call transcription.

Three WebSocket paths (mounted at app root, NOT under /api/v2):
1. /ws/call-transcript/{call_sid}     -- Frontend connects here to receive transcripts
2. /ws/twilio-media/{call_sid}        -- Twilio Media Streams sends audio here
3. /ws/ringcentral-audio/{call_id}    -- Frontend sends RingCentral WebRTC audio here
"""

import base64
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.call_transcript_manager import transcript_manager
from app.services import google_stt_service
from app.services.google_stt_service import GoogleSTTStreamer

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------
# 1. Frontend WebSocket -- browser connects to receive transcript entries
# --------------------------------------------------------------------------

@router.websocket("/ws/call-transcript/{call_sid}")
async def ws_call_transcript(websocket: WebSocket, call_sid: str):
    """
    Frontend clients connect here to receive real-time transcripts.
    Sends JSON messages matching TranscriptEntry:
      { speaker: "customer", text: "...", isFinal: bool, timestamp: "..." }
    """
    await websocket.accept()
    await transcript_manager.connect(call_sid, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except (json.JSONDecodeError, TypeError):
                pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Frontend transcript WS error for call {call_sid}: {e}")
    finally:
        await transcript_manager.disconnect(call_sid, websocket)


# --------------------------------------------------------------------------
# 2. Twilio Media Stream WebSocket -- receives raw audio, feeds to STT
# --------------------------------------------------------------------------

@router.websocket("/ws/twilio-media/{call_sid}")
async def ws_twilio_media(websocket: WebSocket, call_sid: str):
    """
    Twilio Media Streams WebSocket endpoint.
    Receives mu-law 8kHz audio and pipes it to Google STT.
    Transcription results are broadcast to frontend listeners.
    """
    await websocket.accept()
    logger.info(f"Twilio media stream connected for call {call_sid}")

    streamer = None

    try:
        if google_stt_service.is_available():
            async def on_transcript(text: str, is_final: bool):
                await transcript_manager.broadcast_transcript(
                    call_sid=call_sid,
                    text=text,
                    is_final=is_final,
                    speaker="customer",
                )

            streamer = GoogleSTTStreamer(on_transcript=on_transcript)
            await streamer.start()
            logger.info(f"Google STT started for call {call_sid}")
        else:
            logger.warning(
                f"Google STT not available for call {call_sid}. "
                f"Installed={google_stt_service.GOOGLE_SPEECH_AVAILABLE}, "
                f"Enabled={google_stt_service.settings.GOOGLE_STT_ENABLED}, "
                f"Creds={'set' if google_stt_service.settings.GOOGLE_STT_CREDENTIALS_JSON else 'missing'}"
            )

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event = msg.get("event")

            if event == "connected":
                logger.info(f"Twilio media event=connected: streamSid={msg.get('streamSid', 'unknown')}")

            elif event == "start":
                start_info = msg.get("start", {})
                logger.info(
                    f"Twilio media event=start for call {call_sid}: "
                    f"tracks={start_info.get('tracks', [])}"
                )

            elif event == "media":
                payload = msg.get("media", {}).get("payload", "")
                if payload and streamer:
                    audio_bytes = base64.b64decode(payload)
                    streamer.feed_audio(audio_bytes)

            elif event == "stop":
                logger.info(f"Twilio media event=stop for call {call_sid}")
                break

    except WebSocketDisconnect:
        logger.info(f"Twilio media stream disconnected for call {call_sid}")
    except Exception as e:
        logger.error(f"Twilio media stream error for call {call_sid}: {e}")
    finally:
        if streamer:
            await streamer.stop()
        logger.info(f"Twilio media stream cleanup complete for call {call_sid}")


# --------------------------------------------------------------------------
# 3. RingCentral Audio WebSocket -- receives PCM audio from browser WebRTC
# --------------------------------------------------------------------------

@router.websocket("/ws/ringcentral-audio/{call_id}")
async def ws_ringcentral_audio(websocket: WebSocket, call_id: str):
    """
    Receives raw Linear16 PCM audio (16kHz, mono) from the browser.
    The frontend captures RingCentral WebRTC remote audio via AudioContext
    and sends Int16 PCM binary frames here.

    Transcription results are broadcast to /ws/call-transcript/{call_id}.
    """
    await websocket.accept()
    logger.info(f"RingCentral audio stream connected for call {call_id}")

    streamer = None

    try:
        if google_stt_service.is_available():
            async def on_transcript(text: str, is_final: bool):
                await transcript_manager.broadcast_transcript(
                    call_sid=call_id,
                    text=text,
                    is_final=is_final,
                    speaker="customer",
                )

            streamer = GoogleSTTStreamer(
                on_transcript=on_transcript,
                encoding="LINEAR16",
                sample_rate=16000,
            )
            await streamer.start()
            logger.info(f"Google STT (LINEAR16/16kHz) started for RC call {call_id}")
        else:
            logger.warning(
                f"Google STT not available for RC call {call_id}. "
                f"Installed={google_stt_service.GOOGLE_SPEECH_AVAILABLE}, "
                f"Enabled={google_stt_service.settings.GOOGLE_STT_ENABLED}, "
                f"Creds={'set' if google_stt_service.settings.GOOGLE_STT_CREDENTIALS_JSON else 'missing'}"
            )

        while True:
            # Receive binary PCM audio frames
            audio_bytes = await websocket.receive_bytes()
            if streamer and audio_bytes:
                streamer.feed_audio(audio_bytes)

    except WebSocketDisconnect:
        logger.info(f"RingCentral audio stream disconnected for call {call_id}")
    except Exception as e:
        logger.error(f"RingCentral audio stream error for call {call_id}: {e}")
    finally:
        if streamer:
            await streamer.stop()
        logger.info(f"RingCentral audio stream cleanup complete for call {call_id}")
