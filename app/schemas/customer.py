from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional
from app.models.customer import CustomerType, ProspectStage, LeadSource


class CustomerBase(BaseModel):
    """Base customer schema."""
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zip_code: Optional[str] = Field(None, max_length=20)
    customer_type: Optional[CustomerType] = CustomerType.residential
    prospect_stage: Optional[ProspectStage] = ProspectStage.new_lead
    lead_source: Optional[LeadSource] = None
    notes: Optional[str] = None
    is_active: bool = True
    preferred_contact_method: Optional[str] = None
    company_name: Optional[str] = None
    tags: Optional[str] = None


class CustomerCreate(CustomerBase):
    """Schema for creating a customer."""
    pass


class CustomerUpdate(BaseModel):
    """Schema for updating a customer (all fields optional)."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    zip_code: Optional[str] = Field(None, max_length=20)
    customer_type: Optional[CustomerType] = None
    prospect_stage: Optional[ProspectStage] = None
    lead_source: Optional[LeadSource] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    preferred_contact_method: Optional[str] = None
    company_name: Optional[str] = None
    tags: Optional[str] = None


class CustomerResponse(CustomerBase):
    """Schema for customer response."""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CustomerListResponse(BaseModel):
    """Paginated customer list response."""
    items: list[CustomerResponse]
    total: int
    page: int
    page_size: int
