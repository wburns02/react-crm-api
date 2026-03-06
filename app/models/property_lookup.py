"""
Property Lookup model for tank size estimation.

Stores Nashville-area property records (Davidson, Rutherford, Wilson, Williamson)
with enough data to estimate septic tank size from address alone.
"""

import uuid
from sqlalchemy import Column, String, Integer, Float, DateTime, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class PropertyLookup(Base):
    """Property record for tank size estimation."""

    __tablename__ = "property_lookups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Address (normalized for matching)
    address_normalized = Column(String(500), nullable=False, index=True)
    address_raw = Column(String(500))
    city = Column(String(100))
    state = Column(String(2), default="TN")
    zip_code = Column(String(10))
    county = Column(String(100), nullable=False)

    # Property characteristics (varies by source)
    sqft = Column(Integer)                    # TotalFinishedArea (Rutherford)
    acres = Column(Float)                     # Acres (Davidson)
    improvement_value = Column(Integer)       # ImprAppr (Davidson)
    total_value = Column(Integer)             # TotlAppr / TotalValue
    year_built = Column(Integer)              # YearBuilt
    land_use = Column(String(100))            # LUDesc / LandUseCode
    bedrooms = Column(Integer)               # Beds (if available)

    # Septic-specific (Williamson)
    system_type = Column(String(200))         # work_type from permit data
    designation = Column(String(100))         # Single Family, Commercial, etc.

    # Estimation result (pre-computed)
    estimated_tank_gallons = Column(Integer, nullable=False, default=1000)
    estimation_confidence = Column(String(20), default="medium")  # high, medium, low
    estimation_source = Column(String(50))    # sqft, acres_value, system_type, default

    # Metadata
    data_source = Column(String(100), nullable=False)  # davidson_property, rutherford_property, etc.
    source_id = Column(String(100))           # ParID or project_number from source
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_property_lookup_addr_city", "address_normalized", "city"),
        Index("idx_property_lookup_county", "county"),
        Index("idx_property_lookup_zip", "zip_code"),
    )

    def __repr__(self):
        return f"<PropertyLookup {self.address_normalized} {self.city} - {self.estimated_tank_gallons}gal>"
