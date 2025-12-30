"""Inventory model for tracking parts, materials, and supplies."""
from sqlalchemy import Column, String, DateTime, Text, Integer, Float, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class InventoryItem(Base):
    """Inventory item model for parts and materials tracking."""

    __tablename__ = "inventory_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Item identification
    sku = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True, index=True)  # parts, chemicals, supplies, tools

    # Pricing
    unit_price = Column(Float, nullable=True)  # Sell price
    cost_price = Column(Float, nullable=True)  # Purchase cost
    markup_percent = Column(Float, nullable=True)

    # Stock levels
    quantity_on_hand = Column(Integer, default=0)
    quantity_reserved = Column(Integer, default=0)  # Reserved for work orders
    reorder_level = Column(Integer, default=0)  # Alert when stock falls below this
    reorder_quantity = Column(Integer, nullable=True)  # How much to order

    # Unit of measure
    unit = Column(String(20), default="each")  # each, gallon, foot, box, etc.

    # Supplier info
    supplier_name = Column(String(255), nullable=True)
    supplier_sku = Column(String(100), nullable=True)
    supplier_phone = Column(String(20), nullable=True)

    # Location
    warehouse_location = Column(String(100), nullable=True)  # Bin, shelf, etc.
    vehicle_id = Column(String(36), nullable=True)  # If stocked on a truck

    # Status
    is_active = Column(Boolean, default=True)
    is_taxable = Column(Boolean, default=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<InventoryItem {self.sku} - {self.name}>"

    @property
    def quantity_available(self) -> int:
        """Available quantity (on hand minus reserved)."""
        return (self.quantity_on_hand or 0) - (self.quantity_reserved or 0)

    @property
    def needs_reorder(self) -> bool:
        """Check if item needs to be reordered."""
        return self.quantity_on_hand <= self.reorder_level
