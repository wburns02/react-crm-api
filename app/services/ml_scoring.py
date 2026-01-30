"""ML Scoring Service - Rule-based lead scoring and predictions.

Provides rule-based scoring for leads until proper ML models are deployed.
Factors considered:
- Recent activity (< 7 days: +20, < 30 days: +10)
- Open quotes: +15
- Previous work orders (existing customer): +10
- Property value/size (tank size as proxy): +5-15
- Customer type (commercial premium): +10
- Lead source quality: varies
- Engagement signals: varies

Labels:
- hot: 75+ score
- warm: 50-74 score
- cold: <50 score
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import uuid

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.work_order import WorkOrder
from app.models.quote import Quote
from app.models.activity import Activity
from app.models.prediction import LeadScore

logger = logging.getLogger(__name__)


@dataclass
class ScoringFactors:
    """Container for scoring factors and their contributions."""

    recent_activity: int = 0
    open_quotes: int = 0
    previous_work_orders: int = 0
    property_size: int = 0
    customer_type: int = 0
    lead_source: int = 0
    engagement: int = 0
    recency: int = 0
    base_score: int = 25  # Starting baseline

    def total_score(self) -> int:
        """Calculate total score (capped at 100)."""
        total = (
            self.base_score
            + self.recent_activity
            + self.open_quotes
            + self.previous_work_orders
            + self.property_size
            + self.customer_type
            + self.lead_source
            + self.engagement
            + self.recency
        )
        return min(100, max(0, total))

    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary for storage."""
        return {
            "base_score": self.base_score,
            "recent_activity": self.recent_activity,
            "open_quotes": self.open_quotes,
            "previous_work_orders": self.previous_work_orders,
            "property_size": self.property_size,
            "customer_type": self.customer_type,
            "lead_source": self.lead_source,
            "engagement": self.engagement,
            "recency": self.recency,
        }


def get_score_label(score: int) -> str:
    """Convert numeric score to label."""
    if score >= 75:
        return "hot"
    elif score >= 50:
        return "warm"
    else:
        return "cold"


def calculate_confidence(factors: ScoringFactors, data_points: int) -> float:
    """Calculate confidence score based on available data."""
    # More data = higher confidence
    base_confidence = 0.5
    data_boost = min(0.4, data_points * 0.05)  # Up to 0.4 boost for 8+ data points

    # If we have activity data, boost confidence
    if factors.recent_activity > 0 or factors.engagement > 0:
        data_boost += 0.1

    return min(0.95, base_confidence + data_boost)


# Lead source quality scores
LEAD_SOURCE_SCORES = {
    "referral": 20,
    "repeat_customer": 15,
    "google_ads": 12,
    "website": 10,
    "facebook": 8,
    "yelp": 8,
    "angies_list": 7,
    "home_advisor": 5,
    "cold_call": 0,
    "unknown": 0,
    None: 0,
}


async def calculate_customer_lead_score(
    db: AsyncSession,
    customer: Customer,
) -> Dict[str, Any]:
    """
    Calculate lead score for a single customer.

    Returns dict with score, label, confidence, and factors.
    """
    factors = ScoringFactors()
    today = date.today()
    now = datetime.utcnow()
    data_points = 0

    # 1. Recent Activity Score
    # Check for activities in last 7/30 days
    try:
        activity_result = await db.execute(
            select(func.max(Activity.created_at)).where(Activity.customer_id == customer.id)
        )
        last_activity = activity_result.scalar()

        if last_activity:
            data_points += 1
            days_since = (now - last_activity).days
            if days_since <= 7:
                factors.recent_activity = 20
            elif days_since <= 30:
                factors.recent_activity = 10
            elif days_since <= 90:
                factors.recent_activity = 5
    except Exception as e:
        logger.warning(f"Error checking activities: {e}")

    # 2. Open Quotes Score
    try:
        open_quotes_result = await db.execute(
            select(func.count())
            .select_from(Quote)
            .where(and_(Quote.customer_id == customer.id, Quote.status.in_(["draft", "sent", "pending"])))
        )
        open_quotes = open_quotes_result.scalar() or 0

        if open_quotes > 0:
            data_points += 1
            factors.open_quotes = 15 + min(10, (open_quotes - 1) * 5)  # Up to +25 for multiple quotes
    except Exception as e:
        logger.warning(f"Error checking quotes: {e}")

    # 3. Previous Work Orders Score
    try:
        work_order_result = await db.execute(
            select(func.count()).select_from(WorkOrder).where(WorkOrder.customer_id == customer.id)
        )
        work_order_count = work_order_result.scalar() or 0

        if work_order_count > 0:
            data_points += 1
            factors.previous_work_orders = 10 + min(15, work_order_count * 2)  # Up to +25 for loyal customers
    except Exception as e:
        logger.warning(f"Error checking work orders: {e}")

    # 4. Property Size Score (using tank_size_gallons as proxy)
    if customer.tank_size_gallons:
        data_points += 1
        if customer.tank_size_gallons >= 2000:
            factors.property_size = 15
        elif customer.tank_size_gallons >= 1500:
            factors.property_size = 12
        elif customer.tank_size_gallons >= 1000:
            factors.property_size = 8
        else:
            factors.property_size = 5

    # 5. Customer Type Score
    if customer.customer_type:
        data_points += 1
        customer_type = customer.customer_type.lower()
        if "commercial" in customer_type or "business" in customer_type:
            factors.customer_type = 15
        elif "property_manager" in customer_type or "property manager" in customer_type:
            factors.customer_type = 12
        elif "residential" in customer_type:
            factors.customer_type = 5

    # 6. Lead Source Score
    if customer.lead_source:
        data_points += 1
        source = customer.lead_source.lower().replace(" ", "_")
        factors.lead_source = LEAD_SOURCE_SCORES.get(source, 0)

    # 7. Recency Score (how recently created)
    if customer.created_at:
        data_points += 1
        days_old = (now - customer.created_at).days
        if days_old <= 3:
            factors.recency = 15  # Very fresh lead
        elif days_old <= 7:
            factors.recency = 10
        elif days_old <= 14:
            factors.recency = 5
        elif days_old > 180:
            factors.recency = -10  # Stale lead penalty

    # 8. Engagement signals
    # Check if customer has phone/email (can be contacted)
    engagement_signals = 0
    if customer.email:
        engagement_signals += 1
    if customer.phone:
        engagement_signals += 1
    if customer.mobile_phone:
        engagement_signals += 1
    if customer.address_line1:
        engagement_signals += 1

    if engagement_signals >= 3:
        factors.engagement = 10
    elif engagement_signals >= 2:
        factors.engagement = 5

    # Calculate final score
    total_score = factors.total_score()
    label = get_score_label(total_score)
    confidence = calculate_confidence(factors, data_points)

    return {
        "customer_id": customer.id,
        "score": total_score,
        "score_label": label,
        "confidence": round(confidence, 2),
        "factors": factors.to_dict(),
        "data_points": data_points,
    }


async def calculate_lead_scores_batch(
    db: AsyncSession,
    customer_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Calculate lead scores for multiple customers.

    If customer_ids is None, calculates for all prospects.
    Returns summary of calculation results.
    """
    now = datetime.utcnow()
    results = {
        "calculated": 0,
        "errors": 0,
        "hot_leads": 0,
        "warm_leads": 0,
        "cold_leads": 0,
    }

    # Build customer query
    query = select(Customer)
    if customer_ids:
        query = query.where(Customer.id.in_(customer_ids))
    else:
        # Only score active customers
        query = query.where(Customer.is_active == True)

    customer_result = await db.execute(query)
    customers = customer_result.scalars().all()

    logger.info(f"Calculating lead scores for {len(customers)} customers")

    for customer in customers:
        try:
            score_data = await calculate_customer_lead_score(db, customer)

            # Check if score already exists
            existing_result = await db.execute(select(LeadScore).where(LeadScore.customer_id == customer.id))
            existing_score = existing_result.scalar_one_or_none()

            if existing_score:
                # Update existing
                existing_score.score = score_data["score"]
                existing_score.score_label = score_data["score_label"]
                existing_score.confidence = score_data["confidence"]
                existing_score.factors = score_data["factors"]
                existing_score.scored_at = now
            else:
                # Create new
                new_score = LeadScore(
                    id=uuid.uuid4(),
                    customer_id=customer.id,
                    score=score_data["score"],
                    score_label=score_data["score_label"],
                    confidence=score_data["confidence"],
                    factors=score_data["factors"],
                    model_version="rule-based-v1",
                    scored_at=now,
                )
                db.add(new_score)

            results["calculated"] += 1

            # Track label distribution
            if score_data["score_label"] == "hot":
                results["hot_leads"] += 1
            elif score_data["score_label"] == "warm":
                results["warm_leads"] += 1
            else:
                results["cold_leads"] += 1

        except Exception as e:
            logger.error(f"Error scoring customer {customer.id}: {e}")
            results["errors"] += 1

    await db.commit()

    logger.info(
        f"Lead scoring complete: {results['calculated']} calculated, "
        f"{results['hot_leads']} hot, {results['warm_leads']} warm, "
        f"{results['cold_leads']} cold, {results['errors']} errors"
    )

    return results


async def get_lead_scoring_summary(db: AsyncSession) -> Dict[str, Any]:
    """Get summary statistics for lead scoring."""
    # Count by label
    hot_result = await db.execute(select(func.count()).select_from(LeadScore).where(LeadScore.score_label == "hot"))
    hot_count = hot_result.scalar() or 0

    warm_result = await db.execute(select(func.count()).select_from(LeadScore).where(LeadScore.score_label == "warm"))
    warm_count = warm_result.scalar() or 0

    cold_result = await db.execute(select(func.count()).select_from(LeadScore).where(LeadScore.score_label == "cold"))
    cold_count = cold_result.scalar() or 0

    # Average score
    avg_result = await db.execute(select(func.avg(LeadScore.score)))
    avg_score = avg_result.scalar() or 0

    # Most recent scoring
    recent_result = await db.execute(select(func.max(LeadScore.scored_at)))
    last_scored = recent_result.scalar()

    return {
        "total_scored": hot_count + warm_count + cold_count,
        "hot_leads": hot_count,
        "warm_leads": warm_count,
        "cold_leads": cold_count,
        "average_score": round(avg_score, 1) if avg_score else 0,
        "last_scored_at": last_scored.isoformat() if last_scored else None,
    }
