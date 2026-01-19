"""
Septic permit API endpoints.

Provides:
- Hybrid search (keyword + semantic)
- Single permit retrieval
- Batch ingestion from scrapers
- Dashboard statistics
- Duplicate management
"""

import logging
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session

from app.api.deps import DbSession, CurrentUser
from app.models.septic_permit import (
    SepticPermit, State, County, SepticSystemType, SourcePortal,
    PermitVersion, PermitDuplicate
)
from app.schemas.septic_permit import (
    PermitSearchRequest, PermitSearchResponse, PermitResponse,
    PermitStatsResponse, PermitStatsOverview,
    BatchIngestionRequest, BatchIngestionResponse,
    DuplicatePair, DuplicateResolution, DuplicateResponse,
    StateResponse, CountyResponse, SystemTypeResponse, SourcePortalResponse,
    PermitVersionResponse, PermitHistoryResponse, PermitSummary
)
from app.services.permit_ingestion_service import get_permit_ingestion_service
from app.services.permit_search_service import get_permit_search_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ===== SEARCH ENDPOINTS =====

@router.get("/search", response_model=PermitSearchResponse)
async def search_permits(
    query: Optional[str] = Query(None, min_length=2, max_length=500, description="Search query"),
    state_codes: Optional[str] = Query(None, description="Comma-separated state codes"),
    county_ids: Optional[str] = Query(None, description="Comma-separated county IDs"),
    city: Optional[str] = Query(None),
    zip_code: Optional[str] = Query(None),
    permit_date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    permit_date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    latitude: Optional[float] = Query(None, ge=-90, le=90),
    longitude: Optional[float] = Query(None, ge=-180, le=180),
    radius_miles: Optional[float] = Query(None, ge=0.1, le=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = Query("relevance"),
    sort_order: str = Query("desc"),
    include_inactive: bool = Query(False),
    db: DbSession,
    current_user: CurrentUser
):
    """
    Search septic permits with hybrid keyword + semantic search.

    Supports:
    - Full-text search on address, owner, city, permit number
    - Trigram fuzzy matching on address
    - State/county/city/zip filtering
    - Date range filtering
    - Geo-radius search
    - Pagination and sorting
    """
    try:
        # Parse comma-separated values
        state_list = state_codes.split(',') if state_codes else None
        county_list = [int(c) for c in county_ids.split(',')] if county_ids else None

        # Parse dates
        from datetime import date
        permit_from = date.fromisoformat(permit_date_from) if permit_date_from else None
        permit_to = date.fromisoformat(permit_date_to) if permit_date_to else None

        # Build request
        request = PermitSearchRequest(
            query=query,
            state_codes=state_list,
            county_ids=county_list,
            city=city,
            zip_code=zip_code,
            permit_date_from=permit_from,
            permit_date_to=permit_to,
            latitude=latitude,
            longitude=longitude,
            radius_miles=radius_miles,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            include_inactive=include_inactive
        )

        service = get_permit_search_service(db)
        return service.search(request)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid parameter: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed"
        )


@router.post("/search", response_model=PermitSearchResponse)
async def search_permits_post(
    request: PermitSearchRequest,
    db: DbSession,
    current_user: CurrentUser
):
    """
    Search permits via POST (for complex filter combinations).
    """
    try:
        service = get_permit_search_service(db)
        return service.search(request)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed"
        )


# ===== SINGLE PERMIT =====

@router.get("/{permit_id}", response_model=PermitResponse)
async def get_permit(
    permit_id: UUID,
    db: DbSession,
    current_user: CurrentUser
):
    """Get a single permit by ID with full details."""
    try:
        service = get_permit_search_service(db)
        permit = service.get_permit(permit_id)

        if not permit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Permit {permit_id} not found"
            )

        return permit

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get permit {permit_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve permit"
        )


@router.get("/{permit_id}/history", response_model=PermitHistoryResponse)
async def get_permit_history(
    permit_id: UUID,
    db: DbSession,
    current_user: CurrentUser
):
    """Get version history for a permit."""
    try:
        # Get permit
        permit = db.query(SepticPermit).filter(SepticPermit.id == permit_id).first()
        if not permit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Permit {permit_id} not found"
            )

        # Get versions
        versions = db.query(PermitVersion).filter(
            PermitVersion.permit_id == permit_id
        ).order_by(PermitVersion.version.desc()).all()

        return PermitHistoryResponse(
            permit_id=permit_id,
            current_version=permit.version,
            versions=[
                PermitVersionResponse(
                    id=v.id,
                    permit_id=v.permit_id,
                    version=v.version,
                    changed_fields=v.changed_fields,
                    change_source=v.change_source,
                    change_reason=v.change_reason,
                    created_by=v.created_by,
                    created_at=v.created_at,
                    permit_data=v.permit_data
                )
                for v in versions
            ]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get permit history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve permit history"
        )


# ===== STATISTICS =====

@router.get("/stats/overview", response_model=PermitStatsOverview)
async def get_permit_stats(
    db: DbSession,
    current_user: CurrentUser
):
    """Get dashboard statistics for permits."""
    try:
        service = get_permit_search_service(db)
        return service.get_stats()
    except Exception as e:
        logger.error(f"Failed to get permit stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics"
        )


# ===== BATCH INGESTION =====

@router.post("/batch", response_model=BatchIngestionResponse)
async def ingest_batch(
    request: BatchIngestionRequest,
    db: DbSession,
    current_user: CurrentUser
):
    """
    Ingest a batch of permits from scrapers.

    - Normalizes addresses for deduplication
    - Updates existing records if changed
    - Creates version history for updates
    - Returns statistics on processing
    """
    try:
        if len(request.permits) > 10000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Batch size cannot exceed 10,000 records"
            )

        service = get_permit_ingestion_service(db)
        return service.ingest_batch(request.permits, request.source_portal_code)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch ingestion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Batch ingestion failed"
        )


# ===== DUPLICATES =====

@router.get("/duplicates", response_model=List[DuplicatePair])
async def list_duplicates(
    status_filter: Optional[str] = Query("pending", description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    db: DbSession,
    current_user: CurrentUser
):
    """List potential duplicate permit pairs for review."""
    try:
        query = db.query(PermitDuplicate)

        if status_filter:
            query = query.filter(PermitDuplicate.status == status_filter)

        duplicates = query.order_by(
            PermitDuplicate.confidence_score.desc()
        ).limit(limit).all()

        results = []
        for dup in duplicates:
            # Get both permits
            permit1 = db.query(SepticPermit).filter(SepticPermit.id == dup.permit_id_1).first()
            permit2 = db.query(SepticPermit).filter(SepticPermit.id == dup.permit_id_2).first()

            if permit1 and permit2:
                state1 = db.query(State).filter(State.id == permit1.state_id).first()
                state2 = db.query(State).filter(State.id == permit2.state_id).first()
                county1 = db.query(County).filter(County.id == permit1.county_id).first() if permit1.county_id else None
                county2 = db.query(County).filter(County.id == permit2.county_id).first() if permit2.county_id else None

                results.append(DuplicatePair(
                    id=dup.id,
                    permit_1=PermitSummary(
                        id=permit1.id,
                        permit_number=permit1.permit_number,
                        address=permit1.address,
                        city=permit1.city,
                        state_code=state1.code if state1 else None,
                        county_name=county1.name if county1 else None,
                        owner_name=permit1.owner_name,
                        permit_date=permit1.permit_date,
                        system_type=permit1.system_type_raw
                    ),
                    permit_2=PermitSummary(
                        id=permit2.id,
                        permit_number=permit2.permit_number,
                        address=permit2.address,
                        city=permit2.city,
                        state_code=state2.code if state2 else None,
                        county_name=county2.name if county2 else None,
                        owner_name=permit2.owner_name,
                        permit_date=permit2.permit_date,
                        system_type=permit2.system_type_raw
                    ),
                    detection_method=dup.detection_method,
                    confidence_score=dup.confidence_score or 0.0,
                    matching_fields=dup.matching_fields or [],
                    status=dup.status,
                    created_at=dup.created_at
                ))

        return results

    except Exception as e:
        logger.error(f"Failed to list duplicates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve duplicates"
        )


@router.post("/duplicates/{duplicate_id}/resolve", response_model=DuplicateResponse)
async def resolve_duplicate(
    duplicate_id: UUID,
    resolution: DuplicateResolution,
    db: DbSession,
    current_user: CurrentUser
):
    """Resolve a duplicate pair (merge, reject, or mark as reviewed)."""
    try:
        from datetime import datetime

        dup = db.query(PermitDuplicate).filter(PermitDuplicate.id == duplicate_id).first()
        if not dup:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Duplicate pair {duplicate_id} not found"
            )

        if resolution.action == 'merge':
            if not resolution.canonical_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="canonical_id required for merge action"
                )

            # Mark non-canonical record as inactive
            non_canonical_id = dup.permit_id_2 if resolution.canonical_id == dup.permit_id_1 else dup.permit_id_1
            non_canonical = db.query(SepticPermit).filter(SepticPermit.id == non_canonical_id).first()
            if non_canonical:
                non_canonical.is_active = False
                non_canonical.duplicate_of_id = resolution.canonical_id

            dup.status = 'merged'
            dup.canonical_id = resolution.canonical_id

        elif resolution.action == 'reject':
            dup.status = 'rejected'

        else:  # review
            dup.status = 'reviewed'

        dup.resolved_at = datetime.utcnow()
        dup.resolved_by = str(current_user.id) if hasattr(current_user, 'id') else 'unknown'
        dup.resolution_notes = resolution.notes

        db.commit()

        return DuplicateResponse(
            id=dup.id,
            status=dup.status,
            canonical_id=dup.canonical_id,
            resolved_at=dup.resolved_at,
            message=f"Duplicate {resolution.action}d successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve duplicate: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve duplicate"
        )


# ===== REFERENCE DATA =====

@router.get("/ref/states", response_model=List[StateResponse])
async def list_states(
    db: DbSession,
    current_user: CurrentUser
):
    """List all US states."""
    try:
        states = db.query(State).filter(State.is_active == True).order_by(State.name).all()
        return [
            StateResponse(
                id=s.id,
                code=s.code,
                name=s.name,
                fips_code=s.fips_code,
                region=s.region
            )
            for s in states
        ]
    except Exception as e:
        logger.error(f"Failed to list states: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve states"
        )


@router.get("/ref/counties", response_model=List[CountyResponse])
async def list_counties(
    state_code: Optional[str] = Query(None, description="Filter by state code"),
    db: DbSession,
    current_user: CurrentUser
):
    """List counties, optionally filtered by state."""
    try:
        query = db.query(County).join(State).filter(County.is_active == True)

        if state_code:
            query = query.filter(State.code == state_code.upper())

        counties = query.order_by(County.name).all()
        return [
            CountyResponse(
                id=c.id,
                state_id=c.state_id,
                name=c.name,
                normalized_name=c.normalized_name,
                fips_code=c.fips_code,
                population=c.population,
                state_code=c.state.code if c.state else None
            )
            for c in counties
        ]
    except Exception as e:
        logger.error(f"Failed to list counties: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve counties"
        )


@router.get("/ref/system-types", response_model=List[SystemTypeResponse])
async def list_system_types(
    db: DbSession,
    current_user: CurrentUser
):
    """List septic system types."""
    try:
        types = db.query(SepticSystemType).filter(
            SepticSystemType.is_active == True
        ).order_by(SepticSystemType.name).all()

        return [
            SystemTypeResponse(
                id=t.id,
                code=t.code,
                name=t.name,
                category=t.category,
                description=t.description
            )
            for t in types
        ]
    except Exception as e:
        logger.error(f"Failed to list system types: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system types"
        )


@router.get("/ref/portals", response_model=List[SourcePortalResponse])
async def list_source_portals(
    db: DbSession,
    current_user: CurrentUser
):
    """List data source portals."""
    try:
        portals = db.query(SourcePortal).filter(
            SourcePortal.is_active == True
        ).order_by(SourcePortal.name).all()

        return [
            SourcePortalResponse(
                id=p.id,
                code=p.code,
                name=p.name,
                state_id=p.state_id,
                platform=p.platform,
                base_url=p.base_url,
                is_active=p.is_active,
                last_scraped_at=p.last_scraped_at,
                total_records_scraped=p.total_records_scraped
            )
            for p in portals
        ]
    except Exception as e:
        logger.error(f"Failed to list portals: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve source portals"
        )
