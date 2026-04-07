# AI Outbound Sales Agent — Design Spec

**Date:** 2026-04-07
**Status:** Approved
**Scope:** Finish wiring the existing outbound agent pipeline

## Overview

Complete the MAC Septic CRM's AI outbound sales agent. The Twilio + Deepgram + Cartesia + Claude pipeline exists but tool handlers are stubs, there's no call persistence, no streaming STT, and no barge-in. This spec covers the 5 gaps to close.

## What Already Exists

- **Twilio call placement** with AMD voicemail detection (`campaign_dialer.py`)
- **Deepgram Nova-3 STT** — batch mode (`outbound_agent.py:_speech_to_text()`)
- **Cartesia Sonic TTS** with ElevenLabs fallback (`outbound_agent.py:_cartesia_tts()`)
- **Claude Haiku conversation engine** with 8 tool definitions (`outbound_agent.py:OutboundAgentSession`)
- **Campaign management API** — start/stop/pause/resume/status (`outbound_agent.py` REST endpoints)
- **WebSocket media stream** handler for Twilio audio (`outbound_agent.py` WS endpoint)
- **Frontend dashboard** with campaign controls and status polling (`AIAgentDashboard.tsx`)

## Gap 1: Streaming STT + Barge-in

**Replace** batch Deepgram calls with a persistent WebSocket per call.

### Deepgram Streaming Connection
- Open `wss://api.deepgram.com/v1/listen` when call connects
- Params: `model=nova-3`, `encoding=mulaw`, `sample_rate=8000`, `interim_results=true`, `utterance_end_ms=1200`
- Forward every Twilio media packet (raw bytes after base64 decode) directly to Deepgram
- On `is_final` transcript: send text to Claude
- On `utterance_end`: backup trigger if `is_final` was missed

### Barge-in
- Track `agent_is_speaking` boolean per session
- Set `true` when TTS audio starts flowing to Twilio, `false` when finished
- If Deepgram returns `is_final` while `agent_is_speaking`:
  1. Stop sending TTS packets to Twilio
  2. Send Twilio `clear` event to flush audio buffer
  3. Set `agent_is_speaking = false`
  4. Feed customer's interruption to Claude as next turn

### Latency Budget
Customer stops → Deepgram is_final (~300ms) → Claude (~400ms) → Cartesia first chunk (~200ms) → ~900ms total.

## Gap 2: Tool Execution

Wire the 8 Claude tools to real CRM actions.

| Tool | Action | Confirms with customer first? |
|------|--------|------------------------------|
| `get_prospect_details` | Read customer + quote + property + history from DB | No |
| `check_availability` | Query WorkOrder table for open slots in service zone, next 7 biz days | No |
| `book_appointment` | Create WorkOrder: `created_by="ai_agent"`, `source="outbound_campaign"` | Yes |
| `transfer_call` | Twilio `<Dial>` to +16153452544 | No |
| `create_callback` | Create AgentTask `type="follow_up_call"` with preferred time | Yes |
| `leave_voicemail` | Claude generates text → Cartesia TTS → play into Twilio (not `<Say>`) | No |
| `set_disposition` | Update CallLog with final disposition | No |
| `send_followup_sms` | Twilio SMS via existing `twilio_service.send_sms()` | Yes |

### Tool Result Flow
After execution, result (success/failure + data) is added to Claude conversation as `tool_result`. Claude knows whether the action succeeded and responds accordingly.

### AI Work Order Flag
- WorkOrder `created_by = "ai_agent"`
- WorkOrder `source = "outbound_campaign"`
- WorkOrder `notes` prefixed: `[AI Agent] Booked via outbound call on {date}`
- Frontend: purple left border + "AI Booked" badge on work order cards where `created_by == "ai_agent"`

## Gap 3: Call Persistence

Reuse existing `call_logs` table. No new migration for core data.

### Fields per call

| Field | Value |
|-------|-------|
| `direction` | `"outbound"` |
| `caller_number` | Outbound agent number |
| `called_number` | Prospect phone |
| `customer_id` | Prospect UUID |
| `call_disposition` | `appointment_set` / `callback_requested` / `transferred` / `voicemail_left` / `not_interested` / `no_answer` / `max_attempts` |
| `duration_seconds` | From Twilio status callback |
| `recording_url` | Twilio recording URL |
| `transcription` | Full timestamped transcript (both sides) |
| `ai_summary` | Claude 2-3 sentence summary |
| `sentiment` | Set by Claude during call |
| `notes` | Tool actions taken |
| `assigned_to` | `"ai_outbound_agent"` |

### Transcript Format
```
[00:00] Agent: Hi, this is Sarah calling from MAC Septic...
[00:05] Customer: Oh hey, yeah I got that quote...
```

### Recording
Twilio recording already enabled. Save URL from status callback to CallLog. Playback via existing `/ringcentral/recording/` proxy pattern (extend to support Twilio URLs too).

## Gap 4: Dashboard Live Transcript

Stream conversation to the frontend in real-time.

- Backend: broadcast transcript lines via existing WebSocket infrastructure or SSE
- Frontend `AIAgentDashboard.tsx`: add a live transcript panel showing the conversation as it happens
- Each line: timestamp, speaker (Agent/Customer), text
- Auto-scroll, with manual scroll-lock if user scrolls up

## Gap 5: Voicemail via Cartesia

Replace Twilio `<Say>` with Cartesia TTS for voicemail messages.

- When AMD detects voicemail: Claude generates personalized voicemail text using prospect data
- Text → Cartesia TTS → mu-law audio → stream into Twilio media
- Wait for audio to finish, then hang up
- Save disposition as `voicemail_left`

## Tech Stack (Final)

| Layer | Technology |
|-------|-----------|
| Calling | Twilio Voice + Media Streams |
| STT | Deepgram Nova-3 Streaming WebSocket |
| TTS | Cartesia Sonic (primary), ElevenLabs (fallback) |
| AI Brain | Claude Haiku 4.5 |
| Backend | FastAPI + SQLAlchemy + PostgreSQL |
| Frontend | React + TanStack Query + Zustand |

## Files to Modify

### Backend (`/home/will/react-crm-api/`)
- `app/api/v2/outbound_agent.py` — streaming STT, barge-in, live transcript broadcast, call persistence
- `app/services/outbound_agent.py` — tool execution wiring, Deepgram streaming, voicemail via Cartesia
- `app/services/campaign_dialer.py` — minor: save CallLog on call complete

### Frontend (`/home/will/ReactCRM/`)
- `src/features/outbound-campaigns/pages/AIAgentDashboard.tsx` — live transcript panel, enhanced stats
- Work order components — purple "AI Booked" badge where `created_by == "ai_agent"`

## Out of Scope
- A/B testing scripts/voices
- Campaign scheduling UI
- Lead scoring integration
- Email follow-up automation
- Call performance analytics beyond disposition counts
