"""Frame-level event logger for the Pipecat voice agent.

Appends one JSON line per event to voice_eval_runs/frames.jsonl. Read by
scripts/voice_eval.py to produce per-call latency reports.

Events the WS handler should emit (calling sites added in a follow-up):
  - stream_connected: WebSocket accepted
  - amd_received: amd_result string
  - greeting_first_audio: prerendered greeting starts playing
  - user_speech_start: VAD detected user speaking
  - user_speech_end: VAD detected user finished
  - stt_final: Deepgram returned a finalized utterance
  - llm_first_token: LLM produced the first token
  - llm_done: LLM finished generating
  - tts_first_byte: TTS service emitted the first audio byte
  - audio_out_first: first audio frame for THIS turn shipped to Twilio
  - hallucination_caught: HallucinationGuard rewrote a sentence
  - forced_action: SessionStateMachine triggered a forced action
  - call_end: pipeline shut down

Each event has at minimum:
  - call_sid: str
  - ts: float (time.monotonic() — relative; for absolute use ts_unix)
  - ts_unix: float (time.time())
  - event: str
  - plus event-specific kwargs (e.g., text, action, latency_ms)
"""
import json
import logging
import os
import threading
import time
from pathlib import Path


logger = logging.getLogger(__name__)

_FRAMES_DIR = Path(os.environ.get("VOICE_EVAL_DIR", "voice_eval_runs"))
_FRAMES_FILE = _FRAMES_DIR / "frames.jsonl"
_lock = threading.Lock()


def _ensure_dir() -> None:
    _FRAMES_DIR.mkdir(parents=True, exist_ok=True)


def log_event(call_sid: str, event: str, **kwargs) -> None:
    """Append a single JSON-line event to the frames log."""
    if not call_sid:
        return
    record = {
        "call_sid": call_sid,
        "event": event,
        "ts": time.monotonic(),
        "ts_unix": time.time(),
        **kwargs,
    }
    try:
        _ensure_dir()
        line = json.dumps(record, default=str)
        with _lock:
            with open(_FRAMES_FILE, "a") as fh:
                fh.write(line + "\n")
    except Exception as exc:
        # Frame log failure must never break a live call
        logger.debug(f"[frame_logger] write failed: {exc}")


def disabled() -> bool:
    """True if logging is explicitly disabled via env var."""
    return os.environ.get("VOICE_EVAL_DISABLED", "").lower() in ("1", "true", "yes")
