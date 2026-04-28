"""State machine triggers forced actions when counters cross thresholds."""
import pytest

from app.services.voice_agent.state_machine import (
    SessionStateMachine,
    ForcedAction,
)


def test_no_action_in_normal_state():
    sm = SessionStateMachine()
    action = sm.tick(now_seconds=10, last_user_speech_at=8, agent_speaking=False)
    assert action is None


def test_audio_complaint_threshold_triggers_disposition():
    sm = SessionStateMachine()
    sm.note_audio_quality_complaint()
    assert sm.tick(now_seconds=10, last_user_speech_at=9, agent_speaking=False) is None
    sm.note_audio_quality_complaint()  # 2nd complaint = hard threshold
    action = sm.tick(now_seconds=20, last_user_speech_at=19, agent_speaking=False)
    assert action == ForcedAction.AUDIO_QUALITY_HANGUP


def test_silence_soft_then_hard():
    sm = SessionStateMachine()
    # Soft: silence >=8s after agent stops talking
    soft = sm.tick(now_seconds=20, last_user_speech_at=10, agent_speaking=False)
    assert soft == ForcedAction.SILENCE_SOFT_PROMPT
    # Subsequent ticks within the same silence window should not re-fire SOFT
    again = sm.tick(now_seconds=21, last_user_speech_at=10, agent_speaking=False)
    assert again is None
    # Hard: total silence >=15s
    hard = sm.tick(now_seconds=26, last_user_speech_at=10, agent_speaking=False)
    assert hard == ForcedAction.SILENCE_HANGUP


def test_silence_resets_when_user_speaks_again():
    sm = SessionStateMachine()
    sm.tick(now_seconds=20, last_user_speech_at=10, agent_speaking=False)  # soft fired
    sm.tick(now_seconds=22, last_user_speech_at=22, agent_speaking=False)  # user spoke
    assert sm.tick(now_seconds=30, last_user_speech_at=22, agent_speaking=False) == ForcedAction.SILENCE_SOFT_PROMPT


def test_two_tool_failures_in_a_row_trigger_transfer():
    sm = SessionStateMachine()
    sm.note_tool_call_result(success=True)
    sm.note_tool_call_result(success=False)
    sm.note_tool_call_result(success=False)
    action = sm.tick(now_seconds=30, last_user_speech_at=29, agent_speaking=False)
    assert action == ForcedAction.TRANSFER_ON_TOOL_FAILURES


def test_one_failure_then_success_does_not_trigger():
    sm = SessionStateMachine()
    sm.note_tool_call_result(success=False)
    sm.note_tool_call_result(success=True)
    sm.note_tool_call_result(success=False)
    assert sm.tick(now_seconds=30, last_user_speech_at=29, agent_speaking=False) is None


def test_total_call_seconds_soft_then_hard():
    sm = SessionStateMachine()
    soft = sm.tick(now_seconds=240, last_user_speech_at=239, agent_speaking=False)
    assert soft == ForcedAction.TIME_SOFT_WRAP
    hard = sm.tick(now_seconds=360, last_user_speech_at=359, agent_speaking=False)
    assert hard == ForcedAction.TIME_HARD_HANGUP


def test_best_disposition_for_time_hangup_defaults_to_callback():
    sm = SessionStateMachine()
    assert sm.best_progress_disposition() == "callback_requested"


def test_best_disposition_picks_highest_progress():
    sm = SessionStateMachine()
    sm.note_progress_signal("callback_discussed")
    sm.note_progress_signal("appointment_booked")
    sm.note_progress_signal("transfer_mentioned")
    # Booking is highest progress
    assert sm.best_progress_disposition() == "appointment_set"


def test_audio_action_fires_only_once():
    sm = SessionStateMachine()
    sm.note_audio_quality_complaint()
    sm.note_audio_quality_complaint()
    first = sm.tick(now_seconds=10, last_user_speech_at=9, agent_speaking=False)
    assert first == ForcedAction.AUDIO_QUALITY_HANGUP
    second = sm.tick(now_seconds=11, last_user_speech_at=10, agent_speaking=False)
    assert second is None
