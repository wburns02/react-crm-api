"""
Google Cloud Speech-to-Text streaming service for real-time call transcription.
Receives mu-law 8kHz audio from Twilio Media Streams and returns live transcripts.
"""

import asyncio
import base64
import json
import logging
from typing import Optional, Callable, Awaitable

from app.config import settings

logger = logging.getLogger(__name__)

# Google Cloud Speech imports are optional -- only needed when STT is enabled
try:
    from google.cloud import speech
    from google.oauth2 import service_account
    GOOGLE_SPEECH_AVAILABLE = True
except ImportError:
    GOOGLE_SPEECH_AVAILABLE = False
    logger.info("google-cloud-speech not installed. Real-time STT disabled.")


def is_available() -> bool:
    """Check if Google STT is configured and importable."""
    return (
        GOOGLE_SPEECH_AVAILABLE
        and settings.GOOGLE_STT_ENABLED
        and bool(settings.GOOGLE_STT_CREDENTIALS_JSON)
    )


def _build_credentials():
    """Build Google credentials from base64-encoded or raw JSON env var."""
    if not settings.GOOGLE_STT_CREDENTIALS_JSON:
        raise RuntimeError("GOOGLE_STT_CREDENTIALS_JSON not set")

    raw = settings.GOOGLE_STT_CREDENTIALS_JSON
    # Support both raw JSON and base64-encoded JSON
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        decoded = base64.b64decode(raw)
        info = json.loads(decoded)

    return service_account.Credentials.from_service_account_info(info)


class GoogleSTTStreamer:
    """
    Manages a single streaming recognition session.
    Receives raw audio bytes and invokes a callback with transcript results.

    Usage:
        streamer = GoogleSTTStreamer(on_transcript=my_callback)
        await streamer.start()
        streamer.feed_audio(audio_bytes)  # call repeatedly
        await streamer.stop()
    """

    # Google imposes a ~5 min limit on streaming sessions.
    # Reconnect proactively at 4 min 50 sec to avoid abrupt cutoff.
    _RECONNECT_SECONDS = 290

    def __init__(
        self,
        on_transcript: Callable[[str, bool], Awaitable[None]],
        language_code: Optional[str] = None,
    ):
        """
        Args:
            on_transcript: async callback(text, is_final) invoked for each result.
            language_code: BCP-47 language code, defaults to config value.
        """
        self._on_transcript = on_transcript
        self._language_code = language_code or settings.GOOGLE_STT_LANGUAGE_CODE
        self._audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Begin the streaming recognition loop."""
        if not is_available():
            logger.warning("Google STT not available -- skipping start")
            return
        self._running = True
        self._task = asyncio.create_task(self._recognition_loop())
        logger.info("Google STT streamer started")

    def feed_audio(self, audio_bytes: bytes):
        """Feed raw mu-law audio bytes into the recognition stream."""
        if self._running:
            try:
                self._audio_queue.put_nowait(audio_bytes)
            except asyncio.QueueFull:
                pass  # drop frame rather than block

    async def stop(self):
        """Stop the recognition loop and clean up."""
        self._running = False
        # Signal the generator to stop
        await self._audio_queue.put(None)
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Google STT streamer stopped")

    async def _recognition_loop(self):
        """Main loop: create streaming sessions, auto-reconnect on timeout."""
        credentials = _build_credentials()

        while self._running:
            try:
                client = speech.SpeechAsyncClient(credentials=credentials)

                config = speech.RecognitionConfig(
                    encoding=speech.RecognitionConfig.AudioEncoding.MULAW,
                    sample_rate_hertz=8000,
                    language_code=self._language_code,
                    enable_automatic_punctuation=True,
                    model="telephony",
                )
                streaming_config = speech.StreamingRecognitionConfig(
                    config=config,
                    interim_results=True,
                )

                logger.debug("Starting new STT streaming session")

                async def request_generator():
                    # First message: config only
                    yield speech.StreamingRecognizeRequest(
                        streaming_config=streaming_config
                    )
                    # Subsequent messages: audio content
                    deadline = asyncio.get_event_loop().time() + self._RECONNECT_SECONDS
                    while self._running:
                        if asyncio.get_event_loop().time() >= deadline:
                            logger.debug("STT session approaching time limit, reconnecting")
                            return
                        try:
                            chunk = await asyncio.wait_for(
                                self._audio_queue.get(), timeout=1.0
                            )
                        except asyncio.TimeoutError:
                            continue
                        if chunk is None:
                            return
                        yield speech.StreamingRecognizeRequest(audio_content=chunk)

                responses = await client.streaming_recognize(
                    requests=request_generator()
                )

                async for response in responses:
                    if not self._running:
                        break
                    for result in response.results:
                        transcript = result.alternatives[0].transcript
                        is_final = result.is_final
                        try:
                            await self._on_transcript(transcript, is_final)
                        except Exception as cb_err:
                            logger.error(f"Transcript callback error: {cb_err}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.error(f"STT streaming error: {e}")
                    await asyncio.sleep(1)  # brief pause before reconnect
                else:
                    break

        logger.debug("STT recognition loop exited")
