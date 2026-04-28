"""Anti-fragmentation aggregator merges short utterance fragments into coherent turns."""
import pytest

from app.services.voice_agent.aggregators import FragmentMerger


def test_pass_through_long_utterance():
    fm = FragmentMerger()
    out = fm.consume(text="I have a question about the inspection price.", duration_ms=2400)
    assert out == "I have a question about the inspection price."


def test_short_fragment_is_buffered_not_emitted():
    fm = FragmentMerger()
    out = fm.consume(text="the foam", duration_ms=400)
    assert out is None
    assert fm.has_buffered()


def test_buffered_fragment_merges_with_next():
    fm = FragmentMerger()
    fm.consume(text="the foam", duration_ms=400)
    out = fm.consume(text="the phone is breaking up", duration_ms=1800)
    assert out == "the foam the phone is breaking up"
    assert not fm.has_buffered()


def test_short_fragment_with_question_mark_emits_immediately():
    fm = FragmentMerger()
    out = fm.consume(text="really?", duration_ms=500)
    assert out == "really?"


def test_buffer_flushed_after_timeout():
    fm = FragmentMerger()
    fm.consume(text="seems like", duration_ms=600)
    flushed = fm.flush_if_stale(now_ms=10_000, last_buffer_at_ms=4_000, stale_after_ms=3_000)
    assert flushed == "seems like"
    assert not fm.has_buffered()


def test_buffer_not_flushed_when_fresh():
    fm = FragmentMerger()
    fm.consume(text="seems like", duration_ms=600)
    flushed = fm.flush_if_stale(now_ms=4_500, last_buffer_at_ms=4_000, stale_after_ms=3_000)
    assert flushed is None
    assert fm.has_buffered()


def test_three_word_short_duration_is_still_a_fragment():
    fm = FragmentMerger()
    out = fm.consume(text="and also the", duration_ms=600)
    assert out is None


def test_three_words_with_real_duration_passes_through():
    fm = FragmentMerger()
    out = fm.consume(text="and also the", duration_ms=1200)
    assert out == "and also the"
