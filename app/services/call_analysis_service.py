"""
Voice AI Call Analysis Service

Pipeline: Recording → Whisper Transcription → Claude Analysis → Auto-draft Work Order
"""

import httpx
import logging
import io
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.call_log import CallLog
from app.models.customer import Customer
from app.models.work_order import WorkOrder
from app.config import settings
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)


def _format_phone(raw: str) -> str:
    """Normalize phone to (XXX) XXX-XXXX for DB lookup."""
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return raw or ""


async def analyze_call(call_log_id: str) -> None:
    """Full post-call AI pipeline."""
    async with async_session_maker() as db:
        result = await db.execute(select(CallLog).where(CallLog.id == call_log_id))
        call_log = result.scalar_one_or_none()
        if not call_log:
            logger.error(f"CallLog {call_log_id} not found")
            return

        if not call_log.recording_url:
            logger.warning(f"CallLog {call_log_id} has no recording URL")
            return

        # Step 1: Transcribe
        transcript = await _transcribe(call_log.recording_url)
        if not transcript:
            call_log.transcription_status = "failed"
            await db.commit()
            return

        call_log.transcription = transcript
        call_log.transcription_status = "completed"
        await db.commit()

        # Step 2: AI Analysis
        customer_context = ""
        if call_log.customer_id:
            cust_result = await db.execute(
                select(Customer).where(Customer.id == call_log.customer_id)
            )
            customer = cust_result.scalar_one_or_none()
            if customer:
                customer_context = (
                    f"Customer: {customer.first_name} {customer.last_name}, "
                    f"Address: {customer.address_line1}, {customer.city}, {customer.state}, "
                    f"System type: {customer.system_type or 'unknown'}, "
                    f"Manufacturer: {customer.manufacturer or 'unknown'}"
                )

        analysis = await _analyze_transcript(transcript, customer_context)
        if analysis:
            call_log.ai_summary = analysis.get("summary")
            call_log.sentiment = analysis.get("sentiment")
            call_log.sentiment_score = analysis.get("sentiment_score")
            call_log.topics = analysis.get("topics", [])
            call_log.analyzed_at = datetime.now(timezone.utc)
            call_log.escalation_risk = analysis.get("urgency")
            await db.commit()

            # Step 3: Auto-draft work order for scheduling/emergency
            intent = analysis.get("intent", "")
            if intent in ("scheduling", "emergency") and call_log.customer_id:
                await _create_draft_work_order(db, call_log, analysis)

        # Broadcast to frontend
        await manager.broadcast_event("call_analyzed", {
            "call_log_id": str(call_log_id),
            "has_transcript": bool(transcript),
            "has_analysis": bool(analysis),
        })


async def _transcribe(recording_url: str) -> str | None:
    """Transcribe recording using OpenAI Whisper API."""
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set, skipping transcription")
        return None

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Download recording from Twilio
            audio_resp = await client.get(
                recording_url,
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            )
            audio_resp.raise_for_status()

            # Send to Whisper
            whisper_resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                files={"file": ("recording.wav", io.BytesIO(audio_resp.content), "audio/wav")},
                data={"model": "whisper-1"},
            )
            whisper_resp.raise_for_status()
            return whisper_resp.json().get("text", "")

    except Exception as e:
        logger.error(f"Transcription failed: {type(e).__name__}: {e}")
        return None


async def _analyze_transcript(transcript: str, customer_context: str) -> dict | None:
    """Analyze transcript using Claude API."""
    api_key = settings.ANTHROPIC_API_KEY
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set, skipping analysis")
        return None

    prompt = f"""Analyze this septic service call transcript. Return ONLY valid JSON.

{f"Customer context: {customer_context}" if customer_context else "No customer context available."}

Transcript:
{transcript}

Return this exact JSON structure:
{{
  "intent": "scheduling|emergency|billing|complaint|inquiry",
  "sentiment": "positive|neutral|negative",
  "sentiment_score": <number -100 to 100>,
  "urgency": "low|medium|high|critical",
  "key_details": {{
    "address": "<if mentioned>",
    "system_type": "<if mentioned>",
    "symptoms": ["<list>"],
    "preferred_date": "<if mentioned>"
  }},
  "summary": "<2-3 sentence summary>",
  "topics": ["<list of topics>"]
}}"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            content = resp.json()["content"][0]["text"]

            import json
            # Extract JSON from response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
            return None

    except Exception as e:
        logger.error(f"Analysis failed: {type(e).__name__}: {e}")
        return None


async def _create_draft_work_order(db: AsyncSession, call_log: CallLog, analysis: dict) -> None:
    """Create a draft work order from call analysis."""
    import uuid

    intent = analysis.get("intent", "")
    key_details = analysis.get("key_details", {})

    wo = WorkOrder(
        id=uuid.uuid4(),
        customer_id=call_log.customer_id,
        job_type="emergency" if intent == "emergency" else "maintenance",
        priority="urgent" if intent == "emergency" else "normal",
        status="draft",
        notes=f"Auto-created from call analysis:\n{analysis.get('summary', '')}\n\nSymptoms: {', '.join(key_details.get('symptoms', []))}",
    )
    db.add(wo)
    await db.commit()
    logger.info(f"Draft work order created: {wo.id} for customer {call_log.customer_id}")
