"""
Send Time Optimization Service

Calculates optimal send times for campaigns based on historical engagement data:
- Per-customer profile calculation from engagement history
- Campaign-level timing analysis
- Optimal send time recommendations
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models.customer import Customer
from app.models.customer_success import (
    CampaignStepExecution,
    CampaignEnrollment,
)
from app.models.customer_success.send_time_optimization import (
    CustomerSendTimeProfile,
    CampaignSendTimeAnalysis,
)

logger = logging.getLogger(__name__)


class SendTimeOptimizer:
    """
    Service for calculating and managing optimal send times.

    Analyzes historical engagement data to determine the best times
    to send messages to individual customers or across campaigns.
    """

    # Minimum samples required for meaningful analysis
    MIN_SAMPLES_FOR_PROFILE = 5
    MIN_SAMPLES_PER_HOUR = 3

    # Confidence scaling (50 emails = 100% confidence)
    CONFIDENCE_SCALE = 2

    # Default send hour when no profile data is available
    DEFAULT_SEND_HOUR = 9

    def __init__(self, db: AsyncSession):
        """Initialize optimizer with database session."""
        self.db = db

    async def calculate_customer_profile(self, customer_id: int) -> Dict[str, Any]:
        """
        Calculate optimal send times for a customer based on engagement history.

        Analyzes all campaign step executions for the customer to determine
        which hours and days yield the best open and click rates.

        Args:
            customer_id: The customer to calculate profile for

        Returns:
            Dict containing best_hour, open_rate_by_hour, confidence, sample_size
        """
        # Verify customer exists
        customer_result = await self.db.execute(
            select(Customer).where(Customer.id == customer_id)
        )
        customer = customer_result.scalar_one_or_none()
        if not customer:
            return {"error": "Customer not found", "customer_id": customer_id}

        # Get all step executions for this customer
        result = await self.db.execute(
            select(CampaignStepExecution)
            .join(CampaignEnrollment)
            .where(CampaignEnrollment.customer_id == customer_id)
            .where(CampaignStepExecution.sent_at.isnot(None))
        )
        executions = result.scalars().all()

        if len(executions) < self.MIN_SAMPLES_FOR_PROFILE:
            return {
                "customer_id": customer_id,
                "confidence": 0,
                "message": f"Not enough data (need {self.MIN_SAMPLES_FOR_PROFILE}, have {len(executions)})",
                "sample_size": len(executions),
            }

        # Aggregate engagement by hour
        hourly_stats = defaultdict(lambda: {"sent": 0, "opened": 0, "clicked": 0})

        for exec in executions:
            hour = exec.sent_at.hour if exec.sent_at else 0
            hourly_stats[hour]["sent"] += 1
            if exec.opened_at:
                hourly_stats[hour]["opened"] += 1
            if exec.clicked_at:
                hourly_stats[hour]["clicked"] += 1

        # Calculate rates and find best hour
        best_hour = self.DEFAULT_SEND_HOUR
        best_open_rate = 0
        open_rate_by_hour = {}
        click_rate_by_hour = {}

        for hour, stats in hourly_stats.items():
            if stats["sent"] > 0:
                open_rate = stats["opened"] / stats["sent"]
                click_rate = stats["clicked"] / stats["sent"]
                open_rate_by_hour[hour] = round(open_rate, 3)
                click_rate_by_hour[hour] = round(click_rate, 3)

                # Only consider hours with sufficient samples for best hour
                if open_rate > best_open_rate and stats["sent"] >= self.MIN_SAMPLES_PER_HOUR:
                    best_open_rate = open_rate
                    best_hour = hour

        # Calculate confidence based on sample size
        total_samples = sum(s["sent"] for s in hourly_stats.values())
        confidence = min(100, total_samples * self.CONFIDENCE_SCALE)

        # Update or create profile
        profile_result = await self.db.execute(
            select(CustomerSendTimeProfile).where(
                CustomerSendTimeProfile.customer_id == customer_id
            )
        )
        profile = profile_result.scalar_one_or_none()

        if not profile:
            profile = CustomerSendTimeProfile(customer_id=customer_id)
            self.db.add(profile)

        profile.best_hour_email = best_hour
        profile.open_rate_by_hour = open_rate_by_hour
        profile.click_rate_by_hour = click_rate_by_hour
        profile.confidence = confidence
        profile.sample_size = total_samples
        profile.last_calculated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(profile)

        logger.info(
            f"Calculated send time profile for customer {customer_id}: "
            f"best_hour={best_hour}, confidence={confidence}%"
        )

        return {
            "customer_id": customer_id,
            "best_hour": best_hour,
            "open_rate_by_hour": open_rate_by_hour,
            "click_rate_by_hour": click_rate_by_hour,
            "confidence": confidence,
            "sample_size": total_samples,
            "profile_id": profile.id,
        }

    async def get_optimal_send_time(
        self,
        customer_id: int,
        channel: str = "email",
    ) -> datetime:
        """
        Get the optimal send time for a customer.

        Args:
            customer_id: The customer to get optimal time for
            channel: Communication channel ('email' or 'sms')

        Returns:
            datetime representing the next optimal send time
        """
        result = await self.db.execute(
            select(CustomerSendTimeProfile).where(
                CustomerSendTimeProfile.customer_id == customer_id
            )
        )
        profile = result.scalar_one_or_none()

        now = datetime.utcnow()

        if not profile or profile.confidence < 50:
            # Default to 9 AM tomorrow when no reliable profile exists
            optimal = now.replace(hour=self.DEFAULT_SEND_HOUR, minute=0, second=0, microsecond=0)
            if optimal <= now:
                optimal += timedelta(days=1)
            return optimal

        # Use profile's best hour based on channel
        best_hour = (
            profile.best_hour_sms if channel == "sms" and profile.best_hour_sms
            else profile.best_hour_email or self.DEFAULT_SEND_HOUR
        )

        optimal = now.replace(hour=best_hour, minute=0, second=0, microsecond=0)
        if optimal <= now:
            optimal += timedelta(days=1)

        return optimal

    async def get_customer_profile(self, customer_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve the existing send time profile for a customer.

        Args:
            customer_id: The customer to get profile for

        Returns:
            Dict with profile data or None if no profile exists
        """
        result = await self.db.execute(
            select(CustomerSendTimeProfile).where(
                CustomerSendTimeProfile.customer_id == customer_id
            )
        )
        profile = result.scalar_one_or_none()

        if not profile:
            return None

        return {
            "customer_id": customer_id,
            "best_hour_email": profile.best_hour_email,
            "best_hour_sms": profile.best_hour_sms,
            "best_days": profile.best_days,
            "open_rate_by_hour": profile.open_rate_by_hour,
            "click_rate_by_hour": profile.click_rate_by_hour,
            "confidence": profile.confidence,
            "sample_size": profile.sample_size,
            "timezone": profile.timezone,
            "last_calculated_at": profile.last_calculated_at,
        }

    async def analyze_campaign_timing(self, campaign_id: int) -> Dict[str, Any]:
        """
        Analyze send time performance for a campaign.

        Aggregates engagement data across all messages sent in the campaign
        to identify optimal timing patterns.

        Args:
            campaign_id: The campaign to analyze

        Returns:
            Dict containing hourly and daily performance data with recommendations
        """
        # Get all executions for this campaign
        result = await self.db.execute(
            select(CampaignStepExecution)
            .join(CampaignEnrollment)
            .where(CampaignEnrollment.campaign_id == campaign_id)
            .where(CampaignStepExecution.sent_at.isnot(None))
        )
        executions = result.scalars().all()

        if not executions:
            return {
                "campaign_id": campaign_id,
                "message": "No messages sent yet",
                "total_analyzed": 0,
            }

        # Aggregate by hour and day
        hourly = defaultdict(lambda: {"sent": 0, "opened": 0, "clicked": 0})
        daily = defaultdict(lambda: {"sent": 0, "opened": 0, "clicked": 0})

        min_date = None
        max_date = None

        for exec in executions:
            if exec.sent_at:
                hour = exec.sent_at.hour
                day = exec.sent_at.weekday()

                hourly[hour]["sent"] += 1
                daily[day]["sent"] += 1

                if exec.opened_at:
                    hourly[hour]["opened"] += 1
                    daily[day]["opened"] += 1
                if exec.clicked_at:
                    hourly[hour]["clicked"] += 1
                    daily[day]["clicked"] += 1

                # Track analysis period
                if min_date is None or exec.sent_at < min_date:
                    min_date = exec.sent_at
                if max_date is None or exec.sent_at > max_date:
                    max_date = exec.sent_at

        # Calculate rates
        def add_rates(stats: dict) -> dict:
            result = {}
            for key, val in stats.items():
                result[key] = {
                    **val,
                    "open_rate": round(val["opened"] / val["sent"] * 100, 1) if val["sent"] > 0 else 0,
                    "click_rate": round(val["clicked"] / val["sent"] * 100, 1) if val["sent"] > 0 else 0,
                }
            return result

        hourly_perf = add_rates(hourly)
        daily_perf = add_rates(daily)

        # Find best hour and day
        best_hour = self.DEFAULT_SEND_HOUR
        best_open_rate = 0
        for hour, perf in hourly_perf.items():
            if perf.get("open_rate", 0) > best_open_rate and perf["sent"] >= self.MIN_SAMPLES_PER_HOUR:
                best_open_rate = perf["open_rate"]
                best_hour = hour

        best_day = 1  # Tuesday default
        best_day_rate = 0
        for day, perf in daily_perf.items():
            if perf.get("open_rate", 0) > best_day_rate and perf["sent"] >= self.MIN_SAMPLES_PER_HOUR:
                best_day_rate = perf["open_rate"]
                best_day = day

        # Store or update analysis
        analysis_result = await self.db.execute(
            select(CampaignSendTimeAnalysis).where(
                CampaignSendTimeAnalysis.campaign_id == campaign_id
            )
        )
        analysis = analysis_result.scalar_one_or_none()

        if not analysis:
            analysis = CampaignSendTimeAnalysis(campaign_id=campaign_id)
            self.db.add(analysis)

        analysis.recommended_hour = best_hour
        analysis.recommended_days = [best_day]
        analysis.hourly_performance = hourly_perf
        analysis.daily_performance = daily_perf
        analysis.analysis_period_start = min_date
        analysis.analysis_period_end = max_date
        analysis.total_messages_analyzed = len(executions)

        await self.db.commit()

        logger.info(
            f"Analyzed campaign {campaign_id} timing: "
            f"recommended_hour={best_hour}, total_messages={len(executions)}"
        )

        return {
            "campaign_id": campaign_id,
            "recommended_hour": best_hour,
            "recommended_day": best_day,
            "hourly_performance": hourly_perf,
            "daily_performance": daily_perf,
            "total_analyzed": len(executions),
            "analysis_period": {
                "start": min_date.isoformat() if min_date else None,
                "end": max_date.isoformat() if max_date else None,
            },
        }

    async def batch_calculate_profiles(
        self,
        customer_ids: list[int],
    ) -> Dict[str, Any]:
        """
        Calculate send time profiles for multiple customers.

        Args:
            customer_ids: List of customer IDs to calculate profiles for

        Returns:
            Summary of calculation results
        """
        results = {
            "total": len(customer_ids),
            "success": 0,
            "skipped": 0,
            "errors": 0,
            "profiles": [],
        }

        for customer_id in customer_ids:
            try:
                profile = await self.calculate_customer_profile(customer_id)
                if profile.get("confidence", 0) > 0:
                    results["success"] += 1
                else:
                    results["skipped"] += 1
                results["profiles"].append(profile)
            except Exception as e:
                logger.error(f"Error calculating profile for customer {customer_id}: {e}")
                results["errors"] += 1
                results["profiles"].append({
                    "customer_id": customer_id,
                    "error": str(e),
                })

        return results
