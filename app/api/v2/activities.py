"""Activities API - Track customer interactions (calls, emails, notes, etc.)."""
from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime
import uuid
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.activity import Activity
from app.schemas.activity import (
    ActivityCreate,
    ActivityUpdate,
    ActivityResponse,
    ActivityListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def activity_to_response(activity: Activity) -> dict:
    """Convert Activity model to response dict."""
    return {
        "id": str(activity.id),
        "customer_id": str(activity.customer_id),  # Convert to string for frontend
        "activity_type": activity.activity_type,
        "description": activity.description,
        "activity_date": activity.activity_date.isoformat() if activity.activity_date else None,
        "created_by": activity.created_by,
        "created_at": activity.created_at.isoformat() if activity.created_at else None,
        "updated_at": activity.updated_at.isoformat() if activity.updated_at else None,
    }


@router.get("", response_model=ActivityListResponse)
async def list_activities(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[str] = None,
    activity_type: Optional[str] = None,
):
    """List activities with pagination and filtering."""
    # Base query
    query = select(Activity)

    # Apply filters
    if customer_id:
        query = query.where(Activity.customer_id == int(customer_id))

    if activity_type:
        query = query.where(Activity.activity_type == activity_type)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination and ordering
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Activity.activity_date.desc())

    # Execute query
    result = await db.execute(query)
    activities = result.scalars().all()

    return ActivityListResponse(
        items=[activity_to_response(a) for a in activities],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{activity_id}", response_model=ActivityResponse)
async def get_activity(
    activity_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single activity by ID."""
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    activity = result.scalar_one_or_none()

    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    return activity_to_response(activity)


@router.post("", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
async def create_activity(
    activity_data: ActivityCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new activity."""
    data = activity_data.model_dump()

    # Convert customer_id from string to int
    data["customer_id"] = int(data["customer_id"])

    # Convert string dates
    if data.get("activity_date"):
        try:
            data["activity_date"] = datetime.fromisoformat(data["activity_date"].replace("Z", "+00:00"))
        except ValueError:
            pass  # Keep as-is if parsing fails

    # Set created_by to current user
    data["created_by"] = current_user.email

    activity = Activity(**data)
    db.add(activity)
    await db.commit()
    await db.refresh(activity)
    return activity_to_response(activity)


@router.patch("/{activity_id}", response_model=ActivityResponse)
async def update_activity(
    activity_id: str,
    activity_data: ActivityUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update an activity."""
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    activity = result.scalar_one_or_none()

    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    # Update only provided fields
    update_data = activity_data.model_dump(exclude_unset=True)

    # Convert string dates
    if update_data.get("activity_date"):
        try:
            update_data["activity_date"] = datetime.fromisoformat(
                update_data["activity_date"].replace("Z", "+00:00")
            )
        except ValueError:
            pass

    for field, value in update_data.items():
        setattr(activity, field, value)

    await db.commit()
    await db.refresh(activity)
    return activity_to_response(activity)


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_activity(
    activity_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete an activity."""
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    activity = result.scalar_one_or_none()

    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found",
        )

    await db.delete(activity)
    await db.commit()
