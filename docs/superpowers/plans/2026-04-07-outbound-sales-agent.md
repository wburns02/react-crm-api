# AI Outbound Sales Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the AI outbound sales agent by wiring streaming STT with barge-in, real tool execution, call persistence, live transcript dashboard, and Cartesia voicemail.

**Architecture:** Extend 3 existing backend files (outbound_agent.py service, outbound_agent.py API, campaign_dialer.py) and 2 frontend files (AIAgentDashboard.tsx, WorkOrderCard.tsx). No new database migrations — reuses existing call_logs table and WorkOrder model fields (created_by, source).

**Tech Stack:** Twilio Media Streams, Deepgram Nova-3 Streaming WebSocket, Cartesia Sonic TTS, Claude Haiku 4.5, FastAPI, React + TanStack Query

**Spec:** `/home/will/react-crm-api/docs/superpowers/specs/2026-04-07-outbound-sales-agent-design.md`

---

### Task 1: Deepgram Streaming STT Class

**Files:**
- Create: `app/services/deepgram_stream.py`

This is a self-contained class that manages a persistent WebSocket connection to Deepgram for real-time transcription. It receives raw mu-law audio bytes and emits transcript callbacks.

- [ ] **Step 1: Create deepgram_stream.py**

```python
"""
Deepgram Streaming STT — persistent WebSocket for real-time transcription.

Usage:
    stream = DeepgramStream(on_transcript=my_callback, on_utterance_end=my_end_callback)
    await stream.connect()
    stream.send_audio(mulaw_bytes)  # non-blocking
    await stream.close()
"""

import asyncio
import json
import logging
from typing import Callable, Optional, Awaitable

import websockets

from app.config import settings

logger = logging.getLogger(__name__)

# Callback types
TranscriptCallback = Callable[[str, bool], Awaitable[None]]  # (text, is_final)
UtteranceEndCallback = Callable[[], Awaitable[None]]


class DeepgramStream:
    """Manages a streaming WebSocket connection to Deepgram Nova-3."""

    def __init__(
        self,
        on_transcript: Optional[TranscriptCallback] = None,
        on_utterance_end: Optional[UtteranceEndCallback] = None,
    ):
        self.on_transcript = on_transcript
        self.on_utterance_end = on_utterance_end
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._closed = False

    async def connect(self):
        """Open streaming connection to Deepgram."""
        if not settings.DEEPGRAM_API_KEY:
            logger.error("DEEPGRAM_API_KEY not set")
            return

        url = (
            "wss://api.deepgram.com/v1/listen?"
            "model=nova-3&"
            "encoding=mulaw&"
            "sample_rate=8000&"
            "channels=1&"
            "interim_results=true&"
            "utterance_end_ms=1200&"
            "smart_format=true&"
            "no_delay=true"
        )

        headers = {"Authorization": f"Token {settings.DEEPGRAM_API_KEY}"}

        try:
            self._ws = await websockets.connect(url, additional_headers=headers)
            self._listen_task = asyncio.create_task(self._listen())
            logger.info("Deepgram streaming connected")
        except Exception as e:
            logger.error(f"Deepgram connect error: {e}")

    def send_audio(self, audio_bytes: bytes):
        """Queue audio bytes to send to Deepgram. Non-blocking."""
        if self._ws and not self._closed:
            asyncio.create_task(self._send(audio_bytes))

    async def _send(self, audio_bytes: bytes):
        try:
            await self._ws.send(audio_bytes)
        except Exception as e:
            logger.error(f"Deepgram send error: {e}")

    async def _listen(self):
        """Listen for Deepgram responses."""
        try:
            async for message in self._ws:
                if self._closed:
                    break
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type")

                if msg_type == "Results":
                    is_final = data.get("is_final", False)
                    transcript = (
                        data.get("channel", {})
                        .get("alternatives", [{}])[0]
                        .get("transcript", "")
                    )
                    if transcript.strip() and self.on_transcript:
                        await self.on_transcript(transcript.strip(), is_final)

                elif msg_type == "UtteranceEnd":
                    if self.on_utterance_end:
                        await self.on_utterance_end()

        except websockets.exceptions.ConnectionClosed:
            logger.info("Deepgram connection closed")
        except Exception as e:
            if not self._closed:
                logger.error(f"Deepgram listen error: {e}")

    async def close(self):
        """Close the Deepgram connection."""
        self._closed = True
        if self._ws:
            try:
                # Send close message per Deepgram protocol
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await self._ws.close()
            except Exception:
                pass
        if self._listen_task:
            self._listen_task.cancel()
```

- [ ] **Step 2: Verify websockets is available**

Run: `cd /home/will/react-crm-api && pip show websockets 2>/dev/null || echo "NOT INSTALLED"`

If not installed: `pip install websockets` and add to requirements.txt.

- [ ] **Step 3: Commit**

```bash
cd /home/will/react-crm-api
git add app/services/deepgram_stream.py
git commit -m "feat: add Deepgram streaming STT WebSocket class"
```

---

### Task 2: Replace Batch STT with Streaming + Barge-in

**Files:**
- Modify: `app/api/v2/outbound_agent.py` (the WebSocket handler, lines 228-365)

Replace the batch STT buffer logic with the new DeepgramStream. Add barge-in detection.

- [ ] **Step 1: Rewrite the WebSocket media handler**

Replace the entire `ws_outbound_agent_media` function (lines 228-365) in `app/api/v2/outbound_agent.py` with:

```python
@media_ws_router.websocket("/ws/outbound-agent/{call_sid}")
async def ws_outbound_agent_media(websocket: WebSocket, call_sid: str):
    """
    Twilio Media Streams WebSocket for the outbound AI agent.
    Uses Deepgram streaming STT with barge-in support.
    """
    await websocket.accept()
    logger.info(f"Outbound agent media stream connected: {call_sid}")

    session = active_sessions.get(call_sid)
    if not session:
        logger.warning(f"No session found for {call_sid}")
        await websocket.close()
        return

    stream_sid = None
    agent_is_speaking = False
    tts_cancel = asyncio.Event()
    pending_speech = ""  # accumulates interim results between is_final events

    # ── Deepgram callbacks ──────────────────────────────────────

    async def on_transcript(text: str, is_final: bool):
        nonlocal agent_is_speaking, pending_speech

        if is_final:
            full_text = (pending_speech + " " + text).strip() if pending_speech else text
            pending_speech = ""

            # Barge-in: if agent is speaking and customer interrupts
            if agent_is_speaking:
                logger.info(f"[{call_sid[:8]}] Barge-in detected: '{full_text}'")
                agent_is_speaking = False
                tts_cancel.set()
                # Clear Twilio audio buffer
                if stream_sid:
                    try:
                        await websocket.send_text(json.dumps({
                            "event": "clear",
                            "streamSid": stream_sid,
                        }))
                    except Exception:
                        pass

            if full_text:
                await session.handle_speech(full_text)
                # Broadcast to live transcript listeners
                _broadcast_transcript(call_sid, "customer", full_text)
        else:
            # Accumulate interim results
            pending_speech = (pending_speech + " " + text).strip() if pending_speech else text

    async def on_utterance_end():
        nonlocal pending_speech
        # If we have accumulated speech that didn't get a final, flush it
        if pending_speech.strip():
            text = pending_speech.strip()
            pending_speech = ""
            await session.handle_speech(text)
            _broadcast_transcript(call_sid, "customer", text)

    # ── TTS speak callback ──────────────────────────────────────

    async def speak(text: str):
        nonlocal stream_sid, agent_is_speaking
        if not stream_sid:
            return

        agent_is_speaking = True
        tts_cancel.clear()

        try:
            audio_data = await _text_to_speech(text)
            if audio_data and not tts_cancel.is_set():
                # Send in chunks to allow barge-in between chunks
                chunk_size = 3200  # 400ms of audio at 8kHz mu-law
                for i in range(0, len(audio_data), chunk_size):
                    if tts_cancel.is_set():
                        break
                    chunk = audio_data[i:i + chunk_size]
                    payload = base64.b64encode(chunk).decode()
                    await websocket.send_text(json.dumps({
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": payload},
                    }))
                    # Small delay between chunks so Twilio doesn't buffer too much
                    await asyncio.sleep(0.05)

                _broadcast_transcript(call_sid, "agent", text)
        except Exception as e:
            logger.error(f"TTS/send error: {e}")
        finally:
            agent_is_speaking = False

    session.on_speak = speak

    async def end_call():
        try:
            if TWILIO_AVAILABLE and settings.TWILIO_ACCOUNT_SID:
                from twilio.rest import Client
                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                client.calls(call_sid).update(status="completed")
        except Exception as e:
            logger.error(f"Failed to end call {call_sid}: {e}")

    session.on_end_call = end_call

    async def transfer(number: str):
        try:
            if TWILIO_AVAILABLE and settings.TWILIO_ACCOUNT_SID:
                from twilio.rest import Client
                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
                twiml = f'<Response><Dial>{number}</Dial></Response>'
                client.calls(call_sid).update(twiml=twiml)
        except Exception as e:
            logger.error(f"Failed to transfer call {call_sid}: {e}")

    session.on_transfer = transfer

    # ── Connect Deepgram streaming ──────────────────────────────

    from app.services.deepgram_stream import DeepgramStream

    dg = DeepgramStream(on_transcript=on_transcript, on_utterance_end=on_utterance_end)
    await dg.connect()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event = msg.get("event")

            if event == "connected":
                logger.info(f"Media stream connected for {call_sid}")

            elif event == "start":
                stream_sid = msg.get("start", {}).get("streamSid")
                logger.info(f"Media stream started: streamSid={stream_sid}")
                await asyncio.sleep(1)
                await session.start_greeting()
                _broadcast_transcript(call_sid, "agent", session.transcript[-1]["text"] if session.transcript else "")

            elif event == "media":
                payload = msg.get("media", {}).get("payload", "")
                if payload:
                    audio_bytes = base64.b64decode(payload)
                    dg.send_audio(audio_bytes)

            elif event == "stop":
                logger.info(f"Media stream stopped for {call_sid}")
                break

    except WebSocketDisconnect:
        logger.info(f"Media stream disconnected for {call_sid}")
    except Exception as e:
        logger.error(f"Media stream error for {call_sid}: {e}")
    finally:
        await dg.close()
        session.ended = True
        # Persist call to database
        await _persist_call(session)
        summary = session.get_summary()
        logger.info(f"Call {call_sid} ended. Disposition: {summary['disposition']}")
```

- [ ] **Step 2: Add the transcript broadcast and persist helpers at module level**

Add these after the existing module-level code in `app/api/v2/outbound_agent.py`:

```python
# ── Live Transcript Broadcasting ─────────────────────────────────
# Simple in-memory pub/sub for live transcript lines

_transcript_listeners: dict[str, list[asyncio.Queue]] = {}


def _broadcast_transcript(call_sid: str, speaker: str, text: str):
    """Broadcast a transcript line to all listeners for this call."""
    if call_sid in _transcript_listeners:
        line = {
            "speaker": speaker,
            "text": text,
            "timestamp": datetime.utcnow().isoformat(),
        }
        for q in _transcript_listeners[call_sid]:
            try:
                q.put_nowait(line)
            except asyncio.QueueFull:
                pass  # Drop if listener is slow


def _subscribe_transcript(call_sid: str) -> asyncio.Queue:
    """Subscribe to live transcript for a call. Returns a Queue."""
    if call_sid not in _transcript_listeners:
        _transcript_listeners[call_sid] = []
    q = asyncio.Queue(maxsize=100)
    _transcript_listeners[call_sid].append(q)
    return q


def _unsubscribe_transcript(call_sid: str, q: asyncio.Queue):
    """Remove a transcript listener."""
    if call_sid in _transcript_listeners:
        _transcript_listeners[call_sid] = [x for x in _transcript_listeners[call_sid] if x is not q]
        if not _transcript_listeners[call_sid]:
            del _transcript_listeners[call_sid]


# ── Call Persistence ─────────────────────────────────────────────

async def _persist_call(session):
    """Save call data to the call_logs table."""
    from app.database import async_session_maker
    from app.models.call_log import CallLog

    try:
        async with async_session_maker() as db:
            # Build timestamped transcript string
            transcript_lines = []
            start_time = session.started_at
            for entry in session.transcript:
                try:
                    ts = datetime.fromisoformat(entry["timestamp"])
                    elapsed = int((ts - start_time).total_seconds())
                    mins, secs = divmod(elapsed, 60)
                    prefix = f"[{mins:02d}:{secs:02d}]"
                except (ValueError, TypeError):
                    prefix = "[??:??]"
                speaker = "Agent" if entry["speaker"] == "agent" else "Customer"
                transcript_lines.append(f"{prefix} {speaker}: {entry['text']}")

            transcript_text = "\n".join(transcript_lines)

            # Generate AI summary via Claude
            ai_summary = await _generate_call_summary(session)

            duration = int((datetime.utcnow() - session.started_at).total_seconds())

            call_log = CallLog(
                caller_number=settings.OUTBOUND_AGENT_FROM_NUMBER or settings.TWILIO_PHONE_NUMBER or "",
                called_number=session.prospect.get("phone", ""),
                direction="outbound",
                call_disposition=session.disposition or "unknown",
                call_type="voice",
                call_date=session.started_at.date(),
                call_time=session.started_at.time(),
                duration_seconds=duration,
                transcription=transcript_text,
                ai_summary=ai_summary,
                sentiment=session.disposition_notes,  # Claude sets this
                notes=f"[AI Agent] Outbound campaign call. Disposition: {session.disposition}",
                assigned_to="ai_outbound_agent",
                customer_id=session.prospect.get("id"),
            )

            db.add(call_log)
            await db.commit()
            logger.info(f"Call {session.call_sid[:8]} persisted to call_logs")

    except Exception as e:
        logger.error(f"Failed to persist call {session.call_sid}: {e}")


async def _generate_call_summary(session) -> Optional[str]:
    """Ask Claude to summarize the call in 2-3 sentences."""
    if not settings.ANTHROPIC_API_KEY or not session.transcript:
        return None

    transcript_text = "\n".join(
        f"{e['speaker'].title()}: {e['text']}" for e in session.transcript
    )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 150,
                    "messages": [{"role": "user", "content": f"Summarize this sales call in 2-3 sentences. What was the outcome?\n\n{transcript_text}"}],
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["content"][0]["text"]
    except Exception as e:
        logger.error(f"Summary generation error: {e}")
    return None
```

- [ ] **Step 3: Add the live transcript SSE endpoint**

Add this endpoint to the `router` in `app/api/v2/outbound_agent.py`:

```python
from fastapi.responses import StreamingResponse

@router.get("/live-transcript/{call_sid}")
async def api_live_transcript(call_sid: str):
    """SSE endpoint for live transcript streaming."""
    q = _subscribe_transcript(call_sid)

    async def event_stream():
        try:
            while True:
                try:
                    line = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(line)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _unsubscribe_transcript(call_sid, q)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: Add StreamingResponse import at top of outbound_agent.py API file**

Add to the imports at the top of `app/api/v2/outbound_agent.py`:

```python
from fastapi.responses import PlainTextResponse, StreamingResponse
```

(Replace the existing `from fastapi.responses import PlainTextResponse` line.)

- [ ] **Step 5: Commit**

```bash
cd /home/will/react-crm-api
git add app/api/v2/outbound_agent.py
git commit -m "feat: streaming STT with barge-in, call persistence, live transcript SSE"
```

---

### Task 3: Wire Tool Execution to Real CRM Actions

**Files:**
- Modify: `app/services/outbound_agent.py` (the `_handle_tool_call` method, lines 337-398)

Replace stub handlers with real database operations.

- [ ] **Step 1: Rewrite _handle_tool_call in OutboundAgentSession**

Replace lines 337-398 of `app/services/outbound_agent.py`:

```python
    async def _handle_tool_call(self, name: str, tool_id: str, args: dict) -> dict:
        """Execute a tool call from Claude. Returns result dict for tool_result message."""
        logger.info(f"[Agent:{self.call_sid[:8]}] Tool: {name}({json.dumps(args)[:100]})")

        if name == "set_disposition":
            self.disposition = args.get("disposition", "unknown")
            self.disposition_notes = args.get("notes", "")
            return {"success": True, "disposition": self.disposition}

        elif name == "end_call":
            self.ended = True
            if self.on_end_call:
                await self.on_end_call()
            return {"success": True}

        elif name == "transfer_call":
            if self.on_transfer:
                await self.on_transfer(settings.OUTBOUND_AGENT_TRANSFER_NUMBER)
            return {"success": True, "transferred_to": settings.OUTBOUND_AGENT_TRANSFER_NUMBER}

        elif name == "leave_voicemail":
            p = self.prospect
            q = self.quote
            line_items = q.get("line_items", [])
            service = line_items[0].get("service", "septic service") if line_items else "septic service"
            vm = (
                f"Hi {p.get('first_name', '')}, this is MAC Septic following up "
                f"on the estimate we sent for {service} at your property. "
                f"Give us a call back at 615-345-2544 when you get a chance. Thanks!"
            )
            if self.on_speak:
                await self.on_speak(vm)
            self.disposition = "voicemail_left"
            self.transcript.append({"speaker": "agent", "text": f"[Voicemail] {vm}", "timestamp": datetime.utcnow().isoformat()})
            await asyncio.sleep(8)
            self.ended = True
            if self.on_end_call:
                await self.on_end_call()
            return {"success": True, "message": "Voicemail left"}

        elif name == "book_appointment":
            return await self._book_appointment(args)

        elif name == "check_availability":
            return await self._check_availability(args)

        elif name == "create_callback":
            return await self._create_callback(args)

        elif name == "send_followup_sms":
            return await self._send_sms(args)

        return {"error": f"Unknown tool: {name}"}

    async def _book_appointment(self, args: dict) -> dict:
        """Create a real WorkOrder in the CRM."""
        from app.database import async_session_maker
        from app.models.work_order import WorkOrder

        try:
            async with async_session_maker() as db:
                wo = WorkOrder(
                    customer_id=UUID(self.prospect["id"]),
                    job_type=args.get("service_type", "pumping"),
                    status="scheduled",
                    scheduled_date=datetime.strptime(args["scheduled_date"], "%Y-%m-%d").date(),
                    time_window=args.get("time_window", "morning"),
                    notes=f"[AI Agent] Booked via outbound call on {date.today()}. {args.get('notes', '')}",
                    created_by="ai_agent",
                    source="outbound_campaign",
                    address_line1=self.prospect.get("address_line1", ""),
                    city=self.prospect.get("city", ""),
                    state=self.prospect.get("state", ""),
                    postal_code=self.prospect.get("postal_code", ""),
                )
                db.add(wo)
                await db.commit()
                await db.refresh(wo)

                logger.info(f"[Agent:{self.call_sid[:8]}] Created WO {wo.id} for {args['scheduled_date']}")
                self.disposition = "appointment_set"
                return {
                    "success": True,
                    "work_order_id": str(wo.id),
                    "scheduled_date": args["scheduled_date"],
                    "message": f"Appointment booked for {args['scheduled_date']}",
                }
        except Exception as e:
            logger.error(f"Book appointment error: {e}")
            return {"success": False, "error": str(e)}

    async def _check_availability(self, args: dict) -> dict:
        """Check real availability by looking at existing work orders."""
        from app.database import async_session_maker
        from app.models.work_order import WorkOrder
        from sqlalchemy import select, func

        try:
            async with async_session_maker() as db:
                today = date.today()
                slots = []
                for i in range(1, 8):
                    d = today + timedelta(days=i)
                    if d.weekday() >= 5:  # Skip weekends
                        continue
                    # Count existing jobs on this date
                    result = await db.execute(
                        select(func.count(WorkOrder.id)).where(
                            WorkOrder.scheduled_date == d,
                            WorkOrder.status.in_(["scheduled", "in_progress"]),
                        )
                    )
                    count = result.scalar() or 0
                    if count < 6:  # Max 6 jobs per day
                        available = []
                        if count < 3:
                            available.append("morning (8am-12pm)")
                        if count < 6:
                            available.append("afternoon (12pm-5pm)")
                        slots.append(f"{d.strftime('%A %B %d')}: {', '.join(available)}")

                return {"available_slots": slots[:5]}
        except Exception as e:
            logger.error(f"Check availability error: {e}")
            # Fallback to hardcoded
            today = date.today()
            slots = []
            for i in range(1, 8):
                d = today + timedelta(days=i)
                if d.weekday() < 5:
                    slots.append(f"{d.strftime('%A %B %d')}: morning or afternoon")
            return {"available_slots": slots[:5]}

    async def _create_callback(self, args: dict) -> dict:
        """Create a callback task in the CRM."""
        from app.database import async_session_maker
        from app.models.ai_agent import AgentTask

        try:
            async with async_session_maker() as db:
                task = AgentTask(
                    task_type="follow_up_call",
                    title=f"Callback: {self.prospect.get('first_name', '')} {self.prospect.get('last_name', '')}",
                    description=f"Customer requested callback at {args.get('callback_time', 'unspecified')}. {args.get('notes', '')}",
                    status="pending",
                    priority="high",
                    customer_id=UUID(self.prospect["id"]),
                    source="outbound_campaign",
                )
                db.add(task)
                await db.commit()
                self.disposition = "callback_requested"
                return {"success": True, "callback_time": args.get("callback_time")}
        except Exception as e:
            logger.error(f"Create callback error: {e}")
            self.disposition = "callback_requested"
            return {"success": True, "note": "Callback noted (manual follow-up needed)"}

    async def _send_sms(self, args: dict) -> dict:
        """Send a follow-up SMS via Twilio."""
        message = args.get("message", "")
        phone = self.prospect.get("phone", "")
        if not phone or not message:
            return {"error": "Missing phone or message"}

        try:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            from_number = settings.TWILIO_PHONE_NUMBER or settings.OUTBOUND_AGENT_FROM_NUMBER
            if not phone.startswith("+"):
                phone = "+1" + phone.replace("-", "").replace("(", "").replace(")", "").replace(" ", "")

            sms = client.messages.create(
                to=phone,
                from_=from_number,
                body=message,
            )
            logger.info(f"[Agent:{self.call_sid[:8]}] SMS sent: {sms.sid}")
            return {"success": True, "sms_sid": sms.sid}
        except Exception as e:
            logger.error(f"SMS error: {e}")
            return {"success": False, "error": str(e)}
```

- [ ] **Step 2: Update _call_claude to pass tool results back**

Replace the `_call_claude` method (lines 291-335) with this version that properly handles tool_use/tool_result flow:

```python
    async def _call_claude(self) -> Optional[str]:
        """Call Claude API for conversation response, handling tool use loops."""
        if not settings.ANTHROPIC_API_KEY:
            logger.error("ANTHROPIC_API_KEY not set")
            return "I'm having a technical issue. Let me transfer you to the office."

        context = self._build_context()
        system = SYSTEM_PROMPT.replace("{prospect_context}", context)

        max_tool_rounds = 3  # Prevent infinite tool loops
        for _ in range(max_tool_rounds):
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": settings.ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 300,
                        "system": system,
                        "messages": self.conversation,
                        "tools": AGENT_TOOLS,
                    },
                )

                if resp.status_code != 200:
                    logger.error(f"Claude API error: {resp.status_code} {resp.text[:200]}")
                    return None

                data = resp.json()
                stop_reason = data.get("stop_reason")
                text_parts = []
                tool_uses = []

                for block in data.get("content", []):
                    if block["type"] == "text":
                        text_parts.append(block["text"])
                    elif block["type"] == "tool_use":
                        tool_uses.append(block)

                # If Claude wants to use tools, execute them and feed results back
                if stop_reason == "tool_use" and tool_uses:
                    # Add Claude's response (with tool_use blocks) to conversation
                    self.conversation.append({"role": "assistant", "content": data["content"]})

                    # Execute each tool and collect results
                    tool_results = []
                    for tool in tool_uses:
                        result = await self._handle_tool_call(tool["name"], tool["id"], tool.get("input", {}))
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool["id"],
                            "content": json.dumps(result),
                        })

                    # Add tool results to conversation
                    self.conversation.append({"role": "user", "content": tool_results})

                    # Continue the loop — Claude will respond to the tool results
                    continue

                # No more tools — return the text response
                return " ".join(text_parts) if text_parts else None

        return None  # Exceeded max tool rounds
```

- [ ] **Step 3: Commit**

```bash
cd /home/will/react-crm-api
git add app/services/outbound_agent.py
git commit -m "feat: wire tool execution to real CRM actions (work orders, SMS, callbacks)"
```

---

### Task 4: Voicemail via Cartesia TTS

**Files:**
- Modify: `app/api/v2/outbound_agent.py` (the voice webhook, lines 121-195)

Replace the Twilio `<Say>` voicemail with Cartesia TTS streamed via a media stream.

- [ ] **Step 1: Update the voicemail path in the voice webhook**

In `app/api/v2/outbound_agent.py`, replace the voicemail handling block (inside `twilio_voice_webhook`, the `if answered_by in ("machine_start", ...)` block around lines 146-166) with:

```python
    if answered_by in ("machine_start", "machine_end_beep", "machine_end_silence"):
        logger.info(f"Voicemail detected for {to_number}")
        # Start media stream — the agent session will handle voicemail via Cartesia TTS
        ws_host = request.headers.get("host", "react-crm-api-production.up.railway.app")
        ws_url = f"wss://{ws_host}/ws/outbound-agent/{call_sid}"

        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '<Connect>'
            f'<Stream url="{ws_url}" />'
            '</Connect>'
            '</Response>'
        )

        # Create agent session in voicemail mode
        prospect = call_data["prospect"]
        quote = call_data["quote"]
        session = OutboundAgentSession(
            call_sid=call_sid,
            prospect=prospect,
            quote=quote,
        )
        session._voicemail_mode = True
        active_sessions[call_sid] = session
        remove_pending_call_data(to_number)
        return PlainTextResponse(twiml, media_type="text/xml")
```

- [ ] **Step 2: Add voicemail mode handling in the WebSocket handler**

In the `ws_outbound_agent_media` function, after the `await asyncio.sleep(1)` and `await session.start_greeting()` in the `event == "start"` block, add a voicemail check:

```python
            elif event == "start":
                stream_sid = msg.get("start", {}).get("streamSid")
                logger.info(f"Media stream started: streamSid={stream_sid}")

                if getattr(session, '_voicemail_mode', False):
                    # Voicemail mode — speak message via Cartesia, then hang up
                    await asyncio.sleep(2)  # Wait for beep
                    p = session.prospect
                    q = session.quote
                    line_items = q.get("line_items", [])
                    service = line_items[0].get("service", "septic service") if line_items else "septic service"
                    vm = (
                        f"Hi {p.get('first_name', '')}, this is MAC Septic following up "
                        f"on the estimate we sent for {service} at your property. "
                        f"Give us a call back at 615-345-2544 when you get a chance. Thanks!"
                    )
                    await speak(vm)
                    session.disposition = "voicemail_left"
                    session.transcript.append({"speaker": "agent", "text": f"[Voicemail] {vm}", "timestamp": datetime.utcnow().isoformat()})
                    await asyncio.sleep(2)  # Let audio finish
                    await end_call()
                else:
                    await asyncio.sleep(1)
                    await session.start_greeting()
                    _broadcast_transcript(call_sid, "agent", session.transcript[-1]["text"] if session.transcript else "")
```

- [ ] **Step 3: Commit**

```bash
cd /home/will/react-crm-api
git add app/api/v2/outbound_agent.py
git commit -m "feat: voicemail via Cartesia TTS instead of Twilio Say"
```

---

### Task 5: Save Recording URL from Twilio Status Callback

**Files:**
- Modify: `app/api/v2/outbound_agent.py` (the status callback, lines 198-219)

- [ ] **Step 1: Update the status callback to capture recording URL**

Replace the `twilio_status_callback` function:

```python
@router.post("/status")
async def twilio_status_callback(request: Request):
    """Twilio call status callback — captures recording URL and final status."""
    form = await request.form()
    call_sid = form.get("CallSid", "")
    status = form.get("CallStatus", "")
    recording_url = form.get("RecordingUrl", "")
    duration = form.get("CallDuration", "0")

    logger.info(f"Outbound call status: SID={call_sid} Status={status} Duration={duration}")

    if status in ("completed", "busy", "no-answer", "failed", "canceled"):
        session = active_sessions.get(call_sid)
        if session:
            if not session.disposition:
                if status == "no-answer":
                    session.disposition = "no_answer"
                elif status in ("busy", "failed"):
                    session.disposition = "no_answer"

            # Store recording URL and duration on the session for persistence
            if recording_url:
                session._recording_url = recording_url
            session._twilio_duration = int(duration) if duration else None

            session.ended = True

    return PlainTextResponse("OK")
```

- [ ] **Step 2: Update _persist_call to use recording URL**

In the `_persist_call` function (added in Task 2), after `duration = ...`, add:

```python
            # Use Twilio duration if available
            twilio_duration = getattr(session, '_twilio_duration', None)
            if twilio_duration:
                duration = twilio_duration

            recording_url = getattr(session, '_recording_url', None)
```

And add `recording_url=recording_url,` to the CallLog constructor.

- [ ] **Step 3: Commit**

```bash
cd /home/will/react-crm-api
git add app/api/v2/outbound_agent.py
git commit -m "feat: capture Twilio recording URL and duration in status callback"
```

---

### Task 6: Frontend — Live Transcript Panel + AI Work Order Badge

**Files:**
- Modify: `src/features/outbound-campaigns/pages/AIAgentDashboard.tsx`
- Modify: `src/features/workorders/components/WorkOrderCard.tsx`

- [ ] **Step 1: Add live transcript panel to AIAgentDashboard.tsx**

Add a new `LiveTranscript` component and render it in the dashboard. Insert this component definition before the `KPICard` function at the bottom of the file:

```tsx
function LiveTranscript({ callSid }: { callSid: string | null }) {
  const [lines, setLines] = useState<{ speaker: string; text: string; timestamp: string }[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const autoScroll = useRef(true);

  useEffect(() => {
    if (!callSid) {
      setLines([]);
      return;
    }

    const baseUrl = apiClient.defaults.baseURL?.replace("/api/v2", "") || "";
    const url = `${baseUrl}/api/v2/outbound-agent/live-transcript/${callSid}`;
    const eventSource = new EventSource(url, { withCredentials: true });

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "keepalive") return;
        setLines((prev) => [...prev, data]);
      } catch {}
    };

    return () => eventSource.close();
  }, [callSid]);

  useEffect(() => {
    if (autoScroll.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    autoScroll.current = scrollHeight - scrollTop - clientHeight < 50;
  };

  if (!callSid) {
    return (
      <div className="bg-bg-card rounded-xl border border-border p-5">
        <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">
          Live Transcript
        </h3>
        <p className="text-sm text-text-muted py-8 text-center">
          Transcript will appear when a call is active
        </p>
      </div>
    );
  }

  return (
    <div className="bg-bg-card rounded-xl border border-border p-5">
      <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4 flex items-center gap-2">
        Live Transcript
        <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
      </h3>
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="space-y-2 max-h-[400px] overflow-y-auto"
      >
        {lines.map((line, i) => (
          <div key={i} className="flex gap-2 text-sm">
            <span className={cn(
              "font-semibold shrink-0 w-20",
              line.speaker === "agent" ? "text-primary" : "text-emerald-600"
            )}>
              {line.speaker === "agent" ? "Sarah:" : "Customer:"}
            </span>
            <span className="text-text-primary">{line.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

Add `useRef` to the imports at the top:

```tsx
import { useState, useEffect, useCallback, useRef } from "react";
```

Then in the JSX, replace the existing 2-column grid (disposition + queue) with a 3-section layout. After the KPI cards grid, replace:

```tsx
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
```

with:

```tsx
      {/* Live Transcript */}
      <LiveTranscript callSid={status?.current_call_sid || null} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
```

- [ ] **Step 2: Add AI Booked badge to WorkOrderCard.tsx**

In `/home/will/ReactCRM/src/features/workorders/components/WorkOrderCard.tsx`, find where the status badge is rendered and add an AI badge next to it. Search for `WorkOrderStatusBadge` usage and add after it:

```tsx
{wo.created_by === "ai_agent" && (
  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400 border border-purple-200 dark:border-purple-800">
    <Bot className="w-3 h-3" />
    AI Booked
  </span>
)}
```

Import `Bot` from lucide-react at the top of the file.

Also add a purple left border for AI-created work orders. Find the outer card wrapper and add a conditional class:

```tsx
className={cn(
  "..existing classes...",
  wo.created_by === "ai_agent" && "border-l-4 border-l-purple-500"
)}
```

- [ ] **Step 3: Build frontend**

```bash
cd /home/will/ReactCRM && npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 4: Commit frontend**

```bash
cd /home/will/ReactCRM
git add src/features/outbound-campaigns/pages/AIAgentDashboard.tsx src/features/workorders/components/WorkOrderCard.tsx
git commit -m "feat: live transcript panel on AI agent dashboard + purple AI Booked badge on work orders"
```

---

### Task 7: Push Both Repos + Verify Deployment

**Files:** None (deployment task)

- [ ] **Step 1: Push backend**

```bash
cd /home/will/react-crm-api && git push origin master
```

- [ ] **Step 2: Push frontend**

```bash
cd /home/will/ReactCRM && git push origin master
```

- [ ] **Step 3: Wait for Railway deploys**

```bash
sleep 120
railway service react-crm-api && railway deployment list | head -3
railway service Mac-Septic-CRM && railway deployment list | head -3
```

Expected: Both show `SUCCESS`.

- [ ] **Step 4: Verify API health**

```bash
curl -s https://react-crm-api-production.up.railway.app/api/v2/outbound-agent/campaign/status | python3 -m json.tool
```

Expected: Returns campaign status JSON (running: false).

- [ ] **Step 5: Test with Playwright — navigate to /ai-agent and verify dashboard loads**

Navigate to `https://react.ecbtx.com/ai-agent`, verify:
- Dashboard loads with "AI Sales Agent" header
- Start Campaign button visible
- Queue shows prospects (or "No prospects" if none)
- Live Transcript panel visible with "Transcript will appear when a call is active"

---

### Task 8: End-to-End Test — Real Call

**Files:** None (testing task)

- [ ] **Step 1: Start a campaign via API**

```bash
curl -X POST https://react-crm-api-production.up.railway.app/api/v2/outbound-agent/campaign/start
```

Or click "Start Campaign" on the dashboard.

- [ ] **Step 2: Monitor the call**

Watch the live transcript panel. Verify:
- Agent greets by name, references the quote
- Customer speech is transcribed in real-time
- Agent responds naturally with <1s latency
- If customer says "book me in" → work order created with purple AI badge
- If voicemail → Cartesia TTS voicemail played, disposition set

- [ ] **Step 3: Verify call persistence**

After the call, check:
- `/call-library` shows the outbound call with transcript
- Work order (if booked) appears with purple "AI Booked" badge
- Campaign dashboard shows updated dispositions

- [ ] **Step 4: Stop campaign**

```bash
curl -X POST https://react-crm-api-production.up.railway.app/api/v2/outbound-agent/campaign/stop
```
