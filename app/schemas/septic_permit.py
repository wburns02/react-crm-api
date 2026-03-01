"""
Pydantic schemas for Septic Permit API endpoints.

These schemas support:
- Permit ingestion from scrapers
- Hybrid search (keyword + semantic)
- Duplicate management
- Dashboard statistics
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


# ===== ENUMS / LITERALS =====

DuplicateStatus = Literal["pending", "merged", "rejected", "reviewed"]
DuplicateDetectionMethod = Literal["address_hash", "fuzzy_match", "semantic", "manual"]
ImportBatchStatus = Literal["pending", "processing", "completed", "failed"]
ChangeSource = Literal["scraper", "manual", "merge", "api"]


# ===== REFERENCE DATA SCHEMAS =====


class StateBase(BaseModel):
    """State reference data."""

    code: str = Field(..., max_length=2, description="2-letter state code")
    name: str = Field(..., max_length=100)
    fips_code: Optional[str] = None
    region: Optional[str] = None


class StateResponse(StateBase):
    """State with ID."""

    id: int

    class Config:
        from_attributes = True


class CountyBase(BaseModel):
    """County reference data."""

    name: str = Field(..., max_length=100)
    normalized_name: Optional[str] = None
    fips_code: Optional[str] = None
    population: Optional[int] = None


class CountyResponse(CountyBase):
    """County with ID and state info."""

    id: int
    state_id: int
    state_code: Optional[str] = None

    class Config:
        from_attributes = True


class SystemTypeBase(BaseModel):
    """Septic system type."""

    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=200)
    category: Optional[str] = None
    description: Optional[str] = None


class SystemTypeResponse(SystemTypeBase):
    """System type with ID."""

    id: int

    class Config:
        from_attributes = True


class SourcePortalBase(BaseModel):
    """Data source portal."""

    code: str = Field(..., max_length=100)
    name: str = Field(..., max_length=200)
    platform: Optional[str] = None
    base_url: Optional[str] = None


class SourcePortalResponse(SourcePortalBase):
    """Source portal with stats."""

    id: int
    state_id: Optional[int] = None
    is_active: bool = True
    last_scraped_at: Optional[datetime] = None
    total_records_scraped: int = 0

    class Config:
        from_attributes = True


# ===== PERMIT SCHEMAS =====


class PermitBase(BaseModel):
    """Base permit fields (for creation/update)."""

    # Identification
    permit_number: Optional[str] = Field(None, max_length=100)
    state_code: str = Field(..., max_length=2, description="2-letter state code")
    county_name: Optional[str] = Field(None, max_length=100)

    # Address
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    zip_code: Optional[str] = Field(None, max_length=20)

    # Parcel/Geo
    parcel_number: Optional[str] = Field(None, max_length=100)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)

    # Owner/Applicant
    owner_name: Optional[str] = Field(None, max_length=255)
    applicant_name: Optional[str] = Field(None, max_length=255)
    contractor_name: Optional[str] = Field(None, max_length=255)

    # Dates
    install_date: Optional[date] = None
    permit_date: Optional[date] = None
    expiration_date: Optional[date] = None

    # System specs
    system_type: Optional[str] = Field(None, max_length=200)
    tank_size_gallons: Optional[int] = Field(None, ge=0)
    drainfield_size_sqft: Optional[int] = Field(None, ge=0)
    bedrooms: Optional[int] = Field(None, ge=0, le=50)
    daily_flow_gpd: Optional[int] = Field(None, ge=0)

    # Documents
    pdf_url: Optional[str] = None
    permit_url: Optional[str] = None

    # Source tracking
    source_portal_code: Optional[str] = Field(None, max_length=100)
    scraped_at: Optional[datetime] = None

    # Raw data
    raw_data: Optional[Dict[str, Any]] = None


class PermitCreate(PermitBase):
    """Create a new permit (from scraper ingestion)."""

    scraped_at: datetime = Field(default_factory=datetime.utcnow)


class PermitUpdate(BaseModel):
    """Update an existing permit."""

    permit_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None
    parcel_number: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    owner_name: Optional[str] = None
    applicant_name: Optional[str] = None
    contractor_name: Optional[str] = None
    install_date: Optional[date] = None
    permit_date: Optional[date] = None
    expiration_date: Optional[date] = None
    system_type: Optional[str] = None
    tank_size_gallons: Optional[int] = None
    drainfield_size_sqft: Optional[int] = None
    bedrooms: Optional[int] = None
    daily_flow_gpd: Optional[int] = None
    pdf_url: Optional[str] = None
    permit_url: Optional[str] = None


class PermitResponse(BaseModel):
    """Full permit response with all fields."""

    id: UUID
    permit_number: Optional[str] = None

    # Customer linking
    customer_id: Optional[UUID] = None

    # Location
    state_id: int
    state_code: Optional[str] = None
    state_name: Optional[str] = None
    county_id: Optional[int] = None
    county_name: Optional[str] = None

    # Address
    address: Optional[str] = None
    address_normalized: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None

    # Parcel/Geo
    parcel_number: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Owner/Applicant
    owner_name: Optional[str] = None
    applicant_name: Optional[str] = None
    contractor_name: Optional[str] = None

    # Dates
    install_date: Optional[date] = None
    permit_date: Optional[date] = None
    expiration_date: Optional[date] = None

    # System specs
    system_type_id: Optional[int] = None
    system_type_raw: Optional[str] = None
    system_type_name: Optional[str] = None
    tank_size_gallons: Optional[int] = None
    drainfield_size_sqft: Optional[int] = None
    bedrooms: Optional[int] = None
    daily_flow_gpd: Optional[int] = None

    # Documents
    pdf_url: Optional[str] = None
    permit_url: Optional[str] = None

    # Source tracking
    source_portal_id: Optional[int] = None
    source_portal_code: Optional[str] = None
    source_portal_name: Optional[str] = None
    scraped_at: Optional[datetime] = None

    # Metadata
    is_active: bool = True
    data_quality_score: Optional[int] = None
    version: int = 1
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PermitSummary(BaseModel):
    """Compact permit summary for list views."""

    id: UUID
    permit_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state_code: Optional[str] = None
    county_name: Optional[str] = None
    owner_name: Optional[str] = None
    permit_date: Optional[date] = None
    system_type: Optional[str] = None
    has_property: bool = False  # Whether permit is linked to a property

    class Config:
        from_attributes = True


# ===== SEARCH SCHEMAS =====


class PermitSearchRequest(BaseModel):
    """Search parameters for permit search."""

    # Text search
    query: Optional[str] = Field(None, min_length=2, max_length=500, description="Search query for hybrid search")

    # Filters
    state_codes: Optional[List[str]] = Field(None, description="Filter by state codes")
    county_ids: Optional[List[int]] = Field(None, description="Filter by county IDs")
    city: Optional[str] = None
    zip_code: Optional[str] = None
    system_type_ids: Optional[List[int]] = None

    # Date filters
    permit_date_from: Optional[date] = None
    permit_date_to: Optional[date] = None
    install_date_from: Optional[date] = None
    install_date_to: Optional[date] = None

    # Geo search
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    radius_miles: Optional[float] = Field(None, ge=0.1, le=100)

    # Pagination
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=100)

    # Sorting
    sort_by: str = Field("relevance", description="Sort field: relevance, permit_date, address, owner_name")
    sort_order: str = Field("desc", description="Sort direction: asc, desc")

    # Search options
    include_inactive: bool = Field(False, description="Include soft-deleted records")
    semantic_weight: float = Field(0.5, ge=0, le=1, description="Weight for semantic vs keyword search")


class SearchHighlight(BaseModel):
    """Search result highlighting."""

    field: str
    fragments: List[str]


class PermitSearchResult(BaseModel):
    """Single search result with score and highlighting."""

    permit: PermitSummary
    score: float = Field(..., description="Combined relevance score")
    keyword_score: Optional[float] = None
    semantic_score: Optional[float] = None
    highlights: List[SearchHighlight] = []


class PermitSearchResponse(BaseModel):
    """Paginated search results."""

    results: List[PermitSearchResult] = []
    total: int = 0
    page: int = 1
    page_size: int = 25
    total_pages: int = 0
    query: Optional[str] = None
    execution_time_ms: float = 0.0

    # Facets for filtering UI
    state_facets: Optional[List[Dict[str, Any]]] = None
    county_facets: Optional[List[Dict[str, Any]]] = None
    system_type_facets: Optional[List[Dict[str, Any]]] = None


# ===== BATCH INGESTION SCHEMAS =====


class BatchIngestionRequest(BaseModel):
    """Request to ingest a batch of permits."""

    source_portal_code: str = Field(..., max_length=100)
    permits: List[PermitCreate] = Field(..., max_items=10000)


class BatchIngestionStats(BaseModel):
    """Statistics from batch ingestion."""

    batch_id: UUID
    source_portal_code: str
    total_records: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    duplicate_candidates: int = 0
    processing_time_seconds: float = 0.0
    error_details: Optional[List[Dict[str, Any]]] = None


class BatchIngestionResponse(BaseModel):
    """Response from batch ingestion."""

    status: ImportBatchStatus
    stats: BatchIngestionStats
    message: str = ""


# ===== DUPLICATE MANAGEMENT SCHEMAS =====


class DuplicatePair(BaseModel):
    """A pair of potential duplicate permits."""

    id: UUID
    permit_1: PermitSummary
    permit_2: PermitSummary
    detection_method: DuplicateDetectionMethod
    confidence_score: float = Field(..., ge=0, le=100)
    matching_fields: List[str] = []
    status: DuplicateStatus = "pending"
    created_at: datetime


class DuplicateResolution(BaseModel):
    """Request to resolve a duplicate pair."""

    action: Literal["merge", "reject", "review"]
    canonical_id: Optional[UUID] = Field(None, description="ID of the record to keep when merging")
    notes: Optional[str] = None


class DuplicateResponse(BaseModel):
    """Response after resolving duplicate."""

    id: UUID
    status: DuplicateStatus
    canonical_id: Optional[UUID] = None
    resolved_at: datetime
    message: str = ""


# ===== STATISTICS SCHEMAS =====


class PermitStatsByState(BaseModel):
    """Permit counts by state."""

    state_code: str
    state_name: str
    total_permits: int
    active_permits: int
    permits_this_year: int
    avg_data_quality: Optional[float] = None


class PermitStatsByCounty(BaseModel):
    """Permit counts by county."""

    county_id: int
    county_name: str
    state_code: str
    total_permits: int
    permits_this_year: int


class PermitStatsByYear(BaseModel):
    """Permit counts by year."""

    year: int
    total_permits: int
    by_state: Optional[Dict[str, int]] = None


class PermitStatsOverview(BaseModel):
    """Dashboard overview statistics."""

    total_permits: int = 0
    total_states: int = 0
    total_counties: int = 0
    total_source_portals: int = 0

    permits_this_month: int = 0
    permits_this_year: int = 0

    avg_data_quality_score: float = 0.0
    duplicate_pending_count: int = 0

    top_states: List[PermitStatsByState] = []
    permits_by_year: List[PermitStatsByYear] = []

    last_updated: datetime = Field(default_factory=datetime.utcnow)


class PermitStatsResponse(BaseModel):
    """Response for permit statistics endpoint."""

    overview: PermitStatsOverview
    by_state: List[PermitStatsByState] = []
    by_county: Optional[List[PermitStatsByCounty]] = None

    class Config:
        from_attributes = True


# ===== VERSION HISTORY SCHEMAS =====


class PermitVersionResponse(BaseModel):
    """Version history entry for a permit."""

    id: UUID
    permit_id: UUID
    version: int
    changed_fields: Optional[List[str]] = None
    change_source: ChangeSource
    change_reason: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime

    # Snapshot data available on request
    permit_data: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class PermitHistoryResponse(BaseModel):
    """Full version history for a permit."""

    permit_id: UUID
    current_version: int
    versions: List[PermitVersionResponse] = []


# ===== PERMIT-CUSTOMER LINKING SCHEMAS =====


class PermitLinkRequest(BaseModel):
    """Request to manually link a permit to a customer."""
    customer_id: UUID


class PermitLinkResponse(BaseModel):
    """Response after linking a permit to a customer."""
    permit_id: UUID
    customer_id: UUID
    message: str = ""


class BatchLinkResponse(BaseModel):
    """Response from batch auto-linking."""
    processed: int = 0
    linked_high: int = 0
    linked_medium: int = 0
    skipped: int = 0
    errors: int = 0


class PermitCustomerSummary(BaseModel):
    """Permit summary for customer detail views."""
    id: UUID
    permit_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    county_name: Optional[str] = None
    owner_name: Optional[str] = None
    contractor_name: Optional[str] = None
    permit_date: Optional[date] = None
    install_date: Optional[date] = None
    system_type_raw: Optional[str] = None
    tank_size_gallons: Optional[int] = None
    drainfield_size_sqft: Optional[int] = None
    bedrooms: Optional[int] = None
    raw_data: Optional[Dict[str, Any]] = None
    data_quality_score: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CustomerPermitsResponse(BaseModel):
    """All permits linked to a customer."""
    customer_id: UUID
    permits: List[PermitCustomerSummary] = []
    total: int = 0


class ProspectRecord(BaseModel):
    """A permit holder not yet in the CRM - potential prospect."""
    permit_id: UUID
    owner_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    county_name: Optional[str] = None
    phone: Optional[str] = None
    system_type: Optional[str] = None
    permit_date: Optional[date] = None
    system_age_years: Optional[int] = None


class ProspectsResponse(BaseModel):
    """Paginated list of prospects from permit data."""
    prospects: List[ProspectRecord] = []
    total: int = 0
    page: int = 1
    page_size: int = 50
