"""
AI-Guided Escalation Endpoints for Enterprise Customer Success Platform

"What Do I Do Now?" System - So Simple a 12-Year-Old Can Achieve 95% CSAT and 85 NPS

These endpoints provide AI-powered guidance for escalation resolution:
- Sentiment analysis
- Recommended actions with scripts
- Playbook matching
- Proactive alerts
- Action queue with priority scores
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select
from typing import Optional
from datetime import datetime
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.customer_success import Escalation
from app.services.escalation_ai_service import escalation_ai_service, PLAYBOOKS

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{escalation_id}/ai-guidance")
async def get_ai_guidance(
    escalation_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Get AI guidance for an escalation - the 'WHAT DO I DO NOW?' answer.

    Returns:
    - Summary of the situation
    - Customer sentiment analysis with emoji
    - Recommended action with exact words to say
    - Success prediction
    - Playbook to follow
    - Similar resolved cases for reference
    """
    try:
        guidance = await escalation_ai_service.get_guidance(db, escalation_id)

        if "error" in guidance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=guidance["error"],
            )

        return guidance
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting AI guidance: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting AI guidance: {str(e)}"
        )


@router.get("/ai/alerts")
async def get_ai_alerts(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Get proactive alerts for escalations needing attention.

    Returns alerts for:
    - SLA about to breach (within 30 minutes)
    - Critical severity unassigned
    - No response for 2+ hours
    """
    try:
        alerts = await escalation_ai_service.get_proactive_alerts(db, current_user.id)
        return {
            "alerts": alerts,
            "total": len(alerts),
        }
    except Exception as e:
        logger.error(f"Error getting AI alerts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting AI alerts: {str(e)}"
        )


@router.post("/{escalation_id}/ai-generate-response")
async def generate_ai_response(
    escalation_id: int,
    db: DbSession,
    current_user: CurrentUser,
    response_type: str = Query("email", description="Type of response: email, sms, chat"),
):
    """
    Generate an AI response for the escalation.

    Returns generated text that can be edited before sending.
    """
    try:
        response = await escalation_ai_service.generate_response(db, escalation_id, response_type)

        if "error" in response:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=response["error"],
            )

        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating AI response: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating AI response: {str(e)}"
        )


@router.get("/ai/action-queue")
async def get_action_queue(
    db: DbSession,
    current_user: CurrentUser,
    assigned_to_me: bool = Query(True, description="Only show escalations assigned to current user"),
):
    """
    Get prioritized action queue for escalations.

    Returns escalations sorted by priority score with AI recommendations,
    designed to show the most urgent items at the top with clear action buttons.
    """
    try:
        # Get open/in-progress escalations
        query = select(Escalation).where(
            Escalation.status.in_(["open", "in_progress", "pending_customer", "pending_internal"])
        )

        if assigned_to_me:
            query = query.where(Escalation.assigned_to_user_id == current_user.id)

        result = await db.execute(query)
        escalations = result.scalars().all()

        # Build action queue with AI analysis
        queue_items = []
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for esc in escalations:
            # Get AI guidance for each escalation
            guidance = await escalation_ai_service.get_guidance(db, esc.id)

            # Get customer name
            cust_result = await db.execute(
                select(Customer.name).where(Customer.id == esc.customer_id)
            )
            customer_name = cust_result.scalar_one_or_none() or "Unknown"

            # Calculate time remaining
            time_remaining = None
            if esc.sla_deadline:
                delta = esc.sla_deadline - datetime.utcnow()
                time_remaining = int(delta.total_seconds() / 60)

            queue_items.append({
                "escalation_id": esc.id,
                "customer_name": customer_name,
                "title": esc.title,
                "severity": esc.severity,
                "sentiment_emoji": guidance.get("sentiment", {}).get("emoji", ""),
                "sentiment_label": guidance.get("sentiment", {}).get("label", "Unknown"),
                "time_remaining_minutes": time_remaining,
                "sla_status": guidance.get("sla_status", {}).get("status", "unknown"),
                "sla_color": guidance.get("sla_status", {}).get("color", "gray"),
                "recommended_action": guidance.get("recommended_action", {}).get("type", "call"),
                "big_button_text": guidance.get("recommended_action", {}).get("big_button_text", "TAKE ACTION"),
                "priority_score": guidance.get("priority_score", 50),
            })

            # Count by severity
            if esc.severity in severity_counts:
                severity_counts[esc.severity] += 1

        # Sort by priority score (highest first)
        queue_items.sort(key=lambda x: x["priority_score"], reverse=True)

        return {
            "items": queue_items,
            "total": len(queue_items),
            "critical_count": severity_counts["critical"],
            "high_count": severity_counts["high"],
            "medium_count": severity_counts["medium"],
            "low_count": severity_counts["low"],
        }
    except Exception as e:
        logger.error(f"Error getting action queue: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting action queue: {str(e)}"
        )


@router.get("/ai/playbooks")
async def list_playbooks(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    List available escalation playbooks.

    Returns all pre-built playbooks with success rates and trigger conditions.
    """
    playbooks = []
    for playbook_id, playbook in PLAYBOOKS.items():
        playbooks.append({
            "id": playbook_id,
            "name": playbook["name"],
            "trigger_keywords": playbook["trigger_keywords"],
            "success_rate": playbook["success_rate"],
            "steps_count": len(playbook["steps"]),
            "steps": playbook["steps"],
        })

    return {
        "playbooks": playbooks,
        "total": len(playbooks),
    }


@router.get("/ai/playbooks/{playbook_id}")
async def get_playbook(
    playbook_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Get details of a specific playbook.
    """
    playbook = PLAYBOOKS.get(playbook_id)
    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    return {
        "id": playbook_id,
        "name": playbook["name"],
        "trigger_keywords": playbook["trigger_keywords"],
        "success_rate": playbook["success_rate"],
        "steps": playbook["steps"],
    }
