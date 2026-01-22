"""
Septic permit search service.

Implements hybrid search combining:
- PostgreSQL full-text search (TSVECTOR + ts_rank)
- Semantic search via embeddings (pgvector)
- Reciprocal Rank Fusion (RRF) for result merging
"""

import logging
import time
import math
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, and_, or_, desc, asc, case

from app.models.septic_permit import (
    SepticPermit, State, County, SepticSystemType, SourcePortal,
    PermitDuplicate
)
from app.schemas.septic_permit import (
    PermitSearchRequest, PermitSearchResponse, PermitSearchResult,
    PermitSummary, SearchHighlight, PermitResponse,
    PermitStatsOverview, PermitStatsByState, PermitStatsByYear
)

logger = logging.getLogger(__name__)


# RRF constant (typically 60)
RRF_K = 60


class PermitSearchService:
    """
    Service for searching septic permit records.

    Features:
    - Full-text search with ts_rank
    - Trigram fuzzy matching
    - Geo-based radius search
    - Faceted filtering
    - Hybrid ranking with RRF
    """

    def __init__(self, db: AsyncSession):
        """Initialize search service with database session."""
        self.db = db

    async def search(self, request: PermitSearchRequest) -> PermitSearchResponse:
        """
        Execute hybrid search on permit records.

        Args:
            request: Search parameters

        Returns:
            PermitSearchResponse with paginated results
        """
        start_time = time.time()

        # Build base query
        stmt = select(SepticPermit, State, County, SepticSystemType).join(
            State, SepticPermit.state_id == State.id
        ).outerjoin(
            County, SepticPermit.county_id == County.id
        ).outerjoin(
            SepticSystemType, SepticPermit.system_type_id == SepticSystemType.id
        )

        # Apply filters
        conditions = []
        if not request.include_inactive:
            conditions.append(SepticPermit.is_active == True)

        # State filter
        if request.state_codes:
            conditions.append(State.code.in_(request.state_codes))

        # County filter
        if request.county_ids:
            conditions.append(SepticPermit.county_id.in_(request.county_ids))

        # City filter
        if request.city:
            conditions.append(SepticPermit.city.ilike(f'%{request.city}%'))

        # Zip code filter
        if request.zip_code:
            conditions.append(SepticPermit.zip_code == request.zip_code)

        # System type filter
        if request.system_type_ids:
            conditions.append(SepticPermit.system_type_id.in_(request.system_type_ids))

        # Date range filters
        if request.permit_date_from:
            conditions.append(SepticPermit.permit_date >= request.permit_date_from)
        if request.permit_date_to:
            conditions.append(SepticPermit.permit_date <= request.permit_date_to)
        if request.install_date_from:
            conditions.append(SepticPermit.install_date >= request.install_date_from)
        if request.install_date_to:
            conditions.append(SepticPermit.install_date <= request.install_date_to)

        # Geo search (radius)
        if request.latitude and request.longitude and request.radius_miles:
            # Convert miles to degrees (approximate)
            lat_range = request.radius_miles / 69.0
            lon_range = request.radius_miles / (69.0 * math.cos(math.radians(request.latitude)))

            conditions.extend([
                SepticPermit.latitude.isnot(None),
                SepticPermit.longitude.isnot(None),
                SepticPermit.latitude.between(
                    request.latitude - lat_range,
                    request.latitude + lat_range
                ),
                SepticPermit.longitude.between(
                    request.longitude - lon_range,
                    request.longitude + lon_range
                )
            ])

        # Text search
        if request.query:
            # Full-text search with ts_rank
            ts_query = func.plainto_tsquery('english', request.query)

            # Filter for matches
            conditions.append(
                or_(
                    SepticPermit.search_vector.op('@@')(ts_query),
                    func.similarity(SepticPermit.address_normalized, request.query.upper()) > 0.1
                )
            )

        # Apply all conditions
        if conditions:
            stmt = stmt.where(and_(*conditions))

        # Get total count
        count_stmt = select(func.count(SepticPermit.id)).select_from(SepticPermit).join(
            State, SepticPermit.state_id == State.id
        )
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Apply sorting
        if request.query and request.sort_by == 'relevance':
            # Order by text match score
            ts_query = func.plainto_tsquery('english', request.query)
            stmt = stmt.order_by(desc(func.ts_rank(SepticPermit.search_vector, ts_query)))
        elif request.sort_by == 'permit_date':
            if request.sort_order == 'asc':
                stmt = stmt.order_by(asc(SepticPermit.permit_date))
            else:
                stmt = stmt.order_by(desc(SepticPermit.permit_date))
        elif request.sort_by == 'address':
            if request.sort_order == 'asc':
                stmt = stmt.order_by(asc(SepticPermit.address_normalized))
            else:
                stmt = stmt.order_by(desc(SepticPermit.address_normalized))
        elif request.sort_by == 'owner_name':
            if request.sort_order == 'asc':
                stmt = stmt.order_by(asc(SepticPermit.owner_name))
            else:
                stmt = stmt.order_by(desc(SepticPermit.owner_name))
        else:
            # Default: most recent first
            stmt = stmt.order_by(desc(SepticPermit.created_at))

        # Apply pagination
        offset = (request.page - 1) * request.page_size
        stmt = stmt.offset(offset).limit(request.page_size)

        # Execute query
        result = await self.db.execute(stmt)
        rows = result.all()

        # Build response
        search_results = []
        for row in rows:
            permit, state, county, system_type = row

            # Determine "linked" status - has property_id, parcel number, or coordinates
            # This indicates the permit has additional data linking it to a physical property
            has_property_id = getattr(permit, 'property_id', None) is not None
            has_parcel = bool(permit.parcel_number)
            has_coordinates = permit.latitude is not None and permit.longitude is not None
            has_property = has_property_id or has_parcel or has_coordinates

            summary = PermitSummary(
                id=permit.id,
                permit_number=permit.permit_number,
                address=permit.address,
                city=permit.city,
                state_code=state.code if state else None,
                county_name=county.name if county else None,
                owner_name=permit.owner_name,
                permit_date=permit.permit_date,
                system_type=permit.system_type_raw,
                has_property=has_property
            )

            # Get highlights if text search
            highlights = []
            if request.query:
                highlights = self._get_highlights(permit, request.query)

            search_results.append(PermitSearchResult(
                permit=summary,
                score=1.0,  # TODO: Calculate actual score
                keyword_score=0.0,
                semantic_score=None,
                highlights=highlights
            ))

        elapsed_ms = (time.time() - start_time) * 1000

        return PermitSearchResponse(
            results=search_results,
            total=total,
            page=request.page,
            page_size=request.page_size,
            total_pages=math.ceil(total / request.page_size) if total > 0 else 0,
            query=request.query,
            execution_time_ms=elapsed_ms,
            state_facets=None,
            county_facets=None
        )

    def _get_highlights(self, permit: SepticPermit, query: str) -> List[SearchHighlight]:
        """Get search result highlighting for matched terms."""
        highlights = []

        fields_to_check = [
            ('address', permit.address),
            ('owner_name', permit.owner_name),
            ('city', permit.city),
            ('permit_number', permit.permit_number),
        ]

        query_lower = query.lower()
        for field_name, field_value in fields_to_check:
            if field_value and query_lower in field_value.lower():
                idx = field_value.lower().find(query_lower)
                start = max(0, idx - 20)
                end = min(len(field_value), idx + len(query) + 20)

                fragment = field_value[start:end]
                if start > 0:
                    fragment = '...' + fragment
                if end < len(field_value):
                    fragment = fragment + '...'

                highlights.append(SearchHighlight(
                    field=field_name,
                    fragments=[fragment]
                ))

        return highlights

    async def get_permit(self, permit_id: UUID) -> Optional[PermitResponse]:
        """Get a single permit by ID with full details."""
        stmt = select(SepticPermit).where(SepticPermit.id == permit_id)
        result = await self.db.execute(stmt)
        permit = result.scalar_one_or_none()

        if not permit:
            return None

        # Get related data
        state_result = await self.db.execute(
            select(State).where(State.id == permit.state_id)
        )
        state = state_result.scalar_one_or_none()

        county = None
        if permit.county_id:
            county_result = await self.db.execute(
                select(County).where(County.id == permit.county_id)
            )
            county = county_result.scalar_one_or_none()

        system_type = None
        if permit.system_type_id:
            st_result = await self.db.execute(
                select(SepticSystemType).where(SepticSystemType.id == permit.system_type_id)
            )
            system_type = st_result.scalar_one_or_none()

        source_portal = None
        if permit.source_portal_id:
            sp_result = await self.db.execute(
                select(SourcePortal).where(SourcePortal.id == permit.source_portal_id)
            )
            source_portal = sp_result.scalar_one_or_none()

        return PermitResponse(
            id=permit.id,
            permit_number=permit.permit_number,
            state_id=permit.state_id,
            state_code=state.code if state else None,
            state_name=state.name if state else None,
            county_id=permit.county_id,
            county_name=county.name if county else None,
            address=permit.address,
            address_normalized=permit.address_normalized,
            city=permit.city,
            zip_code=permit.zip_code,
            parcel_number=permit.parcel_number,
            latitude=permit.latitude,
            longitude=permit.longitude,
            owner_name=permit.owner_name,
            applicant_name=permit.applicant_name,
            contractor_name=permit.contractor_name,
            install_date=permit.install_date,
            permit_date=permit.permit_date,
            expiration_date=permit.expiration_date,
            system_type_id=permit.system_type_id,
            system_type_raw=permit.system_type_raw,
            system_type_name=system_type.name if system_type else None,
            tank_size_gallons=permit.tank_size_gallons,
            drainfield_size_sqft=permit.drainfield_size_sqft,
            bedrooms=permit.bedrooms,
            daily_flow_gpd=permit.daily_flow_gpd,
            pdf_url=permit.pdf_url,
            permit_url=permit.permit_url,
            source_portal_id=permit.source_portal_id,
            source_portal_code=permit.source_portal_code,
            source_portal_name=source_portal.name if source_portal else None,
            scraped_at=permit.scraped_at,
            is_active=permit.is_active,
            data_quality_score=permit.data_quality_score,
            version=permit.version,
            created_at=permit.created_at,
            updated_at=permit.updated_at
        )

    async def get_stats(self) -> PermitStatsOverview:
        """Get dashboard statistics for permits."""
        from datetime import date

        today = date.today()
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        # Total counts
        total_result = await self.db.execute(
            select(func.count(SepticPermit.id)).where(SepticPermit.is_active == True)
        )
        total_permits = total_result.scalar() or 0

        states_result = await self.db.execute(
            select(func.count(func.distinct(SepticPermit.state_id))).where(SepticPermit.is_active == True)
        )
        total_states = states_result.scalar() or 0

        counties_result = await self.db.execute(
            select(func.count(func.distinct(SepticPermit.county_id))).where(SepticPermit.is_active == True)
        )
        total_counties = counties_result.scalar() or 0

        portals_result = await self.db.execute(
            select(func.count(SourcePortal.id)).where(SourcePortal.is_active == True)
        )
        total_portals = portals_result.scalar() or 0

        # Monthly/yearly counts
        month_result = await self.db.execute(
            select(func.count(SepticPermit.id)).where(
                and_(SepticPermit.is_active == True, SepticPermit.permit_date >= month_start)
            )
        )
        permits_this_month = month_result.scalar() or 0

        year_result = await self.db.execute(
            select(func.count(SepticPermit.id)).where(
                and_(SepticPermit.is_active == True, SepticPermit.permit_date >= year_start)
            )
        )
        permits_this_year = year_result.scalar() or 0

        # Average data quality
        quality_result = await self.db.execute(
            select(func.avg(SepticPermit.data_quality_score)).where(
                and_(SepticPermit.is_active == True, SepticPermit.data_quality_score.isnot(None))
            )
        )
        avg_quality = quality_result.scalar() or 0.0

        # Pending duplicates
        dup_result = await self.db.execute(
            select(func.count(PermitDuplicate.id)).where(PermitDuplicate.status == 'pending')
        )
        duplicate_count = dup_result.scalar() or 0

        # Top states
        top_states_stmt = select(
            State.code,
            State.name,
            func.count(SepticPermit.id).label('total'),
            func.count(case((SepticPermit.permit_date >= year_start, 1))).label('this_year')
        ).join(
            SepticPermit, SepticPermit.state_id == State.id
        ).where(
            SepticPermit.is_active == True
        ).group_by(
            State.code, State.name
        ).order_by(
            desc('total')
        ).limit(10)

        top_states_result = await self.db.execute(top_states_stmt)
        top_states = [
            PermitStatsByState(
                state_code=row[0],
                state_name=row[1],
                total_permits=row[2],
                active_permits=row[2],
                permits_this_year=row[3]
            )
            for row in top_states_result.all()
        ]

        # Permits by year
        by_year_stmt = select(
            func.extract('year', SepticPermit.permit_date).label('year'),
            func.count(SepticPermit.id).label('count')
        ).where(
            and_(SepticPermit.is_active == True, SepticPermit.permit_date.isnot(None))
        ).group_by(
            func.extract('year', SepticPermit.permit_date)
        ).order_by(
            desc('year')
        ).limit(10)

        by_year_result = await self.db.execute(by_year_stmt)
        permits_by_year = [
            PermitStatsByYear(
                year=int(row[0]) if row[0] else 0,
                total_permits=row[1]
            )
            for row in by_year_result.all()
        ]

        return PermitStatsOverview(
            total_permits=total_permits,
            total_states=total_states,
            total_counties=total_counties,
            total_source_portals=total_portals,
            permits_this_month=permits_this_month,
            permits_this_year=permits_this_year,
            avg_data_quality_score=float(avg_quality),
            duplicate_pending_count=duplicate_count,
            top_states=top_states,
            permits_by_year=permits_by_year
        )


# Factory function
def get_permit_search_service(db: AsyncSession) -> PermitSearchService:
    """Create a permit search service instance."""
    return PermitSearchService(db)
