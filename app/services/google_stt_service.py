"""
Google Cloud Speech-to-Text Streaming Service

Wraps Google STT streaming_recognize for real-time transcription of
Twilio Media Stream audio (mulaw/8000Hz).

Features:
- Async generator pattern for streaming audio chunks
- 5-minute session rotation (Google's streaming limit)
- Callback-based transcript delivery
"""

import asyncio
import base64
import json
import logging
import time
from typing import Callable, Awaitable

from app.config import settings

logger = logging.getLogger(__name__)

# Google STT streaming limit is ~5 minutes
MAX_STREAM_DURATION_SECONDS = 280  # rotate at 4m40s to be safe


class GoogleSTTService:
    """Manages a Google STT streaming session for one call."""

    def __init__(
        self,
        on_transcript: Callable[[str, bool], Awaitable[None]],
        language: str | None = None,
    ):
        self.on_transcript = on_transcript
        self.language = language or settings.GOOGLE_STT_LANGUAGE
        self._client = None
        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._stream_task: asyncio.Task | None = None
        self._running = False
        self._stream_start_time = 0.0

    async def _get_client(self):
        """Lazy-init the async STT client from credentials."""
        if self._client is not None:
            return self._client

        from google.cloud.speech_v1 import SpeechAsyncClient
        from google.oauth2 import service_account

        creds_raw = settings.GOOGLE_STT_CREDENTIALS_JSON
        if not creds_raw:
            raise RuntimeError("GOOGLE_STT_CREDENTIALS_JSON not configured")

        # Support both raw JSON and base64-encoded JSON
        try:
            creds_json = base64.b64decode(creds_raw).decode("utf-8")
        except Exception:
            creds_json = creds_raw

        creds_dict = json.loads(creds_json)
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        self._client = SpeechAsyncClient(credentials=credentials)
        return self._client

    async def start_stream(self):
        """Start the streaming recognition loop."""
        if self._running:
            return
        self._running = True
        self._stream_task = asyncio.create_task(self._stream_loop())
        logger.info("Google STT stream started")

    async def feed_audio(self, chunk: bytes):
        """Feed raw audio bytes (mulaw/8000Hz) into the stream."""
        if self._running:
            await self._audio_queue.put(chunk)

    async def stop_stream(self):
        """Stop the streaming recognition loop."""
        self._running = False
        # Signal the generator to stop
        await self._audio_queue.put(None)
        if self._stream_task:
            try:
                await asyncio.wait_for(self._stream_task, timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                self._stream_task.cancel()
            self._stream_task = None
        logger.info("Google STT stream stopped")

    async def _stream_loop(self):
        """Main loop that handles stream creation and 5-min rotation."""
        while self._running:
            try:
                await self._run_single_stream()
            except Exception as e:
                if not self._running:
                    break
                logger.warning("STT stream error, restarting in 1s: %s", e)
                await asyncio.sleep(1)

    async def _run_single_stream(self):
        """Run a single streaming_recognize session (up to ~5min)."""
        from google.cloud.speech_v1 import (
            StreamingRecognizeRequest,
            StreamingRecognitionConfig,
            RecognitionConfig,
        )

        client = await self._get_client()

        config = StreamingRecognitionConfig(
            config=RecognitionConfig(
                encoding=RecognitionConfig.AudioEncoding.MULAW,
                sample_rate_hertz=8000,
                language_code=self.language,
                enable_automatic_punctuation=True,
                model="phone_call",
                use_enhanced=True,
            ),
            interim_results=True,
            single_utterance=False,
        )

        self._stream_start_time = time.monotonic()

        async def request_generator():
            # First message must be config-only
            yield StreamingRecognizeRequest(streaming_config=config)

            while self._running:
                # Check rotation timer
                elapsed = time.monotonic() - self._stream_start_time
                if elapsed >= MAX_STREAM_DURATION_SECONDS:
                    logger.info("STT stream rotation after %.0fs", elapsed)
                    return

                try:
                    chunk = await asyncio.wait_for(self._audio_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                if chunk is None:
                    return

                yield StreamingRecognizeRequest(audio_content=chunk)

        try:
            responses = await client.streaming_recognize(
                requests=request_generator()
            )

            async for response in responses:
                if not self._running:
                    break
                for result in response.results:
                    transcript = result.alternatives[0].transcript if result.alternatives else ""
                    if transcript:
                        try:
                            await self.on_transcript(transcript, result.is_final)
                        except Exception as e:
                            logger.error("Transcript callback error: %s", e)
        except Exception as e:
            if self._running:
                raise
            logger.debug("STT stream ended: %s", e)
