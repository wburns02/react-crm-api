from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


class TechnicianBase(BaseModel):
    """Base technician schema."""
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
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
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Custom validation to convert integer id to string."""
        if hasattr(obj, 'id') and isinstance(obj.id, int):
            # Create a dict-like wrapper that converts id to string
            class IdWrapper:
                def __init__(self, original):
                    self._original = original

                def __getattr__(self, name):
                    if name == 'id':
                        return str(self._original.id)
                    if name == 'full_name':
                        return f"{self._original.first_name} {self._original.last_name}"
                    return getattr(self._original, name)

            obj = IdWrapper(obj)
        return super().model_validate(obj, **kwargs)


class TechnicianListResponse(BaseModel):
    """Paginated technician list response."""
    items: list[TechnicianResponse]
    total: int
    page: int
    page_size: int
