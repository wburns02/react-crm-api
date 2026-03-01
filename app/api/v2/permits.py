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
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, desc

from app.api.deps import DbSession, CurrentUser
from app.models.septic_permit import (
    SepticPermit,
    State,
    County,
    SepticSystemType,
    SourcePortal,
    PermitVersion,
    PermitDuplicate,
)
from app.schemas.septic_permit import (
    PermitSearchRequest,
    PermitSearchResponse,
    PermitResponse,
    PermitStatsOverview,
    BatchIngestionRequest,
    BatchIngestionResponse,
    DuplicatePair,
    DuplicateResolution,
    DuplicateResponse,
    StateResponse,
    CountyResponse,
    SystemTypeResponse,
    SourcePortalResponse,
    PermitVersionResponse,
    PermitHistoryResponse,
    PermitSummary,
    PermitLinkResponse,
    BatchLinkResponse,
    PermitCustomerSummary,
    CustomerPermitsResponse,
    ProspectRecord,
    ProspectsResponse,
)
from app.models.customer import Customer
from app.services.permit_ingestion_service import get_permit_ingestion_service
from app.services.permit_search_service import get_permit_search_service
from app.services.permit_customer_linker import find_customer_for_permit, batch_link_permits, normalize_address

logger = logging.getLogger(__name__)

router = APIRouter()


# ===== SEARCH ENDPOINTS =====


@router.get("/search", response_model=PermitSearchResponse)
async def search_permits(
    db: DbSession,
    current_user: CurrentUser,
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
        state_list = state_codes.split(",") if state_codes else None
        county_list = [int(c) for c in county_ids.split(",")] if county_ids else None

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
            include_inactive=include_inactive,
        )

        service = get_permit_search_service(db)
        return await service.search(request)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid parameter: {str(e)}")
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Search failed")


@router.post("/search", response_model=PermitSearchResponse)
async def search_permits_post(request: PermitSearchRequest, db: DbSession, current_user: CurrentUser):
    """
    Search permits via POST (for complex filter combinations).
    """
    try:
        service = get_permit_search_service(db)
        return await service.search(request)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Search failed")


# ===== PERMIT LOOKUP =====


@router.get("/lookup")
async def lookup_permits(
    db: DbSession,
    current_user: CurrentUser,
    address: Optional[str] = Query(None, description="Address to search"),
    phone: Optional[str] = Query(None, description="Phone number to search"),
):
    """
    Find permits by address or phone number.
    Used for auto-fill when creating customers.
    """
    try:
        from app.services.permit_customer_linker import normalize_address, normalize_phone

        results = []

        if address:
            normalized = normalize_address(address)
            if normalized:
                stmt = (
                    select(SepticPermit, State, County)
                    .outerjoin(State, SepticPermit.state_id == State.id)
                    .outerjoin(County, SepticPermit.county_id == County.id)
                    .where(SepticPermit.is_active == True)
                    .limit(20)
                )
                result = await db.execute(stmt)
                rows = result.all()
                for permit, state, county in rows:
                    permit_addr = normalize_address(permit.address_normalized or permit.address)
                    if permit_addr and normalized in permit_addr:
                        results.append({
                            "id": str(permit.id),
                            "permit_number": permit.permit_number,
                            "address": permit.address,
                            "city": permit.city,
                            "state_code": state.code if state else None,
                            "county_name": county.name if county else None,
                            "owner_name": permit.owner_name,
                            "contractor_name": permit.contractor_name,
                            "permit_date": str(permit.permit_date) if permit.permit_date else None,
                            "install_date": str(permit.install_date) if permit.install_date else None,
                            "system_type": permit.system_type_raw,
                            "tank_size_gallons": permit.tank_size_gallons,
                            "raw_data": permit.raw_data,
                        })

                # If no results from in-memory filtering, try SQL ILIKE
                if not results:
                    like_pattern = f"%{address.strip()}%"
                    stmt = (
                        select(SepticPermit, State, County)
                        .outerjoin(State, SepticPermit.state_id == State.id)
                        .outerjoin(County, SepticPermit.county_id == County.id)
                        .where(
                            SepticPermit.is_active == True,
                            SepticPermit.address.ilike(like_pattern),
                        )
                        .limit(10)
                    )
                    result = await db.execute(stmt)
                    rows = result.all()
                    for permit, state, county in rows:
                        results.append({
                            "id": str(permit.id),
                            "permit_number": permit.permit_number,
                            "address": permit.address,
                            "city": permit.city,
                            "state_code": state.code if state else None,
                            "county_name": county.name if county else None,
                            "owner_name": permit.owner_name,
                            "contractor_name": permit.contractor_name,
                            "permit_date": str(permit.permit_date) if permit.permit_date else None,
                            "install_date": str(permit.install_date) if permit.install_date else None,
                            "system_type": permit.system_type_raw,
                            "tank_size_gallons": permit.tank_size_gallons,
                            "raw_data": permit.raw_data,
                        })

        if phone:
            from app.services.permit_customer_linker import normalize_phone
            norm_phone = normalize_phone(phone)
            if norm_phone:
                # Search raw_data for phone matches
                stmt = (
                    select(SepticPermit, State, County)
                    .outerjoin(State, SepticPermit.state_id == State.id)
                    .outerjoin(County, SepticPermit.county_id == County.id)
                    .where(
                        SepticPermit.is_active == True,
                        SepticPermit.raw_data.isnot(None),
                    )
                    .limit(100)
                )
                result = await db.execute(stmt)
                rows = result.all()
                for permit, state, county in rows:
                    if permit.raw_data and isinstance(permit.raw_data, dict):
                        permit_phone = normalize_phone(permit.raw_data.get("owner_phone"))
                        if permit_phone == norm_phone:
                            results.append({
                                "id": str(permit.id),
                                "permit_number": permit.permit_number,
                                "address": permit.address,
                                "city": permit.city,
                                "state_code": state.code if state else None,
                                "county_name": county.name if county else None,
                                "owner_name": permit.owner_name,
                                "contractor_name": permit.contractor_name,
                                "permit_date": str(permit.permit_date) if permit.permit_date else None,
                                "install_date": str(permit.install_date) if permit.install_date else None,
                                "system_type": permit.system_type_raw,
                                "tank_size_gallons": permit.tank_size_gallons,
                                "raw_data": permit.raw_data,
                            })

        return {"results": results, "total": len(results)}

    except Exception as e:
        logger.error(f"Permit lookup failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Permit lookup failed")


@router.get("/customer/{customer_id}", response_model=CustomerPermitsResponse)
async def get_customer_permits(customer_id: UUID, db: DbSession, current_user: CurrentUser):
    """Get all permits linked to a customer."""
    try:
        # Verify customer exists
        cust_result = await db.execute(select(Customer).where(Customer.id == customer_id))
        customer = cust_result.scalar_one_or_none()
        if not customer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {customer_id} not found")

        # Get linked permits
        stmt = (
            select(SepticPermit, County)
            .outerjoin(County, SepticPermit.county_id == County.id)
            .where(
                SepticPermit.customer_id == customer_id,
                SepticPermit.is_active == True,
            )
            .order_by(desc(SepticPermit.permit_date))
        )
        result = await db.execute(stmt)
        rows = result.all()

        permits = []
        for permit, county in rows:
            permits.append(PermitCustomerSummary(
                id=permit.id,
                permit_number=permit.permit_number,
                address=permit.address,
                city=permit.city,
                county_name=county.name if county else None,
                owner_name=permit.owner_name,
                contractor_name=permit.contractor_name,
                permit_date=permit.permit_date,
                install_date=permit.install_date,
                system_type_raw=permit.system_type_raw,
                tank_size_gallons=permit.tank_size_gallons,
                drainfield_size_sqft=permit.drainfield_size_sqft,
                bedrooms=permit.bedrooms,
                raw_data=permit.raw_data,
                data_quality_score=permit.data_quality_score,
                created_at=permit.created_at,
            ))

        return CustomerPermitsResponse(
            customer_id=customer_id,
            permits=permits,
            total=len(permits),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get customer permits: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve customer permits")


@router.post("/batch-link", response_model=BatchLinkResponse)
async def run_batch_link(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(1000, ge=1, le=10000),
    include_medium: bool = Query(False, description="Also auto-link medium confidence matches"),
):
    """Run auto-linking on unlinked permits."""
    try:
        stats = await batch_link_permits(db, limit=limit, auto_link_only=not include_medium)
        return BatchLinkResponse(**stats)
    except Exception as e:
        logger.error(f"Batch linking failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Batch linking failed")


@router.get("/prospects", response_model=ProspectsResponse)
async def get_prospects(
    db: DbSession,
    current_user: CurrentUser,
    county: Optional[str] = Query(None, description="Filter by county name"),
    system_type: Optional[str] = Query(None, description="Filter by system type"),
    min_age: Optional[int] = Query(None, ge=0, description="Minimum system age in years"),
    max_age: Optional[int] = Query(None, ge=0, description="Maximum system age in years"),
    has_phone: Optional[bool] = Query(None, description="Only show records with phone numbers"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """
    Get permit holders NOT yet in the CRM as prospects.
    Used by outbound reps to build targeted call lists.
    """
    try:
        from datetime import date as date_type

        stmt = (
            select(SepticPermit, County)
            .outerjoin(County, SepticPermit.county_id == County.id)
            .where(
                SepticPermit.customer_id.is_(None),
                SepticPermit.is_active == True,
                SepticPermit.owner_name.isnot(None),
            )
        )

        # Apply filters
        if county:
            stmt = stmt.where(County.name.ilike(f"%{county}%"))
        if system_type:
            stmt = stmt.where(SepticPermit.system_type_raw.ilike(f"%{system_type}%"))
        if min_age is not None:
            cutoff = date_type(date_type.today().year - min_age, 1, 1)
            stmt = stmt.where(SepticPermit.permit_date <= cutoff)
        if max_age is not None:
            cutoff = date_type(date_type.today().year - max_age, 1, 1)
            stmt = stmt.where(SepticPermit.permit_date >= cutoff)

        # Count total
        from sqlalchemy import func as sqlfunc
        count_stmt = select(sqlfunc.count()).select_from(stmt.subquery())
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Paginate
        stmt = stmt.order_by(desc(SepticPermit.permit_date))
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(stmt)
        rows = result.all()

        today = date_type.today()
        prospects = []
        for permit, county_obj in rows:
            # Filter by has_phone if requested
            phone = None
            if permit.raw_data and isinstance(permit.raw_data, dict):
                phone = permit.raw_data.get("owner_phone")
            if has_phone and not phone:
                continue

            age = None
            if permit.permit_date:
                age = today.year - permit.permit_date.year

            prospects.append(ProspectRecord(
                permit_id=permit.id,
                owner_name=permit.owner_name,
                address=permit.address,
                city=permit.city,
                county_name=county_obj.name if county_obj else None,
                phone=phone,
                system_type=permit.system_type_raw,
                permit_date=permit.permit_date,
                system_age_years=age,
            ))

        return ProspectsResponse(
            prospects=prospects,
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error(f"Failed to get prospects: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve prospects")


@router.post("/prospects/export")
async def export_prospects(
    db: DbSession,
    current_user: CurrentUser,
    county: Optional[str] = Query(None),
    system_type: Optional[str] = Query(None),
    min_age: Optional[int] = Query(None, ge=0),
    max_age: Optional[int] = Query(None, ge=0),
    has_phone: Optional[bool] = Query(None),
    limit: int = Query(5000, ge=1, le=50000),
):
    """Export prospects as CSV for campaign import."""
    try:
        from datetime import date as date_type
        import csv
        import io
        from fastapi.responses import StreamingResponse

        stmt = (
            select(SepticPermit, County)
            .outerjoin(County, SepticPermit.county_id == County.id)
            .where(
                SepticPermit.customer_id.is_(None),
                SepticPermit.is_active == True,
                SepticPermit.owner_name.isnot(None),
            )
        )

        if county:
            stmt = stmt.where(County.name.ilike(f"%{county}%"))
        if system_type:
            stmt = stmt.where(SepticPermit.system_type_raw.ilike(f"%{system_type}%"))
        if min_age is not None:
            cutoff = date_type(date_type.today().year - min_age, 1, 1)
            stmt = stmt.where(SepticPermit.permit_date <= cutoff)
        if max_age is not None:
            cutoff = date_type(date_type.today().year - max_age, 1, 1)
            stmt = stmt.where(SepticPermit.permit_date >= cutoff)

        stmt = stmt.order_by(desc(SepticPermit.permit_date)).limit(limit)
        result = await db.execute(stmt)
        rows = result.all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "owner_name", "address", "city", "county", "phone",
            "system_type", "permit_date", "system_age_years",
        ])

        today = date_type.today()
        for permit, county_obj in rows:
            phone = None
            if permit.raw_data and isinstance(permit.raw_data, dict):
                phone = permit.raw_data.get("owner_phone")
            if has_phone and not phone:
                continue

            age = None
            if permit.permit_date:
                age = today.year - permit.permit_date.year

            writer.writerow([
                permit.owner_name,
                permit.address,
                permit.city,
                county_obj.name if county_obj else "",
                phone or "",
                permit.system_type_raw or "",
                str(permit.permit_date) if permit.permit_date else "",
                age or "",
            ])

        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=permit_prospects.csv"},
        )

    except Exception as e:
        logger.error(f"Failed to export prospects: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to export prospects")


# ===== SINGLE PERMIT =====


@router.get("/{permit_id}", response_model=PermitResponse)
async def get_permit(permit_id: UUID, db: DbSession, current_user: CurrentUser):
    """Get a single permit by ID with full details."""
    try:
        service = get_permit_search_service(db)
        permit = await service.get_permit(permit_id)

        if not permit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Permit {permit_id} not found")

        return permit

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get permit {permit_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve permit")


@router.post("/{permit_id}/link/{customer_id}", response_model=PermitLinkResponse)
async def link_permit_to_customer(
    permit_id: UUID, customer_id: UUID, db: DbSession, current_user: CurrentUser
):
    """Manually link a permit to a customer."""
    try:
        # Verify permit exists
        result = await db.execute(select(SepticPermit).where(SepticPermit.id == permit_id))
        permit = result.scalar_one_or_none()
        if not permit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Permit {permit_id} not found")

        # Verify customer exists
        cust_result = await db.execute(select(Customer).where(Customer.id == customer_id))
        customer = cust_result.scalar_one_or_none()
        if not customer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Customer {customer_id} not found")

        permit.customer_id = customer_id
        await db.commit()

        return PermitLinkResponse(
            permit_id=permit_id,
            customer_id=customer_id,
            message=f"Permit linked to {customer.first_name} {customer.last_name}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to link permit: {e}")
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to link permit")


@router.delete("/{permit_id}/unlink", response_model=PermitLinkResponse)
async def unlink_permit(permit_id: UUID, db: DbSession, current_user: CurrentUser):
    """Remove the link between a permit and a customer."""
    try:
        result = await db.execute(select(SepticPermit).where(SepticPermit.id == permit_id))
        permit = result.scalar_one_or_none()
        if not permit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Permit {permit_id} not found")

        old_customer_id = permit.customer_id
        permit.customer_id = None
        await db.commit()

        return PermitLinkResponse(
            permit_id=permit_id,
            customer_id=old_customer_id or permit_id,  # Return old ID if available
            message="Permit unlinked from customer",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unlink permit: {e}")
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to unlink permit")


@router.get("/{permit_id}/property")
async def get_permit_property(permit_id: UUID, db: DbSession, current_user: CurrentUser):
    """
    Get linked property data for a permit.
    Returns the permit's own data as a synthetic property record
    so the frontend can display permit details in the property panel.
    """
    try:
        service = get_permit_search_service(db)
        permit = await service.get_permit(permit_id)

        if not permit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Permit {permit_id} not found")

        # Check if permit has rich data (same logic as has_property in search)
        has_data = (
            bool(permit.parcel_number)
            or (permit.latitude is not None and permit.longitude is not None)
            or bool(permit.pdf_url)
            or bool(permit.permit_url)
        )

        if not has_data:
            return {
                "permit_id": str(permit_id),
                "property": None,
                "all_permits": [],
                "total_permits": 0,
                "message": "No property data available for this permit",
            }

        # Return permit data as synthetic property
        return {
            "permit_id": str(permit_id),
            "property": {
                "id": str(permit.id),
                "address": permit.address,
                "address_normalized": permit.address_normalized,
                "street_number": None,
                "street_name": None,
                "city": permit.city,
                "zip_code": permit.zip_code,
                "subdivision": None,
                "parcel_id": permit.parcel_number,
                "gis_link": None,
                "latitude": permit.latitude,
                "longitude": permit.longitude,
                "year_built": None,
                "square_footage": None,
                "bedrooms": permit.bedrooms,
                "bathrooms": None,
                "stories": None,
                "foundation_type": None,
                "construction_type": None,
                "lot_size_acres": None,
                "lot_size_sqft": None,
                "calculated_acres": None,
                "assessed_value": None,
                "assessed_land": None,
                "assessed_improvement": None,
                "market_value": None,
                "market_land": None,
                "market_improvement": None,
                "last_assessed_date": None,
                "owner_name": permit.owner_name,
                "owner_name_2": None,
                "owner_mailing_address": None,
                "owner_city": None,
                "owner_state": None,
                "owner_zip": None,
                "last_sale_date": None,
                "last_sale_price": None,
                "deed_book": None,
                "deed_page": None,
                "property_type": None,
                "property_type_code": None,
                "parcel_type": None,
                "zoning": None,
                "data_quality_score": permit.data_quality_score,
                "has_building_details": False,
                "source_portal_code": permit.source_portal_code,
                "scraped_at": str(permit.scraped_at) if permit.scraped_at else None,
            },
            "all_permits": [
                {
                    "id": str(permit.id),
                    "permit_number": permit.permit_number,
                    "address": permit.address,
                    "city": permit.city,
                    "state_code": permit.state_code,
                    "county_name": permit.county_name,
                    "owner_name": permit.owner_name,
                    "permit_date": str(permit.permit_date) if permit.permit_date else None,
                    "install_date": str(permit.install_date) if permit.install_date else None,
                    "system_type": permit.system_type_raw,
                    "tank_size_gallons": permit.tank_size_gallons,
                    "drainfield_size_sqft": permit.drainfield_size_sqft,
                    "permit_url": permit.permit_url,
                    "pdf_url": permit.pdf_url,
                    "is_current": True,
                }
            ],
            "total_permits": 1,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get permit property: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve permit property data"
        )


@router.get("/{permit_id}/history", response_model=PermitHistoryResponse)
async def get_permit_history(permit_id: UUID, db: DbSession, current_user: CurrentUser):
    """Get version history for a permit."""
    try:
        # Get permit
        result = await db.execute(select(SepticPermit).where(SepticPermit.id == permit_id))
        permit = result.scalar_one_or_none()
        if not permit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Permit {permit_id} not found")

        # Get versions
        versions_result = await db.execute(
            select(PermitVersion).where(PermitVersion.permit_id == permit_id).order_by(desc(PermitVersion.version))
        )
        versions = versions_result.scalars().all()

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
                    permit_data=v.permit_data,
                )
                for v in versions
            ],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get permit history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve permit history"
        )


# ===== STATISTICS =====


@router.get("/stats/overview", response_model=PermitStatsOverview)
async def get_permit_stats(db: DbSession, current_user: CurrentUser):
    """Get dashboard statistics for permits."""
    try:
        service = get_permit_search_service(db)
        return await service.get_stats()
    except Exception as e:
        logger.error(f"Failed to get permit stats: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve statistics")


# ===== BATCH INGESTION =====


@router.post("/batch", response_model=BatchIngestionResponse)
async def ingest_batch(request: BatchIngestionRequest, db: DbSession, current_user: CurrentUser):
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
                status_code=status.HTTP_400_BAD_REQUEST, detail="Batch size cannot exceed 10,000 records"
            )

        service = get_permit_ingestion_service(db)
        return await service.ingest_batch(request.permits, request.source_portal_code)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch ingestion failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Batch ingestion failed")


# ===== DUPLICATES =====


@router.get("/duplicates", response_model=List[DuplicatePair])
async def list_duplicates(
    db: DbSession,
    current_user: CurrentUser,
    status_filter: Optional[str] = Query("pending", description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
):
    """List potential duplicate permit pairs for review."""
    try:
        stmt = select(PermitDuplicate)
        if status_filter:
            stmt = stmt.where(PermitDuplicate.status == status_filter)
        stmt = stmt.order_by(desc(PermitDuplicate.confidence_score)).limit(limit)

        result = await db.execute(stmt)
        duplicates = result.scalars().all()

        results = []
        for dup in duplicates:
            # Get both permits
            p1_result = await db.execute(select(SepticPermit).where(SepticPermit.id == dup.permit_id_1))
            permit1 = p1_result.scalar_one_or_none()

            p2_result = await db.execute(select(SepticPermit).where(SepticPermit.id == dup.permit_id_2))
            permit2 = p2_result.scalar_one_or_none()

            if permit1 and permit2:
                s1_result = await db.execute(select(State).where(State.id == permit1.state_id))
                state1 = s1_result.scalar_one_or_none()

                s2_result = await db.execute(select(State).where(State.id == permit2.state_id))
                state2 = s2_result.scalar_one_or_none()

                county1 = None
                if permit1.county_id:
                    c1_result = await db.execute(select(County).where(County.id == permit1.county_id))
                    county1 = c1_result.scalar_one_or_none()

                county2 = None
                if permit2.county_id:
                    c2_result = await db.execute(select(County).where(County.id == permit2.county_id))
                    county2 = c2_result.scalar_one_or_none()

                results.append(
                    DuplicatePair(
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
                            system_type=permit1.system_type_raw,
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
                            system_type=permit2.system_type_raw,
                        ),
                        detection_method=dup.detection_method,
                        confidence_score=dup.confidence_score or 0.0,
                        matching_fields=dup.matching_fields or [],
                        status=dup.status,
                        created_at=dup.created_at,
                    )
                )

        return results

    except Exception as e:
        logger.error(f"Failed to list duplicates: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve duplicates")


@router.post("/duplicates/{duplicate_id}/resolve", response_model=DuplicateResponse)
async def resolve_duplicate(
    duplicate_id: UUID, resolution: DuplicateResolution, db: DbSession, current_user: CurrentUser
):
    """Resolve a duplicate pair (merge, reject, or mark as reviewed)."""
    try:
        result = await db.execute(select(PermitDuplicate).where(PermitDuplicate.id == duplicate_id))
        dup = result.scalar_one_or_none()
        if not dup:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Duplicate pair {duplicate_id} not found"
            )

        if resolution.action == "merge":
            if not resolution.canonical_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="canonical_id required for merge action"
                )

            # Mark non-canonical record as inactive
            non_canonical_id = dup.permit_id_2 if resolution.canonical_id == dup.permit_id_1 else dup.permit_id_1
            nc_result = await db.execute(select(SepticPermit).where(SepticPermit.id == non_canonical_id))
            non_canonical = nc_result.scalar_one_or_none()
            if non_canonical:
                non_canonical.is_active = False
                non_canonical.duplicate_of_id = resolution.canonical_id

            dup.status = "merged"
            dup.canonical_id = resolution.canonical_id

        elif resolution.action == "reject":
            dup.status = "rejected"

        else:  # review
            dup.status = "reviewed"

        dup.resolved_at = datetime.utcnow()
        dup.resolved_by = str(current_user.id) if hasattr(current_user, "id") else "unknown"
        dup.resolution_notes = resolution.notes

        await db.commit()

        return DuplicateResponse(
            id=dup.id,
            status=dup.status,
            canonical_id=dup.canonical_id,
            resolved_at=dup.resolved_at,
            message=f"Duplicate {resolution.action}d successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve duplicate: {e}")
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to resolve duplicate")


# ===== REFERENCE DATA =====


@router.get("/ref/states", response_model=List[StateResponse])
async def list_states(db: DbSession, current_user: CurrentUser):
    """List all US states."""
    try:
        result = await db.execute(select(State).where(State.is_active == True).order_by(State.name))
        states = result.scalars().all()
        return [
            StateResponse(id=s.id, code=s.code, name=s.name, fips_code=s.fips_code, region=s.region) for s in states
        ]
    except Exception as e:
        logger.error(f"Failed to list states: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve states")


@router.get("/ref/counties", response_model=List[CountyResponse])
async def list_counties(
    db: DbSession,
    current_user: CurrentUser,
    state_code: Optional[str] = Query(None, description="Filter by state code"),
):
    """List counties, optionally filtered by state."""
    try:
        stmt = select(County, State).join(State, County.state_id == State.id).where(County.is_active == True)

        if state_code:
            stmt = stmt.where(State.code == state_code.upper())

        stmt = stmt.order_by(County.name)
        result = await db.execute(stmt)
        rows = result.all()

        return [
            CountyResponse(
                id=c.id,
                state_id=c.state_id,
                name=c.name,
                normalized_name=c.normalized_name,
                fips_code=c.fips_code,
                population=c.population,
                state_code=s.code,
            )
            for c, s in rows
        ]
    except Exception as e:
        logger.error(f"Failed to list counties: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve counties")


@router.get("/ref/system-types", response_model=List[SystemTypeResponse])
async def list_system_types(db: DbSession, current_user: CurrentUser):
    """List septic system types."""
    try:
        result = await db.execute(
            select(SepticSystemType).where(SepticSystemType.is_active == True).order_by(SepticSystemType.name)
        )
        types = result.scalars().all()

        return [
            SystemTypeResponse(id=t.id, code=t.code, name=t.name, category=t.category, description=t.description)
            for t in types
        ]
    except Exception as e:
        logger.error(f"Failed to list system types: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve system types")


@router.get("/ref/portals", response_model=List[SourcePortalResponse])
async def list_source_portals(db: DbSession, current_user: CurrentUser):
    """List data source portals."""
    try:
        result = await db.execute(
            select(SourcePortal).where(SourcePortal.is_active == True).order_by(SourcePortal.name)
        )
        portals = result.scalars().all()

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
                total_records_scraped=p.total_records_scraped,
            )
            for p in portals
        ]
    except Exception as e:
        logger.error(f"Failed to list portals: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve source portals"
        )
