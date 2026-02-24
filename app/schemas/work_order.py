from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date, time
from typing import Optional, Any
from decimal import Decimal

from app.schemas.types import UUIDStr


class WorkOrderBase(BaseModel):
    """Base work order schema."""

    customer_id: UUIDStr
    technician_id: Optional[UUIDStr] = None
    job_type: str
    status: Optional[str] = "draft"
    priority: Optional[str] = "normal"

    # Scheduling
    scheduled_date: Optional[date] = None
    time_window_start: Optional[time] = None
    time_window_end: Optional[time] = None
    estimated_duration_hours: Optional[float] = None

    # Service location
    service_address_line1: Optional[str] = None
    service_address_line2: Optional[str] = None
    service_city: Optional[str] = None
    service_state: Optional[str] = None
    service_postal_code: Optional[str] = None
    service_latitude: Optional[float] = None
    service_longitude: Optional[float] = None

    # Job specifics
    estimated_gallons: Optional[int] = None
    notes: Optional[str] = None
    internal_notes: Optional[str] = None

    # Recurrence
    is_recurring: Optional[bool] = False
    recurrence_frequency: Optional[str] = None
    next_recurrence_date: Optional[date] = None

    # Checklist
    checklist: Optional[Any] = None

    # Assignment
    assigned_vehicle: Optional[str] = None
    assigned_technician: Optional[str] = None

    # Septic system type
    system_type: Optional[str] = "conventional"

    # Financial
    total_amount: Optional[Decimal] = None

    @field_validator("assigned_technician", mode="before")
    @classmethod
    def title_case_technician(cls, v: Optional[str]) -> Optional[str]:
        if v and isinstance(v, str):
            return v.strip().title()
        return v

    @field_validator("service_city", mode="before")
    @classmethod
    def title_case_city(cls, v: Optional[str]) -> Optional[str]:
        if v and isinstance(v, str):
            return v.strip().title()
        return v


class WorkOrderCreate(WorkOrderBase):
    """Schema for creating a work order."""

    pass


class WorkOrderUpdate(BaseModel):
    """Schema for updating a work order (all fields optional)."""

    customer_id: Optional[str] = None
    technician_id: Optional[str] = None
    job_type: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None

    scheduled_date: Optional[date] = None
    time_window_start: Optional[time] = None
    time_window_end: Optional[time] = None
    estimated_duration_hours: Optional[float] = None

    service_address_line1: Optional[str] = None
    service_address_line2: Optional[str] = None
    service_city: Optional[str] = None
    service_state: Optional[str] = None
    service_postal_code: Optional[str] = None
    service_latitude: Optional[float] = None
    service_longitude: Optional[float] = None

    estimated_gallons: Optional[int] = None
    notes: Optional[str] = None
    internal_notes: Optional[str] = None

    is_recurring: Optional[bool] = None
    recurrence_frequency: Optional[str] = None
    next_recurrence_date: Optional[date] = None

    checklist: Optional[Any] = None

    assigned_vehicle: Optional[str] = None
    assigned_technician: Optional[str] = None

    system_type: Optional[str] = None

    total_amount: Optional[Decimal] = None

    # Time tracking
    actual_start_time: Optional[datetime] = None
    actual_end_time: Optional[datetime] = None
    travel_start_time: Optional[datetime] = None
    travel_end_time: Optional[datetime] = None
    break_minutes: Optional[int] = None
    is_clocked_in: Optional[bool] = None


class WorkOrderResponse(WorkOrderBase):
    """Schema for work order response."""

    id: UUIDStr  # Flask uses VARCHAR(36) UUID
    work_order_number: Optional[str] = None  # Human-readable WO-NNNNNN format
    customer_name: Optional[str] = None  # Populated from Customer JOIN
    customer_phone: Optional[str] = None  # Populated from Customer JOIN
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    source: Optional[str] = None

    # Time tracking
    actual_start_time: Optional[datetime] = None
    actual_end_time: Optional[datetime] = None
    travel_start_time: Optional[datetime] = None
    travel_end_time: Optional[datetime] = None
    break_minutes: Optional[int] = None
    total_labor_minutes: Optional[int] = None
    total_travel_minutes: Optional[int] = None

    # Clock in/out
    is_clocked_in: Optional[bool] = False
    clock_in_gps_lat: Optional[float] = None
    clock_in_gps_lon: Optional[float] = None
    clock_out_gps_lat: Optional[float] = None
    clock_out_gps_lon: Optional[float] = None

    # Notification (populated on PATCH responses when status → completed)
    notification_sent: Optional[bool] = False

    class Config:
        from_attributes = True


class WorkOrderListResponse(BaseModel):
    """Paginated work order list response."""

    items: list[WorkOrderResponse]
    total: int
    page: int
    page_size: int


class WorkOrderCursorResponse(BaseModel):
    """Cursor-paginated work order list response (for large datasets)."""

    items: list[WorkOrderResponse]
    next_cursor: Optional[str] = None
    has_more: bool
    total: Optional[int] = None  # Optional for performance


class WorkOrderAuditLogResponse(BaseModel):
    """Single audit log entry."""

    id: UUIDStr
    work_order_id: UUIDStr
    action: str
    description: Optional[str] = None
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    source: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    changes: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True
