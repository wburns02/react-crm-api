from pydantic import BaseModel, Field
from typing import Optional


class TechnicianBase(BaseModel):
    """Base technician schema."""
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)
    # Using str instead of EmailStr to allow empty strings from database
    email: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=20)
    employee_id: Optional[str] = Field(None, max_length=50)
    is_active: bool = True

    # Home location
    home_region: Optional[str] = Field(None, max_length=100)
    home_address: Optional[str] = Field(None, max_length=255)
    home_city: Optional[str] = Field(None, max_length=100)
    home_state: Optional[str] = Field(None, max_length=50)
    home_postal_code: Optional[str] = Field(None, max_length=20)
    home_latitude: Optional[float] = None
    home_longitude: Optional[float] = None

    # Skills (array of skill strings)
    skills: Optional[list[str]] = None

    # Vehicle info
    assigned_vehicle: Optional[str] = Field(None, max_length=100)
    vehicle_capacity_gallons: Optional[float] = None

    # Licensing
    license_number: Optional[str] = Field(None, max_length=100)
    license_expiry: Optional[str] = Field(None, max_length=20)

    # Payroll
    hourly_rate: Optional[float] = None

    # Notes
    notes: Optional[str] = None


class TechnicianCreate(TechnicianBase):
    """Schema for creating a technician."""
    pass


class TechnicianUpdate(BaseModel):
    """Schema for updating a technician (all fields optional)."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    employee_id: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None

    # Home location
    home_region: Optional[str] = Field(None, max_length=100)
    home_address: Optional[str] = Field(None, max_length=255)
    home_city: Optional[str] = Field(None, max_length=100)
    home_state: Optional[str] = Field(None, max_length=50)
    home_postal_code: Optional[str] = Field(None, max_length=20)
    home_latitude: Optional[float] = None
    home_longitude: Optional[float] = None

    # Skills
    skills: Optional[list[str]] = None

    # Vehicle info
    assigned_vehicle: Optional[str] = Field(None, max_length=100)
    vehicle_capacity_gallons: Optional[float] = None

    # Licensing
    license_number: Optional[str] = Field(None, max_length=100)
    license_expiry: Optional[str] = Field(None, max_length=20)

    # Payroll
    hourly_rate: Optional[float] = None

    # Notes
    notes: Optional[str] = None


class TechnicianResponse(TechnicianBase):
    """Schema for technician response."""
    id: str  # Frontend expects string ID
    full_name: Optional[str] = None
    # Accept both datetime and string for flexibility
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class TechnicianListResponse(BaseModel):
    """Paginated technician list response."""
    items: list[TechnicianResponse]
    total: int
    page: int
    page_size: int
