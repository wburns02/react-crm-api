"""Pydantic schemas for CompanyEntity CRUD."""

from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class CompanyEntityCreate(BaseModel):
    name: str = Field(..., max_length=100)
    short_code: str = Field(..., max_length=10)
    tax_id: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    logo_url: Optional[str] = None
    invoice_prefix: Optional[str] = None


class CompanyEntityUpdate(BaseModel):
    name: Optional[str] = None
    short_code: Optional[str] = None
    tax_id: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    logo_url: Optional[str] = None
    invoice_prefix: Optional[str] = None
    is_active: Optional[bool] = None


class CompanyEntityResponse(BaseModel):
    id: str
    name: str
    short_code: Optional[str] = None
    tax_id: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    logo_url: Optional[str] = None
    invoice_prefix: Optional[str] = None
    is_active: bool = True
    is_default: bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_entity(cls, entity) -> "CompanyEntityResponse":
        return cls(
            id=str(entity.id),
            name=entity.name,
            short_code=entity.short_code,
            tax_id=entity.tax_id,
            address_line1=entity.address_line1,
            address_line2=entity.address_line2,
            city=entity.city,
            state=entity.state,
            postal_code=entity.postal_code,
            phone=entity.phone,
            email=entity.email,
            logo_url=entity.logo_url,
            invoice_prefix=entity.invoice_prefix,
            is_active=entity.is_active,
            is_default=entity.is_default,
        )
