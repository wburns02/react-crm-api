"""
Campaign API Endpoints for Enterprise Customer Success Platform

Provides endpoints for managing nurture campaigns and customer enrollments.
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, timedelta
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.customer_success import Campaign, CampaignStep, CampaignEnrollment, CampaignStepExecution, Segment
from app.schemas.customer_success.campaign import (
    CampaignCreate,
    CampaignUpdate,
    CampaignResponse,
    CampaignListResponse,
    CampaignStepCreate,
    CampaignStepUpdate,
    CampaignStepResponse,
    CampaignEnrollmentCreate,
    CampaignEnrollmentUpdate,
    CampaignEnrollmentResponse,
    EnrollmentListResponse,
    CampaignAnalytics,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# Campaign CRUD


@router.get("/", response_model=CampaignListResponse)
async def list_campaigns(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    campaign_type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    """List campaigns with filtering."""
    try:
        query = select(Campaign).options(selectinload(Campaign.steps))

        if campaign_type:
            query = query.where(Campaign.campaign_type == campaign_type)
        if status:
            query = query.where(Campaign.status == status)
        if search:
            query = query.where(Campaign.name.ilike(f"%{search}%"))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Campaign.created_at.desc())

        result = await db.execute(query)
        campaigns = result.scalars().unique().all()

        # Build segment name map in ONE query (N+1 fix)
        segment_ids = [c.target_segment_id for c in campaigns if c.target_segment_id]
        segment_map = {}
        if segment_ids:
            seg_result = await db.execute(
                select(Segment.id, Segment.name).where(Segment.id.in_(segment_ids))
            )
            segment_map = {row.id: row.name for row in seg_result}

        # Enhance with segment names using the pre-fetched map
        items = []
        for campaign in campaigns:
            campaign_dict = {
                "id": campaign.id,
                "name": campaign.name,
                "description": campaign.description,
                "campaign_type": campaign.campaign_type,
                "status": campaign.status,
                "primary_channel": campaign.primary_channel,
                "target_segment_id": campaign.target_segment_id,
                "target_criteria": campaign.target_criteria,
                "start_date": campaign.start_date,
                "end_date": campaign.end_date,
                "timezone": campaign.timezone,
                "is_recurring": campaign.is_recurring,
                "recurrence_pattern": campaign.recurrence_pattern,
                "allow_re_enrollment": campaign.allow_re_enrollment,
                "max_enrollments_per_customer": campaign.max_enrollments_per_customer,
                "goal_type": campaign.goal_type,
                "goal_metric": campaign.goal_metric,
                "goal_target": campaign.goal_target,
                "enrolled_count": campaign.enrolled_count or 0,
                "active_count": campaign.active_count or 0,
                "completed_count": campaign.completed_count or 0,
                "converted_count": campaign.converted_count or 0,
                "conversion_rate": campaign.conversion_rate or 0,
                "avg_engagement_score": campaign.avg_engagement_score,
                "steps": campaign.steps,
                "created_by_user_id": campaign.created_by_user_id,
                "owned_by_user_id": campaign.owned_by_user_id,
                "created_at": campaign.created_at,
                "updated_at": campaign.updated_at,
                "launched_at": campaign.launched_at,
                "target_segment_name": segment_map.get(campaign.target_segment_id) if campaign.target_segment_id else None,
            }

            items.append(campaign_dict)

        return CampaignListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error listing campaigns: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error listing campaigns: {str(e)}"
        )


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific campaign with steps."""
    result = await db.execute(select(Campaign).options(selectinload(Campaign.steps)).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return campaign


@router.post("/", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    data: CampaignCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new campaign."""
    campaign_data = data.model_dump(exclude={"steps"})
    campaign = Campaign(
        **campaign_data,
        created_by_user_id=current_user.id,
        owned_by_user_id=current_user.id,
    )
    db.add(campaign)
    await db.flush()

    # Create steps if provided
    if data.steps:
        for i, step_data in enumerate(data.steps):
            step = CampaignStep(
                campaign_id=campaign.id,
                order=step_data.order if step_data.order else i,
                **step_data.model_dump(exclude={"order"}),
            )
            db.add(step)

    await db.commit()
    await db.refresh(campaign)

    # Load steps
    result = await db.execute(select(Campaign).options(selectinload(Campaign.steps)).where(Campaign.id == campaign.id))
    return result.scalar_one()


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: int,
    data: CampaignUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(campaign, field, value)

    # Handle status transitions
    if data.status == "active" and not campaign.launched_at:
        campaign.launched_at = datetime.utcnow()

    await db.commit()

    # Load steps
    result = await db.execute(select(Campaign).options(selectinload(Campaign.steps)).where(Campaign.id == campaign.id))
    return result.scalar_one()


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    if campaign.status == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete an active campaign",
        )

    await db.delete(campaign)
    await db.commit()


# Campaign Steps


@router.post("/{campaign_id}/steps", response_model=CampaignStepResponse, status_code=status.HTTP_201_CREATED)
async def create_step(
    campaign_id: int,
    data: CampaignStepCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Add a step to a campaign."""
    campaign_result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    if not campaign_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    step = CampaignStep(
        campaign_id=campaign_id,
        **data.model_dump(),
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


@router.patch("/{campaign_id}/steps/{step_id}", response_model=CampaignStepResponse)
async def update_step(
    campaign_id: int,
    step_id: int,
    data: CampaignStepUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a campaign step."""
    result = await db.execute(
        select(CampaignStep).where(
            CampaignStep.id == step_id,
            CampaignStep.campaign_id == campaign_id,
        )
    )
    step = result.scalar_one_or_none()

    if not step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Step not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(step, field, value)

    await db.commit()
    await db.refresh(step)
    return step


@router.delete("/{campaign_id}/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_step(
    campaign_id: int,
    step_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a campaign step."""
    result = await db.execute(
        select(CampaignStep).where(
            CampaignStep.id == step_id,
            CampaignStep.campaign_id == campaign_id,
        )
    )
    step = result.scalar_one_or_none()

    if not step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Step not found",
        )

    await db.delete(step)
    await db.commit()


# Campaign Enrollments


@router.get("/{campaign_id}/enrollments", response_model=EnrollmentListResponse)
async def list_enrollments(
    campaign_id: int,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
):
    """List enrollments for a campaign."""
    query = select(CampaignEnrollment).where(CampaignEnrollment.campaign_id == campaign_id)

    if status:
        query = query.where(CampaignEnrollment.status == status)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(CampaignEnrollment.enrolled_at.desc())

    result = await db.execute(query)
    enrollments = result.scalars().all()

    # Enhance with customer names
    items = []
    for enrollment in enrollments:
        enrollment_dict = {
            "id": enrollment.id,
            "campaign_id": enrollment.campaign_id,
            "customer_id": enrollment.customer_id,
            "status": enrollment.status,
            "current_step_id": enrollment.current_step_id,
            "steps_completed": enrollment.steps_completed,
            "next_step_scheduled_at": enrollment.next_step_scheduled_at,
            "messages_sent": enrollment.messages_sent,
            "messages_opened": enrollment.messages_opened,
            "messages_clicked": enrollment.messages_clicked,
            "engagement_score": enrollment.engagement_score,
            "converted_at": enrollment.converted_at,
            "conversion_value": enrollment.conversion_value,
            "exit_reason": enrollment.exit_reason,
            "exited_at": enrollment.exited_at,
            "enrolled_at": enrollment.enrolled_at,
            "completed_at": enrollment.completed_at,
        }
        cust_result = await db.execute(select(Customer.name).where(Customer.id == enrollment.customer_id))
        enrollment_dict["customer_name"] = cust_result.scalar_one_or_none()
        items.append(enrollment_dict)

    return EnrollmentListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{campaign_id}/enroll", response_model=CampaignEnrollmentResponse)
async def enroll_customer(
    campaign_id: int,
    data: CampaignEnrollmentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Enroll a customer in a campaign."""
    # Verify campaign exists and is active
    campaign_result = await db.execute(
        select(Campaign).options(selectinload(Campaign.steps)).where(Campaign.id == campaign_id)
    )
    campaign = campaign_result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    if campaign.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campaign is not active",
        )

    # Check for existing enrollment
    existing_enrollments = await db.execute(
        select(func.count()).where(
            CampaignEnrollment.campaign_id == campaign_id,
            CampaignEnrollment.customer_id == data.customer_id,
        )
    )
    enrollment_count = existing_enrollments.scalar()

    if enrollment_count >= campaign.max_enrollments_per_customer:
        if not campaign.allow_re_enrollment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer has reached max enrollments for this campaign",
            )

    # Create enrollment
    first_step = campaign.steps[0] if campaign.steps else None
    enrollment = CampaignEnrollment(
        campaign_id=campaign_id,
        customer_id=data.customer_id,
        status="active",
        current_step_id=first_step.id if first_step else None,
        next_step_scheduled_at=datetime.utcnow() if first_step else None,
    )
    db.add(enrollment)

    # Update campaign metrics
    campaign.enrolled_count = (campaign.enrolled_count or 0) + 1
    campaign.active_count = (campaign.active_count or 0) + 1

    await db.commit()
    await db.refresh(enrollment)
    return enrollment


@router.patch("/{campaign_id}/enrollments/{enrollment_id}", response_model=CampaignEnrollmentResponse)
async def update_enrollment(
    campaign_id: int,
    enrollment_id: int,
    data: CampaignEnrollmentUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update an enrollment status."""
    result = await db.execute(
        select(CampaignEnrollment).where(
            CampaignEnrollment.id == enrollment_id,
            CampaignEnrollment.campaign_id == campaign_id,
        )
    )
    enrollment = result.scalar_one_or_none()

    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found",
        )

    old_status = enrollment.status
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(enrollment, field, value)

    # Handle status transitions
    if data.status and data.status != old_status:
        campaign = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = campaign.scalar_one()

        if old_status == "active":
            campaign.active_count = max(0, (campaign.active_count or 1) - 1)

        if data.status == "completed":
            enrollment.completed_at = datetime.utcnow()
            campaign.completed_count = (campaign.completed_count or 0) + 1
        elif data.status == "converted":
            enrollment.converted_at = datetime.utcnow()
            campaign.converted_count = (campaign.converted_count or 0) + 1
            # Recalculate conversion rate
            if campaign.enrolled_count > 0:
                campaign.conversion_rate = (campaign.converted_count / campaign.enrolled_count) * 100
        elif data.status == "exited":
            enrollment.exited_at = datetime.utcnow()

    await db.commit()
    await db.refresh(enrollment)
    return enrollment


# Campaign Actions


@router.post("/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Launch a campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    if campaign.status == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campaign is already active",
        )

    campaign.status = "active"
    campaign.launched_at = datetime.utcnow()
    await db.commit()

    return {"status": "success", "message": "Campaign launched"}


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Pause an active campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    if campaign.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only pause active campaigns",
        )

    campaign.status = "paused"
    await db.commit()

    return {"status": "success", "message": "Campaign paused"}


@router.post("/{campaign_id}/complete")
async def complete_campaign(
    campaign_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Mark a campaign as completed."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    campaign.status = "completed"
    await db.commit()

    return {"status": "success", "message": "Campaign completed"}


# Campaign Analytics


@router.get("/{campaign_id}/analytics", response_model=CampaignAnalytics)
async def get_campaign_analytics(
    campaign_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get analytics for a campaign."""
    result = await db.execute(select(Campaign).options(selectinload(Campaign.steps)).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    # Aggregate step metrics
    total_sent = sum(step.sent_count or 0 for step in campaign.steps)
    total_opened = sum(step.opened_count or 0 for step in campaign.steps)
    total_clicked = sum(step.clicked_count or 0 for step in campaign.steps)

    open_rate = (total_opened / total_sent * 100) if total_sent > 0 else None
    click_rate = (total_clicked / total_sent * 100) if total_sent > 0 else None

    # Per-step performance
    step_performance = [
        {
            "step_id": step.id,
            "step_name": step.name,
            "sent": step.sent_count or 0,
            "opened": step.opened_count or 0,
            "clicked": step.clicked_count or 0,
            "open_rate": step.open_rate,
            "click_rate": step.click_rate,
        }
        for step in campaign.steps
    ]

    # Enrollment trend (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    trend_result = await db.execute(
        select(
            func.date(CampaignEnrollment.enrolled_at).label("date"),
            func.count(CampaignEnrollment.id).label("enrollments"),
            func.sum(func.case((CampaignEnrollment.status == "completed", 1), else_=0)).label("completions"),
        )
        .where(
            CampaignEnrollment.campaign_id == campaign_id,
            CampaignEnrollment.enrolled_at >= thirty_days_ago,
        )
        .group_by(func.date(CampaignEnrollment.enrolled_at))
        .order_by(func.date(CampaignEnrollment.enrolled_at))
    )
    enrollment_trend = [
        {"date": str(row.date), "enrollments": row.enrollments, "completions": row.completions or 0}
        for row in trend_result.fetchall()
    ]

    return CampaignAnalytics(
        campaign_id=campaign_id,
        total_enrolled=campaign.enrolled_count or 0,
        total_completed=campaign.completed_count or 0,
        total_converted=campaign.converted_count or 0,
        conversion_rate=campaign.conversion_rate or 0,
        avg_engagement_score=campaign.avg_engagement_score,
        messages_sent=total_sent,
        messages_opened=total_opened,
        messages_clicked=total_clicked,
        open_rate=open_rate,
        click_rate=click_rate,
        step_performance=step_performance,
        enrollment_trend=enrollment_trend,
    )


# Send Time Optimization Endpoints


@router.get("/{campaign_id}/send-time-analysis")
async def get_send_time_analysis(
    campaign_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Get send time performance analysis for a campaign.

    Analyzes historical message engagement data to identify optimal
    send times based on open and click rates by hour and day of week.
    """
    from app.services.customer_success.send_time_optimizer import SendTimeOptimizer

    # Verify campaign exists
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    optimizer = SendTimeOptimizer(db)
    analysis = await optimizer.analyze_campaign_timing(campaign_id)
    return analysis


@router.post("/customers/{customer_id}/optimize-send-time")
async def calculate_customer_send_profile(
    customer_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Calculate optimal send time profile for a customer.

    Analyzes the customer's historical engagement with campaign messages
    to determine the best times to send future communications.
    """
    from app.services.customer_success.send_time_optimizer import SendTimeOptimizer

    optimizer = SendTimeOptimizer(db)
    profile = await optimizer.calculate_customer_profile(customer_id)

    if "error" in profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=profile["error"],
        )

    return profile


@router.get("/customers/{customer_id}/send-time-profile")
async def get_customer_send_profile(
    customer_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Get the existing send time profile for a customer.

    Returns the customer's optimal send time profile if one has been calculated.
    """
    from app.services.customer_success.send_time_optimizer import SendTimeOptimizer

    optimizer = SendTimeOptimizer(db)
    profile = await optimizer.get_customer_profile(customer_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No send time profile found for this customer",
        )

    return profile


@router.get("/customers/{customer_id}/optimal-send-time")
async def get_optimal_send_time(
    customer_id: int,
    db: DbSession,
    current_user: CurrentUser,
    channel: str = "email",
):
    """
    Get the next optimal send time for a customer.

    Returns the next recommended datetime to send a message to this customer
    based on their engagement history.
    """
    from app.services.customer_success.send_time_optimizer import SendTimeOptimizer

    optimizer = SendTimeOptimizer(db)
    optimal_time = await optimizer.get_optimal_send_time(customer_id, channel)

    return {
        "customer_id": customer_id,
        "channel": channel,
        "optimal_send_time": optimal_time.isoformat(),
    }
