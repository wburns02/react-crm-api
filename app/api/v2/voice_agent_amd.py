"""Twilio AsyncAmd webhook receiver.

Twilio fires this ~3.5s after answer with `AnsweredBy` set to one of:
  human | machine_start | machine_end_beep | machine_end_silence |
  machine_end_other | fax | unknown

The Pipecat WS handler subscribes to amd events keyed by call_sid via an
in-memory dict so it can decide whether to play the prerendered greeting,
trigger the voicemail flow, or proceed cautiously on `unknown`.
"""
import asyncio
import logging

from fastapi import APIRouter, Form, Response


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outbound-agent/amd", tags=["outbound-agent"])


# call_sid -> asyncio.Event signaling AMD result is in
_amd_events: dict[str, asyncio.Event] = {}
# call_sid -> AnsweredBy result string
_amd_results: dict[str, str] = {}


def register(call_sid: str) -> asyncio.Event:
    """Called by the WS handler before the AMD result is expected.

    Returns an asyncio.Event that the WS handler can await. The Twilio webhook
    will set this event when the AMD result arrives.
    """
    ev = asyncio.Event()
    _amd_events[call_sid] = ev
    return ev


def get_result(call_sid: str) -> str | None:
    return _amd_results.get(call_sid)


def cleanup(call_sid: str) -> None:
    """Drop both the event and result entry for a call_sid (call ended)."""
    _amd_events.pop(call_sid, None)
    _amd_results.pop(call_sid, None)


@router.post("")
async def amd_callback(
    AnsweredBy: str = Form(""),
    CallSid: str = Form(""),
):
    logger.info(f"[AMD] CallSid={CallSid} AnsweredBy={AnsweredBy}")
    _amd_results[CallSid] = AnsweredBy
    ev = _amd_events.get(CallSid)
    if ev:
        ev.set()
    return Response(status_code=200)
