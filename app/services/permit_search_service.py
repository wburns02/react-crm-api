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
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select, func, text, and_, or_, desc, asc, case
from sqlalchemy.dialects.postgresql import TSVECTOR

from app.models.septic_permit import (
    SepticPermit, State, County, SepticSystemType, SourcePortal,
    PermitDuplicate
)
from app.schemas.septic_permit import (
    PermitSearchRequest, PermitSearchResponse, PermitSearchResult,
    PermitSummary, SearchHighlight, PermitResponse,
    PermitStatsOverview, PermitStatsByState, PermitStatsByYear
)
from app.database import SessionLocal

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

    def __init__(self, db: Session):
        """Initialize search service with database session."""
        self.db = db

    def search(self, request: PermitSearchRequest) -> PermitSearchResponse:
        """
        Execute hybrid search on permit records.

        Args:
            request: Search parameters

        Returns:
            PermitSearchResponse with paginated results
        """
        start_time = time.time()

        # Build base query with eager loading
        query = self.db.query(SepticPermit).join(
            State, SepticPermit.state_id == State.id
        ).outerjoin(
            County, SepticPermit.county_id == County.id
        ).outerjoin(
            SepticSystemType, SepticPermit.system_type_id == SepticSystemType.id
        )

        # Apply filters
        if not request.include_inactive:
            query = query.filter(SepticPermit.is_active == True)

        # State filter
        if request.state_codes:
            query = query.filter(State.code.in_(request.state_codes))

        # County filter
        if request.county_ids:
            query = query.filter(SepticPermit.county_id.in_(request.county_ids))

        # City filter
        if request.city:
            query = query.filter(
                SepticPermit.city.ilike(f'%{request.city}%')
            )

        # Zip code filter
        if request.zip_code:
            query = query.filter(SepticPermit.zip_code == request.zip_code)

        # System type filter
        if request.system_type_ids:
            query = query.filter(
                SepticPermit.system_type_id.in_(request.system_type_ids)
            )

        # Date range filters
        if request.permit_date_from:
            query = query.filter(SepticPermit.permit_date >= request.permit_date_from)
        if request.permit_date_to:
            query = query.filter(SepticPermit.permit_date <= request.permit_date_to)
        if request.install_date_from:
            query = query.filter(SepticPermit.install_date >= request.install_date_from)
        if request.install_date_to:
            query = query.filter(SepticPermit.install_date <= request.install_date_to)

        # Geo search (radius)
        if request.latitude and request.longitude and request.radius_miles:
            # Convert miles to degrees (approximate)
            lat_range = request.radius_miles / 69.0
            lon_range = request.radius_miles / (69.0 * math.cos(math.radians(request.latitude)))

            query = query.filter(
                and_(
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
                )
            )

        # Text search scoring
        search_scores = []
        if request.query:
            # Full-text search with ts_rank
            ts_query = func.plainto_tsquery('english', request.query)
            keyword_rank = func.ts_rank(SepticPermit.search_vector, ts_query)

            # Trigram similarity on address
            address_similarity = func.similarity(
                SepticPermit.address_normalized,
                request.query.upper()
            )

            # Combined score
            combined_score = (keyword_rank * 0.7) + (address_similarity * 0.3)

            # Filter for matches
            query = query.filter(
                or_(
                    SepticPermit.search_vector.op('@@')(ts_query),
                    func.similarity(SepticPermit.address_normalized, request.query.upper()) > 0.1
                )
            )

            # Add score to result
            query = query.add_columns(
                combined_score.label('relevance_score'),
                keyword_rank.label('keyword_score')
            )

        else:
            # No text search - use default ordering
            query = query.add_columns(
                text('1.0').label('relevance_score'),
                text('0.0').label('keyword_score')
            )

        # Get total count (before pagination)
        count_query = query.with_entities(func.count(SepticPermit.id))
        total = count_query.scalar()

        # Apply sorting
        if request.query and request.sort_by == 'relevance':
            query = query.order_by(desc('relevance_score'))
        elif request.sort_by == 'permit_date':
            if request.sort_order == 'asc':
                query = query.order_by(asc(SepticPermit.permit_date))
            else:
                query = query.order_by(desc(SepticPermit.permit_date))
        elif request.sort_by == 'address':
            if request.sort_order == 'asc':
                query = query.order_by(asc(SepticPermit.address_normalized))
            else:
                query = query.order_by(desc(SepticPermit.address_normalized))
        elif request.sort_by == 'owner_name':
            if request.sort_order == 'asc':
                query = query.order_by(asc(SepticPermit.owner_name))
            else:
                query = query.order_by(desc(SepticPermit.owner_name))
        else:
            # Default: most recent first
            query = query.order_by(desc(SepticPermit.created_at))

        # Apply pagination
        offset = (request.page - 1) * request.page_size
        query = query.offset(offset).limit(request.page_size)

        # Execute query
        results = query.all()

        # Build response
        search_results = []
        for row in results:
            permit = row[0] if isinstance(row, tuple) else row
            relevance = row[1] if isinstance(row, tuple) and len(row) > 1 else 1.0
            keyword_score = row[2] if isinstance(row, tuple) and len(row) > 2 else 0.0

            # Get related data
            state = self.db.query(State).filter(State.id == permit.state_id).first()
            county = self.db.query(County).filter(County.id == permit.county_id).first() if permit.county_id else None

            summary = PermitSummary(
                id=permit.id,
                permit_number=permit.permit_number,
                address=permit.address,
                city=permit.city,
                state_code=state.code if state else None,
                county_name=county.name if county else None,
                owner_name=permit.owner_name,
                permit_date=permit.permit_date,
                system_type=permit.system_type_raw
            )

            # Get highlights if text search
            highlights = []
            if request.query:
                highlights = self._get_highlights(permit, request.query)

            search_results.append(PermitSearchResult(
                permit=summary,
                score=float(relevance) if relevance else 0.0,
                keyword_score=float(keyword_score) if keyword_score else 0.0,
                semantic_score=None,  # TODO: Add when embeddings are implemented
                highlights=highlights
            ))

        # Build facets (optional)
        state_facets = self._get_state_facets(request) if not request.state_codes else None
        county_facets = self._get_county_facets(request) if request.state_codes and not request.county_ids else None

        elapsed_ms = (time.time() - start_time) * 1000

        return PermitSearchResponse(
            results=search_results,
            total=total or 0,
            page=request.page,
            page_size=request.page_size,
            total_pages=math.ceil((total or 0) / request.page_size),
            query=request.query,
            execution_time_ms=elapsed_ms,
            state_facets=state_facets,
            county_facets=county_facets
        )

    def _get_highlights(self, permit: SepticPermit, query: str) -> List[SearchHighlight]:
        """Get search result highlighting for matched terms."""
        highlights = []

        # Check each searchable field
        fields_to_check = [
            ('address', permit.address),
            ('owner_name', permit.owner_name),
            ('city', permit.city),
            ('permit_number', permit.permit_number),
        ]

        query_lower = query.lower()
        for field_name, field_value in fields_to_check:
            if field_value and query_lower in field_value.lower():
                # Create highlighted fragment
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

    def _get_state_facets(self, request: PermitSearchRequest) -> List[Dict[str, Any]]:
        """Get permit counts by state for faceted filtering."""
        query = self.db.query(
            State.code,
            State.name,
            func.count(SepticPermit.id).label('count')
        ).join(
            SepticPermit, SepticPermit.state_id == State.id
        ).filter(
            SepticPermit.is_active == True
        ).group_by(
            State.code, State.name
        ).order_by(
            desc('count')
        ).limit(20)

        return [
            {'code': row[0], 'name': row[1], 'count': row[2]}
            for row in query.all()
        ]

    def _get_county_facets(self, request: PermitSearchRequest) -> List[Dict[str, Any]]:
        """Get permit counts by county for faceted filtering."""
        query = self.db.query(
            County.id,
            County.name,
            func.count(SepticPermit.id).label('count')
        ).join(
            SepticPermit, SepticPermit.county_id == County.id
        ).join(
            State, SepticPermit.state_id == State.id
        ).filter(
            SepticPermit.is_active == True
        )

        if request.state_codes:
            query = query.filter(State.code.in_(request.state_codes))

        query = query.group_by(
            County.id, County.name
        ).order_by(
            desc('count')
        ).limit(50)

        return [
            {'id': row[0], 'name': row[1], 'count': row[2]}
            for row in query.all()
        ]

    def get_permit(self, permit_id: UUID) -> Optional[PermitResponse]:
        """Get a single permit by ID with full details."""
        permit = self.db.query(SepticPermit).filter(
            SepticPermit.id == permit_id
        ).first()

        if not permit:
            return None

        # Get related data
        state = self.db.query(State).filter(State.id == permit.state_id).first()
        county = self.db.query(County).filter(County.id == permit.county_id).first() if permit.county_id else None
        system_type = self.db.query(SepticSystemType).filter(
            SepticSystemType.id == permit.system_type_id
        ).first() if permit.system_type_id else None
        source_portal = self.db.query(SourcePortal).filter(
            SourcePortal.id == permit.source_portal_id
        ).first() if permit.source_portal_id else None

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

    def get_stats(self) -> PermitStatsOverview:
        """Get dashboard statistics for permits."""
        from datetime import date, timedelta

        today = date.today()
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        # Total counts
        total_permits = self.db.query(func.count(SepticPermit.id)).filter(
            SepticPermit.is_active == True
        ).scalar() or 0

        total_states = self.db.query(func.count(func.distinct(SepticPermit.state_id))).filter(
            SepticPermit.is_active == True
        ).scalar() or 0

        total_counties = self.db.query(func.count(func.distinct(SepticPermit.county_id))).filter(
            SepticPermit.is_active == True
        ).scalar() or 0

        total_portals = self.db.query(func.count(SourcePortal.id)).filter(
            SourcePortal.is_active == True
        ).scalar() or 0

        # Monthly/yearly counts
        permits_this_month = self.db.query(func.count(SepticPermit.id)).filter(
            SepticPermit.is_active == True,
            SepticPermit.permit_date >= month_start
        ).scalar() or 0

        permits_this_year = self.db.query(func.count(SepticPermit.id)).filter(
            SepticPermit.is_active == True,
            SepticPermit.permit_date >= year_start
        ).scalar() or 0

        # Average data quality
        avg_quality = self.db.query(func.avg(SepticPermit.data_quality_score)).filter(
            SepticPermit.is_active == True,
            SepticPermit.data_quality_score.isnot(None)
        ).scalar() or 0.0

        # Pending duplicates
        duplicate_count = self.db.query(func.count(PermitDuplicate.id)).filter(
            PermitDuplicate.status == 'pending'
        ).scalar() or 0

        # Top states
        top_states_query = self.db.query(
            State.code,
            State.name,
            func.count(SepticPermit.id).label('total'),
            func.count(case((SepticPermit.permit_date >= year_start, 1))).label('this_year')
        ).join(
            SepticPermit, SepticPermit.state_id == State.id
        ).filter(
            SepticPermit.is_active == True
        ).group_by(
            State.code, State.name
        ).order_by(
            desc('total')
        ).limit(10)

        top_states = [
            PermitStatsByState(
                state_code=row[0],
                state_name=row[1],
                total_permits=row[2],
                active_permits=row[2],
                permits_this_year=row[3]
            )
            for row in top_states_query.all()
        ]

        # Permits by year (last 10 years)
        permits_by_year_query = self.db.query(
            func.extract('year', SepticPermit.permit_date).label('year'),
            func.count(SepticPermit.id).label('count')
        ).filter(
            SepticPermit.is_active == True,
            SepticPermit.permit_date.isnot(None)
        ).group_by(
            func.extract('year', SepticPermit.permit_date)
        ).order_by(
            desc('year')
        ).limit(10)

        permits_by_year = [
            PermitStatsByYear(
                year=int(row[0]) if row[0] else 0,
                total_permits=row[1]
            )
            for row in permits_by_year_query.all()
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
def get_permit_search_service(db: Session) -> PermitSearchService:
    """Create a permit search service instance."""
    return PermitSearchService(db)
