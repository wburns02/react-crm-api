"""Compliance API - Licenses, Certifications, and Inspections.

Features:
- CRUD for licenses, certifications, inspections
- Expiring items dashboard
- Compliance summary reports
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, or_, and_
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
import logging
import uuid

from app.api.deps import DbSession, CurrentUser
from app.models.license import License
from app.models.certification import Certification
from app.models.inspection import Inspection

logger = logging.getLogger(__name__)
router = APIRouter()


# ========================
# Pydantic Schemas
# ========================


# License Schemas
class LicenseCreate(BaseModel):
    license_number: str
    license_type: str
    issuing_authority: Optional[str] = None
    issuing_state: Optional[str] = None
    holder_type: str = "business"
    holder_id: Optional[str] = None
    holder_name: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: date
    document_url: Optional[str] = None
    notes: Optional[str] = None


class LicenseUpdate(BaseModel):
    license_number: Optional[str] = None
    license_type: Optional[str] = None
    issuing_authority: Optional[str] = None
    issuing_state: Optional[str] = None
    holder_type: Optional[str] = None
    holder_id: Optional[str] = None
    holder_name: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    status: Optional[str] = None
    document_url: Optional[str] = None
    notes: Optional[str] = None


class LicenseResponse(BaseModel):
    id: str
    license_number: str
    license_type: str
    issuing_authority: Optional[str] = None
    issuing_state: Optional[str] = None
    holder_type: str
    holder_id: Optional[str] = None
    holder_name: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: date
    status: str
    days_until_expiry: Optional[int] = None
    document_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Certification Schemas
class CertificationCreate(BaseModel):
    name: str
    certification_type: str
    certification_number: Optional[str] = None
    issuing_organization: Optional[str] = None
    technician_id: str
    technician_name: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    training_hours: Optional[int] = None
    training_date: Optional[date] = None
    training_provider: Optional[str] = None
    document_url: Optional[str] = None
    notes: Optional[str] = None


class CertificationUpdate(BaseModel):
    name: Optional[str] = None
    certification_type: Optional[str] = None
    certification_number: Optional[str] = None
    issuing_organization: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    status: Optional[str] = None
    training_hours: Optional[int] = None
    document_url: Optional[str] = None
    notes: Optional[str] = None


class CertificationResponse(BaseModel):
    id: str
    name: str
    certification_type: str
    certification_number: Optional[str] = None
    issuing_organization: Optional[str] = None
    technician_id: str
    technician_name: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    status: str
    days_until_expiry: Optional[int] = None
    training_hours: Optional[int] = None
    document_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Inspection Schemas
class InspectionCreate(BaseModel):
    inspection_type: str
    customer_id: int
    property_address: Optional[str] = None
    system_type: Optional[str] = None
    system_age_years: Optional[int] = None
    tank_size_gallons: Optional[int] = None
    scheduled_date: Optional[date] = None
    technician_id: Optional[str] = None
    technician_name: Optional[str] = None
    work_order_id: Optional[str] = None
    inspection_fee: Optional[float] = None
    notes: Optional[str] = None


class InspectionUpdate(BaseModel):
    inspection_type: Optional[str] = None
    property_address: Optional[str] = None
    system_type: Optional[str] = None
    scheduled_date: Optional[date] = None
    completed_date: Optional[date] = None
    technician_id: Optional[str] = None
    technician_name: Optional[str] = None
    status: Optional[str] = None
    result: Optional[str] = None
    overall_condition: Optional[str] = None
    checklist: Optional[list] = None
    sludge_depth_inches: Optional[float] = None
    scum_depth_inches: Optional[float] = None
    liquid_depth_inches: Optional[float] = None
    requires_followup: Optional[bool] = None
    followup_due_date: Optional[date] = None
    violations_found: Optional[list] = None
    corrective_actions: Optional[str] = None
    notes: Optional[str] = None


class InspectionResponse(BaseModel):
    id: str
    inspection_number: str
    inspection_type: str
    customer_id: int
    property_address: Optional[str] = None
    system_type: Optional[str] = None
    scheduled_date: Optional[date] = None
    completed_date: Optional[date] = None
    technician_id: Optional[str] = None
    technician_name: Optional[str] = None
    status: str
    result: Optional[str] = None
    overall_condition: Optional[str] = None
    requires_followup: bool
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# List Response
class ListResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    page_size: int


# Dashboard Response
class ComplianceDashboardResponse(BaseModel):
    expiring_licenses: List[dict]
    expiring_certifications: List[dict]
    pending_inspections: List[dict]
    overdue_inspections: List[dict]
    summary: dict


# ========================
# License Endpoints
# ========================


@router.get("/licenses", response_model=ListResponse)
async def list_licenses(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    holder_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    expiring_within_days: Optional[int] = Query(None, description="Show licenses expiring within N days"),
):
    """List all licenses with filtering."""
    try:
        query = select(License)

        if holder_type:
            query = query.where(License.holder_type == holder_type)
        if status:
            query = query.where(License.status == status)
        if expiring_within_days:
            expiry_threshold = date.today() + timedelta(days=expiring_within_days)
            query = query.where(License.expiry_date <= expiry_threshold)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(License.expiry_date)

        result = await db.execute(query)
        licenses = result.scalars().all()

        return {
            "items": [
                {
                    "id": str(lic.id),
                    "license_number": lic.license_number,
                    "license_type": lic.license_type,
                    "holder_type": lic.holder_type,
                    "holder_name": lic.holder_name,
                    "expiry_date": lic.expiry_date,
                    "status": lic.status,
                    "days_until_expiry": lic.days_until_expiry,
                }
                for lic in licenses
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"Error listing licenses: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/licenses", response_model=LicenseResponse, status_code=status.HTTP_201_CREATED)
async def create_license(
    license_data: LicenseCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new license."""
    try:
        license_obj = License(**license_data.model_dump())
        db.add(license_obj)
        await db.commit()
        await db.refresh(license_obj)

        return {
            "id": str(license_obj.id),
            "license_number": license_obj.license_number,
            "license_type": license_obj.license_type,
            "issuing_authority": license_obj.issuing_authority,
            "issuing_state": license_obj.issuing_state,
            "holder_type": license_obj.holder_type,
            "holder_id": license_obj.holder_id,
            "holder_name": license_obj.holder_name,
            "issue_date": license_obj.issue_date,
            "expiry_date": license_obj.expiry_date,
            "status": license_obj.status,
            "days_until_expiry": license_obj.days_until_expiry,
            "document_url": license_obj.document_url,
            "notes": license_obj.notes,
            "created_at": license_obj.created_at,
        }
    except Exception as e:
        logger.error(f"Error creating license: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/licenses/{license_id}", response_model=LicenseResponse)
async def get_license(
    license_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific license."""
    try:
        result = await db.execute(select(License).where(License.id == uuid.UUID(license_id)))
        license_obj = result.scalar_one_or_none()

        if not license_obj:
            raise HTTPException(status_code=404, detail="License not found")

        return {
            "id": str(license_obj.id),
            "license_number": license_obj.license_number,
            "license_type": license_obj.license_type,
            "issuing_authority": license_obj.issuing_authority,
            "issuing_state": license_obj.issuing_state,
            "holder_type": license_obj.holder_type,
            "holder_id": license_obj.holder_id,
            "holder_name": license_obj.holder_name,
            "issue_date": license_obj.issue_date,
            "expiry_date": license_obj.expiry_date,
            "status": license_obj.status,
            "days_until_expiry": license_obj.days_until_expiry,
            "document_url": license_obj.document_url,
            "notes": license_obj.notes,
            "created_at": license_obj.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting license {license_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/licenses/{license_id}", response_model=LicenseResponse)
async def update_license(
    license_id: str,
    update_data: LicenseUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a license."""
    try:
        result = await db.execute(select(License).where(License.id == uuid.UUID(license_id)))
        license_obj = result.scalar_one_or_none()

        if not license_obj:
            raise HTTPException(status_code=404, detail="License not found")

        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(license_obj, key, value)

        await db.commit()
        await db.refresh(license_obj)

        return {
            "id": str(license_obj.id),
            "license_number": license_obj.license_number,
            "license_type": license_obj.license_type,
            "issuing_authority": license_obj.issuing_authority,
            "issuing_state": license_obj.issuing_state,
            "holder_type": license_obj.holder_type,
            "holder_id": license_obj.holder_id,
            "holder_name": license_obj.holder_name,
            "issue_date": license_obj.issue_date,
            "expiry_date": license_obj.expiry_date,
            "status": license_obj.status,
            "days_until_expiry": license_obj.days_until_expiry,
            "document_url": license_obj.document_url,
            "notes": license_obj.notes,
            "created_at": license_obj.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating license {license_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/licenses/{license_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_license(
    license_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a license."""
    try:
        result = await db.execute(select(License).where(License.id == uuid.UUID(license_id)))
        license_obj = result.scalar_one_or_none()

        if not license_obj:
            raise HTTPException(status_code=404, detail="License not found")

        await db.delete(license_obj)
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting license {license_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Certification Endpoints
# ========================


@router.get("/certifications", response_model=ListResponse)
async def list_certifications(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    technician_id: Optional[str] = Query(None),
    certification_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    expiring_within_days: Optional[int] = Query(None),
):
    """List certifications with filtering."""
    try:
        query = select(Certification)

        if technician_id:
            query = query.where(Certification.technician_id == technician_id)
        if certification_type:
            query = query.where(Certification.certification_type == certification_type)
        if status:
            query = query.where(Certification.status == status)
        if expiring_within_days:
            expiry_threshold = date.today() + timedelta(days=expiring_within_days)
            query = query.where(Certification.expiry_date <= expiry_threshold)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Certification.expiry_date)

        result = await db.execute(query)
        certs = result.scalars().all()

        return {
            "items": [
                {
                    "id": str(cert.id),
                    "name": cert.name,
                    "certification_type": cert.certification_type,
                    "technician_id": cert.technician_id,
                    "technician_name": cert.technician_name,
                    "expiry_date": cert.expiry_date,
                    "status": cert.status,
                    "days_until_expiry": cert.days_until_expiry,
                }
                for cert in certs
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"Error listing certifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/certifications", response_model=CertificationResponse, status_code=status.HTTP_201_CREATED)
async def create_certification(
    cert_data: CertificationCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new certification."""
    try:
        cert = Certification(**cert_data.model_dump())
        db.add(cert)
        await db.commit()
        await db.refresh(cert)

        return {
            "id": str(cert.id),
            "name": cert.name,
            "certification_type": cert.certification_type,
            "certification_number": cert.certification_number,
            "issuing_organization": cert.issuing_organization,
            "technician_id": cert.technician_id,
            "technician_name": cert.technician_name,
            "issue_date": cert.issue_date,
            "expiry_date": cert.expiry_date,
            "status": cert.status,
            "days_until_expiry": cert.days_until_expiry,
            "training_hours": cert.training_hours,
            "document_url": cert.document_url,
            "notes": cert.notes,
            "created_at": cert.created_at,
        }
    except Exception as e:
        logger.error(f"Error creating certification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/certifications/{cert_id}", response_model=CertificationResponse)
async def get_certification(
    cert_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific certification."""
    try:
        result = await db.execute(select(Certification).where(Certification.id == uuid.UUID(cert_id)))
        cert = result.scalar_one_or_none()

        if not cert:
            raise HTTPException(status_code=404, detail="Certification not found")

        return {
            "id": str(cert.id),
            "name": cert.name,
            "certification_type": cert.certification_type,
            "certification_number": cert.certification_number,
            "issuing_organization": cert.issuing_organization,
            "technician_id": cert.technician_id,
            "technician_name": cert.technician_name,
            "issue_date": cert.issue_date,
            "expiry_date": cert.expiry_date,
            "status": cert.status,
            "days_until_expiry": cert.days_until_expiry,
            "training_hours": cert.training_hours,
            "document_url": cert.document_url,
            "notes": cert.notes,
            "created_at": cert.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting certification {cert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/certifications/{cert_id}", response_model=CertificationResponse)
async def update_certification(
    cert_id: str,
    update_data: CertificationUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a certification."""
    try:
        result = await db.execute(select(Certification).where(Certification.id == uuid.UUID(cert_id)))
        cert = result.scalar_one_or_none()

        if not cert:
            raise HTTPException(status_code=404, detail="Certification not found")

        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(cert, key, value)

        await db.commit()
        await db.refresh(cert)

        return {
            "id": str(cert.id),
            "name": cert.name,
            "certification_type": cert.certification_type,
            "certification_number": cert.certification_number,
            "issuing_organization": cert.issuing_organization,
            "technician_id": cert.technician_id,
            "technician_name": cert.technician_name,
            "issue_date": cert.issue_date,
            "expiry_date": cert.expiry_date,
            "status": cert.status,
            "days_until_expiry": cert.days_until_expiry,
            "training_hours": cert.training_hours,
            "document_url": cert.document_url,
            "notes": cert.notes,
            "created_at": cert.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating certification {cert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/certifications/{cert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certification(
    cert_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a certification."""
    try:
        result = await db.execute(select(Certification).where(Certification.id == uuid.UUID(cert_id)))
        cert = result.scalar_one_or_none()

        if not cert:
            raise HTTPException(status_code=404, detail="Certification not found")

        await db.delete(cert)
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting certification {cert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Inspection Endpoints
# ========================


def generate_inspection_number():
    """Generate unique inspection number."""
    from datetime import datetime

    return f"INS-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"


@router.get("/inspections", response_model=ListResponse)
async def list_inspections(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[int] = Query(None),
    technician_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    inspection_type: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
):
    """List inspections with filtering."""
    try:
        query = select(Inspection)

        if customer_id:
            query = query.where(Inspection.customer_id == customer_id)
        if technician_id:
            query = query.where(Inspection.technician_id == technician_id)
        if status:
            query = query.where(Inspection.status == status)
        if inspection_type:
            query = query.where(Inspection.inspection_type == inspection_type)
        if date_from:
            query = query.where(Inspection.scheduled_date >= date_from)
        if date_to:
            query = query.where(Inspection.scheduled_date <= date_to)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Inspection.scheduled_date.desc())

        result = await db.execute(query)
        inspections = result.scalars().all()

        return {
            "items": [
                {
                    "id": str(insp.id),
                    "inspection_number": insp.inspection_number,
                    "inspection_type": insp.inspection_type,
                    "customer_id": insp.customer_id,
                    "property_address": insp.property_address,
                    "scheduled_date": insp.scheduled_date,
                    "completed_date": insp.completed_date,
                    "status": insp.status,
                    "result": insp.result,
                    "technician_name": insp.technician_name,
                }
                for insp in inspections
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"Error listing inspections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inspections", response_model=InspectionResponse, status_code=status.HTTP_201_CREATED)
async def create_inspection(
    insp_data: InspectionCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new inspection."""
    try:
        insp = Inspection(inspection_number=generate_inspection_number(), **insp_data.model_dump())
        db.add(insp)
        await db.commit()
        await db.refresh(insp)

        return {
            "id": str(insp.id),
            "inspection_number": insp.inspection_number,
            "inspection_type": insp.inspection_type,
            "customer_id": insp.customer_id,
            "property_address": insp.property_address,
            "system_type": insp.system_type,
            "scheduled_date": insp.scheduled_date,
            "completed_date": insp.completed_date,
            "technician_id": insp.technician_id,
            "technician_name": insp.technician_name,
            "status": insp.status,
            "result": insp.result,
            "overall_condition": insp.overall_condition,
            "requires_followup": insp.requires_followup,
            "notes": insp.notes,
            "created_at": insp.created_at,
        }
    except Exception as e:
        logger.error(f"Error creating inspection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inspections/{inspection_id}", response_model=InspectionResponse)
async def get_inspection(
    inspection_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific inspection."""
    try:
        result = await db.execute(select(Inspection).where(Inspection.id == uuid.UUID(inspection_id)))
        insp = result.scalar_one_or_none()

        if not insp:
            raise HTTPException(status_code=404, detail="Inspection not found")

        return {
            "id": str(insp.id),
            "inspection_number": insp.inspection_number,
            "inspection_type": insp.inspection_type,
            "customer_id": insp.customer_id,
            "property_address": insp.property_address,
            "system_type": insp.system_type,
            "scheduled_date": insp.scheduled_date,
            "completed_date": insp.completed_date,
            "technician_id": insp.technician_id,
            "technician_name": insp.technician_name,
            "status": insp.status,
            "result": insp.result,
            "overall_condition": insp.overall_condition,
            "requires_followup": insp.requires_followup,
            "notes": insp.notes,
            "created_at": insp.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting inspection {inspection_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/inspections/{inspection_id}", response_model=InspectionResponse)
async def update_inspection(
    inspection_id: str,
    update_data: InspectionUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update an inspection."""
    try:
        result = await db.execute(select(Inspection).where(Inspection.id == uuid.UUID(inspection_id)))
        insp = result.scalar_one_or_none()

        if not insp:
            raise HTTPException(status_code=404, detail="Inspection not found")

        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(insp, key, value)

        await db.commit()
        await db.refresh(insp)

        return {
            "id": str(insp.id),
            "inspection_number": insp.inspection_number,
            "inspection_type": insp.inspection_type,
            "customer_id": insp.customer_id,
            "property_address": insp.property_address,
            "system_type": insp.system_type,
            "scheduled_date": insp.scheduled_date,
            "completed_date": insp.completed_date,
            "technician_id": insp.technician_id,
            "technician_name": insp.technician_name,
            "status": insp.status,
            "result": insp.result,
            "overall_condition": insp.overall_condition,
            "requires_followup": insp.requires_followup,
            "notes": insp.notes,
            "created_at": insp.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating inspection {inspection_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/inspections/{inspection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inspection(
    inspection_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete an inspection."""
    try:
        result = await db.execute(select(Inspection).where(Inspection.id == uuid.UUID(inspection_id)))
        insp = result.scalar_one_or_none()

        if not insp:
            raise HTTPException(status_code=404, detail="Inspection not found")

        await db.delete(insp)
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting inspection {inspection_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Dashboard Endpoint
# ========================


@router.get("/dashboard", response_model=ComplianceDashboardResponse)
async def get_compliance_dashboard(
    db: DbSession,
    current_user: CurrentUser,
    expiring_within_days: int = Query(30, description="Show items expiring within N days"),
):
    """Get compliance dashboard with expiring items and pending inspections."""
    try:
        expiry_threshold = date.today() + timedelta(days=expiring_within_days)
        today = date.today()

        # Expiring licenses
        lic_result = await db.execute(
            select(License)
            .where(License.expiry_date <= expiry_threshold, License.status == "active")
            .order_by(License.expiry_date)
            .limit(10)
        )
        expiring_licenses = [
            {
                "id": str(lic.id),
                "license_number": lic.license_number,
                "license_type": lic.license_type,
                "holder_name": lic.holder_name,
                "expiry_date": lic.expiry_date,
                "days_until_expiry": lic.days_until_expiry,
            }
            for lic in lic_result.scalars().all()
        ]

        # Expiring certifications
        cert_result = await db.execute(
            select(Certification)
            .where(Certification.expiry_date <= expiry_threshold, Certification.status == "active")
            .order_by(Certification.expiry_date)
            .limit(10)
        )
        expiring_certs = [
            {
                "id": str(cert.id),
                "name": cert.name,
                "technician_name": cert.technician_name,
                "expiry_date": cert.expiry_date,
                "days_until_expiry": cert.days_until_expiry,
            }
            for cert in cert_result.scalars().all()
        ]

        # Pending inspections
        pending_result = await db.execute(
            select(Inspection)
            .where(Inspection.status.in_(["pending", "scheduled"]))
            .order_by(Inspection.scheduled_date)
            .limit(10)
        )
        pending_inspections = [
            {
                "id": str(insp.id),
                "inspection_number": insp.inspection_number,
                "inspection_type": insp.inspection_type,
                "scheduled_date": insp.scheduled_date,
                "customer_id": insp.customer_id,
            }
            for insp in pending_result.scalars().all()
        ]

        # Overdue inspections
        overdue_result = await db.execute(
            select(Inspection)
            .where(Inspection.scheduled_date < today, Inspection.status.in_(["pending", "scheduled"]))
            .order_by(Inspection.scheduled_date)
            .limit(10)
        )
        overdue_inspections = [
            {
                "id": str(insp.id),
                "inspection_number": insp.inspection_number,
                "inspection_type": insp.inspection_type,
                "scheduled_date": insp.scheduled_date,
                "customer_id": insp.customer_id,
            }
            for insp in overdue_result.scalars().all()
        ]

        # Summary counts
        total_licenses = (await db.execute(select(func.count(License.id)))).scalar() or 0
        total_certs = (await db.execute(select(func.count(Certification.id)))).scalar() or 0
        total_inspections = (await db.execute(select(func.count(Inspection.id)))).scalar() or 0
        completed_inspections = (
            await db.execute(select(func.count(Inspection.id)).where(Inspection.status == "completed"))
        ).scalar() or 0

        return {
            "expiring_licenses": expiring_licenses,
            "expiring_certifications": expiring_certs,
            "pending_inspections": pending_inspections,
            "overdue_inspections": overdue_inspections,
            "summary": {
                "total_licenses": total_licenses,
                "expiring_licenses_count": len(expiring_licenses),
                "total_certifications": total_certs,
                "expiring_certifications_count": len(expiring_certs),
                "total_inspections": total_inspections,
                "completed_inspections": completed_inspections,
                "pending_inspections_count": len(pending_inspections),
                "overdue_inspections_count": len(overdue_inspections),
            },
        }
    except Exception as e:
        logger.error(f"Error getting compliance dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))
