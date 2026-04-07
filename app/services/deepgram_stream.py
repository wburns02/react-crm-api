"""
DeepgramStream — persistent WebSocket client for real-time STT via Deepgram.

Audio source: Twilio Media Streams (mu-law, 8 kHz, mono).
Model: nova-3 with utterance-end detection.

Usage:
    stream = DeepgramStream(
        on_transcript=lambda text, is_final: ...,
        on_utterance_end=lambda: ...,
    )
    await stream.connect()
    stream.send_audio(mulaw_bytes)   # non-blocking
    await stream.close()
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from app.config import settings

logger = logging.getLogger(__name__)

# Deepgram streaming endpoint
_DG_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-3"
    "&encoding=mulaw"
    "&sample_rate=8000"
    "&channels=1"
    "&interim_results=true"
    "&utterance_end_ms=1200"
    "&smart_format=true"
    "&no_delay=true"
)

# Type aliases for callback signatures (sync or async)
TranscriptCallback = Callable[[str, bool], Any]
UtteranceEndCallback = Callable[[], Any]


class DeepgramStream:
    """
    Manages a persistent WebSocket connection to Deepgram for real-time STT.

    Callbacks are invoked on the running event loop and may be either
    plain functions or coroutines.

    Args:
        on_transcript: Called with (text: str, is_final: bool) for every
                       Results message that contains a non-empty transcript.
        on_utterance_end: Called with no arguments when Deepgram signals
                          UtteranceEnd (i.e. the speaker stopped talking).
    """

    def __init__(
        self,
        on_transcript: TranscriptCallback | None = None,
        on_utterance_end: UtteranceEndCallback | None = None,
    ) -> None:
        self._on_transcript = on_transcript
        self._on_utterance_end = on_utterance_end

        self._ws: websockets.WebSocketClientProtocol | None = None
        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._send_task: asyncio.Task[None] | None = None
        self._recv_task: asyncio.Task[None] | None = None
        self._closed = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the WebSocket to Deepgram and start background I/O tasks."""
        if not settings.DEEPGRAM_API_KEY:
            raise RuntimeError(
                "DEEPGRAM_API_KEY is not configured in settings. "
                "Set the environment variable before using DeepgramStream."
            )

        headers = {"Authorization": f"Token {settings.DEEPGRAM_API_KEY}"}

        try:
            # websockets v12+ uses additional_headers; older versions use extra_headers
            try:
                self._ws = await websockets.connect(
                    _DG_URL,
                    additional_headers=headers,
                    ping_interval=20,
                    ping_timeout=10,
                )
            except TypeError:
                self._ws = await websockets.connect(
                    _DG_URL,
                    extra_headers=headers,
                    ping_interval=20,
                    ping_timeout=10,
                )
            logger.info("DeepgramStream: WebSocket connected")
        except Exception as exc:
            logger.error("DeepgramStream: failed to connect — %s", exc)
            raise

        self._closed = False
        loop = asyncio.get_event_loop()
        self._send_task = loop.create_task(self._audio_sender(), name="dg_audio_sender")
        self._recv_task = loop.create_task(self._message_receiver(), name="dg_msg_receiver")

    def send_audio(self, data: bytes) -> None:
        """
        Queue raw mu-law audio bytes for delivery to Deepgram.

        This method is non-blocking; audio is delivered by the background
        sender task.  Safe to call from sync or async code.
        """
        if self._closed:
            return
        try:
            self._audio_queue.put_nowait(data)
        except asyncio.QueueFull:
            logger.warning("DeepgramStream: audio queue full — dropping frame")

    async def close(self) -> None:
        """Send a CloseStream message, drain the queue, and close the WebSocket."""
        if self._closed:
            return
        self._closed = True

        # Signal sender task to stop
        await self._audio_queue.put(None)

        # Send Deepgram CloseStream control message
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
            except Exception as exc:
                logger.debug("DeepgramStream: error sending CloseStream — %s", exc)

        # Cancel background tasks
        for task in (self._send_task, self._recv_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        # Close underlying socket
        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception as exc:
                logger.debug("DeepgramStream: error closing WebSocket — %s", exc)

        logger.info("DeepgramStream: closed")

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    async def _audio_sender(self) -> None:
        """Drain the audio queue and forward bytes to Deepgram."""
        try:
            while not self._closed:
                chunk = await self._audio_queue.get()
                if chunk is None:
                    # Sentinel value — time to stop
                    break
                if self._ws and not self._ws.closed:
                    try:
                        await self._ws.send(chunk)
                    except ConnectionClosed:
                        logger.warning("DeepgramStream: connection closed while sending audio")
                        break
                    except Exception as exc:
                        logger.error("DeepgramStream: send error — %s", exc)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("DeepgramStream: _audio_sender unhandled error — %s", exc)

    async def _message_receiver(self) -> None:
        """Receive messages from Deepgram and invoke registered callbacks."""
        try:
            async for raw in self._ws:  # type: ignore[union-attr]
                if self._closed:
                    break
                try:
                    await self._handle_message(raw)
                except Exception as exc:
                    logger.error("DeepgramStream: error handling message — %s", exc)
        except ConnectionClosed as exc:
            if not self._closed:
                logger.warning("DeepgramStream: connection closed unexpectedly — %s", exc)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("DeepgramStream: _message_receiver unhandled error — %s", exc)

    async def _handle_message(self, raw: str | bytes) -> None:
        """Parse a single Deepgram message and fire the appropriate callback."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("DeepgramStream: non-JSON message received — %r", raw[:120])
            return

        msg_type = msg.get("type", "")

        if msg_type == "Results":
            await self._handle_results(msg)
        elif msg_type == "UtteranceEnd":
            await self._fire(self._on_utterance_end)
        elif msg_type == "Metadata":
            logger.debug("DeepgramStream: Metadata — %s", msg)
        elif msg_type == "Error":
            logger.error(
                "DeepgramStream: Deepgram error — code=%s description=%s",
                msg.get("error_code"),
                msg.get("description"),
            )
        else:
            logger.debug("DeepgramStream: unknown message type %r", msg_type)

    async def _handle_results(self, msg: dict[str, Any]) -> None:
        """Extract transcript text and is_final flag from a Results message."""
        try:
            channel = msg.get("channel", {})
            alternatives = channel.get("alternatives", [])
            if not alternatives:
                return

            transcript: str = alternatives[0].get("transcript", "").strip()
            if not transcript:
                return

            is_final: bool = msg.get("is_final", False)
            await self._fire(self._on_transcript, transcript, is_final)
        except (KeyError, IndexError, TypeError) as exc:
            logger.debug("DeepgramStream: could not parse Results — %s", exc)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    async def _fire(cb: Callable | None, *args: Any) -> None:
        """Call a callback (sync or coroutine) safely, ignoring None."""
        if cb is None:
            return
        try:
            result = cb(*args)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            logger.error("DeepgramStream: callback raised — %s", exc)
