"""FastAPI WebSocket route that runs the Pipecat-based outbound agent.

Twilio Media Streams calls this URL. We accept the WS, build a Pipecat
Pipeline keyed to the call_sid, and run it. AMD result + greeting prerender
are coordinated through in-memory dicts in voice_agent_amd / greeting_prerender.

Selected via campaign_dialer when settings.VOICE_AGENT_ENGINE == "pipecat".

Pipecat 0.0.108 notes (verified at implementation time):

- ``AnthropicLLMService.create_context_aggregator(...)`` is DEPRECATED in 0.0.99+.
  We use the universal ``LLMContext`` plus ``LLMContextAggregatorPair`` from
  ``pipecat.processors.aggregators.llm_response_universal``. The pair exposes
  ``.user()`` and ``.assistant()`` processors that bracket the LLM in the
  pipeline so multi-turn history is preserved. ``LLMContext`` accepts a
  ``ToolsSchema`` (built natively in ``voice_agent.tools.get_tools_schema``).
- The Anthropic LLM service inside Pipecat applies cache_control markers on
  the most recent user messages automatically (see
  ``pipecat.adapters.services.anthropic_adapter._with_cache_control_markers``)
  — we don't need to set them ourselves on the system prompt.
- ``PipelineTask`` exposes ``queue_frame`` / ``queue_frames`` (not
  ``push_frame``) for injecting frames into the pipeline.
- ``OutputAudioRawFrame`` is the right frame for raw output audio injection.

Phase 7 (eval rig) will revisit transcript assembly — see TODO markers below.
"""
import asyncio
import base64
import json
import logging
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.v2 import voice_agent_amd
from app.config import settings
from app.services.campaign_dialer import (
    active_sessions,
    get_pending_call_data,
    remove_pending_call_data,
)
from app.services.voice_agent import greeting_prerender, voicemail
from app.services.voice_agent.pipeline_factory import build_pipeline
from app.services.voice_agent.session import OutboundAgentSession
from app.services.voice_agent.greeting_prerender import render_text as render_greeting_text

# Pipecat 0.0.108 imports — verified against installed package.
from pipecat.frames.frames import OutputAudioRawFrame
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/outbound-agent/voice", tags=["outbound-agent"])


@router.websocket("/stream")
async def voice_stream(websocket: WebSocket):
    """Twilio Media Streams entrypoint for the Pipecat-based outbound agent."""
    await websocket.accept()

    call_sid: str | None = None
    stream_sid: str | None = None

    # Twilio sends a "connected" event then a "start" event. We loop until we
    # see the "start" event so we can capture stream_sid + call_sid.
    try:
        while True:
            first_msg = await websocket.receive_text()
            data = json.loads(first_msg)
            event = data.get("event")
            if event == "start":
                stream_sid = data["start"]["streamSid"]
                call_sid = data["start"]["callSid"]
                break
            elif event == "connected":
                continue
            else:
                logger.error(f"[VoiceWS] unexpected pre-start event: {event}")
                await websocket.close()
                return
    except Exception as exc:
        logger.exception(f"[VoiceWS] Failed to parse start frame: {exc}")
        try:
            await websocket.close()
        except Exception:
            pass
        return

    short_sid = call_sid[:8] if call_sid else "????????"
    logger.info(f"[VoiceWS:{short_sid}] stream started, streamSid={stream_sid}")

    pending = get_pending_call_data(call_sid) or {}
    prospect = pending.get("prospect", {}) or {}
    quote = pending.get("quote", {}) or {}

    if not prospect:
        logger.warning(
            f"[VoiceWS:{short_sid}] no pending call data — proceeding with empty context"
        )

    session = OutboundAgentSession(
        call_sid=call_sid,
        prospect=prospect,
        quote=quote,
        stream_sid=stream_sid,
    )
    active_sessions[call_sid] = session

    # Don't BLOCK on AMD — Twilio's AsyncAmd takes ~3.5s and on test calls #1-#4
    # frequently returned `unknown` anyway, costing 4s of dead air for nothing.
    # Register so the AMD callback can still set `session.amd_result` later, but
    # proceed with the conversation immediately. If Twilio retroactively decides
    # this was a machine, we'll see it in the call_logs.amd_result column.
    voice_agent_amd.register(call_sid)
    session.amd_result = voice_agent_amd.get_result(call_sid) or "pending"
    logger.info(f"[VoiceWS:{short_sid}] AMD={session.amd_result} (not waiting)")

    if session.amd_result.startswith("machine"):
        await _run_voicemail_branch(
            websocket=websocket,
            session=session,
            stream_sid=stream_sid,
            prospect=prospect,
            quote=quote,
        )
        return

    # Human (or unknown — proceed cautiously).
    #
    # We build the LLMContext up here (instead of inside _run_human_branch) so
    # that whatever happens during the run — including a mid-call exception —
    # the finally block can still call _capture_transcript(context, session)
    # before _persist_call_log writes the call_logs row.
    context = _build_context(session, prospect, quote)
    try:
        await _run_human_branch(
            websocket=websocket,
            session=session,
            call_sid=call_sid,
            context=context,
        )
    except WebSocketDisconnect:
        logger.info(f"[VoiceWS:{short_sid}] websocket disconnected")
    except Exception as exc:
        logger.exception(f"[VoiceWS:{short_sid}] pipeline error: {exc}")
    finally:
        session.ended = True
        _capture_transcript(context, session)
        await _persist_call_log(session)
        voice_agent_amd.cleanup(call_sid)
        active_sessions.pop(call_sid, None)
        remove_pending_call_data(call_sid)
        try:
            await websocket.close()
        except Exception:
            pass


# ── Branch handlers ─────────────────────────────────────────────────────


async def _run_voicemail_branch(
    *,
    websocket: WebSocket,
    session: OutboundAgentSession,
    stream_sid: str,
    prospect: dict,
    quote: dict,
) -> None:
    """Bypass Pipecat: synth voicemail audio, stream to Twilio, persist, hang up."""
    short_sid = session.call_sid[:8]
    try:
        audio = await voicemail.synthesize_voicemail_audio(prospect, quote)
        if audio:
            await _send_audio_via_twilio_ws(websocket, stream_sid, audio)
        else:
            logger.warning(f"[VoiceWS:{short_sid}] no voicemail audio synthesized")
    except Exception as exc:
        logger.exception(f"[VoiceWS:{short_sid}] voicemail send error: {exc}")
    finally:
        session.ended = True
        # Voicemail counts as a completed disposition.
        session.disposition = "voicemail_left"
        session.disposition_notes = "Voicemail flow — AMD detected machine"
        await _persist_voicemail(session)
        greeting_prerender.discard(session.call_sid)
        voice_agent_amd.cleanup(session.call_sid)
        active_sessions.pop(session.call_sid, None)
        remove_pending_call_data(session.call_sid)
        try:
            await websocket.close()
        except Exception:
            pass


async def _run_human_branch(
    *,
    websocket: WebSocket,
    session: OutboundAgentSession,
    call_sid: str,
    context,
) -> None:
    """Build and run the Pipecat pipeline for a human-answered call.

    ``context`` is the seeded ``LLMContext`` (system prompt + greeting + tools).
    The caller owns it so transcript capture can read messages off of it after
    the pipeline ends.
    """
    short_sid = call_sid[:8]

    # Build the aggregator pair that brackets the LLM in the pipeline. Done
    # here (not inside build_pipeline) so the same factory can be reused by
    # a non-WebSocket eval harness later.
    context_pair = _build_aggregator_pair(context)

    pipeline = build_pipeline(
        session=session,
        websocket=websocket,
        context_aggregator_pair=context_pair,
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
    )

    runner = PipelineRunner()

    # Inject prerendered greeting BEFORE the LLM kicks in. Twilio plays media
    # frames in the order they arrive on the WS, so this is functionally a
    # "say-this-first" hook.
    greeting_audio = greeting_prerender.take_buffer(call_sid)
    if greeting_audio:
        await _push_audio_into_pipeline(task, greeting_audio)
        logger.info(
            f"[VoiceWS:{short_sid}] queued prerendered greeting "
            f"({len(greeting_audio)} bytes)"
        )
    else:
        logger.info(f"[VoiceWS:{short_sid}] no prerendered greeting available")

    await runner.run(task)


def _build_context(session: OutboundAgentSession, prospect: dict, quote: dict):
    """Construct an LLMContext seeded with system prompt + prerendered greeting.

    Phase 6.1-fix-2: the prerendered greeting plays as audio out, but the LLM
    has no idea it just spoke unless we put the greeting text on the context
    as an assistant message. Without this, when the user replies "yeah I have
    a question," the LLM sees only ``[system, user_reply]`` and may not connect
    to the quote follow-up framing. Seeding the greeting as the first
    assistant turn keeps the multi-turn framing intact.

    The system prompt is added as a plain system message — the Anthropic
    adapter inside Pipecat applies cache_control markers automatically on the
    most recent user messages at send time, so we don't need to mark the
    system prompt by hand.
    """
    from pipecat.processors.aggregators.llm_context import LLMContext

    from app.services.voice_agent.tools import get_tools_schema

    greeting_text = render_greeting_text(prospect, quote)
    return LLMContext(
        messages=[
            {"role": "system", "content": session.system_prompt},
            {"role": "assistant", "content": greeting_text},
        ],
        tools=get_tools_schema(),
    )


def _build_aggregator_pair(context):
    """Wrap the seeded ``LLMContext`` in an ``LLMContextAggregatorPair``.

    Split out from context construction so transcript capture can read off
    the same ``LLMContext`` instance the aggregators are appending to.
    """
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
    )

    return LLMContextAggregatorPair(context)


def _capture_transcript(context, session: OutboundAgentSession) -> None:
    """Copy LLMContext messages onto the legacy session.transcript list.

    The legacy ``_persist_call`` reads ``session.transcript`` (a list of dicts
    with ``speaker``/``text``/``timestamp`` keys) and renders a timestamped
    transcript block before writing it to ``call_logs.transcription``. Pipecat
    owns the conversation now and never populates that list, so we pull
    ``LLMContext.get_messages()`` and translate it into the legacy shape.

    Anthropic content can be either a string (textual turn) or a list of
    content blocks (when tool_use blocks are mixed in) — we extract the
    ``text`` blocks only. System messages are skipped.
    """
    if context is None or session is None:
        return
    try:
        messages = list(context.get_messages() or [])
    except Exception as exc:
        logger.warning(f"[VoiceWS] transcript capture: get_messages failed: {exc}")
        return

    legacy = getattr(session, "_legacy_helpers", None)
    if legacy is None:
        return

    transcript: list[dict] = []
    started_iso = None
    try:
        started_iso = legacy.started_at.isoformat()
    except Exception:
        pass

    for msg in messages:
        try:
            role = msg.get("role") if isinstance(msg, dict) else None
        except Exception:
            role = None
        if not role or role == "system":
            continue
        speaker = "agent" if role == "assistant" else "customer"

        content = msg.get("content", "") if isinstance(msg, dict) else ""
        text = ""
        if isinstance(content, str):
            stripped = content.strip()
            # Pipecat stores tool_result content as a JSON string under role="user".
            # Filter those out so they don't render as customer turns.
            if (
                role == "user"
                and stripped.startswith("{")
                and stripped.endswith("}")
            ):
                try:
                    json.loads(stripped)
                    continue
                except (json.JSONDecodeError, ValueError):
                    pass
            text = content
        elif isinstance(content, list):
            chunks = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text"):
                    chunks.append(block["text"])
            text = " ".join(chunks).strip()
        if not text:
            continue
        transcript.append(
            {
                "speaker": speaker,
                "text": text,
                # Best-effort timestamp — every line lands at started_at.
                # _persist_call falls back to "[??:??]" gracefully if absent.
                "timestamp": started_iso or "",
            }
        )

    legacy.transcript = transcript


# ── Audio helpers ───────────────────────────────────────────────────────


async def _send_audio_via_twilio_ws(
    websocket: WebSocket, stream_sid: str, audio: bytes
) -> None:
    """Stream raw μ-law audio to Twilio Media Streams as base64 frames (20ms chunks)."""
    chunk_size = 320  # 20ms at 8kHz μ-law
    for i in range(0, len(audio), chunk_size):
        chunk = audio[i : i + chunk_size]
        try:
            await websocket.send_text(
                json.dumps(
                    {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": base64.b64encode(chunk).decode()},
                    }
                )
            )
        except Exception as exc:
            logger.warning(f"[VoiceWS] audio send failed mid-stream: {exc}")
            return
        # Pace at real time so Twilio's jitter buffer doesn't drop frames.
        await asyncio.sleep(0.02)


async def _push_audio_into_pipeline(task: PipelineTask, audio: bytes) -> None:
    """Inject prerendered μ-law audio into Pipecat's output stream.

    Pipecat 0.0.108 ``PipelineTask`` exposes ``queue_frame`` / ``queue_frames``
    for ad-hoc frame injection. ``OutputAudioRawFrame`` is the canonical raw
    output audio frame. Greeting audio is μ-law 8kHz mono (matches Twilio
    Media Streams' inbound serializer expectations).
    """
    try:
        frame = OutputAudioRawFrame(audio=audio, sample_rate=8000, num_channels=1)
        if hasattr(task, "queue_frames"):
            await task.queue_frames([frame])
        elif hasattr(task, "queue_frame"):
            await task.queue_frame(frame)
        else:
            logger.warning(
                "[VoiceWS] PipelineTask has no queue_frame(s) — greeting injection skipped"
            )
    except Exception as exc:
        logger.warning(f"[VoiceWS] greeting injection failed: {exc}")


# ── Persistence ─────────────────────────────────────────────────────────


async def _persist_call_log(session: OutboundAgentSession) -> None:
    """Write call_logs row using the legacy _persist_call helper, plus new fields.

    Strategy: the legacy ``_persist_call(session)`` reads attrs off the
    OutboundAgentSession class in ``app/services/outbound_agent.py``. The new
    Pipecat session keeps a ``_legacy_helpers`` instance of that exact class,
    so we forward to ``_persist_call(session._legacy_helpers)`` after copying
    over disposition / disposition_notes that the new state machine owns.
    Then we patch the freshly-inserted row to add hallucinations + amd_result
    (columns that the legacy persister doesn't know about).

    Phase 6.1-fix-2: ``_capture_transcript(context, session)`` is invoked
    from the WebSocket finally block before this function runs, so
    ``legacy.transcript`` is populated from the LLMContext and the
    persisted ``call_logs.transcription`` is non-empty for human-branch
    calls. (Phase 7 may swap to a TranscriptProcessor for richer turn-level
    timing — for now the system+assistant+user message log is sufficient.)
    """
    short_sid = session.call_sid[:8]

    # Forward state captured by the new state machine onto the legacy helper
    # so _persist_call sees the right disposition + notes.
    legacy = session._legacy_helpers
    legacy.disposition = session.disposition
    legacy.disposition_notes = session.disposition_notes

    try:
        from app.api.v2.outbound_agent import _persist_call
    except ImportError as exc:
        logger.error(f"[VoiceWS:{short_sid}] legacy _persist_call import failed: {exc}")
        # Fall back to a minimal voicemail-shaped row so we don't lose the call.
        await _persist_voicemail(session)
        return

    try:
        await _persist_call(legacy)
    except Exception as exc:
        logger.exception(f"[VoiceWS:{short_sid}] _persist_call failed: {exc}")
        # Even on persist failure, keep going so we still attempt the patch.

    # Patch the row to add hallucinations + amd_result. Match by call_sid via
    # the ringcentral_call_id index on call_logs (the legacy persister doesn't
    # set this column, but we can match by called_number+date as a fallback).
    try:
        from sqlalchemy import select, update

        from app.database import async_session_maker
        from app.models.call_log import CallLog

        # Match the most recent call_logs row for this prospect's phone number
        # written within the last few minutes — the legacy persister just
        # called insert with no FK on call_sid so we can't be more precise.
        called_number = (legacy.prospect or {}).get("phone", "") or ""
        async with async_session_maker() as db:
            row = await db.execute(
                select(CallLog)
                .where(CallLog.called_number == called_number)
                .where(CallLog.external_system == "outbound_agent")
                .order_by(CallLog.created_at.desc())
                .limit(1)
            )
            log = row.scalar_one_or_none()
            if log is None:
                logger.warning(
                    f"[VoiceWS:{short_sid}] could not locate call_logs row to patch"
                )
                return

            await db.execute(
                update(CallLog)
                .where(CallLog.id == log.id)
                .values(
                    hallucinations=session.hallucinations_log or None,
                    amd_result=session.amd_result,
                    ringcentral_call_id=session.call_sid,
                )
            )
            await db.commit()
            logger.info(
                f"[VoiceWS:{short_sid}] patched call_logs row {log.id} with "
                f"amd={session.amd_result} hallucinations={len(session.hallucinations_log or [])}"
            )
    except Exception as exc:
        logger.exception(f"[VoiceWS:{short_sid}] post-persist update failed: {exc}")


async def _persist_voicemail(session: OutboundAgentSession) -> None:
    """Write a minimal call_logs row for a voicemail-branch call."""
    from app.database import async_session_maker
    from app.models.call_log import CallLog

    short_sid = session.call_sid[:8]
    now = datetime.utcnow()
    duration = max(0, int(time.monotonic() - session.start_time))
    called_number = (session.prospect or {}).get("phone", "") or ""
    caller_number = (
        settings.OUTBOUND_AGENT_FROM_NUMBER or settings.TWILIO_PHONE_NUMBER or ""
    )

    customer_uuid = None
    raw_id = (session.prospect or {}).get("id")
    if raw_id:
        try:
            customer_uuid = uuid.UUID(str(raw_id))
        except (ValueError, TypeError):
            pass

    try:
        async with async_session_maker() as db:
            log = CallLog(
                id=uuid.uuid4(),
                ringcentral_call_id=session.call_sid,
                direction="outbound",
                call_type="voice",
                caller_number=caller_number,
                called_number=called_number,
                customer_id=customer_uuid,
                call_disposition=session.disposition or "voicemail_left",
                call_date=now.date(),
                call_time=now.time(),
                duration_seconds=duration,
                transcription="",
                transcription_status="not_applicable",
                ai_summary="Voicemail flow — answering machine detected, no conversation",
                sentiment="neutral",
                notes=session.disposition_notes
                or "Voicemail left via outbound voice agent (Pipecat).",
                assigned_to="ai_outbound_agent",
                external_system="outbound_agent",
                user_id="1",
                amd_result=session.amd_result,
            )
            db.add(log)
            await db.commit()
            logger.info(
                f"[VoiceWS:{short_sid}] voicemail call_logs row written ({log.id})"
            )
    except Exception as exc:
        logger.exception(f"[VoiceWS:{short_sid}] voicemail persist failed: {exc}")
