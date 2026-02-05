"""Equipment schemas for request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional, Literal


EquipmentType = Literal[
    "septic_tank", "pump", "drain_field", "grease_trap", "lift_station", "distribution_box", "other"
]
EquipmentCondition = Literal["excellent", "good", "fair", "poor", "needs_replacement"]


class EquipmentBase(BaseModel):
    """Base equipment schema."""

    customer_id: str = Field(..., description="Customer ID")
    equipment_type: str = Field(..., min_length=1, max_length=100)
    manufacturer: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    serial_number: Optional[str] = Field(None, max_length=100)
    capacity_gallons: Optional[int] = None
    size_description: Optional[str] = Field(None, max_length=255)
    install_date: Optional[str] = None  # YYYY-MM-DD
    installed_by: Optional[str] = Field(None, max_length=100)
    warranty_expiry: Optional[str] = None  # YYYY-MM-DD
    warranty_notes: Optional[str] = None
    last_service_date: Optional[str] = None  # YYYY-MM-DD
    next_service_date: Optional[str] = None  # YYYY-MM-DD
    service_interval_months: Optional[int] = None
    location_description: Optional[str] = Field(None, max_length=255)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    condition: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[str] = "active"


class EquipmentCreate(EquipmentBase):
    """Schema for creating equipment."""

    pass


class EquipmentUpdate(BaseModel):
    """Schema for updating equipment (all fields optional)."""

    equipment_type: Optional[str] = Field(None, min_length=1, max_length=100)
    manufacturer: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    serial_number: Optional[str] = Field(None, max_length=100)
    capacity_gallons: Optional[int] = None
    size_description: Optional[str] = Field(None, max_length=255)
    install_date: Optional[str] = None
    installed_by: Optional[str] = Field(None, max_length=100)
    warranty_expiry: Optional[str] = None
    warranty_notes: Optional[str] = None
    last_service_date: Optional[str] = None
    next_service_date: Optional[str] = None
    service_interval_months: Optional[int] = None
    location_description: Optional[str] = Field(None, max_length=255)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    condition: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[str] = None


class EquipmentResponse(BaseModel):
    """Schema for equipment response."""

    id: str
    customer_id: str
    equipment_type: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    capacity_gallons: Optional[int] = None
    size_description: Optional[str] = None
    install_date: Optional[str] = None
    installed_by: Optional[str] = None
    warranty_expiry: Optional[str] = None
    warranty_notes: Optional[str] = None
    last_service_date: Optional[str] = None
    next_service_date: Optional[str] = None
    service_interval_months: Optional[int] = None
    location_description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    condition: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class EquipmentListResponse(BaseModel):
    """Paginated equipment list response."""

    items: list[EquipmentResponse]
    total: int
    page: int
    page_size: int
