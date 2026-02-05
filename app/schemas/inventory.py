"""Inventory schemas for request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional

from app.schemas.types import UUIDStr


class InventoryItemBase(BaseModel):
    """Base inventory item schema."""

    sku: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    unit_price: Optional[float] = None
    cost_price: Optional[float] = None
    markup_percent: Optional[float] = None
    quantity_on_hand: Optional[int] = 0
    quantity_reserved: Optional[int] = 0
    reorder_level: Optional[int] = 0
    reorder_quantity: Optional[int] = None
    unit: Optional[str] = Field("each", max_length=20)
    supplier_name: Optional[str] = Field(None, max_length=255)
    supplier_sku: Optional[str] = Field(None, max_length=100)
    supplier_phone: Optional[str] = Field(None, max_length=20)
    warehouse_location: Optional[str] = Field(None, max_length=100)
    vehicle_id: Optional[str] = None
    is_active: Optional[bool] = True
    is_taxable: Optional[bool] = True
    notes: Optional[str] = None


class InventoryItemCreate(InventoryItemBase):
    """Schema for creating an inventory item."""

    pass


class InventoryItemUpdate(BaseModel):
    """Schema for updating an inventory item (all fields optional)."""

    sku: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    unit_price: Optional[float] = None
    cost_price: Optional[float] = None
    markup_percent: Optional[float] = None
    quantity_on_hand: Optional[int] = None
    quantity_reserved: Optional[int] = None
    reorder_level: Optional[int] = None
    reorder_quantity: Optional[int] = None
    unit: Optional[str] = Field(None, max_length=20)
    supplier_name: Optional[str] = Field(None, max_length=255)
    supplier_sku: Optional[str] = Field(None, max_length=100)
    supplier_phone: Optional[str] = Field(None, max_length=20)
    warehouse_location: Optional[str] = Field(None, max_length=100)
    vehicle_id: Optional[str] = None
    is_active: Optional[bool] = None
    is_taxable: Optional[bool] = None
    notes: Optional[str] = None


class InventoryItemResponse(BaseModel):
    """Schema for inventory item response."""

    id: UUIDStr
    sku: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    unit_price: Optional[float] = None
    cost_price: Optional[float] = None
    markup_percent: Optional[float] = None
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int  # Computed: on_hand - reserved
    reorder_level: int
    reorder_quantity: Optional[int] = None
    needs_reorder: bool  # Computed: on_hand <= reorder_level
    unit: str
    supplier_name: Optional[str] = None
    supplier_sku: Optional[str] = None
    supplier_phone: Optional[str] = None
    warehouse_location: Optional[str] = None
    vehicle_id: Optional[UUIDStr] = None
    is_active: bool
    is_taxable: bool
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class InventoryListResponse(BaseModel):
    """Paginated inventory list response."""

    items: list[InventoryItemResponse]
    total: int
    page: int
    page_size: int


class InventoryAdjustment(BaseModel):
    """Schema for adjusting inventory quantity."""

    adjustment: int = Field(..., description="Positive to add, negative to subtract")
    reason: Optional[str] = Field(None, max_length=255)
    reference_type: Optional[str] = Field(None, max_length=50, description="work_order, manual, restock, return")
    reference_id: Optional[str] = Field(None, max_length=36)
