from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from typing import List
from datetime import datetime
import uuid
import logging
import traceback

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.work_order_photo import WorkOrderPhoto
from app.schemas.work_order_photo import (
    WorkOrderPhotoCreate,
    WorkOrderPhotoResponse,
)
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{work_order_id}/photos", response_model=List[WorkOrderPhotoResponse])
async def list_work_order_photos(
    work_order_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get all photos for a work order."""
    try:
        # Verify work order exists
        wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
        work_order = wo_result.scalar_one_or_none()

        if not work_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Work order not found",
            )

        # Get photos
        query = (
            select(WorkOrderPhoto)
            .where(WorkOrderPhoto.work_order_id == work_order_id)
            .order_by(WorkOrderPhoto.created_at.desc())
        )

        result = await db.execute(query)
        photos = result.scalars().all()

        return [WorkOrderPhotoResponse.from_model(photo) for photo in photos]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching photos for work order {work_order_id}: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.post("/{work_order_id}/photos", response_model=WorkOrderPhotoResponse, status_code=status.HTTP_201_CREATED)
async def upload_work_order_photo(
    work_order_id: str,
    photo_data: WorkOrderPhotoCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Upload a photo for a work order."""
    # Verify work order exists
    wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = wo_result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work order not found",
        )

    try:
        photo = WorkOrderPhoto(
            id=str(uuid.uuid4()),
            work_order_id=work_order_id,
            photo_type=photo_data.photo_type,
            data=photo_data.data,
            thumbnail=photo_data.thumbnail,
            timestamp=photo_data.timestamp,
            device_info=photo_data.device_info,
            gps_lat=photo_data.gps_lat,
            gps_lng=photo_data.gps_lng,
            gps_accuracy=photo_data.gps_accuracy,
        )
        db.add(photo)
        await db.commit()
        await db.refresh(photo)

        logger.info(f"Photo uploaded for work order {work_order_id}: {photo.id}")

        # Broadcast photo upload event
        await manager.broadcast_event(
            event_type="work_order_update",
            data={
                "work_order_id": work_order_id,
                "photo_id": photo.id,
                "photo_type": photo.photo_type,
            },
        )

        return WorkOrderPhotoResponse.from_model(photo)

    except Exception as e:
        await db.rollback()
        logger.error(f"Error uploading photo for work order {work_order_id}: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to upload photo: {str(e)}")


@router.delete("/{work_order_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work_order_photo(
    work_order_id: str,
    photo_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a photo from a work order."""
    # Find the photo
    result = await db.execute(
        select(WorkOrderPhoto).where(
            WorkOrderPhoto.id == photo_id,
            WorkOrderPhoto.work_order_id == work_order_id,
        )
    )
    photo = result.scalar_one_or_none()

    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )

    await db.delete(photo)
    await db.commit()

    logger.info(f"Photo deleted from work order {work_order_id}: {photo_id}")

    # Broadcast photo delete event
    await manager.broadcast_event(
        event_type="work_order_update",
        data={
            "work_order_id": work_order_id,
            "photo_id": photo_id,
        },
    )
