"""
Database models for National Septic Permit OCR system.

Stores 7M+ septic permit records with deduplication support,
hybrid search (keyword + semantic), and version tracking.
"""

import uuid
import hashlib
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Date,
    Float,
    Integer,
    SmallInteger,
    String,
    Text,
    JSON,
    ForeignKey,
    Index,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, TSVECTOR
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


# ===== REFERENCE TABLES =====


class State(Base):
    """US State reference table."""

    __tablename__ = "states"

    id = Column(Integer, primary_key=True)
    code = Column(String(2), unique=True, nullable=False, index=True)  # 'TX', 'FL'
    name = Column(String(100), nullable=False)
    fips_code = Column(String(2), nullable=True)
    region = Column(String(50), nullable=True)  # 'South', 'Northeast'
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    counties = relationship("County", back_populates="state", cascade="all, delete-orphan")
    permits = relationship("SepticPermit", back_populates="state")

    def __repr__(self):
        return f"<State(code={self.code}, name={self.name})>"


class County(Base):
    """County reference table for all US counties."""

    __tablename__ = "counties"

    id = Column(Integer, primary_key=True)
    state_id = Column(Integer, ForeignKey("states.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    normalized_name = Column(String(100), nullable=False)  # Uppercase, no 'County'
    fips_code = Column(String(5), nullable=True)  # Full state+county FIPS
    population = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    state = relationship("State", back_populates="counties")
    permits = relationship("SepticPermit", back_populates="county")

    __table_args__ = (
        UniqueConstraint("state_id", "normalized_name", name="uq_county_state_name"),
        Index("idx_counties_state", "state_id"),
        Index("idx_counties_normalized_name", "normalized_name"),
    )

    def __repr__(self):
        return f"<County(name={self.name}, state_id={self.state_id})>"


class SepticSystemType(Base):
    """Septic system type enumeration."""

    __tablename__ = "septic_system_types"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)  # 'CONVENTIONAL', 'ATU'
    name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=True)  # 'Standard', 'Alternative'
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<SepticSystemType(code={self.code})>"


class SourcePortal(Base):
    """Data source portal tracking for scraped data."""

    __tablename__ = "source_portals"

    id = Column(Integer, primary_key=True)
    code = Column(String(100), unique=True, nullable=False)  # 'florida_ebridge'
    name = Column(String(200), nullable=False)
    state_id = Column(Integer, ForeignKey("states.id"), nullable=True)
    platform = Column(String(50), nullable=True)  # 'accela', 'energov', 'custom'
    base_url = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_scraped_at = Column(DateTime(timezone=True), nullable=True)
    total_records_scraped = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<SourcePortal(code={self.code}, name={self.name})>"


# ===== MAIN PERMIT TABLE =====


class SepticPermit(Base):
    """
    Main septic permit records table (7M+ records).

    Features:
    - UUID primary key for distributed writes
    - Address normalization and deduplication via hash
    - Full-text search via TSVECTOR
    - Semantic search via embedding vector
    - Version tracking for updates
    """

    __tablename__ = "septic_permits"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ===== CORE IDENTIFICATION =====
    permit_number = Column(String(100), nullable=True, index=True)
    state_id = Column(Integer, ForeignKey("states.id"), nullable=False, index=True)
    county_id = Column(Integer, ForeignKey("counties.id"), nullable=True, index=True)

    # ===== ADDRESS FIELDS (for deduplication) =====
    address = Column(Text, nullable=True)  # Original address as scraped
    address_normalized = Column(Text, nullable=True)  # Normalized version
    address_hash = Column(String(64), nullable=True, index=True)  # SHA256 hash
    city = Column(String(100), nullable=True, index=True)
    zip_code = Column(String(20), nullable=True, index=True)

    # ===== PARCEL AND GEO =====
    parcel_number = Column(String(100), nullable=True, index=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # ===== OWNER/APPLICANT INFORMATION =====
    owner_name = Column(String(255), nullable=True)
    owner_name_normalized = Column(String(255), nullable=True)
    applicant_name = Column(String(255), nullable=True)
    contractor_name = Column(String(255), nullable=True)

    # ===== DATES =====
    install_date = Column(Date, nullable=True, index=True)
    permit_date = Column(Date, nullable=True, index=True)
    expiration_date = Column(Date, nullable=True)

    # ===== SYSTEM SPECIFICATIONS =====
    system_type_id = Column(Integer, ForeignKey("septic_system_types.id"), nullable=True)
    system_type_raw = Column(String(200), nullable=True)  # Original value before mapping
    tank_size_gallons = Column(Integer, nullable=True)
    drainfield_size_sqft = Column(Integer, nullable=True)
    bedrooms = Column(SmallInteger, nullable=True)
    daily_flow_gpd = Column(Integer, nullable=True)  # Gallons per day

    # ===== DOCUMENT LINKS =====
    pdf_url = Column(Text, nullable=True)
    permit_url = Column(Text, nullable=True)

    # ===== SOURCE TRACKING =====
    source_portal_id = Column(Integer, ForeignKey("source_portals.id"), nullable=True)
    source_portal_code = Column(String(100), nullable=True)  # Denormalized for fast access
    scraped_at = Column(DateTime(timezone=True), nullable=False)

    # ===== RAW DATA STORAGE =====
    raw_data = Column(JSON, nullable=True)  # Original scraped data

    # ===== SEARCH OPTIMIZATION =====
    # Semantic search embedding (384 dimensions for all-MiniLM-L6-v2)
    # Note: Stored as JSON for SQLite test compatibility
    embedding = Column(JSON, nullable=True)
    embedding_model = Column(String(100), nullable=True)
    embedding_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Full-text search vector (PostgreSQL tsvector, auto-populated by trigger)
    search_vector = Column(TSVECTOR, nullable=True)

    # Combined searchable text for embedding generation
    searchable_text = Column(Text, nullable=True)

    # ===== RECORD METADATA =====
    is_active = Column(Boolean, default=True, nullable=False)
    data_quality_score = Column(SmallInteger, nullable=True)  # 0-100
    duplicate_of_id = Column(UUID(as_uuid=True), nullable=True)  # Points to canonical if dupe
    version = Column(Integer, default=1, nullable=False)
    record_hash = Column(String(64), nullable=True)  # Hash of all fields for change detection

    # ===== TIMESTAMPS =====
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # ===== RELATIONSHIPS =====
    state = relationship("State", back_populates="permits")
    county = relationship("County", back_populates="permits")
    system_type = relationship("SepticSystemType")
    source_portal = relationship("SourcePortal")
    versions = relationship("PermitVersion", back_populates="permit", cascade="all, delete-orphan")

    # ===== INDEXES AND CONSTRAINTS =====
    __table_args__ = (
        # Primary deduplication: normalized address + county + state
        Index(
            "idx_septic_permits_dedup_address",
            "address_hash",
            "county_id",
            "state_id",
            unique=True,
            postgresql_where=((Column("address_hash").isnot(None)) & (Column("is_active") == True)),
        ),
        # Secondary deduplication: permit_number + state
        Index(
            "idx_septic_permits_dedup_permit",
            "permit_number",
            "state_id",
            unique=True,
            postgresql_where=((Column("permit_number").isnot(None)) & (Column("is_active") == True)),
        ),
        # Composite indexes for common queries
        Index("idx_septic_permits_state_county", "state_id", "county_id"),
        Index("idx_septic_permits_state_county_date", "state_id", "county_id", "permit_date"),
        Index("idx_septic_permits_scraped_at", "scraped_at"),
        # Full-text search index (GIN)
        Index("idx_septic_permits_search_vector", "search_vector", postgresql_using="gin"),
    )

    def __repr__(self):
        return f"<SepticPermit(id={self.id}, permit={self.permit_number}, state_id={self.state_id})>"

    @staticmethod
    def compute_address_hash(
        normalized_address: Optional[str], county_name: Optional[str], state_code: Optional[str]
    ) -> Optional[str]:
        """
        Compute SHA256 hash of normalized address + county + state.
        Used for deduplication unique constraint.
        """
        if not normalized_address:
            return None

        components = [normalized_address or "", (county_name or "").upper(), (state_code or "").upper()]
        composite_key = "|".join(components)
        return hashlib.sha256(composite_key.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_record_hash(data: dict) -> str:
        """
        Compute SHA256 hash of full record for change detection.
        """
        import json

        # Exclude metadata fields
        exclude_keys = {
            "id",
            "created_at",
            "updated_at",
            "version",
            "record_hash",
            "search_vector",
            "embedding",
            "embedding_updated_at",
        }
        filtered_data = {k: v for k, v in data.items() if k not in exclude_keys}
        serialized = json.dumps(filtered_data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ===== VERSION HISTORY TABLE =====


class PermitVersion(Base):
    """
    Version history for permit records (audit trail).
    Created when records are updated with newer data from scrapers.
    """

    __tablename__ = "permit_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    permit_id = Column(
        UUID(as_uuid=True), ForeignKey("septic_permits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version = Column(Integer, nullable=False)

    # Snapshot of record state at this version
    permit_data = Column(JSON, nullable=False)  # Full record snapshot

    # Change tracking
    changed_fields = Column(JSON, nullable=True)  # List of fields that changed
    change_source = Column(String(50), nullable=False)  # 'scraper', 'manual', 'merge', 'api'
    change_reason = Column(Text, nullable=True)

    # Source information
    source_portal_id = Column(Integer, ForeignKey("source_portals.id"), nullable=True)
    scraped_at = Column(DateTime(timezone=True), nullable=True)

    # Attribution
    created_by = Column(String(255), nullable=True)  # User ID or 'system'
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    permit = relationship("SepticPermit", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("permit_id", "version", name="uq_permit_version"),
        Index("idx_permit_versions_permit", "permit_id"),
        Index("idx_permit_versions_created", "created_at"),
    )

    def __repr__(self):
        return f"<PermitVersion(permit_id={self.permit_id}, version={self.version})>"


# ===== DUPLICATE TRACKING TABLE =====


class PermitDuplicate(Base):
    """
    Track identified duplicate permit pairs for review and resolution.
    """

    __tablename__ = "permit_duplicates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # The two permits being compared
    permit_id_1 = Column(UUID(as_uuid=True), ForeignKey("septic_permits.id"), nullable=False, index=True)
    permit_id_2 = Column(UUID(as_uuid=True), ForeignKey("septic_permits.id"), nullable=False, index=True)

    # Duplicate detection details
    detection_method = Column(String(50), nullable=False)  # 'address_hash', 'fuzzy_match', 'manual'
    confidence_score = Column(Float, nullable=True)  # 0-100
    matching_fields = Column(JSON, nullable=True)  # Which fields matched

    # Resolution status
    status = Column(String(20), default="pending", nullable=False)  # pending, merged, rejected, reviewed
    canonical_id = Column(UUID(as_uuid=True), nullable=True)  # Which record is the "master"
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(255), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("permit_id_1", "permit_id_2", name="uq_permit_duplicate_pair"),
        CheckConstraint("permit_id_1 < permit_id_2", name="ck_permit_id_ordering"),
        Index("idx_permit_duplicates_permit1", "permit_id_1"),
        Index("idx_permit_duplicates_permit2", "permit_id_2"),
        Index("idx_permit_duplicates_status", "status"),
    )

    def __repr__(self):
        return f"<PermitDuplicate(id={self.id}, status={self.status})>"


# ===== IMPORT BATCH TRACKING =====


class PermitImportBatch(Base):
    """
    Track batch import operations from scrapers.
    """

    __tablename__ = "permit_import_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Source info
    source_portal_id = Column(Integer, ForeignKey("source_portals.id"), nullable=True)
    source_name = Column(String(100), nullable=False)

    # Batch statistics
    total_records = Column(Integer, nullable=False)
    inserted = Column(Integer, default=0)
    updated = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    errors = Column(Integer, default=0)

    # Processing info
    status = Column(String(20), default="pending", nullable=False)  # pending, processing, completed, failed
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    processing_time_seconds = Column(Float, nullable=True)

    # Error details
    error_details = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<PermitImportBatch(id={self.id}, source={self.source_name}, status={self.status})>"
