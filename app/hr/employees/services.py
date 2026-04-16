"""Employee-extension service layer.

Each mutation writes an audit row; every function is idempotent-friendly
(closing an already-closed assignment is a no-op).
"""
from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.employees.models import (
    HrAccessGrant,
    HrEmployeeCertification,
    HrEmployeeDocument,
    HrFuelCardAssignment,
    HrTruckAssignment,
)
from app.hr.employees.schemas import (
    AccessGrantIn,
    CertificationIn,
    CertificationPatch,
    DocumentIn,
    FuelCardAssignmentIn,
    TruckAssignmentIn,
)
from app.hr.shared.audit import write_audit


# ── Certifications ──────────────────────────────────────────────────────

async def create_certification(
    db: AsyncSession,
    *,
    employee_id: UUID,
    payload: CertificationIn,
    actor_user_id: int | None,
) -> HrEmployeeCertification:
    row = HrEmployeeCertification(employee_id=employee_id, **payload.model_dump())
    db.add(row)
    await db.flush()
    await write_audit(
        db,
        entity_type="employee_certification",
        entity_id=row.id,
        event="created",
        diff={"kind": [None, row.kind], "employee_id": [None, str(employee_id)]},
        actor_user_id=actor_user_id,
    )
    return row


async def patch_certification(
    db: AsyncSession,
    *,
    cert_id: UUID,
    payload: CertificationPatch,
    actor_user_id: int | None,
) -> HrEmployeeCertification | None:
    row = (
        await db.execute(
            select(HrEmployeeCertification).where(HrEmployeeCertification.id == cert_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    diff = {}
    for k, v in data.items():
        cur = getattr(row, k)
        if cur != v:
            diff[k] = [str(cur) if cur is not None else None, str(v) if v is not None else None]
            setattr(row, k, v)
    await db.flush()
    if diff:
        await write_audit(
            db,
            entity_type="employee_certification",
            entity_id=row.id,
            event="updated",
            diff=diff,
            actor_user_id=actor_user_id,
        )
    return row


async def list_certifications_for_employee(
    db: AsyncSession, *, employee_id: UUID
) -> list[HrEmployeeCertification]:
    stmt = (
        select(HrEmployeeCertification)
        .where(HrEmployeeCertification.employee_id == employee_id)
        .order_by(HrEmployeeCertification.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_expiring_certifications(
    db: AsyncSession, *, days: int
) -> list[HrEmployeeCertification]:
    """Certs whose expires_at is within `days` days from today (inclusive)."""
    today = date.today()
    cutoff = today + timedelta(days=days)
    stmt = (
        select(HrEmployeeCertification)
        .where(
            HrEmployeeCertification.expires_at.is_not(None),
            HrEmployeeCertification.expires_at <= cutoff,
            HrEmployeeCertification.expires_at >= today,
            HrEmployeeCertification.status == "active",
        )
        .order_by(HrEmployeeCertification.expires_at.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


# ── Documents ───────────────────────────────────────────────────────────

async def upload_document(
    db: AsyncSession,
    *,
    employee_id: UUID,
    payload: DocumentIn,
    actor_user_id: int | None,
) -> HrEmployeeDocument:
    data = payload.model_dump()
    signed_id = data.pop("signed_document_id", None)
    row = HrEmployeeDocument(
        employee_id=employee_id,
        signed_document_id=UUID(signed_id) if signed_id else None,
        uploaded_by=actor_user_id,
        **data,
    )
    db.add(row)
    await db.flush()
    await write_audit(
        db,
        entity_type="employee_document",
        entity_id=row.id,
        event="uploaded",
        diff={"kind": [None, row.kind]},
        actor_user_id=actor_user_id,
    )
    return row


async def list_documents_for_employee(
    db: AsyncSession, *, employee_id: UUID
) -> list[HrEmployeeDocument]:
    stmt = (
        select(HrEmployeeDocument)
        .where(HrEmployeeDocument.employee_id == employee_id)
        .order_by(HrEmployeeDocument.uploaded_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


# ── Truck assignments ───────────────────────────────────────────────────

async def assign_truck(
    db: AsyncSession,
    *,
    employee_id: UUID,
    payload: TruckAssignmentIn,
    actor_user_id: int | None,
) -> HrTruckAssignment:
    row = HrTruckAssignment(
        employee_id=employee_id,
        truck_id=UUID(payload.truck_id),
        assigned_by=actor_user_id,
    )
    db.add(row)
    await db.flush()
    await write_audit(
        db,
        entity_type="truck_assignment",
        entity_id=row.id,
        event="assigned",
        diff={"truck_id": [None, str(row.truck_id)]},
        actor_user_id=actor_user_id,
    )
    return row


async def close_truck_assignment(
    db: AsyncSession, *, assignment_id: UUID, actor_user_id: int | None
) -> HrTruckAssignment | None:
    row = (
        await db.execute(
            select(HrTruckAssignment).where(HrTruckAssignment.id == assignment_id)
        )
    ).scalar_one_or_none()
    if row is None or row.unassigned_at is not None:
        return row
    row.unassigned_at = datetime.utcnow()
    row.unassigned_by = actor_user_id
    await db.flush()
    await write_audit(
        db,
        entity_type="truck_assignment",
        entity_id=row.id,
        event="closed",
        diff={"unassigned_at": [None, row.unassigned_at.isoformat()]},
        actor_user_id=actor_user_id,
    )
    return row


async def open_truck_assignments_for_employee(
    db: AsyncSession, *, employee_id: UUID
) -> list[HrTruckAssignment]:
    stmt = (
        select(HrTruckAssignment)
        .where(
            HrTruckAssignment.employee_id == employee_id,
            HrTruckAssignment.unassigned_at.is_(None),
        )
        .order_by(HrTruckAssignment.assigned_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


# ── Fuel card assignments ───────────────────────────────────────────────

async def assign_fuel_card(
    db: AsyncSession,
    *,
    employee_id: UUID,
    payload: FuelCardAssignmentIn,
    actor_user_id: int | None,
) -> HrFuelCardAssignment:
    row = HrFuelCardAssignment(
        employee_id=employee_id,
        card_id=UUID(payload.card_id),
        assigned_by=actor_user_id,
    )
    db.add(row)
    await db.flush()
    await write_audit(
        db,
        entity_type="fuel_card_assignment",
        entity_id=row.id,
        event="assigned",
        diff={"card_id": [None, str(row.card_id)]},
        actor_user_id=actor_user_id,
    )
    return row


async def close_fuel_card_assignment(
    db: AsyncSession, *, assignment_id: UUID, actor_user_id: int | None
) -> HrFuelCardAssignment | None:
    row = (
        await db.execute(
            select(HrFuelCardAssignment).where(HrFuelCardAssignment.id == assignment_id)
        )
    ).scalar_one_or_none()
    if row is None or row.unassigned_at is not None:
        return row
    row.unassigned_at = datetime.utcnow()
    row.unassigned_by = actor_user_id
    await db.flush()
    await write_audit(
        db,
        entity_type="fuel_card_assignment",
        entity_id=row.id,
        event="closed",
        diff={"unassigned_at": [None, row.unassigned_at.isoformat()]},
        actor_user_id=actor_user_id,
    )
    return row


# ── Access grants ──────────────────────────────────────────────────────

async def grant_access(
    db: AsyncSession,
    *,
    employee_id: UUID,
    payload: AccessGrantIn,
    actor_user_id: int | None,
) -> HrAccessGrant:
    row = HrAccessGrant(
        employee_id=employee_id,
        system=payload.system,
        identifier=payload.identifier,
        granted_by=actor_user_id,
    )
    db.add(row)
    await db.flush()
    await write_audit(
        db,
        entity_type="access_grant",
        entity_id=row.id,
        event="granted",
        diff={"system": [None, row.system]},
        actor_user_id=actor_user_id,
    )
    return row


async def revoke_access(
    db: AsyncSession, *, grant_id: UUID, actor_user_id: int | None
) -> HrAccessGrant | None:
    row = (
        await db.execute(select(HrAccessGrant).where(HrAccessGrant.id == grant_id))
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return row
    row.revoked_at = datetime.utcnow()
    row.revoked_by = actor_user_id
    await db.flush()
    await write_audit(
        db,
        entity_type="access_grant",
        entity_id=row.id,
        event="revoked",
        diff={"revoked_at": [None, row.revoked_at.isoformat()]},
        actor_user_id=actor_user_id,
    )
    return row


async def list_access_grants_for_employee(
    db: AsyncSession, *, employee_id: UUID
) -> list[HrAccessGrant]:
    stmt = (
        select(HrAccessGrant)
        .where(HrAccessGrant.employee_id == employee_id)
        .order_by(HrAccessGrant.granted_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())
