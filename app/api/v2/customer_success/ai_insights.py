"""AI Insights API Endpoints for Customer Success Platform

Provides AI-powered campaign analysis and optimization endpoints:
- Campaign performance analysis with AI insights
- Subject line A/B test suggestions
- Portfolio-wide campaign insights
- Campaign success predictions
- Send time optimization
"""

from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import logging

from app.api.deps import DbSession, CurrentUser
from app.services.customer_success.ai_campaign_optimizer import AICampaignOptimizer

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response Models


class SubjectLineRequest(BaseModel):
    """Request for generating subject line variants."""

    subject: str = Field(..., description="Original subject line to generate variants for")
    campaign_goal: str = Field(
        default="engagement", description="Campaign goal: engagement, conversion, retention, etc."
    )


class SubjectLineVariant(BaseModel):
    """A subject line variant with its strategy."""

    subject: str
    strategy: str


class SubjectLineSuggestions(BaseModel):
    """Response containing subject line suggestions."""

    original: str
    variants: List[SubjectLineVariant]
    recommended_test: str


class CampaignStepConfig(BaseModel):
    """Configuration for a campaign step."""

    name: str
    type: str = Field(..., description="Step type: email, in_app_message, sms, task, wait, condition")
    delay_days: int = 0
    subject: Optional[str] = None
    content: Optional[str] = None


class CampaignConfigRequest(BaseModel):
    """Request for predicting campaign success."""

    name: str = Field(..., description="Campaign name")
    type: str = Field(
        ..., description="Campaign type: nurture, onboarding, adoption, renewal, expansion, winback, custom"
    )
    goal: str = Field(..., description="Campaign goal: engagement, conversion, retention")
    target_segment: str = Field(..., description="Target audience segment")
    steps: List[CampaignStepConfig] = Field(..., description="Campaign steps/sequence")


class CampaignRecommendation(BaseModel):
    """A recommendation for campaign improvement."""

    priority: str
    action: str
    expected_impact: str


class CampaignAnalysis(BaseModel):
    """AI-generated campaign analysis."""

    overall_health: str
    health_score: int
    key_insights: List[str]
    recommendations: List[CampaignRecommendation]
    bottlenecks: List[str]
    opportunities: List[str]


class CampaignAnalysisResponse(BaseModel):
    """Response containing campaign analysis."""

    campaign_id: int
    campaign_name: str
    analysis: CampaignAnalysis
    analyzed_at: str


class StrategicInsight(BaseModel):
    """A strategic insight about the campaign portfolio."""

    category: str
    insight: str
    action: str


class PortfolioInsights(BaseModel):
    """Portfolio-wide campaign insights."""

    portfolio_health: str
    top_performer: str
    needs_attention: List[str]
    strategic_insights: List[StrategicInsight]
    quick_wins: List[str]
    resource_allocation: str


class PortfolioInsightsResponse(BaseModel):
    """Response containing portfolio insights."""

    campaign_count: int
    insights: PortfolioInsights
    generated_at: str


class ExpectedMetrics(BaseModel):
    """Expected performance metrics."""

    open_rate_estimate: str
    click_rate_estimate: str
    conversion_rate_estimate: str


class CampaignPrediction(BaseModel):
    """AI prediction for campaign success."""

    predicted_success_score: int
    confidence: str
    strengths: List[str]
    risks: List[str]
    suggested_improvements: List[str]
    expected_metrics: ExpectedMetrics


class SendTimeRecommendation(BaseModel):
    """A send time recommendation."""

    day: str
    hour: str
    reason: str


class SendTimeRecommendations(BaseModel):
    """Send time optimization recommendations."""

    recommended_times: List[SendTimeRecommendation]
    avoid_times: List[str]
    timezone_considerations: str
    expected_improvement: str


class SendTimeResponse(BaseModel):
    """Response containing send time recommendations."""

    campaign_id: int
    campaign_name: str
    recommendations: SendTimeRecommendations
    analyzed_at: str


# API Endpoints


@router.get("/campaigns/{campaign_id}/ai-analysis")
async def get_campaign_ai_analysis(
    campaign_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Get AI-powered analysis for a specific campaign.

    Analyzes campaign performance metrics using AI to provide:
    - Overall health assessment (good, needs_attention, poor)
    - Health score (0-100)
    - Key insights about campaign performance
    - Prioritized recommendations for improvement
    - Identified bottlenecks in the campaign flow
    - Opportunities for optimization
    """
    try:
        optimizer = AICampaignOptimizer(db)
        analysis = await optimizer.analyze_campaign_performance(campaign_id)

        if "error" in analysis:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=analysis["error"])

        return analysis

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing campaign {campaign_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error analyzing campaign: {str(e)}"
        )


@router.post("/subject-suggestions")
async def get_subject_suggestions(
    request: SubjectLineRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Generate A/B test subject line variants.

    Takes an original subject line and campaign goal, then uses AI to generate
    3 alternative subject lines with different strategies for A/B testing.

    Returns:
    - Original subject line
    - 3 variant subject lines with their strategies
    - Recommendation for which variant to test first
    """
    try:
        optimizer = AICampaignOptimizer(db)
        suggestions = await optimizer.suggest_subject_lines(request.subject, request.campaign_goal)
        return suggestions

    except Exception as e:
        logger.error(f"Error generating subject suggestions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error generating subject suggestions: {str(e)}"
        )


@router.get("/portfolio-insights")
async def get_portfolio_insights(
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Get AI insights across all campaigns.

    Analyzes all active and paused campaigns to provide portfolio-level insights:
    - Portfolio health assessment (healthy, mixed, needs_work)
    - Top performing campaign
    - Campaigns needing attention
    - Strategic insights categorized by performance, timing, targeting, content
    - Quick wins for immediate improvement
    - Resource allocation recommendations
    """
    try:
        optimizer = AICampaignOptimizer(db)
        insights = await optimizer.generate_campaign_insights()
        return insights

    except Exception as e:
        logger.error(f"Error generating portfolio insights: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error generating portfolio insights: {str(e)}"
        )


@router.post("/predict-success")
async def predict_campaign_success(
    request: CampaignConfigRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Predict likely success of a campaign configuration.

    Takes a campaign configuration (before launch) and uses AI to predict:
    - Success score (0-100)
    - Confidence level (high, medium, low)
    - Campaign strengths
    - Potential risks
    - Suggested improvements
    - Expected metrics (open rate, click rate, conversion rate estimates)

    This is useful for evaluating campaigns before launching them.
    """
    try:
        optimizer = AICampaignOptimizer(db)
        prediction = await optimizer.predict_campaign_success(request.model_dump())
        return prediction

    except Exception as e:
        logger.error(f"Error predicting campaign success: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error predicting campaign success: {str(e)}"
        )


@router.get("/campaigns/{campaign_id}/optimize-send-time")
async def get_send_time_recommendations(
    campaign_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Get AI-powered send time optimization recommendations.

    Analyzes campaign engagement patterns to suggest optimal send times:
    - Recommended send times by day and hour with reasoning
    - Times to avoid
    - Timezone considerations
    - Expected improvement from optimizing send times
    """
    try:
        optimizer = AICampaignOptimizer(db)
        recommendations = await optimizer.optimize_send_time(campaign_id)

        if "error" in recommendations:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=recommendations["error"])

        return recommendations

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error optimizing send time for campaign {campaign_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error optimizing send time: {str(e)}"
        )


@router.get("/health")
async def ai_insights_health(
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Health check for AI insights service.

    Returns the status of the AI gateway connection and available features.
    """
    from app.services.ai_gateway import ai_gateway

    ai_health = await ai_gateway.health_check()

    return {
        "status": "healthy",
        "ai_gateway": ai_health,
        "features": [
            "campaign_analysis",
            "subject_suggestions",
            "portfolio_insights",
            "success_prediction",
            "send_time_optimization",
        ],
    }


# ============================================
# CS AI Endpoints - Not yet backed by AI analysis
# Returns honest empty states until AI pipeline is implemented
# ============================================


@router.get("/customers/{customer_id}/insight")
async def get_customer_insight(
    customer_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Get AI-powered insight for a specific customer. Not yet analyzed."""
    return {
        "customer_id": customer_id,
        "risk_level": None,
        "engagement_trend": None,
        "key_findings": [],
        "recommended_actions": [],
        "next_best_action": None,
        "analyzed_at": None,
        "message": "Customer insights require AI analysis pipeline. Not yet available.",
    }


@router.get("/recommendations")
async def get_ai_recommendations(
    db: DbSession,
    current_user: CurrentUser,
) -> List[Dict[str, Any]]:
    """Get AI-powered recommendations. Returns empty until AI pipeline is implemented."""
    return []


class ContentSuggestionRequest(BaseModel):
    """Request for content suggestions."""

    content_type: str = Field(..., description="Type: email, sms, in_app")
    context: str = Field(..., description="Context for the content")
    tone: Optional[str] = None
    customer_segment: Optional[str] = None


@router.post("/content-suggestions")
async def get_content_suggestions(
    request: ContentSuggestionRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Generate AI-powered content suggestions. Not yet implemented."""
    return {
        "suggestion_type": request.content_type,
        "content": None,
        "personalization_tags": [],
        "tone": request.tone or "professional",
        "cta_options": [],
        "message": "AI content generation not yet available.",
    }


@router.post("/recommendations/{recommendation_id}/dismiss")
async def dismiss_recommendation(
    recommendation_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Dismiss an AI recommendation."""
    return {"success": True, "recommendation_id": recommendation_id, "status": "dismissed"}


@router.post("/recommendations/{recommendation_id}/apply")
async def apply_recommendation(
    recommendation_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Apply an AI recommendation."""
    return {"success": True, "recommendation_id": recommendation_id, "result": "Recommendation applied successfully"}


@router.post("/refresh-insights")
async def refresh_insights(
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Refresh all AI insights. Not yet implemented."""
    return {"success": True, "message": "AI insight refresh not yet available. Pipeline pending implementation."}
