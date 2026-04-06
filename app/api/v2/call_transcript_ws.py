"""
WebSocket endpoints for real-time call transcription.

Three WebSocket paths (mounted at app root, NOT under /api/v2):
1. /ws/call-transcript/{call_sid}     -- Frontend connects here to receive transcripts
2. /ws/twilio-media/{call_sid}        -- Twilio Media Streams sends audio here
3. /ws/ringcentral-audio/{call_id}    -- Frontend sends RingCentral WebRTC audio here
"""

import asyncio
import base64
import json
import logging
import re

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.services.call_transcript_manager import transcript_manager
from app.services import google_stt_service
from app.services.google_stt_service import GoogleSTTStreamer
from app.services.location_extractor import LocationExtractor, haversine_distance, estimate_drive_minutes
from app.services.market_config import get_market_by_area_code, get_zone
from app.database import async_session_maker
from app.models.customer import Customer

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
    location_extractor: LocationExtractor | None = None

    try:
        if google_stt_service.is_available():
            async def on_transcript(text: str, is_final: bool):
                await transcript_manager.broadcast_transcript(
                    call_sid=call_sid,
                    text=text,
                    is_final=is_final,
                    speaker="customer",
                )
                # Run location extraction on final transcript chunks
                if is_final and location_extractor:
                    try:
                        location = await asyncio.to_thread(
                            location_extractor.extract_location_from_text, text
                        )
                        if location:
                            await transcript_manager.broadcast_event(
                                call_sid, "location_detected", location
                            )
                    except Exception as e:
                        logger.warning("Location extraction failed for call %s: %s", call_sid, e)

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

                # Extract caller/called numbers from custom parameters
                custom_params = start_info.get("customParameters", {})
                caller_number = custom_params.get("caller_number", "")
                called_number = custom_params.get("called_number", "")
                logger.info(
                    "Twilio media call %s: caller=%s, called=%s",
                    call_sid, caller_number, called_number,
                )

                # Determine market from called number area code
                area_code = ""
                called_digits = re.sub(r"\D", "", called_number)
                if len(called_digits) >= 10:
                    area_code = called_digits[-10:][:3]
                elif len(called_digits) >= 3:
                    area_code = called_digits[:3]

                market = get_market_by_area_code(area_code)
                location_extractor = LocationExtractor(
                    call_sid=call_sid,
                    market_slug=market["slug"],
                )
                logger.info("Location extractor created for call %s, market=%s", call_sid, market["slug"])

                # Customer phone lookup — broadcast location immediately if customer has lat/lng
                if caller_number:
                    try:
                        async with async_session_maker() as db:
                            digits_only = re.sub(r"\D", "", caller_number)
                            if len(digits_only) > 10:
                                digits_only = digits_only[-10:]

                            result = await db.execute(
                                select(Customer).where(
                                    Customer.phone.ilike(f"%{digits_only[-10:]}%"),
                                    Customer.is_active == True,  # noqa: E712
                                ).limit(1)
                            )
                            customer = result.scalar_one_or_none()

                            if customer and customer.latitude and customer.longitude:
                                lat = float(customer.latitude)
                                lng = float(customer.longitude)
                                zone = get_zone(lat, lng, market["slug"])
                                center = market["center"]
                                dist = haversine_distance(center["lat"], center["lng"], lat, lng)
                                drive_min = estimate_drive_minutes(dist)

                                addr_parts = [
                                    customer.address_line1 or "",
                                    customer.city or "",
                                    customer.state or "",
                                ]
                                address_text = ", ".join(p for p in addr_parts if p)

                                location_data = {
                                    "lat": lat,
                                    "lng": lng,
                                    "source": "customer_record",
                                    "address_text": address_text,
                                    "zone": zone,
                                    "drive_minutes": drive_min,
                                    "customer_id": str(customer.id),
                                    "confidence": 0.95,
                                    "transcript_excerpt": "",
                                }
                                location_extractor.last_location = location_data
                                await transcript_manager.broadcast_event(
                                    call_sid, "location_detected", location_data
                                )
                                logger.info(
                                    "Customer location broadcast for call %s: %s",
                                    call_sid, address_text,
                                )
                    except Exception as e:
                        logger.warning("Customer lookup failed for call %s: %s", call_sid, e)

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

    # RingCentral WS doesn't carry caller/called numbers, so use default market.
    # Location extraction still works for transcript-detected city/address mentions.
    from app.services.market_config import DEFAULT_MARKET_SLUG
    rc_location_extractor = LocationExtractor(
        call_sid=call_id,
        market_slug=DEFAULT_MARKET_SLUG,
    )

    try:
        if google_stt_service.is_available():
            async def on_transcript(text: str, is_final: bool):
                await transcript_manager.broadcast_transcript(
                    call_sid=call_id,
                    text=text,
                    is_final=is_final,
                    speaker="customer",
                )
                # Run location extraction on final transcript chunks
                if is_final and rc_location_extractor:
                    try:
                        location = await asyncio.to_thread(
                            rc_location_extractor.extract_location_from_text, text
                        )
                        if location:
                            await transcript_manager.broadcast_event(
                                call_id, "location_detected", location
                            )
                    except Exception as e:
                        logger.warning("Location extraction failed for RC call %s: %s", call_id, e)

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
