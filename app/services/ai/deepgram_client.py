"""Thin async wrapper around deepgram-sdk for pre-recorded transcription.

Used by the call/voicemail leg of the AI Interaction Analyzer worker. Streaming
STT (Twilio Media Streams) lives elsewhere in the codebase and is out of scope
here — this client only handles pre-recorded URL transcription.

Model: nova-3 (per spec).

Compatible with deepgram-sdk >= 3.0 (covers both the legacy v3.x prerecorded
namespace and the v6.x AsyncDeepgramClient.listen.v1.media surface).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deepgram import AsyncDeepgramClient


@dataclass
class TranscriptResult:
    transcript: str
    duration_seconds: int
    confidence: float
    raw: Any = None


class DeepgramTranscriptionClient:
    """Pre-recorded URL transcription via Deepgram Nova-3."""

    def __init__(self, api_key: str) -> None:
        if not api_key or not api_key.strip():
            raise ValueError(
                "DEEPGRAM_API_KEY is required. Set it via Railway env vars."
            )
        self._client = AsyncDeepgramClient(api_key=api_key)

    async def transcribe_url(self, audio_url: str) -> TranscriptResult:
        """Transcribe an audio file at a publicly accessible URL.

        Returns transcript text, duration in seconds, and confidence score
        from the first channel/alternative.
        """
        # SDK v6+ shape — keyword args directly, no PrerecordedOptions object.
        response = await self._client.listen.v1.media.transcribe_url(
            url=audio_url,
            model="nova-3",
            language="en-US",
            smart_format=True,
            diarize=True,
        )
        transcript, duration, confidence = self._extract(response)
        return TranscriptResult(
            transcript=transcript,
            duration_seconds=duration,
            confidence=confidence,
            raw=response,
        )

    @staticmethod
    def _extract(response: Any) -> tuple[str, int, float]:
        """Pull transcript / duration / confidence from a Deepgram response.

        Robust to both the v3.x and v6.x response shapes — both expose
        `results.channels[0].alternatives[0].{transcript,confidence}` and
        `metadata.duration`.
        """
        results = getattr(response, "results", None)
        metadata = getattr(response, "metadata", None)

        transcript = ""
        confidence = 0.0
        if results is not None:
            channels = getattr(results, "channels", None) or []
            if channels:
                alternatives = getattr(channels[0], "alternatives", None) or []
                if alternatives:
                    transcript = str(getattr(alternatives[0], "transcript", "") or "")
                    confidence = float(
                        getattr(alternatives[0], "confidence", 0.0) or 0.0
                    )

        duration = 0
        if metadata is not None:
            raw_duration = getattr(metadata, "duration", 0) or 0
            try:
                duration = int(round(float(raw_duration)))
            except (TypeError, ValueError):
                duration = 0

        return transcript, duration, confidence


__all__ = ["DeepgramTranscriptionClient", "TranscriptResult"]
