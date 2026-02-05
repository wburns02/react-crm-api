from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.sql import func
from uuid import uuid4
from app.database import Base


class InventoryTransaction(Base):
    """Audit trail for inventory quantity adjustments."""

    __tablename__ = "inventory_transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    item_id = Column(String(36), ForeignKey("inventory_items.id"), nullable=False, index=True)
    adjustment = Column(Integer, nullable=False)
    previous_quantity = Column(Integer, nullable=False)
    new_quantity = Column(Integer, nullable=False)
    reason = Column(String(255))
    reference_type = Column(String(50))  # work_order, manual, restock, return
    reference_id = Column(String(36))
    performed_by = Column(Integer)  # user_id
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<InventoryTransaction {self.id} item={self.item_id} adj={self.adjustment}>"
