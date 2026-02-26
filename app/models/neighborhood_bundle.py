"""Neighborhood Bundle model for grouped discount contracts."""

from sqlalchemy import Column, String, DateTime, Text, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class NeighborhoodBundle(Base):
    """Group of contracts for neighbors sharing a discount."""

    __tablename__ = "neighborhood_bundles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)  # e.g., "Cedar Park Estates Group"
    discount_percent = Column(Float, nullable=False, default=10.0)
    min_contracts = Column(Integer, nullable=False, default=5)
    status = Column(String(20), nullable=False, default="active")  # active, inactive
    notes = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    contracts = relationship("Contract", back_populates="neighborhood_bundle")

    def __repr__(self):
        return f"<NeighborhoodBundle {self.name} ({self.discount_percent}% off)>"
