# Outbound Voice Agent — Pipecat Rewrite

**Date:** 2026-04-28
**Project:** react-crm-api (MAC Septic CRM backend)
**Status:** Design — pending user review
**Supersedes:** docs/superpowers/specs/2026-04-07-outbound-sales-agent-design.md (initial DIY implementation)

## Context

The MAC Septic outbound sales agent ("Sarah") was first built 2026-04-07 as a hand-rolled Twilio Media Streams → Deepgram → Claude → ElevenLabs loop in `app/services/outbound_agent.py`. Seven test calls were made that day (all to Will's cell at +1-979-236-1958). The agent has not run since.

Reviewing those seven transcripts surfaces failure modes that make the agent unusable in front of real prospects:

| # | Failure | Evidence |
|---|---------|----------|
| 1 | 5–8s greeting delay | Every call: greeting at [00:05]–[00:08], no audio before |
| 2 | 3–12s mid-turn lag | Call 16:00:04 — customer at [00:55], agent reply at [01:07] |
| 3 | Bad turn detection — fragments treated as final turns | Call 15:17:01 — "the foam the phone", "in regards to the" each fired separate replies |
| 4 | Hallucinated tool use — "I just sent you a text" without calling `send_followup_sms` | Call 16:00:04 [00:51] |
| 5 | Recovery loops on bad audio without ever ending the call | Call 16:07:53 — agent cycled "want me to call back?" 4 times |
| 6 | No graceful identity disclosure when audio quality is questioned | Multiple calls — "Never say I'm an AI" prompt rule has no fallback |
| 7 | Voice character harsh over Twilio μ-law 8kHz codec | All calls — ElevenLabs Multilingual v2 not optimized for phone |

User-ranked priority: **A (latency) → F (voice quality) → B (turn detection) → C (hallucination + tools) → D (disposition + hangup) → E (identity)**.

## Goal

Replace the hand-rolled audio loop in `outbound_agent.py` and `app/api/v2/outbound_agent.py` with a Pipecat-orchestrated pipeline that hits managed-platform quality (Vapi/Retell parity) without managed-platform per-minute cost. Keep all business logic — campaign dialer, tool implementations, DB persistence, smart caller-ID routing — exactly as-is.

## Non-Goals

To keep this shippable in 1–2 weeks:

- Multi-agent orchestration / specialist routing — single Sarah persona only
- New tool surface — keep all 8 existing tools, add none
- Inbound call handling — outbound only; Crown Hardware inbound is a separate codebase
- Call analytics dashboard rebuild — existing CRM call review UI keeps its current shape, only gets better data flowing in
- Multilingual support — English only
- Custom voice cloning — pick a stock Cartesia voice now; clone Sarah only if a follow-up requires it
- Tiered model routing — single LLM (Sonnet 4.6), no Haiku fallback
- Per-prospect TTS personalization

## Architecture

### What stays

| Component | Location | Reason |
|---|---|---|
| Campaign dialer + prospect queue + retry logic | `app/services/campaign_dialer.py` | Works fine, has tests |
| All 8 tool implementations | `app/services/outbound_agent.py` (`_handle_tool_call`, `_send_followup_sms`, `_book_appointment`, etc.) | Real, wired, tested |
| Twilio webhooks (TwiML, status callback) and campaign endpoints | `app/api/v2/outbound_agent.py` | Battle-tested, contract with Twilio is correct |
| `CallLog` persistence + `_persist_call` writer | `app/api/v2/outbound_agent.py:_persist_call` | Schema is correct |
| Smart caller-ID routing (TN_NASHVILLE / TN_COLUMBIA / TX_AUSTIN) | `app/services/campaign_dialer.py` | Shipped 2026-04-27, must keep working |
| Live transcript SSE pub/sub | `app/api/v2/outbound_agent.py:_transcript_listeners` | Frontend depends on this |

### What changes

The hand-rolled WebSocket handler that owns the audio loop today gets replaced with a Pipecat `Pipeline`. Same FastAPI process, same Railway service.

#### New pipeline (top-down through the audio path)

```
Twilio Media Stream WS (μ-law 8kHz, base64 over JSON)
  ↓
TwilioFrameSerializer  (μ-law → PCM in, PCM → μ-law out)
  ↓
SileroVADAnalyzer  (turn detection, barge-in trigger)
  ↓
DeepgramSTTService
    endpointing=300ms
    utterance_end_ms=1000ms
    interim_results=true (consumed for VAD only, never as turn)
    model=nova-3
  ↓
LLMUserContextAggregator  (assembles user message from finalized utterances)
  ↓
AnthropicLLMService
    model=claude-sonnet-4-6
    streaming=true
    tools=AGENT_TOOLS (existing 8)
    system + tools cached via cache_control: {type: "ephemeral"}
  ↓
ToolRouter  (dispatches tool_use blocks → existing _handle_tool_call → results back into context)
  ↓
SentenceAggregator  (chunks streamed tokens at . ? ! boundaries)
  ↓
CartesiaTTSService
    model=sonic-2
    voice_id=<picked during local tuning — selection criteria: warm female voice, natural Southern US cadence, sub-100ms TTFB; shortlist 3 candidates from Cartesia's voice library, A/B on the same test prospect call, Will picks>
    sample_rate=24000
    streaming=true
  ↓
TwilioFrameSerializer  (PCM → μ-law 8kHz)
  ↓
Twilio Media Stream WS (out)
```

#### Sidecar: `OutboundAgentSession`

Lives alongside the Pipeline as the holder of business state and DB persistence. Pipecat's frame observer hooks call into it at:

- Pipeline start → seed prospect/quote context, increment campaign counters
- Each LLM completion → run hallucination guard (see below), update state machine counters
- Tool call → log to `agent_task` table for audit
- Pipeline end → write `call_logs` row via existing `_persist_call`

The class signature stays close to today's so `campaign_dialer.py` doesn't change.

### Greeting prerender

The 5–8s greeting delay is the single biggest user-visible win. It happens because today's flow is: Twilio Media Stream connects → wait for first audio buffer → call Claude → wait for full response → call ElevenLabs → wait for full TTS → play. Six round trips before the customer hears a syllable.

New flow: at the moment `campaign_dialer.py` initiates a Twilio outbound call, we know the prospect name and quote service type. Render the greeting TTS (Cartesia) into an in-memory buffer immediately, parameterized:

> "Hi {first_name}, this is Sarah calling from MAC Septic. We sent you an estimate for {service_type} and I just wanted to follow up — do you have a minute?"

When the Media Stream connects (~3–5s after dial), the prerendered audio is buffered and ready BUT held until the Twilio AMD result arrives (next section). Holding 0–500ms longer than stream connect is the right tradeoff: greeting an answering machine with a friendly "Hi James, this is Sarah" causes more failure (machine hears us mid-beep) than a tiny extra hold does on a human pickup. On AMD = `human` the buffer plays first frame within ~150ms. On AMD = `machine_end_beep` the buffer is discarded and the voicemail flow runs instead.

Conversation engine takes over after the greeting completes; the greeting text is appended to the Claude context as the first assistant turn so subsequent reasoning has continuity.

## Conversation Behavior

### System prompt rewrite

Three rules added to the existing prompt to fix specific failure modes:

#### Rule 1: Strict tool-use discipline

> If you describe an action you are taking ("I just sent you a text", "I'll book you for Tuesday morning", "Let me transfer you"), you MUST call the corresponding tool in the SAME turn before claiming it. Tool first, words second. If you don't have a tool for what the customer is asking, say so honestly and offer to transfer to the office.

Eliminates the SMS hallucination class.

#### Rule 2: Audio-quality escape hatch

> If the customer mentions audio quality, voice quality, delay, echo, or asks if you're a robot/AI more than once: acknowledge it once, offer to text the quote details (call `send_followup_sms`), then call `set_disposition('callback_requested', ...)` and `end_call`. Do NOT loop on apologies or repeated "want me to call back?" prompts.

Kills the recovery-loop pattern.

#### Rule 3: Honest identity disclosure

Replace the current "Never say I'm an AI" with:

> You are Sarah, the AI scheduling assistant for MAC Septic. If asked directly whether you're a real person or an AI, answer honestly in one sentence ("I'm Sarah, MAC Septic's AI assistant — I help with scheduling and quote questions"), then continue the conversation normally. Never claim to be human.

Honest disclosure beats hollow reassurance. Pretending to be human while having TTS tells is what made the test calls feel terrible.

Persona, brand voice, services list, pricing tiers, call-flow steps all stay as in `outbound_agent.py:SYSTEM_PROMPT`.

### State machine

`OutboundAgentSession` tracks four counters. When any threshold trips, the session injects a system message into the Claude context for the next turn so the LLM produces the correct closing line, then enforces the action regardless of what the model returns.

| Counter | Soft threshold | Hard threshold | Action at hard threshold |
|---|---|---|---|
| `audio_quality_complaints` | n/a | ≥ 2 | Force `send_followup_sms` (template: "Hi {name}, here's your quote: {quote_url}. Reply STOP to opt out.") + `set_disposition('callback_requested')` + `end_call` |
| `silent_seconds_after_agent_turn` | ≥ 8s — prompt "Are you still there?" once | ≥ 15s | `set_disposition('no_answer')` + `end_call` |
| `tool_call_failures_in_a_row` | n/a | ≥ 2 | `transfer_call` to office |
| `total_call_seconds` | ≥ 240 (4 min) — soft prompt to wrap up | ≥ 360 (6 min) | Force `set_disposition` with the disposition matching the highest-progress signal seen so far (booked → `appointment_set`, callback discussed → `callback_requested`, transfer mentioned → `transferred_to_sales`, otherwise → `callback_requested`) + `end_call` |

Counters live on the session object. Each forced action is implemented by calling the corresponding tool directly from `OutboundAgentSession`, bypassing the LLM, then injecting a final system message ("Wrap up the call gracefully now") for the closing utterance.

### Hallucination guard (defense in depth)

On every Claude response, before the text is handed to the SentenceAggregator → TTS:

```python
HALLUCINATION_PATTERNS = [
    r"\bI('ve| just)?\s+sent\s+(you\s+)?(a|the)\s+(text|message|email)",
    r"\bI('ll| will)\s+(text|email|book|schedule|call back at)",
    r"\bI('ve| just|'m)?\s*(booking|booked|scheduling|scheduled)\s+",
    r"\bI('m| am)?\s*transferring\s+you",
]
```

If the response matches any pattern AND the LLM turn contains no `tool_use` block whose tool name maps to that pattern (mapping table: `sent.*text|message` → `send_followup_sms`, `book(ing|ed)|schedul(e|ed|ing)` → `book_appointment` or `create_callback`, `transferring` → `transfer_call`, `text|email` future tense → `send_followup_sms`), the guard:

1. Replaces the offending sentence in the assistant message with a soft alternative ("Let me check on that for you") via `re.sub` BEFORE it reaches the SentenceAggregator → TTS.
2. Increments `OutboundAgentSession.hallucination_count` and writes the original + rewritten text to a new `hallucinations` JSON field on the `call_logs` row at call end.
3. Injects a system message into the next Claude turn: `"You said you would [action] but did not call the tool. Either call the tool now or tell the customer you need to follow up."` This nudges Claude to self-correct rather than repeat.

The prompt rule prevents this in most cases; the guard catches misses without breaking the user-perceived flow.

## Latency Budget

Target: **mean turn latency 600–800ms** (customer finishes speaking → first audio out). p95 ≤ 1.2s.

| Hop | Today (measured/estimated) | Target | How |
|---|---|---|---|
| Greeting (call connect → first audible word) | 5–8s | < 800ms | Prerender Cartesia TTS at dial time; play on Media Stream connect |
| STT endpointing | ~1100ms (Deepgram default) | 300ms | Deepgram `endpointing=300`, `utterance_end_ms=1000` |
| VAD / barge-in | none | < 50ms | Silero VAD on Pipecat input; speech-start during TTS cancels playback frame, flushes Cartesia stream |
| LLM TTFT | 600–2000ms (cold), often higher | 200–400ms | Anthropic prompt caching: system prompt + tool defs + persona block all marked `cache_control: {type: "ephemeral"}` |
| LLM → TTS handoff | wait for full response | first sentence streams immediately | Pipecat `SentenceAggregator` flushes to Cartesia on `.`, `?`, `!` |
| TTS TTFB | 800–1500ms (ElevenLabs v2) | < 100ms | Cartesia Sonic-2 streaming WebSocket |
| Network (Twilio ↔ Railway) | ~150ms RTT | unchanged | Pin Railway service to `us-east` to stay close to Twilio ATL/IAD edges |

### Anti-fragmentation rules (kills "the foam the phone")

Two rules in the LLMUserContextAggregator wrapper:

1. Ignore Deepgram interim results entirely as turn boundaries. Only act on `speech_final=true` OR `UtteranceEndEvent`.
2. Reject finalized utterances that are < 3 words AND < 800ms duration UNLESS they end with a question mark. These are usually mid-thought fragments, not real turns. Add the fragment text to a buffer and merge with the next finalized utterance instead of treating each as its own turn.

### Voicemail detection

Use Twilio Answering Machine Detection on the outbound dial:

```
MachineDetection=DetectMessageEnd
AsyncAmd=true
AsyncAmdStatusCallback=https://api.macseptic.com/api/v2/outbound-agent/amd
```

Twilio fires the AMD result ~3.5s after answer. Three branches:

- `human` → start the Pipecat agent normally; greeting prerender is already buffered and ready
- `machine_end_beep` → trigger the existing `leave_voicemail` tool flow (templated TTS: "Hi {name}, this is Sarah from MAC Septic following up on your quote — please give us a call back at {office_number}. Thanks!"), then hang up
- `unknown` → start the agent but tag `call_logs.notes` with `amd_unknown=true` for review

The 3.5s AMD wait runs in parallel with greeting prerender, so it adds zero latency on `human` outcomes.

## Tool Surface (unchanged)

All 8 existing tools stay exactly as-is. Quick inventory for completeness:

| Tool | Purpose | Notes |
|---|---|---|
| `check_availability` | Check appointment slots in next 7 days | Read-only |
| `book_appointment` | Create work order in CRM | Writes |
| `transfer_call` | Hand off to MAC Septic office | Twilio dial verb |
| `create_callback` | Schedule callback at specific time | Writes |
| `set_disposition` | Set call outcome before hangup | One of 9 enums |
| `leave_voicemail` | Play templated voicemail | Triggered by AMD or LLM |
| `end_call` | Hang up | Always after `set_disposition` |
| `send_followup_sms` | Twilio SMS to prospect | Real, wired |

The hallucination guard makes prompt rule #1 a hard constraint without needing new tools.

## Testing & Iteration

### Local dev (where 80% of tuning happens)

- Branch: `voice-agent-pipecat` off `react-crm-api/main`
- New entrypoint: `python -m app.services.pipecat_agent_dev` boots a tiny FastAPI that wires the Pipecat pipeline + receives Twilio webhooks
- `ngrok http 8000` exposes localhost
- A second Twilio number `+1-737-xxx-DEV` (separate from prod caller-IDs) points its Voice webhook at the ngrok URL
- A `is_test_prospect` boolean is added to the prospect rows. Three seeded test rows: Will's cell with three quote scenarios (repair, inspection, pumping)
- Test campaigns filter `is_test_prospect=true`; real campaigns filter `is_test_prospect=false OR null`
- Iteration: edit code → restart `pipecat_agent_dev` → redial via the dev campaign endpoint → ~5s loop

### Tuning rig — `scripts/voice_eval.py`

Records every test call's full Pipecat frame log with timestamps for:

- VAD speech-start / speech-end
- STT interim and final
- LLM TTFT and total time
- TTS TTFB and total time
- Audio out frames

Writes per-turn latency to `voice_eval_runs/{call_sid}.json` and generates a markdown summary: greeting latency, mean/p95 turn latency, barge-in success rate, hallucinations caught, recovery-loop count.

**Merge gate (local):** 10 consecutive test calls with mean turn latency < 800ms, p95 < 1.2s, zero hallucinations, zero recovery loops, clean voicemail handling on a deliberate "send to voicemail" call.

### Pre-prod verification (Railway preview)

- PR opens against `main` → Railway preview environment auto-deploys
- Run the same flow against the preview URL: 5 test calls
- **Merge gate (preview):** mean turn latency < 900ms (allows for Railway routing overhead vs local), all other gates same as local

### Production rollout

- Feature flag: `VOICE_AGENT_ENGINE` env var on `react-crm-api`. Values: `legacy` | `pipecat`
- Deploy with `legacy` initially → smoke-test the deploy didn't break the campaign endpoint
- Flip env var to `pipecat` → run a 5-call test campaign against `is_test_prospect=true` rows (Will's cell)
- If clean → run a 20-prospect real campaign in Nashville with Will live-monitoring the SSE transcript
- Keep the `legacy` code path behind the flag for 2 weeks as rollback insurance, then delete

## Dependencies & Environment

### New Python deps (add to `requirements.txt`)

```
pipecat-ai[anthropic,deepgram,cartesia,silero,twilio]>=0.0.50
```

Pipecat pulls in extras for the providers we use. Existing `httpx`, `anthropic`, FastAPI, etc. stay.

### New env vars (Railway dashboard)

| Var | Purpose |
|---|---|
| `CARTESIA_API_KEY` | Cartesia auth |
| `CARTESIA_VOICE_ID` | Picked voice (TBD during local tuning) |
| `VOICE_AGENT_ENGINE` | Feature flag: `legacy` or `pipecat` |
| `OUTBOUND_AGENT_AMD_CALLBACK` | Twilio AsyncAmd webhook URL |

Existing `DEEPGRAM_API_KEY`, `ANTHROPIC_API_KEY`, `TWILIO_*`, `OUTBOUND_AGENT_FROM_NUMBER`, `TWILIO_PHONE_NUMBER_TN_NASHVILLE/TN_COLUMBIA/TX_AUSTIN` all stay. `ELEVENLABS_API_KEY` becomes unused but stays in case of rollback.

### Provider sign-up

- Cartesia account + API key — needed before local tuning starts
- No other new accounts; Anthropic/Deepgram/Twilio already in place

## Risk & Rollback

| Risk | Mitigation |
|---|---|
| Pipecat version churn breaks the pipeline | Pin to specific minor version in `requirements.txt`; only bump intentionally |
| Cartesia voice doesn't match Sarah's expected character | Pick voice during local tuning before any real campaign; keep ElevenLabs path available behind a TTS provider flag if needed in a follow-up |
| Twilio AMD adds latency or false-positives "machine" on real humans | `unknown` branch starts the agent anyway with a tag; review tagged calls weekly |
| Prompt cache invalidates more often than expected and TTFT regresses | Voice eval rig measures TTFT per turn; if cache hit rate drops, investigate |
| Production regression after flag flip | `VOICE_AGENT_ENGINE=legacy` flips back instantly; legacy code path lives 2 weeks |
| Railway us-east region full / slow | Latency budget has slack for ~250ms network; if regional outage, can fail to us-west with measured impact |

## Success Criteria

After production rollout:

1. Mean turn latency on real prospect calls < 900ms (measured via voice_eval frame logs)
2. p95 turn latency < 1.5s
3. Greeting latency < 1s on > 95% of calls
4. Zero hallucinated tool claims in the first 100 production calls (measured via hallucination guard counter)
5. Zero stuck recovery loops — every call ends in a real disposition + hangup, not silence timeout
6. At least one booked appointment from a real campaign (signal that the agent is conversational enough to close)

## Implementation Order (preview — full plan in writing-plans output)

1. Pipecat + Cartesia setup, baseline pipeline that echoes greeting and ends — proves the audio loop
2. Wire Deepgram + Silero VAD + Anthropic — first end-to-end conversation
3. Port `AGENT_TOOLS` and `_handle_tool_call` to Pipecat's tool router
4. Greeting prerender + Twilio AMD branch
5. State machine + hallucination guard
6. Voice eval rig (`scripts/voice_eval.py`)
7. Anti-fragmentation rules + barge-in tuning
8. Feature flag + preview deploy
9. Production rollout
10. Two-week soak then delete legacy path
