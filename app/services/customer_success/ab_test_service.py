"""
A/B Test Service with Statistical Significance

Provides statistical analysis for A/B tests including:
- Chi-square test for significance
- Confidence level calculation
- Winner determination
- Lift calculation
"""

import math
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import logging

from app.models.customer_success.ab_test import ABTest

logger = logging.getLogger(__name__)


class ABTestService:
    """Service for A/B test statistical analysis and management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def calculate_chi_square(a_success: int, a_total: int, b_success: int, b_total: int) -> Dict[str, Any]:
        """
        Calculate chi-square test for A/B comparison.

        Uses a chi-square test with Yates correction for small samples
        to determine if the difference between variants is statistically significant.

        Args:
            a_success: Number of successes in variant A
            a_total: Total samples in variant A
            b_success: Number of successes in variant B
            b_total: Total samples in variant B

        Returns:
            Dictionary with chi_square, p_value, confidence, and is_significant
        """
        if a_total == 0 or b_total == 0:
            return {"chi_square": 0, "p_value": 1, "confidence": 0, "is_significant": False}

        # Total values
        total = a_total + b_total
        total_success = a_success + b_success
        total_failure = total - total_success

        if total_success == 0 or total_failure == 0:
            return {"chi_square": 0, "p_value": 1, "confidence": 0, "is_significant": False}

        # Expected values under null hypothesis (no difference)
        expected_a_success = (a_total * total_success) / total
        expected_a_failure = (a_total * total_failure) / total
        expected_b_success = (b_total * total_success) / total
        expected_b_failure = (b_total * total_failure) / total

        # Chi-square calculation with Yates correction for continuity
        chi_square = 0
        observations = [
            (a_success, expected_a_success),
            (a_total - a_success, expected_a_failure),
            (b_success, expected_b_success),
            (b_total - b_success, expected_b_failure),
        ]

        for observed, expected in observations:
            if expected > 0:
                # Apply Yates correction for small samples
                correction = 0.5 if total < 40 else 0
                chi_square += ((abs(observed - expected) - correction) ** 2) / expected

        # P-value approximation for 1 degree of freedom
        # Using Wilson-Hilferty approximation
        if chi_square < 0.001:
            p_value = 1.0
        elif chi_square > 20:
            p_value = 0.0001
        else:
            # Approximation using exponential decay
            # More accurate would be scipy.stats.chi2.sf(chi_square, df=1)
            p_value = math.exp(-chi_square / 2)

        confidence = (1 - p_value) * 100

        return {
            "chi_square": round(chi_square, 4),
            "p_value": round(p_value, 4),
            "confidence": round(confidence, 2),
            "is_significant": confidence >= 95,
        }

    @staticmethod
    def calculate_z_score(a_success: int, a_total: int, b_success: int, b_total: int) -> Dict[str, Any]:
        """
        Calculate z-score for proportion comparison.

        Alternative to chi-square, useful for understanding direction of effect.

        Args:
            a_success: Number of successes in variant A
            a_total: Total samples in variant A
            b_success: Number of successes in variant B
            b_total: Total samples in variant B

        Returns:
            Dictionary with z_score, p_value, confidence, is_significant, and direction
        """
        if a_total == 0 or b_total == 0:
            return {"z_score": 0, "p_value": 1, "confidence": 0, "is_significant": False, "direction": None}

        p_a = a_success / a_total
        p_b = b_success / b_total

        # Pooled proportion
        p_pooled = (a_success + b_success) / (a_total + b_total)

        if p_pooled == 0 or p_pooled == 1:
            return {"z_score": 0, "p_value": 1, "confidence": 0, "is_significant": False, "direction": None}

        # Standard error
        se = math.sqrt(p_pooled * (1 - p_pooled) * (1 / a_total + 1 / b_total))

        if se == 0:
            return {"z_score": 0, "p_value": 1, "confidence": 0, "is_significant": False, "direction": None}

        # Z-score
        z = (p_b - p_a) / se

        # Two-tailed p-value approximation
        p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
        confidence = (1 - p_value) * 100

        return {
            "z_score": round(z, 4),
            "p_value": round(p_value, 4),
            "confidence": round(confidence, 2),
            "is_significant": confidence >= 95,
            "direction": "b_wins" if z > 0 else "a_wins" if z < 0 else None,
        }

    async def get_test_by_id(self, test_id: int) -> Optional[ABTest]:
        """Get an A/B test by ID."""
        result = await self.db.execute(select(ABTest).where(ABTest.id == test_id))
        return result.scalar_one_or_none()

    async def get_test_results(self, test_id: int) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive A/B test results with statistical analysis.

        Args:
            test_id: The A/B test ID

        Returns:
            Dictionary with test details, metrics, statistics, and winner determination
        """
        test = await self.get_test_by_id(test_id)
        if not test:
            return None

        # Calculate rates based on primary metric
        primary_metric = test.primary_metric or "conversion"

        # Get appropriate success metrics
        if primary_metric == "conversion":
            a_success, b_success = test.variant_a_converted or 0, test.variant_b_converted or 0
        elif primary_metric == "open":
            a_success, b_success = test.variant_a_opened or 0, test.variant_b_opened or 0
        elif primary_metric == "click":
            a_success, b_success = test.variant_a_clicked or 0, test.variant_b_clicked or 0
        else:
            a_success, b_success = test.variant_a_converted or 0, test.variant_b_converted or 0

        a_total = test.variant_a_sent or 0
        b_total = test.variant_b_sent or 0

        # Calculate rates
        a_rate = (a_success / a_total * 100) if a_total > 0 else 0
        b_rate = (b_success / b_total * 100) if b_total > 0 else 0

        # Statistical significance using chi-square
        chi_stats = self.calculate_chi_square(a_success, a_total, b_success, b_total)

        # Also calculate z-score for direction
        z_stats = self.calculate_z_score(a_success, a_total, b_success, b_total)

        # Determine winner
        winner = None
        if chi_stats["is_significant"] and test.has_min_sample:
            winner = "a" if a_rate > b_rate else "b"

        # Calculate lift (percentage improvement of B over A)
        lift = 0
        if a_rate > 0:
            lift = ((b_rate - a_rate) / a_rate) * 100

        # Calculate relative improvement
        relative_improvement = {
            "value": round(lift, 2),
            "direction": "increase" if lift > 0 else "decrease" if lift < 0 else "none",
            "variant_b_vs_a": f"{'+' if lift > 0 else ''}{round(lift, 1)}%",
        }

        return {
            "test_id": test.id,
            "test_name": test.name,
            "test_type": test.test_type,
            "status": test.status,
            "primary_metric": primary_metric,
            "variant_a": {
                "name": test.variant_a_name,
                "config": test.variant_a_config,
                "sent": a_total,
                "opened": test.variant_a_opened or 0,
                "clicked": test.variant_a_clicked or 0,
                "converted": test.variant_a_converted or 0,
                "open_rate": round(test.variant_a_open_rate, 2),
                "click_rate": round(test.variant_a_click_rate, 2),
                "conversion_rate": round(test.variant_a_conversion_rate, 2),
                "primary_metric_rate": round(a_rate, 2),
            },
            "variant_b": {
                "name": test.variant_b_name,
                "config": test.variant_b_config,
                "sent": b_total,
                "opened": test.variant_b_opened or 0,
                "clicked": test.variant_b_clicked or 0,
                "converted": test.variant_b_converted or 0,
                "open_rate": round(test.variant_b_open_rate, 2),
                "click_rate": round(test.variant_b_click_rate, 2),
                "conversion_rate": round(test.variant_b_conversion_rate, 2),
                "primary_metric_rate": round(b_rate, 2),
            },
            "statistics": {
                "chi_square": chi_stats,
                "z_score": z_stats,
                "confidence": chi_stats["confidence"],
                "is_significant": chi_stats["is_significant"],
                "significance_threshold": test.significance_threshold,
                "min_sample_size": test.min_sample_size,
                "current_sample_size": test.total_sample_size,
                "has_min_sample": test.has_min_sample,
            },
            "winner": winner,
            "lift": relative_improvement,
            "recommendation": self._generate_recommendation(test, chi_stats, winner, lift),
            "timestamps": {
                "created_at": test.created_at.isoformat() if test.created_at else None,
                "started_at": test.started_at.isoformat() if test.started_at else None,
                "completed_at": test.completed_at.isoformat() if test.completed_at else None,
            },
        }

    def _generate_recommendation(self, test: ABTest, stats: Dict[str, Any], winner: Optional[str], lift: float) -> str:
        """Generate a human-readable recommendation based on test results."""
        if test.status == "draft":
            return "Start the test to begin collecting data."

        if not test.has_min_sample:
            remaining = (test.min_sample_size or 100) - test.total_sample_size
            return f"Need {remaining} more samples before statistical significance can be determined."

        if not stats["is_significant"]:
            return "No statistically significant difference detected yet. Continue testing or consider ending the test if enough time has passed."

        if winner == "b":
            return f"Variant B ({test.variant_b_name}) is the winner with {abs(lift):.1f}% {'better' if lift > 0 else 'worse'} performance. Consider implementing this variant."
        elif winner == "a":
            return f"Variant A ({test.variant_a_name}) is the winner. The control performs better than the treatment."
        else:
            return "Test completed but no clear winner determined."

    async def update_metrics(self, test_id: int, variant: str, metric: str, increment: int = 1) -> Optional[ABTest]:
        """
        Update test metrics for a specific variant.

        Args:
            test_id: The A/B test ID
            variant: 'a' or 'b'
            metric: 'sent', 'opened', 'clicked', or 'converted'
            increment: Amount to increment (default 1)

        Returns:
            Updated ABTest object or None if not found
        """
        test = await self.get_test_by_id(test_id)
        if not test:
            return None

        # Validate inputs
        if variant not in ("a", "b"):
            raise ValueError("Variant must be 'a' or 'b'")
        if metric not in ("sent", "opened", "clicked", "converted"):
            raise ValueError("Metric must be 'sent', 'opened', 'clicked', or 'converted'")

        # Update the appropriate field
        field = f"variant_{variant}_{metric}"
        current = getattr(test, field, 0) or 0
        setattr(test, field, current + increment)

        # Check for auto-winner if enabled
        if test.auto_winner and test.status == "running":
            await self._check_auto_winner(test)

        await self.db.commit()
        await self.db.refresh(test)
        return test

    async def _check_auto_winner(self, test: ABTest) -> None:
        """
        Check if a winner can be automatically declared.

        Called after metric updates when auto_winner is enabled.
        """
        if not test.has_min_sample:
            return

        # Calculate statistics based on primary metric
        primary_metric = test.primary_metric or "conversion"

        if primary_metric == "conversion":
            a_success, b_success = test.variant_a_converted or 0, test.variant_b_converted or 0
        elif primary_metric == "open":
            a_success, b_success = test.variant_a_opened or 0, test.variant_b_opened or 0
        elif primary_metric == "click":
            a_success, b_success = test.variant_a_clicked or 0, test.variant_b_clicked or 0
        else:
            a_success, b_success = test.variant_a_converted or 0, test.variant_b_converted or 0

        stats = self.calculate_chi_square(a_success, test.variant_a_sent or 0, b_success, test.variant_b_sent or 0)

        # Check if significant at the configured threshold
        if stats["confidence"] >= (test.significance_threshold or 95):
            a_rate = a_success / (test.variant_a_sent or 1)
            b_rate = b_success / (test.variant_b_sent or 1)

            test.winning_variant = "a" if a_rate > b_rate else "b"
            test.confidence_level = stats["confidence"]
            test.is_significant = True
            test.status = "completed"
            test.completed_at = datetime.utcnow()

            logger.info(
                f"A/B test {test.id} auto-completed. Winner: variant_{test.winning_variant} "
                f"with {stats['confidence']:.1f}% confidence"
            )

    async def start_test(self, test_id: int) -> Optional[ABTest]:
        """Start an A/B test."""
        test = await self.get_test_by_id(test_id)
        if not test:
            return None

        if test.status != "draft":
            raise ValueError(f"Can only start tests in 'draft' status, current: {test.status}")

        test.status = "running"
        test.started_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(test)
        return test

    async def pause_test(self, test_id: int) -> Optional[ABTest]:
        """Pause a running A/B test."""
        test = await self.get_test_by_id(test_id)
        if not test:
            return None

        if test.status != "running":
            raise ValueError(f"Can only pause tests in 'running' status, current: {test.status}")

        test.status = "paused"

        await self.db.commit()
        await self.db.refresh(test)
        return test

    async def resume_test(self, test_id: int) -> Optional[ABTest]:
        """Resume a paused A/B test."""
        test = await self.get_test_by_id(test_id)
        if not test:
            return None

        if test.status != "paused":
            raise ValueError(f"Can only resume tests in 'paused' status, current: {test.status}")

        test.status = "running"

        await self.db.commit()
        await self.db.refresh(test)
        return test

    async def complete_test(self, test_id: int, winner: Optional[str] = None) -> Optional[ABTest]:
        """
        Complete an A/B test and optionally declare a winner.

        Args:
            test_id: The A/B test ID
            winner: Optional manual winner override ('a' or 'b')

        Returns:
            Updated ABTest object
        """
        test = await self.get_test_by_id(test_id)
        if not test:
            return None

        if test.status not in ("running", "paused"):
            raise ValueError(f"Can only complete tests in 'running' or 'paused' status, current: {test.status}")

        test.status = "completed"
        test.completed_at = datetime.utcnow()

        # Set winner if provided manually
        if winner:
            if winner not in ("a", "b"):
                raise ValueError("Winner must be 'a' or 'b'")
            test.winning_variant = winner
        elif not test.winning_variant:
            # Calculate winner if not already set
            results = await self.get_test_results(test_id)
            if results and results.get("winner"):
                test.winning_variant = results["winner"]
                test.confidence_level = results["statistics"]["confidence"]
                test.is_significant = results["statistics"]["is_significant"]

        await self.db.commit()
        await self.db.refresh(test)
        return test

    async def assign_variant(self, test_id: int) -> Optional[str]:
        """
        Assign a variant for a new recipient based on traffic split.

        Args:
            test_id: The A/B test ID

        Returns:
            'a' or 'b' based on traffic split, or None if test not found/not running
        """
        test = await self.get_test_by_id(test_id)
        if not test or test.status != "running":
            return None

        import random

        # traffic_split is the percentage going to variant B
        if random.random() * 100 < (test.traffic_split or 50):
            return "b"
        return "a"

    async def get_campaign_tests(self, campaign_id: int) -> list[ABTest]:
        """Get all A/B tests for a campaign."""
        result = await self.db.execute(
            select(ABTest).where(ABTest.campaign_id == campaign_id).order_by(ABTest.created_at.desc())
        )
        return list(result.scalars().all())
