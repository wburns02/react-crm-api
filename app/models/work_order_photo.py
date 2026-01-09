from sqlalchemy import Column, String, Text, DateTime, Float, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class WorkOrderPhoto(Base):
    """Work Order Photo model - stores photos captured during work order execution."""

    __tablename__ = "work_order_photos"

    id = Column(String(36), primary_key=True, index=True)
    work_order_id = Column(String(36), ForeignKey("work_orders.id"), nullable=False, index=True)

    # Photo type (before, during, after, issue, signature, etc.)
    photo_type = Column(String(50), nullable=False)

    # Base64 encoded image data
    data = Column(Text, nullable=False)
    thumbnail = Column(Text)

    # Metadata
    timestamp = Column(DateTime(timezone=True), nullable=False)
    device_info = Column(String(255))

    # GPS coordinates
    gps_lat = Column(Float)
    gps_lng = Column(Float)
    gps_accuracy = Column(Float)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    work_order = relationship("WorkOrder", backref="photos")

    def __repr__(self):
        return f"<WorkOrderPhoto {self.id} - {self.photo_type}>"
