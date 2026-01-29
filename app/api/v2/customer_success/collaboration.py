"""
Collaboration Hub API Endpoints for Enterprise Customer Success Platform

Provides endpoints for team resources, notes, and activity feed.
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.user import User
from app.models.customer_success import (
    CSResource,
    CSResourceLike,
    CSResourceComment,
    CSTeamNote,
    CSTeamNoteComment,
    CSActivity,
)
from app.schemas.customer_success.collaboration import (
    ResourceCreate,
    ResourceUpdate,
    ResourceResponse,
    ResourceListResponse,
    ResourceCommentCreate,
    ResourceCommentResponse,
    TeamNoteCreate,
    TeamNoteUpdate,
    TeamNoteResponse,
    TeamNoteListResponse,
    TeamNoteCommentCreate,
    TeamNoteCommentResponse,
    ActivityCreate,
    ActivityResponse,
    ActivityListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# Helper function to log activity
async def log_activity(
    db: DbSession,
    activity_type: str,
    user_id: int,
    entity_type: str = None,
    entity_id: int = None,
    title: str = None,
    description: str = None,
    activity_data: dict = None,
    customer_id: int = None,
):
    activity = CSActivity(
        activity_type=activity_type,
        entity_type=entity_type,
        entity_id=entity_id,
        title=title,
        description=description,
        activity_data=activity_data,
        user_id=user_id,
        customer_id=customer_id,
    )
    db.add(activity)
    return activity


# ============ Resources ============


@router.get("/resources", response_model=ResourceListResponse)
async def list_resources(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    resource_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    is_featured: Optional[bool] = None,
    is_pinned: Optional[bool] = None,
):
    """List resources with filtering."""
    try:
        query = (
            select(CSResource)
            .options(
                selectinload(CSResource.likes),
                selectinload(CSResource.comments),
            )
            .where(CSResource.is_active == True, CSResource.is_archived == False)
        )

        if resource_type:
            query = query.where(CSResource.resource_type == resource_type)
        if category:
            query = query.where(CSResource.category == category)
        if search:
            query = query.where(CSResource.title.ilike(f"%{search}%"))
        if is_featured is not None:
            query = query.where(CSResource.is_featured == is_featured)
        if is_pinned is not None:
            query = query.where(CSResource.is_pinned == is_pinned)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = (
            query.offset(offset).limit(page_size).order_by(CSResource.is_pinned.desc(), CSResource.views_count.desc())
        )

        result = await db.execute(query)
        resources = result.scalars().unique().all()

        # Enhance with creator names and like status
        items = []
        for res in resources:
            res_dict = {
                "id": res.id,
                "title": res.title,
                "description": res.description,
                "resource_type": res.resource_type,
                "category": res.category,
                "content": res.content,
                "content_html": res.content_html,
                "url": res.url,
                "file_path": res.file_path,
                "file_size": res.file_size,
                "file_type": res.file_type,
                "tags": res.tags,
                "is_featured": res.is_featured,
                "is_pinned": res.is_pinned,
                "visibility": res.visibility,
                "version": res.version,
                "views_count": res.views_count,
                "likes_count": res.likes_count,
                "downloads_count": res.downloads_count,
                "is_active": res.is_active,
                "is_archived": res.is_archived,
                "created_by_user_id": res.created_by_user_id,
                "parent_resource_id": res.parent_resource_id,
                "comments": res.comments,
                "created_at": res.created_at,
                "updated_at": res.updated_at,
                "last_viewed_at": res.last_viewed_at,
            }

            # Get creator name
            if res.created_by_user_id:
                user_result = await db.execute(select(User.name).where(User.id == res.created_by_user_id))
                res_dict["created_by_name"] = user_result.scalar_one_or_none()
            else:
                res_dict["created_by_name"] = None

            # Check if current user liked
            res_dict["is_liked_by_current_user"] = any(like.user_id == current_user.id for like in res.likes)

            items.append(res_dict)

        return ResourceListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error listing resources: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error listing resources: {str(e)}"
        )


@router.get("/resources/{resource_id}", response_model=ResourceResponse)
async def get_resource(
    resource_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific resource."""
    result = await db.execute(
        select(CSResource)
        .options(
            selectinload(CSResource.likes),
            selectinload(CSResource.comments),
        )
        .where(CSResource.id == resource_id)
    )
    resource = result.scalar_one_or_none()

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    # Increment view count
    resource.views_count = (resource.views_count or 0) + 1
    resource.last_viewed_at = datetime.utcnow()
    await db.commit()

    return resource


@router.post("/resources", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(
    data: ResourceCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new resource."""
    resource = CSResource(
        **data.model_dump(),
        created_by_user_id=current_user.id,
    )
    db.add(resource)
    await db.flush()

    # Log activity
    await log_activity(
        db,
        "resource_created",
        current_user.id,
        "resource",
        resource.id,
        f"Created resource: {resource.title}",
    )

    await db.commit()
    await db.refresh(resource)
    return resource


@router.patch("/resources/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    resource_id: int,
    data: ResourceUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a resource."""
    result = await db.execute(select(CSResource).where(CSResource.id == resource_id))
    resource = result.scalar_one_or_none()

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(resource, field, value)

    await db.commit()
    await db.refresh(resource)
    return resource


@router.delete("/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    resource_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a resource."""
    result = await db.execute(select(CSResource).where(CSResource.id == resource_id))
    resource = result.scalar_one_or_none()

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    await db.delete(resource)
    await db.commit()


@router.post("/resources/{resource_id}/like")
async def like_resource(
    resource_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Like a resource."""
    # Check resource exists
    res_result = await db.execute(select(CSResource).where(CSResource.id == resource_id))
    resource = res_result.scalar_one_or_none()

    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    # Check for existing like
    existing = await db.execute(
        select(CSResourceLike).where(
            CSResourceLike.resource_id == resource_id,
            CSResourceLike.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already liked",
        )

    like = CSResourceLike(
        resource_id=resource_id,
        user_id=current_user.id,
    )
    db.add(like)

    resource.likes_count = (resource.likes_count or 0) + 1

    await db.commit()
    return {"status": "success", "message": "Resource liked"}


@router.delete("/resources/{resource_id}/like")
async def unlike_resource(
    resource_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Unlike a resource."""
    result = await db.execute(
        select(CSResourceLike).where(
            CSResourceLike.resource_id == resource_id,
            CSResourceLike.user_id == current_user.id,
        )
    )
    like = result.scalar_one_or_none()

    if not like:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Like not found",
        )

    # Update count
    res_result = await db.execute(select(CSResource).where(CSResource.id == resource_id))
    resource = res_result.scalar_one_or_none()
    if resource:
        resource.likes_count = max(0, (resource.likes_count or 1) - 1)

    await db.delete(like)
    await db.commit()
    return {"status": "success", "message": "Like removed"}


@router.post(
    "/resources/{resource_id}/comments", response_model=ResourceCommentResponse, status_code=status.HTTP_201_CREATED
)
async def add_resource_comment(
    resource_id: int,
    data: ResourceCommentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Add a comment to a resource."""
    # Check resource exists
    res_result = await db.execute(select(CSResource).where(CSResource.id == resource_id))
    if not res_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found",
        )

    comment = CSResourceComment(
        resource_id=resource_id,
        user_id=current_user.id,
        **data.model_dump(),
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


@router.delete("/resources/{resource_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource_comment(
    resource_id: int,
    comment_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a resource comment."""
    result = await db.execute(
        select(CSResourceComment).where(
            CSResourceComment.id == comment_id,
            CSResourceComment.resource_id == resource_id,
        )
    )
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found",
        )

    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can delete this comment",
        )

    await db.delete(comment)
    await db.commit()


# ============ Team Notes ============


@router.get("/notes", response_model=TeamNoteListResponse)
async def list_notes(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[int] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    is_pinned: Optional[bool] = None,
):
    """List team notes with filtering."""
    try:
        query = select(CSTeamNote).options(selectinload(CSTeamNote.comments))

        if customer_id:
            query = query.where(CSTeamNote.customer_id == customer_id)
        if category:
            query = query.where(CSTeamNote.category == category)
        if search:
            query = query.where(CSTeamNote.title.ilike(f"%{search}%"))
        if is_pinned is not None:
            query = query.where(CSTeamNote.is_pinned == is_pinned)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = (
            query.offset(offset).limit(page_size).order_by(CSTeamNote.is_pinned.desc(), CSTeamNote.created_at.desc())
        )

        result = await db.execute(query)
        notes = result.scalars().unique().all()

        # Enhance with names
        items = []
        for note in notes:
            note_dict = {
                "id": note.id,
                "customer_id": note.customer_id,
                "title": note.title,
                "content": note.content,
                "content_html": note.content_html,
                "category": note.category,
                "tags": note.tags,
                "is_pinned": note.is_pinned,
                "visibility": note.visibility,
                "created_by_user_id": note.created_by_user_id,
                "comments": note.comments,
                "created_at": note.created_at,
                "updated_at": note.updated_at,
            }

            # Get customer name
            if note.customer_id:
                cust_result = await db.execute(select(Customer.name).where(Customer.id == note.customer_id))
                note_dict["customer_name"] = cust_result.scalar_one_or_none()
            else:
                note_dict["customer_name"] = None

            # Get creator name
            user_result = await db.execute(select(User.name).where(User.id == note.created_by_user_id))
            note_dict["created_by_name"] = user_result.scalar_one_or_none()

            items.append(note_dict)

        return TeamNoteListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error listing notes: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error listing notes: {str(e)}")


@router.get("/notes/{note_id}", response_model=TeamNoteResponse)
async def get_note(
    note_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific note."""
    result = await db.execute(
        select(CSTeamNote).options(selectinload(CSTeamNote.comments)).where(CSTeamNote.id == note_id)
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    return note


@router.post("/notes", response_model=TeamNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    data: TeamNoteCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new team note."""
    note = CSTeamNote(
        **data.model_dump(),
        created_by_user_id=current_user.id,
    )
    db.add(note)
    await db.flush()

    # Log activity
    await log_activity(
        db,
        "note_posted",
        current_user.id,
        "note",
        note.id,
        f"Posted note: {note.title}",
        customer_id=note.customer_id,
    )

    await db.commit()
    await db.refresh(note)
    return note


@router.patch("/notes/{note_id}", response_model=TeamNoteResponse)
async def update_note(
    note_id: int,
    data: TeamNoteUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a team note."""
    result = await db.execute(select(CSTeamNote).where(CSTeamNote.id == note_id))
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    # Only author can edit
    if note.created_by_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can edit this note",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(note, field, value)

    await db.commit()
    await db.refresh(note)
    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a team note."""
    result = await db.execute(select(CSTeamNote).where(CSTeamNote.id == note_id))
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    # Only author can delete
    if note.created_by_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can delete this note",
        )

    await db.delete(note)
    await db.commit()


@router.post("/notes/{note_id}/comments", response_model=TeamNoteCommentResponse, status_code=status.HTTP_201_CREATED)
async def add_note_comment(
    note_id: int,
    data: TeamNoteCommentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Add a comment to a note."""
    # Check note exists
    note_result = await db.execute(select(CSTeamNote).where(CSTeamNote.id == note_id))
    if not note_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    comment = CSTeamNoteComment(
        note_id=note_id,
        user_id=current_user.id,
        **data.model_dump(),
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


@router.delete("/notes/{note_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note_comment(
    note_id: int,
    comment_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a note comment."""
    result = await db.execute(
        select(CSTeamNoteComment).where(
            CSTeamNoteComment.id == comment_id,
            CSTeamNoteComment.note_id == note_id,
        )
    )
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found",
        )

    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can delete this comment",
        )

    await db.delete(comment)
    await db.commit()


# ============ Activity Feed ============


@router.get("/activity", response_model=ActivityListResponse)
async def list_activity(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    activity_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    customer_id: Optional[int] = None,
):
    """List team activity feed."""
    try:
        query = select(CSActivity)

        if activity_type:
            query = query.where(CSActivity.activity_type == activity_type)
        if entity_type:
            query = query.where(CSActivity.entity_type == entity_type)
        if customer_id:
            query = query.where(CSActivity.customer_id == customer_id)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(CSActivity.created_at.desc())

        result = await db.execute(query)
        activities = result.scalars().all()

        # Enhance with names
        items = []
        for activity in activities:
            activity_dict = {
                "id": activity.id,
                "activity_type": activity.activity_type,
                "entity_type": activity.entity_type,
                "entity_id": activity.entity_id,
                "title": activity.title,
                "description": activity.description,
                "activity_data": activity.activity_data,
                "user_id": activity.user_id,
                "customer_id": activity.customer_id,
                "created_at": activity.created_at,
            }

            # Get user name
            user_result = await db.execute(select(User.name).where(User.id == activity.user_id))
            activity_dict["user_name"] = user_result.scalar_one_or_none()

            # Get customer name if applicable
            if activity.customer_id:
                cust_result = await db.execute(select(Customer.name).where(Customer.id == activity.customer_id))
                activity_dict["customer_name"] = cust_result.scalar_one_or_none()
            else:
                activity_dict["customer_name"] = None

            items.append(activity_dict)

        return ActivityListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error listing activity: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error listing activity: {str(e)}"
        )
