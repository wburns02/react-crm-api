"""AI Campaign Optimizer - Intelligent Campaign Recommendations

This service leverages the AI gateway (local LLM via vLLM) to provide:
- Campaign performance analysis and insights
- A/B test subject line suggestions
- Portfolio-wide campaign insights
- Campaign success predictions
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.services.ai_gateway import ai_gateway
from app.models.customer_success.campaign import Campaign, CampaignStep, CampaignEnrollment

logger = logging.getLogger(__name__)


class AICampaignOptimizer:
    """AI-powered campaign optimization and recommendations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def analyze_campaign_performance(self, campaign_id: int) -> Dict[str, Any]:
        """Analyze campaign performance and generate AI insights.

        Args:
            campaign_id: The ID of the campaign to analyze

        Returns:
            Dict containing campaign analysis with health score, insights,
            recommendations, bottlenecks, and opportunities
        """
        # Get campaign with all data
        result = await self.db.execute(
            select(Campaign)
            .options(selectinload(Campaign.steps))
            .where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            return {"error": "Campaign not found"}

        # Build context for AI
        campaign_data = {
            "name": campaign.name,
            "type": campaign.campaign_type,
            "status": campaign.status,
            "goal_type": campaign.goal_type,
            "enrolled_count": campaign.enrolled_count or 0,
            "converted_count": campaign.converted_count or 0,
            "conversion_rate": campaign.conversion_rate or 0,
            "steps": [
                {
                    "name": s.name,
                    "type": s.step_type,
                    "sent_count": s.sent_count or 0,
                    "open_rate": s.open_rate,
                    "click_rate": s.click_rate,
                    "delay_days": s.delay_days
                }
                for s in campaign.steps
            ]
        }

        # Generate AI analysis
        prompt = f"""Analyze this marketing campaign and provide actionable insights:

Campaign: {json.dumps(campaign_data, indent=2)}

Provide analysis in this JSON format:
{{
    "overall_health": "good|needs_attention|poor",
    "health_score": 0-100,
    "key_insights": ["insight1", "insight2", "insight3"],
    "recommendations": [
        {{"priority": "high|medium|low", "action": "description", "expected_impact": "description"}}
    ],
    "bottlenecks": ["step or issue causing problems"],
    "opportunities": ["potential improvements"]
}}"""

        response = await ai_gateway.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.3
        )

        try:
            content = response.get("content", "{}")
            # Handle markdown code blocks in response
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            analysis = json.loads(content.strip())
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse AI response for campaign {campaign_id}")
            # Provide fallback analysis based on raw metrics
            analysis = self._generate_fallback_analysis(campaign)

        return {
            "campaign_id": campaign_id,
            "campaign_name": campaign.name,
            "analysis": analysis,
            "analyzed_at": datetime.utcnow().isoformat()
        }

    def _generate_fallback_analysis(self, campaign: Campaign) -> Dict[str, Any]:
        """Generate fallback analysis when AI is unavailable."""
        conversion_rate = campaign.conversion_rate or 0
        enrolled = campaign.enrolled_count or 0

        # Determine health based on conversion rate
        if conversion_rate >= 15:
            health = "good"
            score = 80
        elif conversion_rate >= 5:
            health = "needs_attention"
            score = 50
        else:
            health = "poor"
            score = 30

        insights = []
        recommendations = []

        if enrolled < 100:
            insights.append("Low enrollment count may limit statistical significance")
            recommendations.append({
                "priority": "medium",
                "action": "Expand target segment to increase enrollments",
                "expected_impact": "Better data for optimization decisions"
            })

        if conversion_rate < 5:
            insights.append("Conversion rate is below industry average")
            recommendations.append({
                "priority": "high",
                "action": "Review campaign content and targeting",
                "expected_impact": "Potential 2-3x improvement in conversions"
            })

        return {
            "overall_health": health,
            "health_score": score,
            "key_insights": insights or ["Campaign metrics are within normal range"],
            "recommendations": recommendations,
            "bottlenecks": [],
            "opportunities": ["Consider A/B testing subject lines"]
        }

    async def suggest_subject_lines(self, original_subject: str, campaign_goal: str) -> Dict[str, Any]:
        """Generate A/B test subject line variants.

        Args:
            original_subject: The current subject line
            campaign_goal: The goal of the campaign (engagement, conversion, etc.)

        Returns:
            Dict containing original subject, variants with strategies,
            and a recommendation for which to test first
        """
        prompt = f"""Generate 3 alternative email subject lines for A/B testing.

Original: "{original_subject}"
Campaign Goal: {campaign_goal}

Provide variants in JSON format:
{{
    "original": "{original_subject}",
    "variants": [
        {{"subject": "variant1", "strategy": "what makes this different"}},
        {{"subject": "variant2", "strategy": "what makes this different"}},
        {{"subject": "variant3", "strategy": "what makes this different"}}
    ],
    "recommended_test": "which variant to test first and why"
}}"""

        response = await ai_gateway.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=0.7  # Higher temperature for creative variations
        )

        try:
            content = response.get("content", "{}")
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            suggestions = json.loads(content.strip())
        except json.JSONDecodeError:
            logger.warning("Failed to parse AI response for subject line suggestions")
            # Provide fallback suggestions
            suggestions = {
                "original": original_subject,
                "variants": [
                    {"subject": f"[Action Required] {original_subject}", "strategy": "urgency"},
                    {"subject": f"Quick tip: {original_subject}", "strategy": "value-focused"},
                    {"subject": f"Don't miss: {original_subject}", "strategy": "FOMO"}
                ],
                "recommended_test": "Start with urgency variant for business audience"
            }

        return suggestions

    async def generate_campaign_insights(self) -> Dict[str, Any]:
        """Generate insights across all campaigns.

        Returns:
            Dict containing portfolio health assessment, top performer,
            campaigns needing attention, strategic insights, quick wins,
            and resource allocation recommendations
        """
        # Get all active campaigns with metrics
        result = await self.db.execute(
            select(Campaign)
            .options(selectinload(Campaign.steps))
            .where(Campaign.status.in_(["active", "paused"]))
        )
        campaigns = result.scalars().all()

        if not campaigns:
            return {
                "campaign_count": 0,
                "insights": {"message": "No active campaigns found"},
                "generated_at": datetime.utcnow().isoformat()
            }

        # Build summary for AI
        campaign_summaries = []
        for c in campaigns:
            campaign_summaries.append({
                "name": c.name,
                "type": c.campaign_type,
                "enrolled": c.enrolled_count or 0,
                "conversion_rate": c.conversion_rate or 0,
                "status": c.status
            })

        prompt = f"""Analyze these marketing campaigns and provide strategic insights:

Campaigns: {json.dumps(campaign_summaries, indent=2)}

Provide insights in JSON format:
{{
    "portfolio_health": "healthy|mixed|needs_work",
    "top_performer": "campaign name",
    "needs_attention": ["campaign names"],
    "strategic_insights": [
        {{"category": "performance|timing|targeting|content", "insight": "description", "action": "recommendation"}}
    ],
    "quick_wins": ["easy improvements"],
    "resource_allocation": "where to focus efforts"
}}"""

        response = await ai_gateway.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.3
        )

        try:
            content = response.get("content", "{}")
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            insights = json.loads(content.strip())
        except json.JSONDecodeError:
            logger.warning("Failed to parse AI response for portfolio insights")
            # Generate fallback insights
            insights = self._generate_fallback_portfolio_insights(campaigns)

        return {
            "campaign_count": len(campaigns),
            "insights": insights,
            "generated_at": datetime.utcnow().isoformat()
        }

    def _generate_fallback_portfolio_insights(self, campaigns: List[Campaign]) -> Dict[str, Any]:
        """Generate fallback portfolio insights when AI is unavailable."""
        if not campaigns:
            return {"portfolio_health": "needs_work", "message": "No campaigns to analyze"}

        # Find top performer by conversion rate
        top_performer = max(campaigns, key=lambda c: c.conversion_rate or 0)

        # Find campaigns needing attention (low conversion or paused)
        needs_attention = [
            c.name for c in campaigns
            if (c.conversion_rate or 0) < 5 or c.status == "paused"
        ]

        # Calculate average conversion rate
        avg_conversion = sum(c.conversion_rate or 0 for c in campaigns) / len(campaigns)

        if avg_conversion >= 10:
            health = "healthy"
        elif avg_conversion >= 5:
            health = "mixed"
        else:
            health = "needs_work"

        return {
            "portfolio_health": health,
            "top_performer": top_performer.name if top_performer else "None",
            "needs_attention": needs_attention[:5],  # Limit to top 5
            "strategic_insights": [
                {
                    "category": "performance",
                    "insight": f"Average conversion rate is {avg_conversion:.1f}%",
                    "action": "Review underperforming campaigns for optimization"
                }
            ],
            "quick_wins": ["Review subject lines for low-performing campaigns"],
            "resource_allocation": "Focus on campaigns with highest engagement potential"
        }

    async def predict_campaign_success(self, campaign_config: Dict[str, Any]) -> Dict[str, Any]:
        """Predict likely success of a campaign based on configuration.

        Args:
            campaign_config: Campaign configuration including name, type, goal,
                           target_segment, and steps

        Returns:
            Dict containing predicted success score, confidence level,
            strengths, risks, suggested improvements, and expected metrics
        """
        prompt = f"""Predict the likely success of this campaign configuration:

{json.dumps(campaign_config, indent=2)}

Provide prediction in JSON format:
{{
    "predicted_success_score": 0-100,
    "confidence": "high|medium|low",
    "strengths": ["what's good about this campaign"],
    "risks": ["potential issues"],
    "suggested_improvements": ["ways to increase success"],
    "expected_metrics": {{
        "open_rate_estimate": "X-Y%",
        "click_rate_estimate": "X-Y%",
        "conversion_rate_estimate": "X-Y%"
    }}
}}"""

        response = await ai_gateway.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=768,
            temperature=0.4
        )

        try:
            content = response.get("content", "{}")
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            prediction = json.loads(content.strip())
        except json.JSONDecodeError:
            logger.warning("Failed to parse AI response for campaign prediction")
            # Generate fallback prediction
            prediction = self._generate_fallback_prediction(campaign_config)

        return prediction

    def _generate_fallback_prediction(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Generate fallback prediction when AI is unavailable."""
        steps = config.get("steps", [])
        has_email = any("email" in str(s).lower() for s in steps)
        has_multiple_steps = len(steps) > 2

        # Base score
        score = 50
        strengths = []
        risks = []
        improvements = []

        if has_multiple_steps:
            score += 15
            strengths.append("Multi-step sequence allows for nurturing")
        else:
            risks.append("Limited touchpoints may reduce effectiveness")
            improvements.append("Consider adding more steps to the sequence")

        if has_email:
            score += 10
            strengths.append("Email is a proven channel for engagement")

        campaign_type = config.get("type", "").lower()
        if campaign_type in ["onboarding", "nurture"]:
            score += 10
            strengths.append(f"{campaign_type.title()} campaigns typically have good engagement")

        return {
            "predicted_success_score": min(score, 100),
            "confidence": "low",
            "strengths": strengths or ["Campaign configuration is reasonable"],
            "risks": risks or ["Limited data for prediction"],
            "suggested_improvements": improvements or ["Run A/B tests to optimize performance"],
            "expected_metrics": {
                "open_rate_estimate": "15-25%",
                "click_rate_estimate": "2-5%",
                "conversion_rate_estimate": "1-3%"
            }
        }

    async def optimize_send_time(self, campaign_id: int) -> Dict[str, Any]:
        """Suggest optimal send times based on historical engagement data.

        Args:
            campaign_id: The campaign to optimize send times for

        Returns:
            Dict containing recommended send times by day and hour,
            along with engagement predictions
        """
        # Get campaign enrollment and execution data
        result = await self.db.execute(
            select(Campaign)
            .options(
                selectinload(Campaign.steps),
                selectinload(Campaign.enrollments)
            )
            .where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()

        if not campaign:
            return {"error": "Campaign not found"}

        # Analyze engagement patterns (simplified - would use historical data in production)
        engagement_data = {
            "campaign_name": campaign.name,
            "current_send_times": [
                {"step": s.name, "send_at": s.send_at_time, "days": s.send_on_days}
                for s in campaign.steps if s.send_at_time
            ],
            "total_enrollments": campaign.enrolled_count or 0
        }

        prompt = f"""Analyze this campaign's engagement data and suggest optimal send times:

{json.dumps(engagement_data, indent=2)}

Provide recommendations in JSON format:
{{
    "recommended_times": [
        {{"day": "weekday|weekend", "hour": "HH:MM", "reason": "why this time"}},
    ],
    "avoid_times": ["times to avoid and why"],
    "timezone_considerations": "advice about timezone handling",
    "expected_improvement": "estimated engagement lift"
}}"""

        response = await ai_gateway.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
            temperature=0.3
        )

        try:
            content = response.get("content", "{}")
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            recommendations = json.loads(content.strip())
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse AI response for send time optimization")
            recommendations = {
                "recommended_times": [
                    {"day": "weekday", "hour": "10:00", "reason": "Mid-morning has high open rates"},
                    {"day": "weekday", "hour": "14:00", "reason": "Post-lunch engagement peak"}
                ],
                "avoid_times": ["Late night (after 9 PM)", "Early morning (before 7 AM)"],
                "timezone_considerations": "Send based on recipient's local timezone when possible",
                "expected_improvement": "10-20% lift in open rates with optimized timing"
            }

        return {
            "campaign_id": campaign_id,
            "campaign_name": campaign.name,
            "recommendations": recommendations,
            "analyzed_at": datetime.utcnow().isoformat()
        }
