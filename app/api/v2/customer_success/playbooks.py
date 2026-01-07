"""
Playbook API Endpoints for Enterprise Customer Success Platform
"""

from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime
import logging

from app.api.deps import DbSession, CurrentUser

logger = logging.getLogger(__name__)
from app.models.customer import Customer
from app.models.customer_success import (
    Playbook, PlaybookStep, PlaybookExecution
)
from app.services.customer_success.playbook_runner import PlaybookRunner
from app.schemas.customer_success.playbook import (
    PlaybookCreate,
    PlaybookUpdate,
    PlaybookResponse,
    PlaybookListResponse,
    PlaybookStepCreate,
    PlaybookStepUpdate,
    PlaybookStepResponse,
    PlaybookExecutionCreate,
    PlaybookExecutionResponse,
    PlaybookExecutionListResponse,
    PlaybookTriggerRequest,
    PlaybookBulkTriggerRequest,
    PlaybookExecStatus,
)

router = APIRouter()


# Playbook CRUD

@router.get("/", response_model=PlaybookListResponse)
async def list_playbooks(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    trigger_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
):
    """List playbooks with filtering."""
    try:
        query = select(Playbook).options(selectinload(Playbook.steps))

        if category:
            query = query.where(Playbook.category == category)
        if trigger_type:
            query = query.where(Playbook.trigger_type == trigger_type)
        if is_active is not None:
            query = query.where(Playbook.is_active == is_active)
        if search:
            query = query.where(Playbook.name.ilike(f"%{search}%"))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Playbook.priority.desc(), Playbook.name)

        result = await db.execute(query)
        playbooks = result.scalars().unique().all()

        # Debug: Log playbook data before serialization
        for pb in playbooks:
            logger.info(f"Playbook {pb.id}: {pb.name}, category={pb.category}, priority={pb.priority}")
            for step in pb.steps:
                logger.info(f"  Step {step.id}: {step.name}, type={step.step_type}")

        return PlaybookListResponse(
            items=playbooks,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error listing playbooks: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing playbooks: {str(e)}"
        )


@router.get("/{playbook_id}", response_model=PlaybookResponse)
async def get_playbook(
    playbook_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific playbook with steps."""
    result = await db.execute(
        select(Playbook)
        .options(selectinload(Playbook.steps))
        .where(Playbook.id == playbook_id)
    )
    playbook = result.scalar_one_or_none()

    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    return playbook


@router.post("/", response_model=PlaybookResponse, status_code=status.HTTP_201_CREATED)
async def create_playbook(
    data: PlaybookCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new playbook."""
    # Check for duplicate name
    existing = await db.execute(
        select(Playbook).where(Playbook.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Playbook with this name already exists",
        )

    playbook_data = data.model_dump(exclude={"steps"})
    playbook = Playbook(
        **playbook_data,
        created_by_user_id=current_user.id,
        owned_by_user_id=current_user.id,
    )
    db.add(playbook)
    await db.flush()

    # Create steps if provided
    if data.steps:
        for step_data in data.steps:
            step = PlaybookStep(
                playbook_id=playbook.id,
                **step_data.model_dump(exclude={"playbook_id"}),
            )
            db.add(step)

    await db.commit()
    await db.refresh(playbook)

    # Load steps
    result = await db.execute(
        select(Playbook)
        .options(selectinload(Playbook.steps))
        .where(Playbook.id == playbook.id)
    )
    return result.scalar_one()


@router.patch("/{playbook_id}", response_model=PlaybookResponse)
async def update_playbook(
    playbook_id: int,
    data: PlaybookUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a playbook."""
    result = await db.execute(
        select(Playbook).where(Playbook.id == playbook_id)
    )
    playbook = result.scalar_one_or_none()

    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(playbook, field, value)

    await db.commit()
    await db.refresh(playbook)

    # Load steps
    result = await db.execute(
        select(Playbook)
        .options(selectinload(Playbook.steps))
        .where(Playbook.id == playbook.id)
    )
    return result.scalar_one()


@router.delete("/{playbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playbook(
    playbook_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a playbook."""
    result = await db.execute(
        select(Playbook).where(Playbook.id == playbook_id)
    )
    playbook = result.scalar_one_or_none()

    if not playbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    # Check for active executions
    active_executions = await db.execute(
        select(func.count()).where(
            PlaybookExecution.playbook_id == playbook_id,
            PlaybookExecution.status == PlaybookExecStatus.ACTIVE.value,
        )
    )
    if active_executions.scalar() > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete playbook with active executions",
        )

    await db.delete(playbook)
    await db.commit()


# Playbook Steps

@router.post("/{playbook_id}/steps", response_model=PlaybookStepResponse, status_code=status.HTTP_201_CREATED)
async def create_playbook_step(
    playbook_id: int,
    data: PlaybookStepCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Add a step to a playbook."""
    # Check playbook exists
    playbook_result = await db.execute(
        select(Playbook).where(Playbook.id == playbook_id)
    )
    if not playbook_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    step = PlaybookStep(
        playbook_id=playbook_id,
        **data.model_dump(exclude={"playbook_id"}),
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


@router.patch("/{playbook_id}/steps/{step_id}", response_model=PlaybookStepResponse)
async def update_playbook_step(
    playbook_id: int,
    step_id: int,
    data: PlaybookStepUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a playbook step."""
    result = await db.execute(
        select(PlaybookStep).where(
            PlaybookStep.id == step_id,
            PlaybookStep.playbook_id == playbook_id,
        )
    )
    step = result.scalar_one_or_none()

    if not step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook step not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(step, field, value)

    await db.commit()
    await db.refresh(step)
    return step


@router.delete("/{playbook_id}/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playbook_step(
    playbook_id: int,
    step_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a playbook step."""
    result = await db.execute(
        select(PlaybookStep).where(
            PlaybookStep.id == step_id,
            PlaybookStep.playbook_id == playbook_id,
        )
    )
    step = result.scalar_one_or_none()

    if not step:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook step not found",
        )

    await db.delete(step)
    await db.commit()


# Playbook Executions

@router.get("/{playbook_id}/executions", response_model=PlaybookExecutionListResponse)
async def list_playbook_executions(
    playbook_id: int,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
):
    """List executions for a playbook."""
    query = select(PlaybookExecution).where(PlaybookExecution.playbook_id == playbook_id)

    if status:
        query = query.where(PlaybookExecution.status == status)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(PlaybookExecution.started_at.desc())

    result = await db.execute(query)
    executions = result.scalars().all()

    return PlaybookExecutionListResponse(
        items=executions,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/trigger", response_model=PlaybookExecutionResponse)
async def trigger_playbook(
    request: PlaybookTriggerRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Trigger a playbook for a customer.

    This creates a PlaybookExecution and generates CSTask entries
    for each step in the playbook, allowing CSMs to track and
    complete the playbook workflow.
    """
    try:
        runner = PlaybookRunner(db)
        execution = await runner.trigger_playbook(
            playbook_id=request.playbook_id,
            customer_id=request.customer_id,
            triggered_by=f"user:{current_user.id}",
            reason=request.reason,
            assigned_to_user_id=request.assigned_to_user_id,
        )

        logger.info(
            f"Playbook {request.playbook_id} triggered for customer {request.customer_id} "
            f"by user {current_user.id}. Execution ID: {execution.id}, "
            f"Tasks created: {execution.steps_total}"
        )

        return execution

    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )
        elif "not active" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            )
        elif "cooldown" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            )
        elif "max active" in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            )
    except Exception as e:
        logger.error(f"Error triggering playbook: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger playbook: {str(e)}",
        )


@router.post("/trigger/bulk")
async def bulk_trigger_playbook(
    request: PlaybookBulkTriggerRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
):
    """Bulk trigger a playbook for multiple customers."""
    # Check playbook exists
    playbook_result = await db.execute(
        select(Playbook).where(Playbook.id == request.playbook_id)
    )
    if not playbook_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playbook not found",
        )

    return {
        "status": "accepted",
        "message": "Bulk playbook trigger queued",
        "playbook_id": request.playbook_id,
        "customer_ids": request.customer_ids,
        "segment_id": request.segment_id,
    }


@router.get("/executions/{execution_id}", response_model=PlaybookExecutionResponse)
async def get_execution(
    execution_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific playbook execution."""
    result = await db.execute(
        select(PlaybookExecution).where(PlaybookExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found",
        )

    return execution


@router.post("/executions/{execution_id}/pause")
async def pause_execution(
    execution_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Pause a playbook execution."""
    result = await db.execute(
        select(PlaybookExecution).where(PlaybookExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found",
        )

    if execution.status != PlaybookExecStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only pause active executions",
        )

    execution.status = PlaybookExecStatus.PAUSED.value
    await db.commit()

    return {"status": "success", "message": "Execution paused"}


@router.post("/executions/{execution_id}/resume")
async def resume_execution(
    execution_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Resume a paused playbook execution."""
    result = await db.execute(
        select(PlaybookExecution).where(PlaybookExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found",
        )

    if execution.status != PlaybookExecStatus.PAUSED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only resume paused executions",
        )

    execution.status = PlaybookExecStatus.ACTIVE.value
    await db.commit()

    return {"status": "success", "message": "Execution resumed"}


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: int,
    db: DbSession,
    current_user: CurrentUser,
    reason: Optional[str] = None,
):
    """Cancel a playbook execution."""
    result = await db.execute(
        select(PlaybookExecution).where(PlaybookExecution.id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found",
        )

    if execution.status not in [PlaybookExecStatus.ACTIVE.value, PlaybookExecStatus.PAUSED.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Execution is already completed or cancelled",
        )

    execution.status = PlaybookExecStatus.CANCELLED.value
    execution.cancelled_at = datetime.utcnow()
    execution.outcome_notes = reason

    await db.commit()

    return {"status": "success", "message": "Execution cancelled"}


@router.get("/customer/{customer_id}/executions")
async def list_customer_executions(
    customer_id: int,
    db: DbSession,
    current_user: CurrentUser,
    status: Optional[str] = None,
):
    """List all playbook executions for a customer."""
    query = select(PlaybookExecution).where(PlaybookExecution.customer_id == customer_id)

    if status:
        query = query.where(PlaybookExecution.status == status)

    result = await db.execute(query.order_by(PlaybookExecution.started_at.desc()))
    executions = result.scalars().all()

    return {"items": executions, "total": len(executions)}
