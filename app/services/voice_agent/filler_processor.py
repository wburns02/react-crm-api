"""Pipecat processor that masks LLM first-token latency with quick filler audio.

When the user stops speaking, this processor schedules a brief filler TTS
("Mhm…", "One sec…", "Got it…") to fire after a short delay. If the bot
starts producing real audio before the delay elapses (i.e., the LLM was
fast), the filler is cancelled. If the LLM is slow, the customer hears the
filler and never sits in dead air.

Place between ``user_aggregator`` and ``llm`` in the pipeline. The filler
rides the same TTS path as normal responses (``TTSSpeakFrame``), so it
goes through Cartesia and the TwilioFrameSerializer just like everything else.
"""
import asyncio
import logging
import random

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    TTSSpeakFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


logger = logging.getLogger(__name__)


# Default filler set — mix of acknowledgments and "thinking" cues.
# Keep them tiny so they don't step on the actual response when the LLM is fast.
DEFAULT_FILLERS = (
    "Mhm…",
    "One sec…",
    "Got it…",
    "Sure thing…",
    "Yeah, let me check…",
    "Hmm, one moment…",
)


class FillerProcessor(FrameProcessor):
    """Pushes a quick filler TTS frame to mask LLM first-token latency."""

    def __init__(
        self,
        *,
        fillers: tuple[str, ...] = DEFAULT_FILLERS,
        delay_ms: int = 400,
    ):
        super().__init__()
        self._fillers = fillers
        self._delay_s = delay_ms / 1000.0
        self._bot_speaking = False
        self._pending_filler: asyncio.Task | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStoppedSpeakingFrame):
            self._cancel_pending()
            # Schedule a filler if the bot doesn't start talking on its own
            # within the delay window.
            self._pending_filler = asyncio.create_task(self._fire_after_delay())

        elif isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
            self._cancel_pending()

        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False

        # Always pass through.
        await self.push_frame(frame, direction)

    async def _fire_after_delay(self) -> None:
        try:
            await asyncio.sleep(self._delay_s)
            if self._bot_speaking:
                return
            filler = random.choice(self._fillers)
            logger.info(f"[FillerProcessor] firing filler: {filler!r}")
            await self.push_frame(TTSSpeakFrame(text=filler), FrameDirection.DOWNSTREAM)
        except asyncio.CancelledError:
            return

    def _cancel_pending(self) -> None:
        if self._pending_filler and not self._pending_filler.done():
            self._pending_filler.cancel()
            self._pending_filler = None
