"""Session-level state machine that triggers forced actions on threshold crossings.

The machine is polled (`tick(...)`) by the pipeline frame observer once per
audio chunk. It also receives explicit notifications for events the audio
loop already classifies (audio complaint, tool result, progress signal).
"""
from dataclasses import dataclass, field
from enum import Enum


class ForcedAction(str, Enum):
    AUDIO_QUALITY_HANGUP = "audio_quality_hangup"
    SILENCE_SOFT_PROMPT = "silence_soft_prompt"
    SILENCE_HANGUP = "silence_hangup"
    TRANSFER_ON_TOOL_FAILURES = "transfer_on_tool_failures"
    TIME_SOFT_WRAP = "time_soft_wrap"
    TIME_HARD_HANGUP = "time_hard_hangup"


# Disposition priority — higher index = better progress
_PROGRESS_RANK = {
    "no_signal": ("callback_requested", 0),
    "transfer_mentioned": ("transferred_to_sales", 1),
    "callback_discussed": ("callback_requested", 2),
    "appointment_booked": ("appointment_set", 3),
}

_AUDIO_COMPLAINT_HARD = 2
_SILENCE_SOFT_S = 8
_SILENCE_HARD_S = 15
_TOOL_FAILURE_HARD = 2
_TIME_SOFT_S = 240
_TIME_HARD_S = 360


@dataclass
class SessionStateMachine:
    audio_complaints: int = 0
    consecutive_tool_failures: int = 0
    progress_signals: list[str] = field(default_factory=list)
    _silence_soft_fired: bool = False
    _audio_action_fired: bool = False
    _time_soft_fired: bool = False
    _time_hard_fired: bool = False
    _transfer_fired: bool = False

    def note_audio_quality_complaint(self) -> None:
        self.audio_complaints += 1

    def note_tool_call_result(self, success: bool) -> None:
        if success:
            self.consecutive_tool_failures = 0
        else:
            self.consecutive_tool_failures += 1

    def note_progress_signal(self, signal: str) -> None:
        if signal in _PROGRESS_RANK:
            self.progress_signals.append(signal)

    def tick(
        self,
        *,
        now_seconds: float,
        last_user_speech_at: float,
        agent_speaking: bool,
    ) -> ForcedAction | None:
        # Hard time hangup wins over everything
        if not self._time_hard_fired and now_seconds >= _TIME_HARD_S:
            self._time_hard_fired = True
            return ForcedAction.TIME_HARD_HANGUP

        if not self._audio_action_fired and self.audio_complaints >= _AUDIO_COMPLAINT_HARD:
            self._audio_action_fired = True
            return ForcedAction.AUDIO_QUALITY_HANGUP

        if not self._transfer_fired and self.consecutive_tool_failures >= _TOOL_FAILURE_HARD:
            self._transfer_fired = True
            return ForcedAction.TRANSFER_ON_TOOL_FAILURES

        if not self._time_soft_fired and now_seconds >= _TIME_SOFT_S:
            self._time_soft_fired = True
            return ForcedAction.TIME_SOFT_WRAP

        # Silence handling — only counts when agent isn't currently speaking
        if not agent_speaking:
            silence_s = now_seconds - last_user_speech_at
            if silence_s >= _SILENCE_HARD_S:
                return ForcedAction.SILENCE_HANGUP
            if silence_s >= _SILENCE_SOFT_S and not self._silence_soft_fired:
                self._silence_soft_fired = True
                return ForcedAction.SILENCE_SOFT_PROMPT
            if silence_s < _SILENCE_SOFT_S:
                # User spoke recently — reset soft so a future silence can re-trigger
                self._silence_soft_fired = False

        return None

    def best_progress_disposition(self) -> str:
        if not self.progress_signals:
            return "callback_requested"
        best = max(self.progress_signals, key=lambda s: _PROGRESS_RANK[s][1])
        return _PROGRESS_RANK[best][0]
