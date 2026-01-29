from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class WorkOrderPhotoBase(BaseModel):
    """Base work order photo schema."""

    photo_type: str
    timestamp: datetime
    device_info: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    gps_accuracy: Optional[float] = None


class WorkOrderPhotoCreate(WorkOrderPhotoBase):
    """Schema for creating a work order photo."""

    data: str  # base64 encoded image
    thumbnail: Optional[str] = None  # base64 encoded thumbnail


class WorkOrderPhotoResponse(WorkOrderPhotoBase):
    """Schema for work order photo response."""

    id: str
    work_order_id: str
    data_url: Optional[str] = None  # base64 data URL for display
    thumbnail_url: Optional[str] = None  # base64 thumbnail URL for display
    created_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_model(cls, photo) -> "WorkOrderPhotoResponse":
        """Create response from SQLAlchemy model."""
        return cls(
            id=photo.id,
            work_order_id=photo.work_order_id,
            photo_type=photo.photo_type,
            timestamp=photo.timestamp,
            device_info=photo.device_info,
            gps_lat=photo.gps_lat,
            gps_lng=photo.gps_lng,
            gps_accuracy=photo.gps_accuracy,
            data_url=photo.data,  # Already stored as data URL
            thumbnail_url=photo.thumbnail,
            created_at=photo.created_at,
        )


class WorkOrderPhotoListResponse(BaseModel):
    """Paginated photo list response."""

    items: list[WorkOrderPhotoResponse]
    total: int
