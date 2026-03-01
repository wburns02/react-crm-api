"""
Septic permit ingestion service.

Handles batch ingestion of permit records from scrapers with:
- Address normalization and deduplication
- Update detection via record hash comparison
- Version history tracking
- Duplicate candidate flagging
"""

import logging
import uuid
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func

from app.models.septic_permit import (
    SepticPermit,
    PermitVersion,
    PermitDuplicate,
    PermitImportBatch,
    State,
    County,
    SepticSystemType,
    SourcePortal,
)
from app.schemas.septic_permit import PermitCreate, BatchIngestionStats, BatchIngestionResponse
from app.utils.address_normalization import (
    normalize_address,
    normalize_county,
    normalize_state,
    normalize_owner_name,
    compute_address_hash,
)

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Custom exception for ingestion-related errors."""

    pass


class PermitIngestionService:
    """
    Service for ingesting septic permit records from scrapers.

    Features:
    - Batch processing (up to 10,000 records)
    - Address normalization for deduplication
    - Record hash comparison for change detection
    - Automatic version history creation
    - Duplicate candidate flagging
    """

    def __init__(self, db: AsyncSession):
        """Initialize ingestion service with database session."""
        self.db = db
        self._state_cache: Dict[str, int] = {}
        self._county_cache: Dict[str, int] = {}
        self._system_type_cache: Dict[str, int] = {}
        self._portal_cache: Dict[str, int] = {}

    async def _get_or_create_state(self, state_code: str) -> Optional[int]:
        """Get state ID by code, using cache."""
        if not state_code:
            return None

        code = normalize_state(state_code)
        if not code:
            return None

        if code in self._state_cache:
            return self._state_cache[code]

        result = await self.db.execute(select(State).where(State.code == code))
        state = result.scalar_one_or_none()
        if state:
            self._state_cache[code] = state.id
            return state.id

        return None

    async def _get_or_create_county(self, county_name: str, state_id: int) -> Optional[int]:
        """Get or create county ID."""
        if not county_name or not state_id:
            return None

        normalized = normalize_county(county_name)
        if not normalized:
            return None

        cache_key = f"{state_id}:{normalized}"
        if cache_key in self._county_cache:
            return self._county_cache[cache_key]

        result = await self.db.execute(
            select(County).where(County.state_id == state_id, County.normalized_name == normalized)
        )
        county = result.scalar_one_or_none()

        if county:
            self._county_cache[cache_key] = county.id
            return county.id

        # Create new county
        county = County(state_id=state_id, name=county_name, normalized_name=normalized, is_active=True)
        self.db.add(county)
        await self.db.flush()
        self._county_cache[cache_key] = county.id
        return county.id

    async def _get_system_type_id(self, system_type: str) -> Optional[int]:
        """Get system type ID by raw name."""
        if not system_type:
            return None

        normalized = system_type.upper().strip()

        if normalized in self._system_type_cache:
            return self._system_type_cache[normalized]

        # Try exact match on code first
        result = await self.db.execute(select(SepticSystemType).where(SepticSystemType.code == normalized))
        sys_type = result.scalar_one_or_none()

        if not sys_type:
            # Try partial match on name
            result = await self.db.execute(
                select(SepticSystemType).where(SepticSystemType.name.ilike(f"%{normalized}%"))
            )
            sys_type = result.scalar_one_or_none()

        if sys_type:
            self._system_type_cache[normalized] = sys_type.id
            return sys_type.id

        # Default to UNKNOWN
        result = await self.db.execute(select(SepticSystemType).where(SepticSystemType.code == "UNKNOWN"))
        unknown = result.scalar_one_or_none()
        if unknown:
            self._system_type_cache[normalized] = unknown.id
            return unknown.id

        return None

    async def _get_or_create_portal(self, portal_code: str, state_id: Optional[int] = None) -> Optional[int]:
        """Get or create source portal ID."""
        if not portal_code:
            return None

        if portal_code in self._portal_cache:
            return self._portal_cache[portal_code]

        result = await self.db.execute(select(SourcePortal).where(SourcePortal.code == portal_code))
        portal = result.scalar_one_or_none()

        if portal:
            self._portal_cache[portal_code] = portal.id
            return portal.id

        # Create new portal
        portal = SourcePortal(
            code=portal_code, name=portal_code.replace("_", " ").title(), state_id=state_id, is_active=True
        )
        self.db.add(portal)
        await self.db.flush()
        self._portal_cache[portal_code] = portal.id
        return portal.id

    async def _find_existing_permit(
        self, address_hash: Optional[str], permit_number: Optional[str], state_id: int, county_id: Optional[int]
    ) -> Optional[SepticPermit]:
        """
        Find existing permit by address hash or permit number.

        Priority:
        1. Exact address hash match (normalized address + county + state)
        2. Permit number + state match
        """
        if address_hash:
            result = await self.db.execute(
                select(SepticPermit).where(
                    SepticPermit.address_hash == address_hash,
                    SepticPermit.state_id == state_id,
                    SepticPermit.county_id == county_id,
                    SepticPermit.is_active == True,
                )
            )
            existing = result.scalars().first()
            if existing:
                return existing

        if permit_number:
            result = await self.db.execute(
                select(SepticPermit).where(
                    SepticPermit.permit_number == permit_number,
                    SepticPermit.state_id == state_id,
                    SepticPermit.is_active == True,
                )
            )
            existing = result.scalars().first()
            if existing:
                return existing

        return None

    def _compute_record_hash(self, permit_data: Dict[str, Any]) -> str:
        """Compute hash of permit data for change detection."""
        return SepticPermit.compute_record_hash(permit_data)

    async def _create_version(
        self, permit: SepticPermit, change_source: str = "scraper", changed_fields: Optional[List[str]] = None
    ) -> PermitVersion:
        """Create a version history record for a permit."""
        permit_data = {
            "permit_number": permit.permit_number,
            "address": permit.address,
            "address_normalized": permit.address_normalized,
            "city": permit.city,
            "zip_code": permit.zip_code,
            "parcel_number": permit.parcel_number,
            "latitude": permit.latitude,
            "longitude": permit.longitude,
            "owner_name": permit.owner_name,
            "applicant_name": permit.applicant_name,
            "contractor_name": permit.contractor_name,
            "install_date": str(permit.install_date) if permit.install_date else None,
            "permit_date": str(permit.permit_date) if permit.permit_date else None,
            "expiration_date": str(permit.expiration_date) if permit.expiration_date else None,
            "system_type_raw": permit.system_type_raw,
            "tank_size_gallons": permit.tank_size_gallons,
            "drainfield_size_sqft": permit.drainfield_size_sqft,
            "bedrooms": permit.bedrooms,
            "daily_flow_gpd": permit.daily_flow_gpd,
            "pdf_url": permit.pdf_url,
            "permit_url": permit.permit_url,
            "source_portal_code": permit.source_portal_code,
            "scraped_at": permit.scraped_at.isoformat() if permit.scraped_at else None,
        }

        version = PermitVersion(
            id=uuid.uuid4(),
            permit_id=permit.id,
            version=permit.version,
            permit_data=permit_data,
            changed_fields=changed_fields,
            change_source=change_source,
            source_portal_id=permit.source_portal_id,
            scraped_at=permit.scraped_at,
            created_by="system",
        )
        self.db.add(version)
        return version

    def _get_changed_fields(self, existing: SepticPermit, new_data: Dict[str, Any]) -> List[str]:
        """Determine which fields changed between existing and new data."""
        changed = []
        check_fields = [
            "permit_number",
            "address",
            "city",
            "zip_code",
            "parcel_number",
            "latitude",
            "longitude",
            "owner_name",
            "applicant_name",
            "contractor_name",
            "install_date",
            "permit_date",
            "expiration_date",
            "system_type_raw",
            "tank_size_gallons",
            "drainfield_size_sqft",
            "bedrooms",
            "daily_flow_gpd",
            "pdf_url",
            "permit_url",
        ]

        for field in check_fields:
            old_val = getattr(existing, field, None)
            new_val = new_data.get(field)

            if hasattr(old_val, "isoformat"):
                old_val = str(old_val)
            if hasattr(new_val, "isoformat"):
                new_val = str(new_val)

            if old_val != new_val and new_val is not None:
                changed.append(field)

        return changed

    async def ingest_permit(self, permit_data: PermitCreate) -> Tuple[Optional[uuid.UUID], str]:
        """
        Ingest a single permit record.

        Returns:
            Tuple of (permit_id, action) where action is 'inserted', 'updated', or 'skipped'
        """
        try:
            # Get state ID
            state_id = await self._get_or_create_state(permit_data.state_code)
            if not state_id:
                logger.warning(f"Unknown state code: {permit_data.state_code}")
                return None, "error"

            # Get county ID
            county_id = await self._get_or_create_county(permit_data.county_name, state_id)

            # Normalize address
            address_normalized = normalize_address(permit_data.address)
            owner_normalized = normalize_owner_name(permit_data.owner_name)

            # Compute address hash for deduplication
            result = await self.db.execute(select(State).where(State.id == state_id))
            state = result.scalar_one_or_none()
            address_hash = compute_address_hash(
                address_normalized, permit_data.county_name, state.code if state else None
            )

            # Look for existing permit
            existing = await self._find_existing_permit(address_hash, permit_data.permit_number, state_id, county_id)

            # Prepare permit data dict
            data_dict = {
                "permit_number": permit_data.permit_number,
                "address": permit_data.address,
                "address_normalized": address_normalized,
                "city": permit_data.city,
                "zip_code": permit_data.zip_code,
                "parcel_number": permit_data.parcel_number,
                "latitude": permit_data.latitude,
                "longitude": permit_data.longitude,
                "owner_name": permit_data.owner_name,
                "applicant_name": permit_data.applicant_name,
                "contractor_name": permit_data.contractor_name,
                "install_date": permit_data.install_date,
                "permit_date": permit_data.permit_date,
                "expiration_date": permit_data.expiration_date,
                "system_type_raw": permit_data.system_type,
                "tank_size_gallons": permit_data.tank_size_gallons,
                "drainfield_size_sqft": permit_data.drainfield_size_sqft,
                "bedrooms": permit_data.bedrooms,
                "daily_flow_gpd": permit_data.daily_flow_gpd,
                "pdf_url": permit_data.pdf_url,
                "permit_url": permit_data.permit_url,
                "source_portal_code": permit_data.source_portal_code,
                "scraped_at": permit_data.scraped_at,
                "raw_data": permit_data.raw_data,
            }

            if existing:
                # Check if data actually changed
                new_hash = self._compute_record_hash(data_dict)
                if existing.record_hash == new_hash:
                    return existing.id, "skipped"

                # Data changed - create version and update
                changed_fields = self._get_changed_fields(existing, data_dict)
                await self._create_version(existing, "scraper", changed_fields)

                # Update existing record
                for field, value in data_dict.items():
                    if value is not None:
                        setattr(existing, field, value)

                existing.address_hash = address_hash
                existing.owner_name_normalized = owner_normalized
                existing.system_type_id = await self._get_system_type_id(permit_data.system_type)
                existing.source_portal_id = await self._get_or_create_portal(permit_data.source_portal_code, state_id)
                existing.version += 1
                existing.record_hash = new_hash
                existing.updated_at = datetime.utcnow()

                return existing.id, "updated"

            else:
                # Create new permit
                permit_id = uuid.uuid4()
                new_permit = SepticPermit(
                    id=permit_id,
                    state_id=state_id,
                    county_id=county_id,
                    address_hash=address_hash,
                    owner_name_normalized=owner_normalized,
                    system_type_id=await self._get_system_type_id(permit_data.system_type),
                    source_portal_id=await self._get_or_create_portal(permit_data.source_portal_code, state_id),
                    is_active=True,
                    version=1,
                    **data_dict,
                )
                new_permit.record_hash = self._compute_record_hash(data_dict)

                self.db.add(new_permit)
                return permit_id, "inserted"

        except IntegrityError as e:
            logger.warning(f"Integrity error ingesting permit: {e}")
            await self.db.rollback()
            return None, "error"
        except Exception as e:
            logger.error(f"Error ingesting permit: {e}")
            return None, "error"

    async def ingest_batch(self, permits: List[PermitCreate], source_portal_code: str) -> BatchIngestionResponse:
        """
        Ingest a batch of permits.

        Args:
            permits: List of permit records to ingest
            source_portal_code: Source portal identifier

        Returns:
            BatchIngestionResponse with statistics
        """
        start_time = time.time()
        batch_id = uuid.uuid4()

        # Create import batch record (graceful if table missing)
        import_batch = None
        try:
            import_batch = PermitImportBatch(
                id=batch_id,
                source_name=source_portal_code,
                total_records=len(permits),
                status="processing",
                started_at=datetime.utcnow(),
            )
            self.db.add(import_batch)
            await self.db.commit()
        except Exception as e:
            logger.warning(f"Could not create import batch record (table may not exist): {e}")
            await self.db.rollback()
            import_batch = None

        stats = BatchIngestionStats(
            batch_id=batch_id, source_portal_code=source_portal_code, total_records=len(permits)
        )

        errors = []

        for i, permit_data in enumerate(permits):
            try:
                permit_id, action = await self.ingest_permit(permit_data)

                if action == "inserted":
                    stats.inserted += 1
                elif action == "updated":
                    stats.updated += 1
                elif action == "skipped":
                    stats.skipped += 1
                elif action == "error":
                    stats.errors += 1
                    errors.append({"index": i, "permit_number": permit_data.permit_number, "error": "Failed to ingest"})

                # Commit every 100 records
                if (i + 1) % 100 == 0:
                    await self.db.commit()
                    logger.info(f"Processed {i + 1}/{len(permits)} permits")

            except Exception as e:
                stats.errors += 1
                errors.append(
                    {"index": i, "permit_number": getattr(permit_data, "permit_number", "unknown"), "error": str(e)}
                )
                await self.db.rollback()

        # Final commit
        await self.db.commit()

        # Update source portal stats
        portal_id = self._portal_cache.get(source_portal_code)
        if portal_id:
            result = await self.db.execute(select(SourcePortal).where(SourcePortal.id == portal_id))
            portal = result.scalar_one_or_none()
            if portal:
                portal.last_scraped_at = datetime.utcnow()
                portal.total_records_scraped += stats.inserted + stats.updated

        # Update import batch (if tracking table exists)
        elapsed = time.time() - start_time
        if import_batch is not None:
            try:
                import_batch.status = "completed" if stats.errors == 0 else "completed_with_errors"
                import_batch.completed_at = datetime.utcnow()
                import_batch.processing_time_seconds = elapsed
                import_batch.inserted = stats.inserted
                import_batch.updated = stats.updated
                import_batch.skipped = stats.skipped
                import_batch.errors = stats.errors
                import_batch.error_details = errors if errors else None
                await self.db.commit()
            except Exception as e:
                logger.warning(f"Could not update import batch record: {e}")
                await self.db.rollback()
        else:
            await self.db.commit()

        stats.processing_time_seconds = elapsed
        stats.error_details = errors if errors else None

        logger.info(
            f"Batch ingestion complete: {stats.inserted} inserted, "
            f"{stats.updated} updated, {stats.skipped} skipped, "
            f"{stats.errors} errors in {elapsed:.2f}s"
        )

        return BatchIngestionResponse(
            status="completed" if stats.errors == 0 else "completed_with_errors",
            stats=stats,
            message=f"Processed {len(permits)} records",
        )


# Factory function for easy service creation
def get_permit_ingestion_service(db: AsyncSession) -> PermitIngestionService:
    """Create a permit ingestion service instance."""
    return PermitIngestionService(db)
