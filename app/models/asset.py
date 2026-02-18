"""Asset management models for company-owned assets (trucks, pumps, tools, PPE)."""

from sqlalchemy import Column, String, DateTime, Text, Integer, Float, Date, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Asset(Base):
    """Company-owned asset (vehicle, pump, tool, PPE, trailer, etc.)."""

    __tablename__ = "assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Core identification
    name = Column(String(255), nullable=False)
    asset_tag = Column(String(50), unique=True, index=True)  # e.g., "TRK-001", "PMP-003"
    asset_type = Column(String(50), nullable=False, index=True)  # vehicle, pump, tool, ppe, trailer, part, other
    category = Column(String(100))  # sub-category: vacuum_truck, jetter, shovel, hard_hat, etc.

    # Description
    description = Column(Text)
    make = Column(String(100))
    model = Column(String(100))
    serial_number = Column(String(100))
    year = Column(Integer)

    # Financial
    purchase_date = Column(Date)
    purchase_price = Column(Float)
    current_value = Column(Float)
    salvage_value = Column(Float, default=0)
    useful_life_years = Column(Integer, default=10)
    depreciation_method = Column(String(50), default="straight_line")  # straight_line, declining_balance

    # Status & condition
    status = Column(String(50), default="available", index=True)  # available, in_use, maintenance, retired, lost
    condition = Column(String(50), default="good")  # excellent, good, fair, poor

    # Assignment (current)
    assigned_technician_id = Column(UUID(as_uuid=True), nullable=True)
    assigned_technician_name = Column(String(255))
    assigned_work_order_id = Column(UUID(as_uuid=True), nullable=True)

    # Location & tracking
    location_description = Column(String(255))
    latitude = Column(Float)
    longitude = Column(Float)
    samsara_vehicle_id = Column(String(100))  # Link to Samsara for vehicles

    # Maintenance scheduling
    last_maintenance_date = Column(Date)
    next_maintenance_date = Column(Date)
    maintenance_interval_days = Column(Integer)
    total_hours = Column(Float, default=0)  # Usage hours
    odometer_miles = Column(Float)  # For vehicles

    # Photos & QR
    photo_url = Column(Text)  # Base64 or URL
    qr_code = Column(String(100), unique=True)  # Unique QR identifier

    # Insurance & warranty
    warranty_expiry = Column(Date)
    insurance_policy = Column(String(100))
    insurance_expiry = Column(Date)

    # Metadata
    notes = Column(Text)
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Asset {self.asset_tag} - {self.name}>"

    @property
    def depreciated_value(self) -> float:
        """Calculate current depreciated value using straight-line method."""
        if not self.purchase_price or not self.purchase_date:
            return self.current_value or 0
        from datetime import date
        years_owned = (date.today() - self.purchase_date).days / 365.25
        if self.useful_life_years and self.useful_life_years > 0:
            salvage = self.salvage_value or 0
            annual_depreciation = (self.purchase_price - salvage) / self.useful_life_years
            depreciated = self.purchase_price - (annual_depreciation * min(years_owned, self.useful_life_years))
            return max(depreciated, salvage)
        return self.purchase_price


class AssetMaintenanceLog(Base):
    """Maintenance/service history for an asset."""

    __tablename__ = "asset_maintenance_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)

    # Maintenance details
    maintenance_type = Column(String(50), nullable=False)  # scheduled, repair, inspection, preventive
    title = Column(String(255), nullable=False)
    description = Column(Text)

    # Who performed it
    performed_by_id = Column(UUID(as_uuid=True))
    performed_by_name = Column(String(255))
    performed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Cost tracking
    cost = Column(Float, default=0)
    parts_used = Column(Text)  # JSON string: [{"name": "Oil Filter", "qty": 1, "cost": 15.99}]

    # Usage at time of service
    hours_at_service = Column(Float)
    odometer_at_service = Column(Float)

    # Next due
    next_due_date = Column(Date)
    next_due_hours = Column(Float)
    next_due_miles = Column(Float)

    # Condition tracking
    condition_before = Column(String(50))
    condition_after = Column(String(50))

    # Photos & notes
    photos = Column(Text)  # JSON array of base64/URLs
    notes = Column(Text)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AssetMaintenanceLog {self.id} - {self.title}>"


class AssetAssignment(Base):
    """Check-out/check-in history for asset assignments."""

    __tablename__ = "asset_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)

    # Who/what is it assigned to
    assigned_to_type = Column(String(50), nullable=False)  # technician, work_order
    assigned_to_id = Column(UUID(as_uuid=True), nullable=False)
    assigned_to_name = Column(String(255))

    # Check-out/in timestamps
    checked_out_at = Column(DateTime(timezone=True), server_default=func.now())
    checked_in_at = Column(DateTime(timezone=True), nullable=True)

    # Who checked it out
    checked_out_by_id = Column(UUID(as_uuid=True))
    checked_out_by_name = Column(String(255))

    # Condition tracking
    condition_at_checkout = Column(String(50))
    condition_at_checkin = Column(String(50))

    # Notes
    notes = Column(Text)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AssetAssignment {self.id} - {self.assigned_to_name}>"
