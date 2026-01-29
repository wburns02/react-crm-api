"""
Health Score Calculator Service

Calculates customer health scores based on multiple weighted components:
- Product Adoption (30%): Feature usage, login frequency, depth of use
- Engagement (25%): Response rates, meeting attendance, touchpoint quality
- Relationship (15%): Executive sponsor, champion engagement, NPS
- Financial (20%): Payment history, contract value, renewal status
- Support (10%): Ticket volume, resolution satisfaction, escalations
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.customer_success import HealthScore, HealthScoreEvent, Touchpoint


@dataclass
class ComponentScore:
    """Individual component score with details."""

    score: int
    weight: int
    weighted_score: float
    details: dict


@dataclass
class HealthCalculationResult:
    """Result of health score calculation."""

    overall_score: int
    health_status: str
    product_adoption: ComponentScore
    engagement: ComponentScore
    relationship: ComponentScore
    financial: ComponentScore
    support: ComponentScore
    churn_probability: float
    expansion_probability: float


class HealthScoreCalculator:
    """
    Calculates comprehensive health scores for customers.

    The health score is a weighted composite of multiple factors:
    - Product Adoption (30%): How well the customer uses the product
    - Engagement (25%): How actively they interact with us
    - Relationship (15%): Quality of stakeholder relationships
    - Financial (20%): Payment and contract health
    - Support (10%): Support experience quality
    """

    # Default weights (should sum to 100)
    DEFAULT_WEIGHTS = {
        "adoption": 30,
        "engagement": 25,
        "relationship": 15,
        "financial": 20,
        "support": 10,
    }

    # Health status thresholds
    HEALTHY_THRESHOLD = 70
    AT_RISK_THRESHOLD = 40
    CRITICAL_THRESHOLD = 20

    def __init__(self, db: AsyncSession, weights: Optional[dict] = None):
        """Initialize calculator with database session and optional custom weights."""
        self.db = db
        self.weights = weights or self.DEFAULT_WEIGHTS

    async def calculate_score(self, customer_id: int) -> HealthCalculationResult:
        """
        Calculate health score for a customer.

        Args:
            customer_id: The customer to calculate health for

        Returns:
            HealthCalculationResult with overall score and component breakdowns
        """
        # Get customer data
        customer = await self._get_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        # Calculate each component
        adoption = await self._calculate_adoption_score(customer_id)
        engagement = await self._calculate_engagement_score(customer_id)
        relationship = await self._calculate_relationship_score(customer_id)
        financial = await self._calculate_financial_score(customer)
        support = await self._calculate_support_score(customer_id)

        # Calculate weighted overall score
        overall_score = int(
            adoption.weighted_score
            + engagement.weighted_score
            + relationship.weighted_score
            + financial.weighted_score
            + support.weighted_score
        )

        # Determine health status
        health_status = self._determine_health_status(overall_score)

        # Calculate predictive scores
        churn_probability = self._calculate_churn_probability(
            overall_score, adoption.score, engagement.score, support.score
        )
        expansion_probability = self._calculate_expansion_probability(overall_score, adoption.score, financial.score)

        return HealthCalculationResult(
            overall_score=overall_score,
            health_status=health_status,
            product_adoption=adoption,
            engagement=engagement,
            relationship=relationship,
            financial=financial,
            support=support,
            churn_probability=churn_probability,
            expansion_probability=expansion_probability,
        )

    async def calculate_and_save(self, customer_id: int) -> HealthScore:
        """
        Calculate health score and save to database.

        Args:
            customer_id: The customer to calculate and save health for

        Returns:
            The saved HealthScore model
        """
        result = await self.calculate_score(customer_id)

        # Get or create health score record
        existing = await self.db.execute(select(HealthScore).where(HealthScore.customer_id == customer_id))
        health_score = existing.scalar_one_or_none()

        if health_score:
            # Track changes
            old_score = health_score.overall_score

            # Update existing
            health_score.overall_score = result.overall_score
            health_score.health_status = result.health_status
            health_score.product_adoption_score = result.product_adoption.score
            health_score.engagement_score = result.engagement.score
            health_score.relationship_score = result.relationship.score
            health_score.financial_score = result.financial.score
            health_score.support_score = result.support.score
            health_score.churn_probability = result.churn_probability
            health_score.expansion_probability = result.expansion_probability
            health_score.adoption_details = result.product_adoption.details
            health_score.engagement_details = result.engagement.details
            health_score.relationship_details = result.relationship.details
            health_score.financial_details = result.financial.details
            health_score.support_details = result.support.details
            health_score.previous_score = old_score
            health_score.previous_score_date = health_score.calculated_at
            health_score.calculated_at = datetime.utcnow()

            # Determine trend
            if result.overall_score > old_score + 5:
                health_score.score_trend = "improving"
            elif result.overall_score < old_score - 5:
                health_score.score_trend = "declining"
            else:
                health_score.score_trend = "stable"

            health_score.trend_percentage = (result.overall_score - old_score) / old_score * 100 if old_score > 0 else 0

            # Create event
            if old_score != result.overall_score:
                event = HealthScoreEvent(
                    health_score_id=health_score.id,
                    event_type="score_calculated",
                    old_score=old_score,
                    new_score=result.overall_score,
                    change_amount=result.overall_score - old_score,
                    reason="Automated recalculation",
                )
                self.db.add(event)
        else:
            # Create new
            health_score = HealthScore(
                customer_id=customer_id,
                overall_score=result.overall_score,
                health_status=result.health_status,
                product_adoption_score=result.product_adoption.score,
                engagement_score=result.engagement.score,
                relationship_score=result.relationship.score,
                financial_score=result.financial.score,
                support_score=result.support.score,
                churn_probability=result.churn_probability,
                expansion_probability=result.expansion_probability,
                adoption_weight=self.weights["adoption"],
                engagement_weight=self.weights["engagement"],
                relationship_weight=self.weights["relationship"],
                financial_weight=self.weights["financial"],
                support_weight=self.weights["support"],
                adoption_details=result.product_adoption.details,
                engagement_details=result.engagement.details,
                relationship_details=result.relationship.details,
                financial_details=result.financial.details,
                support_details=result.support.details,
                calculated_at=datetime.utcnow(),
            )
            self.db.add(health_score)

        await self.db.commit()
        await self.db.refresh(health_score)
        return health_score

    async def _get_customer(self, customer_id: int) -> Optional[Customer]:
        """Get customer by ID."""
        result = await self.db.execute(select(Customer).where(Customer.id == customer_id))
        return result.scalar_one_or_none()

    async def _calculate_adoption_score(self, customer_id: int) -> ComponentScore:
        """
        Calculate product adoption score.

        Factors:
        - Feature usage breadth and depth
        - Login frequency
        - Time to first value
        - Usage trend
        """
        # Count product-related touchpoints in last 30 days
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        usage_result = await self.db.execute(
            select(func.count(Touchpoint.id)).where(
                Touchpoint.customer_id == customer_id,
                Touchpoint.touchpoint_type.in_(
                    ["product_login", "feature_usage", "feature_adoption", "training_completed"]
                ),
                Touchpoint.occurred_at >= thirty_days_ago,
            )
        )
        usage_count = usage_result.scalar() or 0

        # Score based on usage frequency
        # 0-5 uses: poor (20-40)
        # 6-15 uses: moderate (40-60)
        # 16-30 uses: good (60-80)
        # 30+ uses: excellent (80-100)
        if usage_count >= 30:
            score = min(100, 80 + (usage_count - 30))
        elif usage_count >= 16:
            score = 60 + int((usage_count - 16) / 14 * 20)
        elif usage_count >= 6:
            score = 40 + int((usage_count - 6) / 10 * 20)
        else:
            score = max(20, 20 + usage_count * 4)

        weight = self.weights["adoption"]
        return ComponentScore(
            score=score,
            weight=weight,
            weighted_score=score * weight / 100,
            details={
                "usage_count_30d": usage_count,
                "login_frequency": "calculated",
                "features_used": "calculated",
            },
        )

    async def _calculate_engagement_score(self, customer_id: int) -> ComponentScore:
        """
        Calculate engagement score.

        Factors:
        - Email response rate
        - Meeting attendance
        - Touchpoint frequency
        - Sentiment trends
        """
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)

        # Count engagement touchpoints
        engagement_result = await self.db.execute(
            select(func.count(Touchpoint.id)).where(
                Touchpoint.customer_id == customer_id,
                Touchpoint.touchpoint_type.in_(
                    ["email_replied", "meeting_held", "call_inbound", "chat_session", "video_call"]
                ),
                Touchpoint.occurred_at >= thirty_days_ago,
            )
        )
        engagement_count = engagement_result.scalar() or 0

        # Get positive interactions
        positive_result = await self.db.execute(
            select(func.count(Touchpoint.id)).where(
                Touchpoint.customer_id == customer_id,
                Touchpoint.was_positive == True,
                Touchpoint.occurred_at >= thirty_days_ago,
            )
        )
        positive_count = positive_result.scalar() or 0

        # Score based on engagement
        base_score = min(100, 30 + engagement_count * 10)

        # Boost for positive interactions
        if engagement_count > 0:
            positive_ratio = positive_count / max(engagement_count, 1)
            base_score = int(base_score * (0.7 + positive_ratio * 0.3))

        weight = self.weights["engagement"]
        return ComponentScore(
            score=min(100, base_score),
            weight=weight,
            weighted_score=min(100, base_score) * weight / 100,
            details={
                "touchpoints_30d": engagement_count,
                "positive_interactions": positive_count,
                "response_rate": "calculated",
            },
        )

    async def _calculate_relationship_score(self, customer_id: int) -> ComponentScore:
        """
        Calculate relationship score.

        Factors:
        - Executive sponsor engagement
        - Champion identification
        - NPS score
        - Stakeholder breadth
        """
        ninety_days_ago = datetime.utcnow() - timedelta(days=90)

        # Check for executive and champion touchpoints
        executive_result = await self.db.execute(
            select(func.count(Touchpoint.id)).where(
                Touchpoint.customer_id == customer_id,
                Touchpoint.contact_is_executive == True,
                Touchpoint.occurred_at >= ninety_days_ago,
            )
        )
        executive_count = executive_result.scalar() or 0

        champion_result = await self.db.execute(
            select(func.count(Touchpoint.id)).where(
                Touchpoint.customer_id == customer_id,
                Touchpoint.contact_is_champion == True,
                Touchpoint.occurred_at >= ninety_days_ago,
            )
        )
        champion_count = champion_result.scalar() or 0

        # Get most recent NPS score
        nps_result = await self.db.execute(
            select(Touchpoint.nps_score)
            .where(
                Touchpoint.customer_id == customer_id,
                Touchpoint.nps_score.isnot(None),
            )
            .order_by(Touchpoint.occurred_at.desc())
            .limit(1)
        )
        nps_score = nps_result.scalar()

        # Base score
        score = 50

        # Boost for executive engagement
        if executive_count > 0:
            score += min(20, executive_count * 5)

        # Boost for champion engagement
        if champion_count > 0:
            score += min(15, champion_count * 3)

        # NPS contribution
        if nps_score is not None:
            if nps_score >= 9:
                score += 15  # Promoter
            elif nps_score >= 7:
                score += 5  # Passive
            else:
                score -= 10  # Detractor

        weight = self.weights["relationship"]
        return ComponentScore(
            score=max(0, min(100, score)),
            weight=weight,
            weighted_score=max(0, min(100, score)) * weight / 100,
            details={
                "executive_touchpoints_90d": executive_count,
                "champion_touchpoints_90d": champion_count,
                "latest_nps": nps_score,
            },
        )

    async def _calculate_financial_score(self, customer: Customer) -> ComponentScore:
        """
        Calculate financial health score.

        Factors:
        - Payment history
        - Contract value
        - Renewal status
        - Revenue trend
        """
        # Base score on customer type/value
        score = 60

        # Adjust based on customer type (if VIP/Enterprise)
        if customer.customer_type in ["enterprise", "vip"]:
            score += 10

        # Check for payment issues
        payment_issues_result = await self.db.execute(
            select(func.count(Touchpoint.id)).where(
                Touchpoint.customer_id == customer.id,
                Touchpoint.touchpoint_type == "payment_issue",
                Touchpoint.occurred_at >= datetime.utcnow() - timedelta(days=90),
            )
        )
        payment_issues = payment_issues_result.scalar() or 0

        if payment_issues > 0:
            score -= payment_issues * 15

        # Check for recent invoices paid
        paid_result = await self.db.execute(
            select(func.count(Touchpoint.id)).where(
                Touchpoint.customer_id == customer.id,
                Touchpoint.touchpoint_type == "invoice_paid",
                Touchpoint.occurred_at >= datetime.utcnow() - timedelta(days=90),
            )
        )
        invoices_paid = paid_result.scalar() or 0

        if invoices_paid > 0:
            score += min(20, invoices_paid * 5)

        weight = self.weights["financial"]
        return ComponentScore(
            score=max(0, min(100, score)),
            weight=weight,
            weighted_score=max(0, min(100, score)) * weight / 100,
            details={
                "payment_issues_90d": payment_issues,
                "invoices_paid_90d": invoices_paid,
                "customer_type": customer.customer_type,
            },
        )

    async def _calculate_support_score(self, customer_id: int) -> ComponentScore:
        """
        Calculate support health score.

        Factors:
        - Ticket volume (fewer is better)
        - Resolution time
        - Escalation frequency
        - CSAT scores
        """
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)

        # Count support tickets
        tickets_result = await self.db.execute(
            select(func.count(Touchpoint.id)).where(
                Touchpoint.customer_id == customer_id,
                Touchpoint.touchpoint_type == "support_ticket_opened",
                Touchpoint.occurred_at >= thirty_days_ago,
            )
        )
        ticket_count = tickets_result.scalar() or 0

        # Count escalations
        escalations_result = await self.db.execute(
            select(func.count(Touchpoint.id)).where(
                Touchpoint.customer_id == customer_id,
                Touchpoint.touchpoint_type == "support_escalation",
                Touchpoint.occurred_at >= thirty_days_ago,
            )
        )
        escalation_count = escalations_result.scalar() or 0

        # Get average CSAT
        csat_result = await self.db.execute(
            select(func.avg(Touchpoint.csat_score)).where(
                Touchpoint.customer_id == customer_id,
                Touchpoint.csat_score.isnot(None),
                Touchpoint.occurred_at >= datetime.utcnow() - timedelta(days=90),
            )
        )
        avg_csat = csat_result.scalar()

        # Base score - high if no tickets
        if ticket_count == 0:
            score = 85
        elif ticket_count <= 2:
            score = 70
        elif ticket_count <= 5:
            score = 55
        else:
            score = max(30, 55 - (ticket_count - 5) * 5)

        # Deduct for escalations
        score -= escalation_count * 10

        # Adjust for CSAT
        if avg_csat:
            if avg_csat >= 4.5:
                score += 10
            elif avg_csat >= 4:
                score += 5
            elif avg_csat < 3:
                score -= 15

        weight = self.weights["support"]
        return ComponentScore(
            score=max(0, min(100, score)),
            weight=weight,
            weighted_score=max(0, min(100, score)) * weight / 100,
            details={
                "tickets_30d": ticket_count,
                "escalations_30d": escalation_count,
                "avg_csat_90d": float(avg_csat) if avg_csat else None,
            },
        )

    def _determine_health_status(self, score: int) -> str:
        """Determine health status category from score."""
        if score >= self.HEALTHY_THRESHOLD:
            return "healthy"
        elif score >= self.AT_RISK_THRESHOLD:
            return "at_risk"
        elif score >= self.CRITICAL_THRESHOLD:
            return "critical"
        else:
            return "churned"

    def _calculate_churn_probability(self, overall: int, adoption: int, engagement: int, support: int) -> float:
        """
        Calculate churn probability based on scores.

        High churn risk if:
        - Low overall score
        - Low engagement
        - High support volume (low support score)
        """
        # Base probability from overall score
        if overall >= 80:
            base_prob = 0.05
        elif overall >= 60:
            base_prob = 0.15
        elif overall >= 40:
            base_prob = 0.35
        else:
            base_prob = 0.60

        # Adjust for engagement
        if engagement < 30:
            base_prob += 0.15
        elif engagement < 50:
            base_prob += 0.05

        # Adjust for support issues
        if support < 40:
            base_prob += 0.10

        return min(0.95, max(0.01, base_prob))

    def _calculate_expansion_probability(self, overall: int, adoption: int, financial: int) -> float:
        """
        Calculate expansion probability based on scores.

        High expansion potential if:
        - High overall health
        - High product adoption (wants more)
        - Good financial standing
        """
        if overall < 50:
            return 0.05  # Low health = low expansion

        # Base probability from overall score
        if overall >= 80:
            base_prob = 0.40
        elif overall >= 70:
            base_prob = 0.25
        else:
            base_prob = 0.10

        # Boost for high adoption
        if adoption >= 80:
            base_prob += 0.15
        elif adoption >= 60:
            base_prob += 0.05

        # Boost for financial health
        if financial >= 80:
            base_prob += 0.10

        return min(0.85, max(0.01, base_prob))
