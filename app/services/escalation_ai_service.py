"""
Escalation AI Service - The "What Do I Do Now?" Brain

This service provides AI-guided escalation management designed to be
"so simple a 12-year-old can achieve 95% CSAT and 85 NPS"

Key capabilities:
- Sentiment analysis and emotion detection
- Recommended action with confidence scores
- Dynamic script generation based on customer context
- Playbook matching and guidance
- Success prediction
- Proactive alerts for at-risk escalations
"""

import logging
import json
import re
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_gateway import ai_gateway
from app.models.customer_success import Escalation, EscalationNote
from app.models.customer import Customer

logger = logging.getLogger(__name__)


class UrgencyLevel(str, Enum):
    IMMEDIATE = "immediate"  # Call within 15 minutes
    URGENT = "urgent"        # Call within 1 hour
    HIGH = "high"            # Call within 4 hours
    NORMAL = "normal"        # Call within 24 hours


class ActionType(str, Enum):
    CALL = "call"
    EMAIL = "email"
    SCHEDULE_MEETING = "schedule_meeting"
    SEND_APOLOGY = "send_apology"
    OFFER_DISCOUNT = "offer_discount"
    ESCALATE_TO_MANAGER = "escalate_to_manager"
    ASSIGN_SENIOR_REP = "assign_senior_rep"
    FOLLOW_UP = "follow_up"


class SentimentEmoji(str, Enum):
    FURIOUS = "😤"
    ANGRY = "😠"
    FRUSTRATED = "😒"
    CONCERNED = "😟"
    NEUTRAL = "😐"
    SATISFIED = "😊"
    DELIGHTED = "😄"


@dataclass
class SentimentResult:
    """Result from sentiment analysis."""
    score: float  # -1 to 1 (negative to positive)
    label: str    # "Very Frustrated", "Neutral", "Happy", etc.
    emoji: str    # Visual indicator
    confidence: float  # 0 to 1
    key_phrases: List[str]  # Detected emotional phrases


@dataclass
class RecommendedAction:
    """AI-recommended action to take."""
    action_type: str
    urgency: str
    reason: str
    predicted_success: float  # 0 to 1
    time_estimate_minutes: int


@dataclass
class ScriptGuidance:
    """Exact words to say/write."""
    opening: str
    key_points: List[str]
    empathy_statements: List[str]
    closing: str
    what_not_to_say: List[str]


@dataclass
class EscalationGuidance:
    """Complete AI guidance for an escalation - the 'WHAT DO I DO NOW?' answer."""
    summary: str
    sentiment: SentimentResult
    recommended_action: RecommendedAction
    script: ScriptGuidance
    win_condition: str  # What success looks like
    similar_cases: List[Dict[str, Any]]
    playbook_id: Optional[int]
    playbook_name: Optional[str]
    priority_score: int  # 1-100, higher = more urgent


# Playbook definitions - these match common escalation patterns
PLAYBOOKS = {
    "customer_threatening_cancel": {
        "name": "Customer Threatening to Cancel",
        "trigger_keywords": ["cancel", "leaving", "competitor", "done", "quit", "switch"],
        "success_rate": 0.87,
        "steps": [
            {"order": 1, "action": "call", "description": "Call immediately - within 15 minutes", "script": "I understand your frustration, and I'm personally taking ownership of this."},
            {"order": 2, "action": "listen", "description": "Let them fully express their frustration", "script": "Tell me everything that's happened. I want to understand."},
            {"order": 3, "action": "acknowledge", "description": "Acknowledge without making excuses", "script": "You're right to be upset. This is not the experience you deserve."},
            {"order": 4, "action": "resolve", "description": "Offer concrete resolution", "script": "Here's exactly what I'm going to do to fix this..."},
            {"order": 5, "action": "goodwill", "description": "Add goodwill gesture", "script": "And as a thank you for your patience, I'd like to offer..."},
            {"order": 6, "action": "follow_up", "description": "Schedule follow-up within 24h", "script": "I'll personally call you tomorrow to make sure everything is resolved."},
        ],
    },
    "billing_dispute": {
        "name": "Billing Dispute",
        "trigger_keywords": ["overcharged", "billing", "invoice", "charged", "refund", "payment"],
        "success_rate": 0.92,
        "steps": [
            {"order": 1, "action": "review", "description": "Review all charges in detail", "script": "Let me pull up your account and review every charge with you."},
            {"order": 2, "action": "identify", "description": "Identify the discrepancy", "script": "I see the issue - let me explain exactly what happened."},
            {"order": 3, "action": "resolve", "description": "Calculate correct amount/refund", "script": "You're owed $X, and I'm processing that credit right now."},
            {"order": 4, "action": "confirm", "description": "Confirm resolution", "script": "You should see this reflected within 3-5 business days."},
            {"order": 5, "action": "document", "description": "Send written confirmation", "script": "I'm sending you an email confirmation with all the details."},
        ],
    },
    "service_quality_complaint": {
        "name": "Service Quality Complaint",
        "trigger_keywords": ["poor service", "bad experience", "unprofessional", "rude", "late", "no-show"],
        "success_rate": 0.85,
        "steps": [
            {"order": 1, "action": "acknowledge", "description": "Acknowledge the issue sincerely", "script": "I'm so sorry you experienced this. This is not who we are."},
            {"order": 2, "action": "redo", "description": "Offer redo at no charge", "script": "I'd like to schedule a new service at no additional cost."},
            {"order": 3, "action": "priority", "description": "Assign senior technician", "script": "I'm assigning our senior technician to handle this personally."},
            {"order": 4, "action": "discount", "description": "Offer goodwill discount", "script": "And I'd like to offer 20% off your next service."},
            {"order": 5, "action": "follow_up", "description": "Call same day after service", "script": "I'll call you right after to make sure everything went perfectly."},
        ],
    },
    "missed_appointment": {
        "name": "Missed Appointment",
        "trigger_keywords": ["missed", "no show", "never came", "stood up", "waited"],
        "success_rate": 0.91,
        "steps": [
            {"order": 1, "action": "apologize", "description": "Sincerely apologize", "script": "I am truly sorry we missed your appointment. That's completely unacceptable."},
            {"order": 2, "action": "prioritize", "description": "Offer next available priority slot", "script": "I'm putting you at the top of tomorrow's schedule."},
            {"order": 3, "action": "discount", "description": "Apply automatic discount", "script": "I'm applying a 25% discount for the inconvenience."},
            {"order": 4, "action": "confirm", "description": "Double-confirm new appointment", "script": "You'll receive a confirmation text and call 1 hour before."},
            {"order": 5, "action": "prevent", "description": "Add notes to prevent recurrence", "script": "I've flagged your account for VIP treatment."},
        ],
    },
    "executive_escalation": {
        "name": "Executive Escalation",
        "trigger_keywords": ["ceo", "manager", "supervisor", "owner", "executive", "lawyer", "attorney", "legal"],
        "success_rate": 0.78,
        "steps": [
            {"order": 1, "action": "alert", "description": "Notify VP/Director within 15 min", "script": "I'm escalating this to our leadership team immediately."},
            {"order": 2, "action": "prepare", "description": "Prepare comprehensive summary", "script": "Compiling full history and proposed resolution."},
            {"order": 3, "action": "contact", "description": "Executive reaches out within 2h", "script": "Our [VP/Director] will personally call you within 2 hours."},
            {"order": 4, "action": "resolve", "description": "Resolve with executive authority", "script": "We have full authority to make this right."},
            {"order": 5, "action": "follow_up", "description": "Executive follow-up in 7 days", "script": "Our leadership will personally check in next week."},
        ],
    },
}


class EscalationAIService:
    """
    AI Brain for escalation guidance - designed to make the right action obvious.

    Philosophy: Every screen should answer "WHAT DO I DO RIGHT NOW?" in 3 seconds.
    """

    def __init__(self):
        self.ai = ai_gateway

    async def get_guidance(
        self,
        db: AsyncSession,
        escalation_id: int,
    ) -> Dict[str, Any]:
        """
        Get complete AI guidance for an escalation.

        Returns the 'WHAT DO I DO NOW?' answer with:
        - Summary of the situation
        - Customer sentiment analysis
        - Recommended action with exact words to say
        - Success prediction
        - What NOT to do
        """
        # Fetch escalation with related data
        result = await db.execute(
            select(Escalation).where(Escalation.id == escalation_id)
        )
        escalation = result.scalar_one_or_none()

        if not escalation:
            return {"error": "Escalation not found"}

        # Fetch customer data
        customer_result = await db.execute(
            select(Customer).where(Customer.id == escalation.customer_id)
        )
        customer = customer_result.scalar_one_or_none()

        # Fetch notes for sentiment context
        notes_result = await db.execute(
            select(EscalationNote)
            .where(EscalationNote.escalation_id == escalation_id)
            .order_by(EscalationNote.created_at.desc())
            .limit(10)
        )
        notes = notes_result.scalars().all()

        # Build context for AI analysis
        context = self._build_context(escalation, customer, notes)

        # Analyze sentiment from description and notes
        sentiment = await self._analyze_sentiment(context)

        # Match to playbook
        playbook = self._match_playbook(context)

        # Generate recommended action
        action = await self._get_recommended_action(escalation, customer, sentiment, playbook)

        # Generate script
        script = await self._generate_script(escalation, customer, sentiment, playbook)

        # Calculate priority score
        priority_score = self._calculate_priority_score(escalation, customer, sentiment)

        # Find similar cases
        similar_cases = await self._find_similar_cases(db, escalation)

        # Build the guidance response
        return {
            "escalation_id": escalation_id,
            "summary": self._generate_summary(escalation, customer, sentiment),
            "sentiment": {
                "score": sentiment.score,
                "label": sentiment.label,
                "emoji": sentiment.emoji,
                "confidence": sentiment.confidence,
                "key_phrases": sentiment.key_phrases,
            },
            "recommended_action": {
                "type": action.action_type,
                "urgency": action.urgency,
                "urgency_minutes": self._urgency_to_minutes(action.urgency),
                "reason": action.reason,
                "predicted_success": action.predicted_success,
                "time_estimate_minutes": action.time_estimate_minutes,
                "big_button_text": self._get_big_button_text(action),
            },
            "script": {
                "opening": script.opening,
                "key_points": script.key_points,
                "empathy_statements": script.empathy_statements,
                "closing": script.closing,
                "what_not_to_say": script.what_not_to_say,
            },
            "win_condition": self._get_win_condition(escalation, playbook),
            "playbook": {
                "id": playbook.get("id") if playbook else None,
                "name": playbook.get("name") if playbook else None,
                "success_rate": playbook.get("success_rate") if playbook else None,
                "steps": playbook.get("steps", []) if playbook else [],
            } if playbook else None,
            "similar_cases": similar_cases,
            "priority_score": priority_score,
            "sla_status": self._get_sla_status(escalation),
            "customer_context": {
                "name": customer.name if customer else "Unknown",
                "tenure_days": (datetime.utcnow() - customer.created_at).days if customer and customer.created_at else 0,
                "lifetime_value": getattr(customer, 'lifetime_value', None) or getattr(customer, 'revenue', None) or 0,
                "past_escalations": 0,  # Would need to query
            },
        }

    def _build_context(
        self,
        escalation: Escalation,
        customer: Optional[Customer],
        notes: List[EscalationNote],
    ) -> str:
        """Build context string for AI analysis."""
        parts = [
            f"Title: {escalation.title}",
            f"Description: {escalation.description}",
            f"Type: {escalation.escalation_type}",
            f"Severity: {escalation.severity}",
        ]

        if customer:
            parts.append(f"Customer: {customer.name}")
            if hasattr(customer, 'created_at') and customer.created_at:
                tenure_days = (datetime.utcnow() - customer.created_at).days
                parts.append(f"Customer tenure: {tenure_days} days")

        if notes:
            parts.append("\nRecent notes:")
            for note in notes[:5]:
                parts.append(f"- {note.content[:200]}")

        return "\n".join(parts)

    async def _analyze_sentiment(self, context: str) -> SentimentResult:
        """
        Analyze customer sentiment from escalation context.
        Returns detailed sentiment analysis with emotional indicators.
        """
        # Use AI gateway for sentiment analysis
        result = await self.ai.analyze_sentiment(context)

        # Convert to our structured format
        raw_sentiment = result.get("sentiment", "neutral")
        raw_score = float(result.get("score", 0.5))

        # Map to our scale (-1 to 1)
        if raw_sentiment == "positive":
            score = raw_score * 0.5 + 0.5  # 0.5 to 1
            label, emoji = self._get_positive_label(score)
        elif raw_sentiment == "negative":
            score = -1 * raw_score  # -1 to 0
            label, emoji = self._get_negative_label(score)
        else:
            score = 0
            label = "Neutral"
            emoji = SentimentEmoji.NEUTRAL.value

        # Extract key phrases indicating emotion
        key_phrases = self._extract_emotional_phrases(context)

        return SentimentResult(
            score=score,
            label=label,
            emoji=emoji,
            confidence=0.85,  # Default confidence
            key_phrases=key_phrases,
        )

    def _get_positive_label(self, score: float) -> tuple:
        """Get label and emoji for positive sentiment."""
        if score > 0.8:
            return "Delighted", SentimentEmoji.DELIGHTED.value
        elif score > 0.6:
            return "Satisfied", SentimentEmoji.SATISFIED.value
        else:
            return "Neutral-Positive", SentimentEmoji.NEUTRAL.value

    def _get_negative_label(self, score: float) -> tuple:
        """Get label and emoji for negative sentiment."""
        if score < -0.8:
            return "Furious", SentimentEmoji.FURIOUS.value
        elif score < -0.6:
            return "Very Angry", SentimentEmoji.ANGRY.value
        elif score < -0.4:
            return "Very Frustrated", SentimentEmoji.FRUSTRATED.value
        elif score < -0.2:
            return "Frustrated", SentimentEmoji.FRUSTRATED.value
        else:
            return "Concerned", SentimentEmoji.CONCERNED.value

    def _extract_emotional_phrases(self, context: str) -> List[str]:
        """Extract phrases indicating customer emotion."""
        emotional_patterns = [
            r"(cancel|canceling|cancelling)",
            r"(furious|angry|frustrated|upset|disappointed)",
            r"(unacceptable|ridiculous|outrageous)",
            r"(never again|done with|fed up)",
            r"(lawyer|legal|sue|attorney)",
            r"(competitor|switch|leaving)",
            r"(worst|terrible|horrible|awful)",
            r"(waited|waiting|no show|missed)",
            r"(overcharged|billing error|wrong amount)",
        ]

        found_phrases = []
        lower_context = context.lower()

        for pattern in emotional_patterns:
            matches = re.findall(pattern, lower_context)
            found_phrases.extend(matches)

        return list(set(found_phrases))[:5]  # Return unique, max 5

    def _match_playbook(self, context: str) -> Optional[Dict]:
        """Match escalation to best playbook based on keywords."""
        lower_context = context.lower()
        best_match = None
        best_score = 0

        for playbook_id, playbook in PLAYBOOKS.items():
            score = sum(
                1 for keyword in playbook["trigger_keywords"]
                if keyword in lower_context
            )
            if score > best_score:
                best_score = score
                best_match = {"id": playbook_id, **playbook}

        return best_match if best_score > 0 else None

    async def _get_recommended_action(
        self,
        escalation: Escalation,
        customer: Optional[Customer],
        sentiment: SentimentResult,
        playbook: Optional[Dict],
    ) -> RecommendedAction:
        """Determine the recommended action based on all context."""

        # Critical severity always gets immediate call
        if escalation.severity == "critical":
            return RecommendedAction(
                action_type=ActionType.CALL.value,
                urgency=UrgencyLevel.IMMEDIATE.value,
                reason="Critical severity requires immediate personal contact",
                predicted_success=0.75,
                time_estimate_minutes=30,
            )

        # Very negative sentiment = immediate action
        if sentiment.score < -0.6:
            return RecommendedAction(
                action_type=ActionType.CALL.value,
                urgency=UrgencyLevel.IMMEDIATE.value,
                reason=f"Customer is {sentiment.label.lower()} - needs immediate attention",
                predicted_success=playbook.get("success_rate", 0.7) if playbook else 0.7,
                time_estimate_minutes=20,
            )

        # High revenue at risk
        if escalation.revenue_at_risk and escalation.revenue_at_risk > 1000:
            return RecommendedAction(
                action_type=ActionType.CALL.value,
                urgency=UrgencyLevel.URGENT.value,
                reason=f"${escalation.revenue_at_risk:,.0f} revenue at risk - prioritize recovery",
                predicted_success=0.8,
                time_estimate_minutes=25,
            )

        # Executive escalation keywords
        if playbook and playbook.get("id") == "executive_escalation":
            return RecommendedAction(
                action_type=ActionType.ESCALATE_TO_MANAGER.value,
                urgency=UrgencyLevel.IMMEDIATE.value,
                reason="Customer requested executive contact",
                predicted_success=0.78,
                time_estimate_minutes=45,
            )

        # Default based on severity
        urgency_map = {
            "high": UrgencyLevel.URGENT.value,
            "medium": UrgencyLevel.HIGH.value,
            "low": UrgencyLevel.NORMAL.value,
        }

        return RecommendedAction(
            action_type=ActionType.CALL.value,
            urgency=urgency_map.get(escalation.severity, UrgencyLevel.HIGH.value),
            reason=f"{escalation.severity.title()} severity escalation - follow playbook",
            predicted_success=playbook.get("success_rate", 0.75) if playbook else 0.75,
            time_estimate_minutes=15,
        )

    async def _generate_script(
        self,
        escalation: Escalation,
        customer: Optional[Customer],
        sentiment: SentimentResult,
        playbook: Optional[Dict],
    ) -> ScriptGuidance:
        """Generate personalized script based on context."""
        customer_name = customer.name.split()[0] if customer and customer.name else "there"

        # Use playbook script if available
        if playbook and playbook.get("steps"):
            first_step = playbook["steps"][0]
            opening = first_step.get("script", "")
        else:
            opening = f"Hi {customer_name}, this is {{rep_name}} from the customer success team."

        # Customize opening based on sentiment
        if sentiment.score < -0.6:
            opening = f"Hi {customer_name}, I want to personally apologize and help resolve this right away."
        elif sentiment.score < -0.3:
            opening = f"Hi {customer_name}, thank you for bringing this to our attention. I'm here to help."

        # Key points based on escalation type
        key_points = self._get_key_points(escalation, playbook)

        # Empathy statements based on sentiment
        empathy_statements = self._get_empathy_statements(sentiment)

        # Closing with commitment
        closing = self._get_closing(escalation, playbook)

        # What NOT to say
        what_not_to_say = [
            "Don't blame other departments or team members",
            "Don't make promises you can't keep",
            "Don't offer discounts before listening fully",
            "Don't say 'calm down' or dismiss their feelings",
            "Don't interrupt while they're explaining",
        ]

        return ScriptGuidance(
            opening=opening,
            key_points=key_points,
            empathy_statements=empathy_statements,
            closing=closing,
            what_not_to_say=what_not_to_say,
        )

    def _get_key_points(self, escalation: Escalation, playbook: Optional[Dict]) -> List[str]:
        """Get key talking points."""
        points = []

        if playbook:
            for step in playbook.get("steps", [])[:3]:
                points.append(step.get("description", ""))
        else:
            points = [
                f"Acknowledge the {escalation.escalation_type} issue",
                "Listen fully without interrupting",
                "Offer concrete resolution with timeline",
            ]

        return points

    def _get_empathy_statements(self, sentiment: SentimentResult) -> List[str]:
        """Get empathy statements based on sentiment."""
        if sentiment.score < -0.5:
            return [
                "I completely understand your frustration",
                "You have every right to be upset",
                "This is not the experience you deserve",
                "I'm going to personally make sure this gets resolved",
            ]
        elif sentiment.score < 0:
            return [
                "I understand this is frustrating",
                "Thank you for your patience",
                "We're committed to making this right",
            ]
        else:
            return [
                "I appreciate you reaching out",
                "We value your business",
                "I'm happy to help with this",
            ]

    def _get_closing(self, escalation: Escalation, playbook: Optional[Dict]) -> str:
        """Get script closing."""
        if playbook and "cancel" in playbook.get("id", ""):
            return "I want to make this right and earn back your trust. Can I follow up with you tomorrow to make sure everything is resolved?"
        return "Is there anything else I can help you with today? I'll follow up to make sure everything is resolved."

    def _calculate_priority_score(
        self,
        escalation: Escalation,
        customer: Optional[Customer],
        sentiment: SentimentResult,
    ) -> int:
        """Calculate 1-100 priority score for sorting."""
        score = 50  # Base score

        # Severity adjustment
        severity_scores = {"critical": 30, "high": 20, "medium": 10, "low": 0}
        score += severity_scores.get(escalation.severity, 0)

        # Sentiment adjustment (negative = higher priority)
        score += int(-sentiment.score * 15)  # -15 to +15

        # SLA proximity
        if escalation.sla_deadline:
            hours_remaining = (escalation.sla_deadline - datetime.utcnow()).total_seconds() / 3600
            if hours_remaining < 0:
                score += 20  # Already breached
            elif hours_remaining < 1:
                score += 15
            elif hours_remaining < 4:
                score += 10

        # Revenue at risk
        if escalation.revenue_at_risk:
            if escalation.revenue_at_risk > 5000:
                score += 15
            elif escalation.revenue_at_risk > 1000:
                score += 10
            elif escalation.revenue_at_risk > 500:
                score += 5

        return min(100, max(1, score))

    async def _find_similar_cases(
        self,
        db: AsyncSession,
        escalation: Escalation,
    ) -> List[Dict[str, Any]]:
        """Find similar past escalations for reference."""
        # Find resolved escalations of same type
        result = await db.execute(
            select(Escalation)
            .where(
                Escalation.escalation_type == escalation.escalation_type,
                Escalation.status.in_(["resolved", "closed"]),
                Escalation.id != escalation.id,
            )
            .order_by(Escalation.resolved_at.desc())
            .limit(3)
        )
        similar = result.scalars().all()

        return [
            {
                "id": esc.id,
                "title": esc.title[:50],
                "outcome": "saved" if esc.customer_satisfaction and esc.customer_satisfaction >= 4 else "resolved",
                "resolution_time_hours": (
                    (esc.resolved_at - esc.created_at).total_seconds() / 3600
                    if esc.resolved_at and esc.created_at else None
                ),
                "resolution_summary": esc.resolution_summary[:100] if esc.resolution_summary else None,
            }
            for esc in similar
        ]

    def _generate_summary(
        self,
        escalation: Escalation,
        customer: Optional[Customer],
        sentiment: SentimentResult,
    ) -> str:
        """Generate a concise situation summary."""
        customer_name = customer.name if customer else "Customer"

        # Calculate tenure if available
        tenure_info = ""
        if customer and hasattr(customer, 'created_at') and customer.created_at:
            tenure_days = (datetime.utcnow() - customer.created_at).days
            if tenure_days > 365:
                tenure_info = f" ({tenure_days // 365}+ year customer)"
            elif tenure_days > 30:
                tenure_info = f" ({tenure_days // 30} month customer)"

        revenue_info = ""
        if escalation.revenue_at_risk:
            revenue_info = f" | ${escalation.revenue_at_risk:,.0f} at risk"

        return f"{customer_name}{tenure_info} - {escalation.title}{revenue_info}"

    def _get_win_condition(self, escalation: Escalation, playbook: Optional[Dict]) -> str:
        """Define what success looks like for this escalation."""
        if playbook:
            if "cancel" in playbook.get("id", ""):
                return "Customer agrees to stay, accepts resolution, scheduled follow-up"
            elif "billing" in playbook.get("id", ""):
                return "Credit issued, customer confirms satisfaction, written confirmation sent"
            elif "service" in playbook.get("id", ""):
                return "Redo scheduled with senior tech, goodwill offered, same-day follow-up"
            elif "missed" in playbook.get("id", ""):
                return "Priority rescheduled, discount applied, VIP flag added"
            elif "executive" in playbook.get("id", ""):
                return "Executive contacted customer, resolution implemented, 7-day follow-up scheduled"

        return "Issue resolved, customer confirms satisfaction, follow-up scheduled"

    def _get_sla_status(self, escalation: Escalation) -> Dict[str, Any]:
        """Get SLA status with visual indicators."""
        if not escalation.sla_deadline:
            return {"status": "no_sla", "color": "gray", "message": "No SLA set"}

        now = datetime.utcnow()
        deadline = escalation.sla_deadline

        if escalation.sla_breached:
            hours_over = (now - deadline).total_seconds() / 3600
            return {
                "status": "breached",
                "color": "red",
                "message": f"SLA breached {hours_over:.1f}h ago",
                "hours_remaining": -hours_over,
            }

        hours_remaining = (deadline - now).total_seconds() / 3600

        if hours_remaining < 1:
            return {
                "status": "critical",
                "color": "red",
                "message": f"{int(hours_remaining * 60)} minutes left",
                "hours_remaining": hours_remaining,
            }
        elif hours_remaining < 4:
            return {
                "status": "warning",
                "color": "yellow",
                "message": f"{hours_remaining:.1f} hours left",
                "hours_remaining": hours_remaining,
            }
        else:
            return {
                "status": "on_track",
                "color": "green",
                "message": f"{hours_remaining:.1f} hours left",
                "hours_remaining": hours_remaining,
            }

    def _urgency_to_minutes(self, urgency: str) -> int:
        """Convert urgency level to minutes."""
        urgency_map = {
            UrgencyLevel.IMMEDIATE.value: 15,
            UrgencyLevel.URGENT.value: 60,
            UrgencyLevel.HIGH.value: 240,
            UrgencyLevel.NORMAL.value: 1440,
        }
        return urgency_map.get(urgency, 240)

    def _get_big_button_text(self, action: RecommendedAction) -> str:
        """Get the big action button text."""
        button_texts = {
            ActionType.CALL.value: "📞 CALL NOW",
            ActionType.EMAIL.value: "📧 SEND EMAIL",
            ActionType.SCHEDULE_MEETING.value: "📅 SCHEDULE MEETING",
            ActionType.SEND_APOLOGY.value: "💌 SEND APOLOGY",
            ActionType.OFFER_DISCOUNT.value: "💰 OFFER DISCOUNT",
            ActionType.ESCALATE_TO_MANAGER.value: "⬆️ ESCALATE TO MANAGER",
            ActionType.ASSIGN_SENIOR_REP.value: "👤 ASSIGN SENIOR REP",
            ActionType.FOLLOW_UP.value: "🔄 FOLLOW UP",
        }
        return button_texts.get(action.action_type, "📞 TAKE ACTION")

    async def get_proactive_alerts(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Get proactive alerts for escalations needing attention.
        These are the "DO THIS NOW" notifications.
        """
        alerts = []
        now = datetime.utcnow()

        # 1. SLA approaching breach (within 30 minutes)
        sla_warning = await db.execute(
            select(Escalation)
            .where(
                Escalation.assigned_to_user_id == user_id,
                Escalation.status.in_(["open", "in_progress"]),
                Escalation.sla_deadline.isnot(None),
                Escalation.sla_breached == False,
                Escalation.sla_deadline <= now + timedelta(minutes=30),
            )
            .order_by(Escalation.sla_deadline.asc())
        )
        for esc in sla_warning.scalars().all():
            minutes_left = int((esc.sla_deadline - now).total_seconds() / 60)
            alerts.append({
                "type": "sla_warning",
                "severity": "critical",
                "escalation_id": esc.id,
                "title": esc.title,
                "message": f"SLA breach in {minutes_left} minutes!",
                "action": "call",
            })

        # 2. Critical severity unassigned
        unassigned_critical = await db.execute(
            select(Escalation)
            .where(
                Escalation.severity == "critical",
                Escalation.status == "open",
                Escalation.assigned_to_user_id.is_(None),
            )
        )
        for esc in unassigned_critical.scalars().all():
            alerts.append({
                "type": "unassigned_critical",
                "severity": "critical",
                "escalation_id": esc.id,
                "title": esc.title,
                "message": "Critical escalation needs owner!",
                "action": "assign",
            })

        # 3. No response for 2+ hours
        no_response = await db.execute(
            select(Escalation)
            .where(
                Escalation.assigned_to_user_id == user_id,
                Escalation.status == "open",
                Escalation.first_response_at.is_(None),
                Escalation.created_at <= now - timedelta(hours=2),
            )
        )
        for esc in no_response.scalars().all():
            hours_waiting = (now - esc.created_at).total_seconds() / 3600
            alerts.append({
                "type": "no_response",
                "severity": "high",
                "escalation_id": esc.id,
                "title": esc.title,
                "message": f"Customer waiting {hours_waiting:.1f}h for response",
                "action": "respond",
            })

        return sorted(alerts, key=lambda x: {"critical": 0, "high": 1, "medium": 2}.get(x["severity"], 3))

    async def generate_response(
        self,
        db: AsyncSession,
        escalation_id: int,
        response_type: str = "email",  # email, sms, chat
    ) -> Dict[str, Any]:
        """Generate a response for the escalation."""
        # Fetch escalation
        result = await db.execute(
            select(Escalation).where(Escalation.id == escalation_id)
        )
        escalation = result.scalar_one_or_none()

        if not escalation:
            return {"error": "Escalation not found"}

        # Fetch customer
        customer_result = await db.execute(
            select(Customer).where(Customer.id == escalation.customer_id)
        )
        customer = customer_result.scalar_one_or_none()
        customer_name = customer.name.split()[0] if customer and customer.name else "there"

        # Generate with AI
        prompt = f"""Generate a professional {response_type} response for this customer escalation:

Customer: {customer_name}
Issue: {escalation.title}
Description: {escalation.description}
Type: {escalation.escalation_type}
Severity: {escalation.severity}

Write a warm, empathetic response that:
1. Acknowledges their frustration
2. Takes ownership of the issue
3. Provides a concrete next step
4. Offers to follow up

Keep it concise and personal."""

        ai_response = await self.ai.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7,
        )

        return {
            "escalation_id": escalation_id,
            "response_type": response_type,
            "generated_text": ai_response.get("content", ""),
            "editable": True,
        }


# Singleton instance
escalation_ai_service = EscalationAIService()


async def get_escalation_ai_service() -> EscalationAIService:
    """Dependency injection for escalation AI service."""
    return escalation_ai_service
