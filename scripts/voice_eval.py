"""Voice eval rig — instruments a Pipecat call and emits per-turn latency reports.

Usage:
    python scripts/voice_eval.py --call-sid CA1234567890... [--out voice_eval_runs/]

Hooks into the in-memory frame log at voice_eval_runs/frames.jsonl that the
WS handler writes to during a test call. Generates a markdown summary:

  - Greeting latency (stream_connected -> greeting_first_audio)
  - Per-turn: user_speech_end -> stt_final -> llm_first_token -> llm_done
              -> tts_first_byte -> audio_out_first
  - Aggregates: mean, p50, p95
  - Hallucinations caught count
  - Forced actions (audio_quality_hangup, silence_hangup, etc.)
"""
import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--call-sid", required=True, help="Twilio call SID")
    parser.add_argument(
        "--out",
        default="voice_eval_runs/",
        help="Output directory for the markdown report",
    )
    parser.add_argument(
        "--frame-log",
        default="voice_eval_runs/frames.jsonl",
        help="Path to the frame log",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    frames = _load_frames(args.frame_log, args.call_sid)
    if not frames:
        print(f"No frames for {args.call_sid}", file=sys.stderr)
        sys.exit(1)

    turns = _segment_turns(frames)
    report = _render_report(args.call_sid, turns, frames)

    out_path = out_dir / f"{args.call_sid}.md"
    out_path.write_text(report)
    print(f"Wrote {out_path}")


def _load_frames(path: str, call_sid: str) -> list[dict]:
    frames = []
    p = Path(path)
    if not p.exists():
        return frames
    with p.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                f = json.loads(line)
            except json.JSONDecodeError:
                continue
            if f.get("call_sid") == call_sid:
                frames.append(f)
    frames.sort(key=lambda f: f.get("ts", 0))
    return frames


_TURN_EVENT_ORDER = [
    "user_speech_end",
    "stt_final",
    "llm_first_token",
    "llm_done",
    "tts_first_byte",
    "audio_out_first",
]


def _segment_turns(frames: list[dict]) -> list[dict]:
    """Group frames into turns delimited by audio_out_first events.

    A turn collects the per-event timestamps from user_speech_end through
    audio_out_first. Each audio_out_first closes the current turn.
    """
    turns: list[dict] = []
    current: dict = {}
    for f in frames:
        ev = f.get("event")
        if ev not in _TURN_EVENT_ORDER:
            continue
        ts = f.get("ts")
        if ev == "audio_out_first":
            current["audio_out_first"] = ts
            turns.append(current)
            current = {}
        else:
            # First sighting wins (user_speech_end before stt_final, etc.)
            current.setdefault(ev, ts)
    return turns


def _render_report(call_sid: str, turns: list[dict], frames: list[dict]) -> str:
    lines = [
        f"# Voice Eval — {call_sid}",
        "",
        f"Generated: {datetime.utcnow().isoformat()}Z",
        "",
    ]

    # Greeting latency: stream_connected -> greeting_first_audio
    stream_start = next((f for f in frames if f.get("event") == "stream_connected"), None)
    greeting = next((f for f in frames if f.get("event") == "greeting_first_audio"), None)
    if greeting and stream_start:
        gl_ms = (greeting["ts"] - stream_start["ts"]) * 1000
        lines.append(f"**Greeting latency:** {gl_ms:.0f}ms")
        lines.append("")
    elif stream_start:
        lines.append("**Greeting latency:** no greeting_first_audio event — fallback to live LLM/TTS?")
        lines.append("")

    # AMD result
    amd = next((f for f in frames if f.get("event") == "amd_received"), None)
    if amd:
        lines.append(f"**AMD result:** `{amd.get('amd_result', 'unknown')}`")
        lines.append("")

    # Per-turn latency
    turn_latencies_ms: list[float] = []
    for t in turns:
        if "audio_out_first" in t and "user_speech_end" in t:
            turn_latencies_ms.append((t["audio_out_first"] - t["user_speech_end"]) * 1000)

    if turn_latencies_ms:
        lines.append("## Turn latency (user_speech_end -> audio_out_first)")
        lines.append(f"- mean: {statistics.mean(turn_latencies_ms):.0f}ms")
        lines.append(f"- p50: {statistics.median(turn_latencies_ms):.0f}ms")
        lines.append(f"- p95: {_percentile(turn_latencies_ms, 95):.0f}ms")
        lines.append(f"- count: {len(turn_latencies_ms)}")
        lines.append("")

        # Per-turn breakdown
        lines.append("## Per-turn breakdown (ms from user_speech_end)")
        lines.append("")
        lines.append("| # | stt_final | llm_first_token | llm_done | tts_first_byte | audio_out_first |")
        lines.append("|---|-----------|-----------------|----------|----------------|-----------------|")
        for i, t in enumerate(turns, 1):
            base = t.get("user_speech_end")
            if base is None:
                continue
            cells = []
            for ev in ("stt_final", "llm_first_token", "llm_done", "tts_first_byte", "audio_out_first"):
                if ev in t:
                    cells.append(f"{(t[ev] - base) * 1000:.0f}")
                else:
                    cells.append("-")
            lines.append(f"| {i} | " + " | ".join(cells) + " |")
        lines.append("")

    # Hallucinations + forced actions
    hallucinations = [f for f in frames if f.get("event") == "hallucination_caught"]
    forced = [f for f in frames if f.get("event") == "forced_action"]
    lines.append(f"**Hallucinations caught:** {len(hallucinations)}")
    if hallucinations:
        for h in hallucinations:
            lines.append(f"  - pattern={h.get('pattern')}: {h.get('original', '')!r} -> {h.get('rewritten', '')!r}")
    lines.append(f"**Forced actions:** {len(forced)}")
    for f in forced:
        lines.append(f"  - {f.get('action', '?')}")
    lines.append("")

    return "\n".join(lines)


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) < 20:
        # Use max for small samples to avoid misleading percentile
        return max(values)
    s = sorted(values)
    k = int(len(s) * percentile / 100)
    return s[min(k, len(s) - 1)]


if __name__ == "__main__":
    main()
