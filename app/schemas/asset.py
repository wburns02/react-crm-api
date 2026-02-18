"""Asset management schemas for request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

from app.schemas.types import UUIDStr


# ---- Asset Schemas ----

class AssetCreate(BaseModel):
    """Schema for creating an asset."""
    name: str = Field(..., min_length=1, max_length=255)
    asset_tag: Optional[str] = Field(None, max_length=50)
    asset_type: str = Field(..., max_length=50)
    category: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    make: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    serial_number: Optional[str] = Field(None, max_length=100)
    year: Optional[int] = None
    purchase_date: Optional[str] = None  # YYYY-MM-DD
    purchase_price: Optional[float] = None
    current_value: Optional[float] = None
    salvage_value: Optional[float] = 0
    useful_life_years: Optional[int] = 10
    depreciation_method: Optional[str] = "straight_line"
    status: Optional[str] = "available"
    condition: Optional[str] = "good"
    assigned_technician_id: Optional[str] = None
    assigned_technician_name: Optional[str] = None
    assigned_work_order_id: Optional[str] = None
    location_description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    samsara_vehicle_id: Optional[str] = None
    last_maintenance_date: Optional[str] = None
    next_maintenance_date: Optional[str] = None
    maintenance_interval_days: Optional[int] = None
    total_hours: Optional[float] = 0
    odometer_miles: Optional[float] = None
    photo_url: Optional[str] = None
    warranty_expiry: Optional[str] = None
    insurance_policy: Optional[str] = None
    insurance_expiry: Optional[str] = None
    notes: Optional[str] = None


class AssetUpdate(BaseModel):
    """Schema for updating an asset (all fields optional)."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    asset_tag: Optional[str] = Field(None, max_length=50)
    asset_type: Optional[str] = Field(None, max_length=50)
    category: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    make: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    serial_number: Optional[str] = Field(None, max_length=100)
    year: Optional[int] = None
    purchase_date: Optional[str] = None
    purchase_price: Optional[float] = None
    current_value: Optional[float] = None
    salvage_value: Optional[float] = None
    useful_life_years: Optional[int] = None
    depreciation_method: Optional[str] = None
    status: Optional[str] = None
    condition: Optional[str] = None
    assigned_technician_id: Optional[str] = None
    assigned_technician_name: Optional[str] = None
    assigned_work_order_id: Optional[str] = None
    location_description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    samsara_vehicle_id: Optional[str] = None
    last_maintenance_date: Optional[str] = None
    next_maintenance_date: Optional[str] = None
    maintenance_interval_days: Optional[int] = None
    total_hours: Optional[float] = None
    odometer_miles: Optional[float] = None
    photo_url: Optional[str] = None
    warranty_expiry: Optional[str] = None
    insurance_policy: Optional[str] = None
    insurance_expiry: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class AssetResponse(BaseModel):
    """Schema for asset response."""
    id: UUIDStr
    name: str
    asset_tag: Optional[str] = None
    asset_type: str
    category: Optional[str] = None
    description: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    year: Optional[int] = None
    purchase_date: Optional[str] = None
    purchase_price: Optional[float] = None
    current_value: Optional[float] = None
    depreciated_value: Optional[float] = None
    salvage_value: Optional[float] = None
    useful_life_years: Optional[int] = None
    depreciation_method: Optional[str] = None
    status: str
    condition: Optional[str] = None
    assigned_technician_id: Optional[UUIDStr] = None
    assigned_technician_name: Optional[str] = None
    assigned_work_order_id: Optional[UUIDStr] = None
    location_description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    samsara_vehicle_id: Optional[str] = None
    last_maintenance_date: Optional[str] = None
    next_maintenance_date: Optional[str] = None
    maintenance_interval_days: Optional[int] = None
    total_hours: Optional[float] = None
    odometer_miles: Optional[float] = None
    photo_url: Optional[str] = None
    qr_code: Optional[str] = None
    warranty_expiry: Optional[str] = None
    insurance_policy: Optional[str] = None
    insurance_expiry: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class AssetListResponse(BaseModel):
    """Paginated asset list response."""
    items: list[AssetResponse]
    total: int
    page: int
    page_size: int


# ---- Maintenance Log Schemas ----

class MaintenanceLogCreate(BaseModel):
    """Schema for creating a maintenance log entry."""
    asset_id: str
    maintenance_type: str = Field(..., max_length=50)
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    performed_by_id: Optional[str] = None
    performed_by_name: Optional[str] = None
    performed_at: Optional[str] = None
    cost: Optional[float] = 0
    parts_used: Optional[str] = None
    hours_at_service: Optional[float] = None
    odometer_at_service: Optional[float] = None
    next_due_date: Optional[str] = None
    next_due_hours: Optional[float] = None
    next_due_miles: Optional[float] = None
    condition_before: Optional[str] = None
    condition_after: Optional[str] = None
    photos: Optional[str] = None
    notes: Optional[str] = None


class MaintenanceLogResponse(BaseModel):
    """Schema for maintenance log response."""
    id: UUIDStr
    asset_id: UUIDStr
    maintenance_type: str
    title: str
    description: Optional[str] = None
    performed_by_id: Optional[UUIDStr] = None
    performed_by_name: Optional[str] = None
    performed_at: Optional[str] = None
    cost: Optional[float] = None
    parts_used: Optional[str] = None
    hours_at_service: Optional[float] = None
    odometer_at_service: Optional[float] = None
    next_due_date: Optional[str] = None
    next_due_hours: Optional[float] = None
    next_due_miles: Optional[float] = None
    condition_before: Optional[str] = None
    condition_after: Optional[str] = None
    photos: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


# ---- Assignment Schemas ----

class AssetCheckout(BaseModel):
    """Schema for checking out an asset."""
    asset_id: str
    assigned_to_type: str = Field(..., max_length=50)  # technician, work_order
    assigned_to_id: str
    assigned_to_name: Optional[str] = None
    condition_at_checkout: Optional[str] = None
    notes: Optional[str] = None


class AssetCheckin(BaseModel):
    """Schema for checking in an asset."""
    condition_at_checkin: Optional[str] = None
    notes: Optional[str] = None


class AssignmentResponse(BaseModel):
    """Schema for assignment response."""
    id: UUIDStr
    asset_id: UUIDStr
    assigned_to_type: str
    assigned_to_id: UUIDStr
    assigned_to_name: Optional[str] = None
    checked_out_at: Optional[str] = None
    checked_in_at: Optional[str] = None
    checked_out_by_id: Optional[UUIDStr] = None
    checked_out_by_name: Optional[str] = None
    condition_at_checkout: Optional[str] = None
    condition_at_checkin: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


# ---- Dashboard Schemas ----

class AssetDashboardResponse(BaseModel):
    """Schema for asset dashboard summary."""
    total_assets: int = 0
    total_value: float = 0
    by_status: dict = {}
    by_type: dict = {}
    by_condition: dict = {}
    maintenance_due: int = 0
    maintenance_overdue: int = 0
    recently_added: list = []
    recent_maintenance: list = []
    low_condition_assets: list = []
