from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.hr.employees.schemas import (
    AccessGrantIn,
    AccessGrantOut,
    CertificationIn,
    CertificationOut,
    CertificationPatch,
    DocumentIn,
    DocumentOut,
    FuelCardAssignmentIn,
    FuelCardAssignmentOut,
    TruckAssignmentIn,
    TruckAssignmentOut,
)
from app.hr.employees.services import (
    assign_fuel_card,
    assign_truck,
    close_fuel_card_assignment,
    close_truck_assignment,
    create_certification,
    grant_access,
    list_access_grants_for_employee,
    list_certifications_for_employee,
    list_documents_for_employee,
    open_truck_assignments_for_employee,
    patch_certification,
    revoke_access,
    upload_document,
)


employees_router = APIRouter(prefix="/employees", tags=["hr-employees"])


# ── Certifications ──────────────────────────────────────────────────────

@employees_router.get("/{employee_id}/certifications", response_model=list[CertificationOut])
async def list_certs(
    employee_id: UUID, db: DbSession, user: CurrentUser
) -> list[CertificationOut]:
    rows = await list_certifications_for_employee(db, employee_id=employee_id)
    return [CertificationOut.model_validate(r) for r in rows]


@employees_router.post(
    "/{employee_id}/certifications",
    response_model=CertificationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_cert(
    employee_id: UUID,
    payload: CertificationIn,
    db: DbSession,
    user: CurrentUser,
) -> CertificationOut:
    row = await create_certification(
        db, employee_id=employee_id, payload=payload, actor_user_id=user.id
    )
    await db.commit()
    return CertificationOut.model_validate(row)


@employees_router.patch(
    "/{employee_id}/certifications/{cert_id}",
    response_model=CertificationOut,
)
async def patch_cert(
    employee_id: UUID,
    cert_id: UUID,
    payload: CertificationPatch,
    db: DbSession,
    user: CurrentUser,
) -> CertificationOut:
    row = await patch_certification(
        db, cert_id=cert_id, payload=payload, actor_user_id=user.id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="certification not found")
    await db.commit()
    return CertificationOut.model_validate(row)


# ── Documents ───────────────────────────────────────────────────────────

@employees_router.get("/{employee_id}/documents", response_model=list[DocumentOut])
async def list_docs(
    employee_id: UUID, db: DbSession, user: CurrentUser
) -> list[DocumentOut]:
    rows = await list_documents_for_employee(db, employee_id=employee_id)
    return [DocumentOut.model_validate(r) for r in rows]


@employees_router.post(
    "/{employee_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_doc(
    employee_id: UUID,
    payload: DocumentIn,
    db: DbSession,
    user: CurrentUser,
) -> DocumentOut:
    row = await upload_document(
        db, employee_id=employee_id, payload=payload, actor_user_id=user.id
    )
    await db.commit()
    return DocumentOut.model_validate(row)


# ── Truck assignments ───────────────────────────────────────────────────

@employees_router.get(
    "/{employee_id}/truck-assignments",
    response_model=list[TruckAssignmentOut],
)
async def list_truck_assignments(
    employee_id: UUID, db: DbSession, user: CurrentUser
) -> list[TruckAssignmentOut]:
    rows = await open_truck_assignments_for_employee(db, employee_id=employee_id)
    return [TruckAssignmentOut.model_validate(r) for r in rows]


@employees_router.post(
    "/{employee_id}/truck-assignments",
    response_model=TruckAssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_truck_assignment(
    employee_id: UUID,
    payload: TruckAssignmentIn,
    db: DbSession,
    user: CurrentUser,
) -> TruckAssignmentOut:
    row = await assign_truck(
        db, employee_id=employee_id, payload=payload, actor_user_id=user.id
    )
    await db.commit()
    return TruckAssignmentOut.model_validate(row)


@employees_router.delete(
    "/{employee_id}/truck-assignments/{assignment_id}",
    response_model=TruckAssignmentOut,
)
async def close_truck_assignment_endpoint(
    employee_id: UUID,
    assignment_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> TruckAssignmentOut:
    row = await close_truck_assignment(
        db, assignment_id=assignment_id, actor_user_id=user.id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="assignment not found")
    await db.commit()
    return TruckAssignmentOut.model_validate(row)


# ── Fuel card assignments ───────────────────────────────────────────────

@employees_router.post(
    "/{employee_id}/fuel-card-assignments",
    response_model=FuelCardAssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_fuel_card_assignment(
    employee_id: UUID,
    payload: FuelCardAssignmentIn,
    db: DbSession,
    user: CurrentUser,
) -> FuelCardAssignmentOut:
    row = await assign_fuel_card(
        db, employee_id=employee_id, payload=payload, actor_user_id=user.id
    )
    await db.commit()
    return FuelCardAssignmentOut.model_validate(row)


@employees_router.delete(
    "/{employee_id}/fuel-card-assignments/{assignment_id}",
    response_model=FuelCardAssignmentOut,
)
async def close_fuel_card_endpoint(
    employee_id: UUID,
    assignment_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> FuelCardAssignmentOut:
    row = await close_fuel_card_assignment(
        db, assignment_id=assignment_id, actor_user_id=user.id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="assignment not found")
    await db.commit()
    return FuelCardAssignmentOut.model_validate(row)


# ── Access grants ──────────────────────────────────────────────────────

@employees_router.get(
    "/{employee_id}/access-grants", response_model=list[AccessGrantOut]
)
async def list_grants(
    employee_id: UUID, db: DbSession, user: CurrentUser
) -> list[AccessGrantOut]:
    rows = await list_access_grants_for_employee(db, employee_id=employee_id)
    return [AccessGrantOut.model_validate(r) for r in rows]


@employees_router.post(
    "/{employee_id}/access-grants",
    response_model=AccessGrantOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_grant(
    employee_id: UUID,
    payload: AccessGrantIn,
    db: DbSession,
    user: CurrentUser,
) -> AccessGrantOut:
    row = await grant_access(
        db, employee_id=employee_id, payload=payload, actor_user_id=user.id
    )
    await db.commit()
    return AccessGrantOut.model_validate(row)


@employees_router.delete(
    "/{employee_id}/access-grants/{grant_id}",
    response_model=AccessGrantOut,
)
async def revoke_grant_endpoint(
    employee_id: UUID,
    grant_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> AccessGrantOut:
    row = await revoke_access(db, grant_id=grant_id, actor_user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="grant not found")
    await db.commit()
    return AccessGrantOut.model_validate(row)
