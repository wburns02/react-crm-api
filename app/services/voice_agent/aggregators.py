"""Fragment merger for Deepgram STT output.

Deepgram occasionally finalizes mid-thought utterances (especially over a
flaky cell connection): "the foam", "in regards to the", "and also". Treating
each as a turn fires the agent reply prematurely. This merger holds short
non-question fragments and concatenates them with the next utterance.
"""
from dataclasses import dataclass


# A short utterance has fewer than 4 words (i.e. 1-3 words). Combined with the
# duration check below this catches "the foam", "and also the", "in regards to"
# style fragments while letting genuine short turns ("yes that's right") through
# on duration alone.
_MIN_WORDS = 4
_MIN_DURATION_MS = 800


@dataclass
class FragmentMerger:
    _buffer: str = ""

    def consume(self, *, text: str, duration_ms: float) -> str | None:
        """Decide whether to emit `text` as a turn or hold it as a fragment.

        Returns the emitted turn text (possibly merged with prior buffer),
        or None if held.
        """
        text = text.strip()
        if not text:
            return None

        is_fragment = (
            self._is_short(text)
            and duration_ms < _MIN_DURATION_MS
            and not text.endswith("?")
        )

        if is_fragment:
            self._buffer = (self._buffer + " " + text).strip() if self._buffer else text
            return None

        if self._buffer:
            merged = (self._buffer + " " + text).strip()
            self._buffer = ""
            return merged

        return text

    def has_buffered(self) -> bool:
        return bool(self._buffer)

    def flush_if_stale(
        self,
        *,
        now_ms: float,
        last_buffer_at_ms: float,
        stale_after_ms: float,
    ) -> str | None:
        """Flush a buffered fragment as its own turn if it has aged out."""
        if not self._buffer:
            return None
        if now_ms - last_buffer_at_ms < stale_after_ms:
            return None
        flushed = self._buffer
        self._buffer = ""
        return flushed

    @staticmethod
    def _is_short(text: str) -> bool:
        return len(text.split()) < _MIN_WORDS
