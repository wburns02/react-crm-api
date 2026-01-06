"""
Task API Endpoints for Enterprise Customer Success Platform
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, or_, and_
from typing import Optional
from datetime import datetime, date

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.customer_success import CSTask
from app.schemas.customer_success.task import (
    CSTaskCreate,
    CSTaskUpdate,
    CSTaskResponse,
    CSTaskListResponse,
    CSTaskCompleteRequest,
    CSTaskAssignRequest,
    CSTaskBulkUpdateRequest,
    TaskStatus,
    TaskPriority,
)

router = APIRouter()


@router.get("/", response_model=CSTaskListResponse)
async def list_tasks(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    priority: Optional[str] = None,
    task_type: Optional[str] = None,
    category: Optional[str] = None,
    assigned_to_user_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    due_before: Optional[date] = None,
    due_after: Optional[date] = None,
    search: Optional[str] = None,
    my_tasks: bool = False,
):
    """List CS tasks with filtering."""
    import logging
    logger = logging.getLogger(__name__)

    try:
        query = select(CSTask)

        # Filters
        if my_tasks:
            query = query.where(CSTask.assigned_to_user_id == current_user.id)
        elif assigned_to_user_id:
            query = query.where(CSTask.assigned_to_user_id == assigned_to_user_id)

        if status:
            query = query.where(CSTask.status == status)
        if priority:
            query = query.where(CSTask.priority == priority)
        if task_type:
            query = query.where(CSTask.task_type == task_type)
        if category:
            query = query.where(CSTask.category == category)
        if customer_id:
            query = query.where(CSTask.customer_id == customer_id)
        if due_before:
            query = query.where(CSTask.due_date <= due_before)
        if due_after:
            query = query.where(CSTask.due_date >= due_after)
        if search:
            query = query.where(
                or_(
                    CSTask.title.ilike(f"%{search}%"),
                    CSTask.description.ilike(f"%{search}%"),
                )
            )

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination and ordering
        offset = (page - 1) * page_size

        # Order by priority then due date
        from sqlalchemy import case
        priority_order = case(
            (CSTask.priority == TaskPriority.CRITICAL.value, 1),
            (CSTask.priority == TaskPriority.HIGH.value, 2),
            (CSTask.priority == TaskPriority.MEDIUM.value, 3),
            (CSTask.priority == TaskPriority.LOW.value, 4),
            else_=5,
        )

        query = query.offset(offset).limit(page_size).order_by(
            priority_order,
            CSTask.due_date.asc().nullslast(),
        )

        result = await db.execute(query)
        tasks = result.scalars().all()

        logger.info(f"Found {len(tasks)} tasks")

        return CSTaskListResponse(
            items=tasks,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error listing tasks: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error listing tasks: {str(e)}"
        )


@router.get("/overdue")
async def list_overdue_tasks(
    db: DbSession,
    current_user: CurrentUser,
    assigned_to_user_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
):
    """List overdue tasks."""
    today = date.today()

    query = select(CSTask).where(
        CSTask.due_date < today,
        CSTask.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
    )

    if assigned_to_user_id:
        query = query.where(CSTask.assigned_to_user_id == assigned_to_user_id)

    query = query.limit(limit).order_by(CSTask.due_date.asc())

    result = await db.execute(query)
    tasks = result.scalars().all()

    return {"items": tasks, "total": len(tasks)}


@router.get("/due-today")
async def list_due_today_tasks(
    db: DbSession,
    current_user: CurrentUser,
    assigned_to_user_id: Optional[int] = None,
):
    """List tasks due today."""
    today = date.today()

    query = select(CSTask).where(
        CSTask.due_date == today,
        CSTask.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
    )

    if assigned_to_user_id:
        query = query.where(CSTask.assigned_to_user_id == assigned_to_user_id)

    result = await db.execute(query)
    tasks = result.scalars().all()

    return {"items": tasks, "total": len(tasks)}


@router.get("/{task_id}", response_model=CSTaskResponse)
async def get_task(
    task_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific task."""
    result = await db.execute(
        select(CSTask).where(CSTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return task


@router.post("/", response_model=CSTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: CSTaskCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new CS task."""
    # Check customer exists
    customer_result = await db.execute(
        select(Customer).where(Customer.id == data.customer_id)
    )
    if not customer_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    task = CSTask(
        **data.model_dump(),
        source="manual",
        assigned_by_user_id=current_user.id,
        assigned_at=datetime.utcnow() if data.assigned_to_user_id else None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.patch("/{task_id}", response_model=CSTaskResponse)
async def update_task(
    task_id: int,
    data: CSTaskUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a task."""
    result = await db.execute(
        select(CSTask).where(CSTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Handle status transitions
    if "status" in update_data:
        new_status = update_data["status"]
        if new_status == TaskStatus.IN_PROGRESS.value and not task.started_at:
            task.started_at = datetime.utcnow()
        elif new_status == TaskStatus.COMPLETED.value:
            task.completed_at = datetime.utcnow()
        elif new_status == TaskStatus.CANCELLED.value:
            task.cancelled_at = datetime.utcnow()

    # Handle assignment
    if "assigned_to_user_id" in update_data and update_data["assigned_to_user_id"] != task.assigned_to_user_id:
        task.assigned_by_user_id = current_user.id
        task.assigned_at = datetime.utcnow()

    for field, value in update_data.items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a task."""
    result = await db.execute(
        select(CSTask).where(CSTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    await db.delete(task)
    await db.commit()


@router.post("/{task_id}/complete", response_model=CSTaskResponse)
async def complete_task(
    task_id: int,
    request: CSTaskCompleteRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Complete a task with outcome."""
    result = await db.execute(
        select(CSTask).where(CSTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if task.status == TaskStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task is already completed",
        )

    task.status = TaskStatus.COMPLETED.value
    task.completed_at = datetime.utcnow()
    task.outcome = request.outcome.value
    task.outcome_notes = request.outcome_notes
    task.completed_artifacts = request.completed_artifacts

    if request.time_spent_minutes:
        task.time_spent_minutes = (task.time_spent_minutes or 0) + request.time_spent_minutes

    await db.commit()
    await db.refresh(task)
    return task


@router.post("/{task_id}/assign", response_model=CSTaskResponse)
async def assign_task(
    task_id: int,
    request: CSTaskAssignRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Assign or reassign a task."""
    result = await db.execute(
        select(CSTask).where(CSTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    task.assigned_to_user_id = request.assigned_to_user_id
    task.assigned_by_user_id = current_user.id
    task.assigned_at = datetime.utcnow()

    await db.commit()
    await db.refresh(task)
    return task


@router.post("/{task_id}/snooze", response_model=CSTaskResponse)
async def snooze_task(
    task_id: int,
    db: DbSession,
    current_user: CurrentUser,
    snooze_until: datetime = Query(...),
):
    """Snooze a task until a specific time."""
    result = await db.execute(
        select(CSTask).where(CSTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    task.status = TaskStatus.SNOOZED.value
    task.snoozed_until = snooze_until

    await db.commit()
    await db.refresh(task)
    return task


@router.post("/bulk-update")
async def bulk_update_tasks(
    request: CSTaskBulkUpdateRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Bulk update tasks."""
    # Get all tasks
    result = await db.execute(
        select(CSTask).where(CSTask.id.in_(request.task_ids))
    )
    tasks = result.scalars().all()

    if not tasks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tasks found",
        )

    updated_count = 0
    for task in tasks:
        if request.status:
            task.status = request.status.value
            if request.status == TaskStatus.COMPLETED:
                task.completed_at = datetime.utcnow()
        if request.priority:
            task.priority = request.priority.value
        if request.assigned_to_user_id:
            task.assigned_to_user_id = request.assigned_to_user_id
            task.assigned_by_user_id = current_user.id
            task.assigned_at = datetime.utcnow()
        if request.due_date:
            task.due_date = request.due_date
        updated_count += 1

    await db.commit()

    return {"status": "success", "updated_count": updated_count}


@router.get("/customer/{customer_id}")
async def list_customer_tasks(
    customer_id: int,
    db: DbSession,
    current_user: CurrentUser,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all tasks for a customer."""
    query = select(CSTask).where(CSTask.customer_id == customer_id)

    if status:
        query = query.where(CSTask.status == status)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(CSTask.due_date.asc().nullslast())

    result = await db.execute(query)
    tasks = result.scalars().all()

    return CSTaskListResponse(
        items=tasks,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/summary")
async def get_task_summary(
    db: DbSession,
    current_user: CurrentUser,
    assigned_to_user_id: Optional[int] = None,
):
    """Get task summary statistics."""
    base_filter = []
    if assigned_to_user_id:
        base_filter.append(CSTask.assigned_to_user_id == assigned_to_user_id)

    # Count by status
    status_counts = {}
    for status_val in TaskStatus:
        count_result = await db.execute(
            select(func.count()).where(
                CSTask.status == status_val.value,
                *base_filter,
            )
        )
        status_counts[status_val.value] = count_result.scalar()

    # Count overdue
    today = date.today()
    overdue_result = await db.execute(
        select(func.count()).where(
            CSTask.due_date < today,
            CSTask.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
            *base_filter,
        )
    )
    overdue_count = overdue_result.scalar()

    # Count due today
    due_today_result = await db.execute(
        select(func.count()).where(
            CSTask.due_date == today,
            CSTask.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
            *base_filter,
        )
    )
    due_today_count = due_today_result.scalar()

    # Count high priority
    high_priority_result = await db.execute(
        select(func.count()).where(
            CSTask.priority.in_([TaskPriority.HIGH.value, TaskPriority.CRITICAL.value]),
            CSTask.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
            *base_filter,
        )
    )
    high_priority_count = high_priority_result.scalar()

    return {
        "status_breakdown": status_counts,
        "overdue_count": overdue_count,
        "due_today_count": due_today_count,
        "high_priority_count": high_priority_count,
        "total_open": status_counts.get(TaskStatus.PENDING.value, 0) + status_counts.get(TaskStatus.IN_PROGRESS.value, 0),
    }
