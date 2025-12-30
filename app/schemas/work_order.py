from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from app.models.work_order import JobType, WorkOrderStatus, Priority


class WorkOrderBase(BaseModel):
    """Base work order schema."""
    customer_id: int
    job_type: JobType
    status: WorkOrderStatus = WorkOrderStatus.draft
    priority: Priority = Priority.normal
    scheduled_date: Optional[datetime] = None
    time_window_start: Optional[str] = None
    time_window_end: Optional[str] = None
    estimated_duration_hours: Optional[float] = None
    assigned_technician: Optional[str] = None
    # Match Flask column names (use aliases for React compatibility)
    service_address_line1: Optional[str] = Field(None, alias="service_address")
    service_city: Optional[str] = None
    service_state: Optional[str] = None
    service_postal_code: Optional[str] = Field(None, alias="service_zip")
    description: Optional[str] = None
    notes: Optional[str] = None
    internal_notes: Optional[str] = None


class WorkOrderCreate(WorkOrderBase):
    """Schema for creating a work order."""
    pass


class WorkOrderUpdate(BaseModel):
    """Schema for updating a work order (all fields optional)."""
    customer_id: Optional[int] = None
    job_type: Optional[JobType] = None
    status: Optional[WorkOrderStatus] = None
    priority: Optional[Priority] = None
    scheduled_date: Optional[datetime] = None
    time_window_start: Optional[str] = None
    time_window_end: Optional[str] = None
    estimated_duration_hours: Optional[float] = None
    assigned_technician: Optional[str] = None
    # Match Flask column names
    service_address_line1: Optional[str] = Field(None, alias="service_address")
    service_city: Optional[str] = None
    service_state: Optional[str] = None
    service_postal_code: Optional[str] = Field(None, alias="service_zip")
    description: Optional[str] = None
    notes: Optional[str] = None
    internal_notes: Optional[str] = None
    completed_at: Optional[datetime] = None
    completion_notes: Optional[str] = None


class WorkOrderResponse(WorkOrderBase):
    """Schema for work order response."""
    id: str  # Flask uses VARCHAR(36) UUID
    completed_at: Optional[datetime] = None
    completion_notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        populate_by_name = True


class WorkOrderListResponse(BaseModel):
    """Paginated work order list response."""
    items: list[WorkOrderResponse]
    total: int
    page: int
    page_size: int
