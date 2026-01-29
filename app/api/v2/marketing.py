"""Marketing API - Campaigns and automation workflows."""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.marketing import MarketingCampaign, MarketingWorkflow, WorkflowEnrollment, EmailTemplate, SMSTemplate

logger = logging.getLogger(__name__)
router = APIRouter()


# Request Models


class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = None
    campaign_type: str
    target_segment: Optional[dict] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    campaign_id: Optional[str] = None
    trigger_type: str
    trigger_config: Optional[dict] = None
    steps: List[dict]


class EmailTemplateCreate(BaseModel):
    name: str
    subject: str
    body_html: str
    body_text: Optional[str] = None
    category: Optional[str] = None
    variables: Optional[List[str]] = None


class SMSTemplateCreate(BaseModel):
    name: str
    body: str = Field(..., max_length=160)
    category: Optional[str] = None
    variables: Optional[List[str]] = None


# Campaign Endpoints


@router.get("/campaigns")
async def list_campaigns(
    db: DbSession,
    current_user: CurrentUser,
    status_filter: Optional[str] = Query(None, alias="status"),
    campaign_type: Optional[str] = None,
):
    """List marketing campaigns."""
    query = select(MarketingCampaign)

    if status_filter:
        query = query.where(MarketingCampaign.status == status_filter)
    if campaign_type:
        query = query.where(MarketingCampaign.campaign_type == campaign_type)

    query = query.order_by(MarketingCampaign.created_at.desc())
    result = await db.execute(query)
    campaigns = result.scalars().all()

    return {
        "items": [
            {
                "id": str(c.id),
                "name": c.name,
                "description": c.description,
                "campaign_type": c.campaign_type,
                "status": c.status,
                "start_date": c.start_date.isoformat() if c.start_date else None,
                "end_date": c.end_date.isoformat() if c.end_date else None,
                "total_sent": c.total_sent,
                "total_opened": c.total_opened,
                "total_clicked": c.total_clicked,
                "total_converted": c.total_converted,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in campaigns
        ],
    }


@router.post("/campaigns")
async def create_campaign(
    request: CampaignCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new marketing campaign."""
    campaign = MarketingCampaign(
        **request.model_dump(),
        created_by=current_user.email,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    return {"id": str(campaign.id), "status": "created"}


@router.post("/campaigns/{campaign_id}/activate")
async def activate_campaign(
    campaign_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Activate a campaign."""
    result = await db.execute(select(MarketingCampaign).where(MarketingCampaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign.status = "active"
    await db.commit()

    return {"status": "active"}


# Workflow Endpoints


@router.get("/workflows")
async def list_workflows(
    db: DbSession,
    current_user: CurrentUser,
    is_active: Optional[bool] = None,
):
    """List marketing workflows."""
    query = select(MarketingWorkflow)

    if is_active is not None:
        query = query.where(MarketingWorkflow.is_active == is_active)

    result = await db.execute(query)
    workflows = result.scalars().all()

    return {
        "items": [
            {
                "id": str(w.id),
                "name": w.name,
                "description": w.description,
                "trigger_type": w.trigger_type,
                "is_active": w.is_active,
                "total_enrolled": w.total_enrolled,
                "total_completed": w.total_completed,
                "steps_count": len(w.steps) if w.steps else 0,
            }
            for w in workflows
        ],
    }


@router.post("/workflows")
async def create_workflow(
    request: WorkflowCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new workflow."""
    data = request.model_dump()
    if data.get("campaign_id"):
        data["campaign_id"] = data["campaign_id"]

    workflow = MarketingWorkflow(**data)
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)

    return {"id": str(workflow.id), "status": "created"}


@router.post("/workflows/{workflow_id}/enroll")
async def enroll_customer(
    workflow_id: str,
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Enroll a customer in a workflow."""
    # Check workflow exists
    wf_result = await db.execute(select(MarketingWorkflow).where(MarketingWorkflow.id == workflow_id))
    workflow = wf_result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Check if already enrolled
    existing = await db.execute(
        select(WorkflowEnrollment).where(
            WorkflowEnrollment.workflow_id == workflow_id,
            WorkflowEnrollment.customer_id == int(customer_id),
            WorkflowEnrollment.status == "active",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Customer already enrolled")

    enrollment = WorkflowEnrollment(
        workflow_id=workflow.id,
        customer_id=int(customer_id),
    )
    db.add(enrollment)

    workflow.total_enrolled += 1
    await db.commit()

    return {"enrollment_id": str(enrollment.id), "status": "enrolled"}


# Template Endpoints


@router.get("/templates/email")
async def list_email_templates(
    db: DbSession,
    current_user: CurrentUser,
    category: Optional[str] = None,
):
    """List email templates."""
    query = select(EmailTemplate).where(EmailTemplate.is_active == True)

    if category:
        query = query.where(EmailTemplate.category == category)

    result = await db.execute(query)
    templates = result.scalars().all()

    return {
        "items": [
            {
                "id": str(t.id),
                "name": t.name,
                "subject": t.subject,
                "category": t.category,
                "variables": t.variables,
            }
            for t in templates
        ],
    }


@router.post("/templates/email")
async def create_email_template(
    request: EmailTemplateCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create an email template."""
    template = EmailTemplate(**request.model_dump())
    db.add(template)
    await db.commit()
    await db.refresh(template)

    return {"id": str(template.id)}


@router.get("/templates/sms")
async def list_sms_templates(
    db: DbSession,
    current_user: CurrentUser,
    category: Optional[str] = None,
):
    """List SMS templates."""
    query = select(SMSTemplate).where(SMSTemplate.is_active == True)

    if category:
        query = query.where(SMSTemplate.category == category)

    result = await db.execute(query)
    templates = result.scalars().all()

    return {
        "items": [
            {
                "id": str(t.id),
                "name": t.name,
                "body": t.body,
                "category": t.category,
                "variables": t.variables,
            }
            for t in templates
        ],
    }


@router.post("/templates/sms")
async def create_sms_template(
    request: SMSTemplateCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create an SMS template."""
    template = SMSTemplate(**request.model_dump())
    db.add(template)
    await db.commit()
    await db.refresh(template)

    return {"id": str(template.id)}
