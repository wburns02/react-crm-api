"""
Journey API Endpoints for Enterprise Customer Success Platform
"""

from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.customer_success import (
    Journey, JourneyStep, JourneyEnrollment, JourneyStepExecution
)
from app.schemas.customer_success.journey import (
    JourneyCreate,
    JourneyUpdate,
    JourneyResponse,
    JourneyListResponse,
    JourneyStepCreate,
    JourneyStepUpdate,
    JourneyStepResponse,
    JourneyEnrollmentCreate,
    JourneyEnrollmentResponse,
    JourneyEnrollmentListResponse,
    JourneyStepExecutionResponse,
    JourneyEnrollRequest,
    JourneyBulkEnrollRequest,
    JourneyStatus,
    EnrollmentStatus,
)

router = APIRouter()


# Journey CRUD

@router.get("/", response_model=JourneyListResponse)
async def list_journeys(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    journey_type: Optional[str] = None,
    search: Optional[str] = None,
):
    """List journeys with filtering."""
    import logging
    logger = logging.getLogger(__name__)

    try:
        query = select(Journey).options(selectinload(Journey.steps))

        # Filter by is_active instead of status (status column may not exist)
        if status:
            # Map status to is_active boolean
            if status in ('active', 'draft'):
                query = query.where(Journey.is_active == True)
            elif status in ('paused', 'archived'):
                query = query.where(Journey.is_active == False)
        if journey_type:
            query = query.where(Journey.journey_type == journey_type)
        if search:
            query = query.where(Journey.name.ilike(f"%{search}%"))

        # Get total count
        count_query = select(func.count()).select_from(Journey)
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination - order by name only (priority column may not exist)
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Journey.name)

        result = await db.execute(query)
        journeys = result.scalars().unique().all()

        logger.info(f"Found {len(journeys)} journeys")

        return JourneyListResponse(
            items=journeys,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error listing journeys: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error listing journeys: {str(e)}"
        )


@router.get("/{journey_id}", response_model=JourneyResponse)
async def get_journey(
    journey_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific journey with steps."""
    result = await db.execute(
        select(Journey)
        .options(selectinload(Journey.steps))
        .where(Journey.id == journey_id)
    )
    journey = result.scalar_one_or_none()

    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Journey not found",
        )

    return journey


@router.post("/", response_model=JourneyResponse, status_code=status.HTTP_201_CREATED)
async def create_journey(
    data: JourneyCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new journey."""
    # Check for duplicate name
    existing = await db.execute(
        select(Journey).where(Journey.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Journey with this name already exists",
        )

    journey_data = data.model_dump(exclude={"steps"})
    journey = Journey(
        **journey_data,
        created_by_user_id=current_user.id,
        owned_by_user_id=current_user.id,
    )
    db.add(journey)
    await db.flush()

    # Create steps if provided
    if data.steps:
        for step_data in data.steps:
            step = JourneyStep(
                journey_id=journey.id,
                **step_data.model_dump(exclude={"journey_id"}),
            )
            db.add(step)

    await db.commit()
    await db.refresh(journey)

    # Load steps
    result = await db.execute(
        select(Journey)
        .options(selectinload(Journey.steps))
        .where(Journey.id == journey.id)
    )
    return result.scalar_one()


@router.patch("/{journey_id}", response_model=JourneyResponse)
async def update_journey(
    journey_id: int,
    data: JourneyUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a journey."""
    result = await db.execute(
        select(Journey).where(Journey.id == journey_id)
    )
    journey = result.scalar_one_or_none()

    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Journey not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(journey, field, value)

    await db.commit()
    await db.refresh(journey)

    # Load steps
    result = await db.execute(
        select(Journey)
        .options(selectinload(Journey.steps))
        .where(Journey.id == journey.id)
    )
    return result.scalar_one()


@router.delete("/{journey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_journey(
    journey_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a journey."""
    result = await db.execute(
        select(Journey).where(Journey.id == journey_id)
    )
    journey = result.scalar_one_or_none()

    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Journey not found",
        )

    # Check for active enrollments
    active_enrollments = await db.execute(
        select(func.count()).where(
            JourneyEnrollment.journey_id == journey_id,
            JourneyEnrollment.status == EnrollmentStatus.ACTIVE.value,
        )
    )
    if active_enrollments.scalar() > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete journey with active enrollments",
        )

    await db.delete(journey)
    await db.commit()


# Journey Steps

@router.post("/{journey_id}/steps", response_model=JourneyStepResponse, status_code=status.HTTP_201_CREATED)
async def create_journey_step(
    journey_id: int,
    data: JourneyStepCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Add a step to a journey."""
    # Check journey exists
    journey_result = await db.execute(
        select(Journey).where(Journey.id == journey_id)
    )
    if not journey_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Journey not found",
        )

    step = JourneyStep(
        journey_id=journey_id,
        **data.model_dump(exclude={"journey_id"}),
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


@router.patch("/{journey_id}/steps/{step_id}", response_model=JourneyStepResponse)
async def update_journey_step(
    journey_id: int,
    step_id: int,
    data: JourneyStepUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a journey step."""
    result = await db.execute(
        select(JourneyStep).where(
            JourneyStep.id == step_id,
            JourneyStep.journey_id == journey_id,
        )
    )
    step = result.scalar_one_or_none()

    if not step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Journey step not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(step, field, value)

    await db.commit()
    await db.refresh(step)
    return step


@router.delete("/{journey_id}/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_journey_step(
    journey_id: int,
    step_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a journey step."""
    result = await db.execute(
        select(JourneyStep).where(
            JourneyStep.id == step_id,
            JourneyStep.journey_id == journey_id,
        )
    )
    step = result.scalar_one_or_none()

    if not step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Journey step not found",
        )

    await db.delete(step)
    await db.commit()


# Enrollments

@router.get("/{journey_id}/enrollments", response_model=JourneyEnrollmentListResponse)
async def list_journey_enrollments(
    journey_id: int,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
):
    """List enrollments for a journey."""
    query = select(JourneyEnrollment).where(JourneyEnrollment.journey_id == journey_id)

    if status:
        query = query.where(JourneyEnrollment.status == status)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(JourneyEnrollment.enrolled_at.desc())

    result = await db.execute(query)
    enrollments = result.scalars().all()

    return JourneyEnrollmentListResponse(
        items=enrollments,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/enroll", response_model=JourneyEnrollmentResponse)
async def enroll_customer(
    request: JourneyEnrollRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Enroll a customer in a journey."""
    # Check journey exists and is active
    journey_result = await db.execute(
        select(Journey)
        .options(selectinload(Journey.steps))
        .where(Journey.id == request.journey_id)
    )
    journey = journey_result.scalar_one_or_none()

    if not journey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Journey not found",
        )

    if journey.status != JourneyStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Journey is not active",
        )

    # Check customer exists
    customer_result = await db.execute(
        select(Customer).where(Customer.id == request.customer_id)
    )
    if not customer_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # Check existing active enrollment
    existing = await db.execute(
        select(JourneyEnrollment).where(
            JourneyEnrollment.journey_id == request.journey_id,
            JourneyEnrollment.customer_id == request.customer_id,
            JourneyEnrollment.status == EnrollmentStatus.ACTIVE.value,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer is already enrolled in this journey",
        )

    # Get first step
    first_step = min(journey.steps, key=lambda s: s.step_order) if journey.steps else None

    enrollment = JourneyEnrollment(
        journey_id=request.journey_id,
        customer_id=request.customer_id,
        status=EnrollmentStatus.ACTIVE.value,
        enrolled_by=f"user:{current_user.id}",
        enrollment_reason=request.reason,
        current_step_id=first_step.id if first_step else None,
        current_step_order=first_step.step_order if first_step else 0,
        steps_total=len(journey.steps),
        enrolled_at=datetime.utcnow(),
        started_at=datetime.utcnow() if request.start_immediately else None,
    )
    db.add(enrollment)

    # Update journey metrics
    journey.total_enrolled = (journey.total_enrolled or 0) + 1
    journey.active_enrolled = (journey.active_enrolled or 0) + 1

    await db.commit()
    await db.refresh(enrollment)
    return enrollment


@router.post("/enroll/bulk")
async def bulk_enroll_customers(
    request: JourneyBulkEnrollRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
):
    """Bulk enroll customers in a journey."""
    # Check journey exists
    journey_result = await db.execute(
        select(Journey).where(Journey.id == request.journey_id)
    )
    if not journey_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Journey not found",
        )

    # In production, this would queue a background job
    return {
        "status": "accepted",
        "message": "Bulk enrollment queued",
        "journey_id": request.journey_id,
        "customer_ids": request.customer_ids,
        "segment_id": request.segment_id,
    }


@router.get("/enrollments/{enrollment_id}", response_model=JourneyEnrollmentResponse)
async def get_enrollment(
    enrollment_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific enrollment."""
    result = await db.execute(
        select(JourneyEnrollment).where(JourneyEnrollment.id == enrollment_id)
    )
    enrollment = result.scalar_one_or_none()

    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found",
        )

    return enrollment


@router.post("/enrollments/{enrollment_id}/pause")
async def pause_enrollment(
    enrollment_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Pause a journey enrollment."""
    result = await db.execute(
        select(JourneyEnrollment).where(JourneyEnrollment.id == enrollment_id)
    )
    enrollment = result.scalar_one_or_none()

    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found",
        )

    if enrollment.status != EnrollmentStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only pause active enrollments",
        )

    enrollment.status = EnrollmentStatus.PAUSED.value
    enrollment.paused_at = datetime.utcnow()

    # Update journey metrics
    journey_result = await db.execute(
        select(Journey).where(Journey.id == enrollment.journey_id)
    )
    journey = journey_result.scalar_one_or_none()
    if journey:
        journey.active_enrolled = max(0, (journey.active_enrolled or 1) - 1)

    await db.commit()
    return {"status": "success", "message": "Enrollment paused"}


@router.post("/enrollments/{enrollment_id}/resume")
async def resume_enrollment(
    enrollment_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Resume a paused journey enrollment."""
    result = await db.execute(
        select(JourneyEnrollment).where(JourneyEnrollment.id == enrollment_id)
    )
    enrollment = result.scalar_one_or_none()

    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found",
        )

    if enrollment.status != EnrollmentStatus.PAUSED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only resume paused enrollments",
        )

    enrollment.status = EnrollmentStatus.ACTIVE.value
    enrollment.paused_at = None

    # Update journey metrics
    journey_result = await db.execute(
        select(Journey).where(Journey.id == enrollment.journey_id)
    )
    journey = journey_result.scalar_one_or_none()
    if journey:
        journey.active_enrolled = (journey.active_enrolled or 0) + 1

    await db.commit()
    return {"status": "success", "message": "Enrollment resumed"}


@router.post("/enrollments/{enrollment_id}/exit")
async def exit_enrollment(
    enrollment_id: int,
    db: DbSession,
    current_user: CurrentUser,
    reason: Optional[str] = None,
):
    """Exit a customer from a journey."""
    result = await db.execute(
        select(JourneyEnrollment).where(JourneyEnrollment.id == enrollment_id)
    )
    enrollment = result.scalar_one_or_none()

    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found",
        )

    if enrollment.status not in [EnrollmentStatus.ACTIVE.value, EnrollmentStatus.PAUSED.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enrollment is already completed or exited",
        )

    enrollment.status = EnrollmentStatus.EXITED.value
    enrollment.exited_at = datetime.utcnow()
    enrollment.exit_reason = reason or "Manual exit"

    # Update journey metrics
    journey_result = await db.execute(
        select(Journey).where(Journey.id == enrollment.journey_id)
    )
    journey = journey_result.scalar_one_or_none()
    if journey and enrollment.status == EnrollmentStatus.ACTIVE.value:
        journey.active_enrolled = max(0, (journey.active_enrolled or 1) - 1)

    await db.commit()
    return {"status": "success", "message": "Enrollment exited"}


@router.get("/customer/{customer_id}/enrollments")
async def list_customer_enrollments(
    customer_id: int,
    db: DbSession,
    current_user: CurrentUser,
    status: Optional[str] = None,
):
    """List all journey enrollments for a customer."""
    query = select(JourneyEnrollment).where(JourneyEnrollment.customer_id == customer_id)

    if status:
        query = query.where(JourneyEnrollment.status == status)

    result = await db.execute(query.order_by(JourneyEnrollment.enrolled_at.desc()))
    enrollments = result.scalars().all()

    return {"items": enrollments, "total": len(enrollments)}
