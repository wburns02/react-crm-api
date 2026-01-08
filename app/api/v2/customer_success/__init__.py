"""
Customer Success Platform API Endpoints

Enterprise-grade Customer Success Platform with:
- Health Score Management
- Customer Segmentation
- Journey Orchestration
- Playbook Management
- Task Management
- Touchpoint Tracking
- Survey Management (NPS/CSAT/CES)
- Campaign Management
- Escalation Management
- Collaboration Hub
- AI Campaign Optimizer (AI-powered campaign insights and recommendations)
- A/B Testing (Campaign optimization testing)
"""

from app.api.v2.customer_success.health_scores import router as health_scores_router
from app.api.v2.customer_success.segments import router as segments_router
from app.api.v2.customer_success.journeys import router as journeys_router
from app.api.v2.customer_success.playbooks import router as playbooks_router
from app.api.v2.customer_success.tasks import router as tasks_router
from app.api.v2.customer_success.touchpoints import router as touchpoints_router
from app.api.v2.customer_success.dashboard import router as dashboard_router
from app.api.v2.customer_success.surveys import router as surveys_router
from app.api.v2.customer_success.campaigns import router as campaigns_router
from app.api.v2.customer_success.escalations import router as escalations_router
from app.api.v2.customer_success.collaboration import router as collaboration_router
from app.api.v2.customer_success.ai_insights import router as ai_insights_router
from app.api.v2.customer_success.ab_tests import router as ab_tests_router

__all__ = [
    "health_scores_router",
    "segments_router",
    "journeys_router",
    "playbooks_router",
    "tasks_router",
    "touchpoints_router",
    "dashboard_router",
    "surveys_router",
    "campaigns_router",
    "escalations_router",
    "collaboration_router",
    "ai_insights_router",
    "ab_tests_router",
]
