"""Employee extension CRUD tests."""
from datetime import date, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.hr.employees.models import HrEmployeeCertification, HrTruckAssignment
from app.hr.employees.schemas import (
    AccessGrantIn,
    CertificationIn,
    CertificationPatch,
    DocumentIn,
    TruckAssignmentIn,
)
from app.hr.employees.services import (
    assign_truck,
    close_truck_assignment,
    create_certification,
    grant_access,
    list_certifications_for_employee,
    list_expiring_certifications,
    patch_certification,
    revoke_access,
    upload_document,
)
from app.models.technician import Technician


@pytest_asyncio.fixture
async def technician(db):
    tech = Technician(first_name="Tech", last_name="Worker", email="t@example.com")
    db.add(tech)
    await db.commit()
    await db.refresh(tech)
    return tech


@pytest.mark.asyncio
async def test_create_and_list_certifications(db, technician):
    await create_certification(
        db,
        employee_id=technician.id,
        payload=CertificationIn(kind="cdl_class_b", number="CDL-12345"),
        actor_user_id=None,
    )
    await db.commit()

    rows = await list_certifications_for_employee(db, employee_id=technician.id)
    assert len(rows) == 1
    assert rows[0].number == "CDL-12345"


@pytest.mark.asyncio
async def test_expiring_certifications_window(db, technician):
    await create_certification(
        db,
        employee_id=technician.id,
        payload=CertificationIn(
            kind="dot_medical", expires_at=date.today() + timedelta(days=10)
        ),
        actor_user_id=None,
    )
    await create_certification(
        db,
        employee_id=technician.id,
        payload=CertificationIn(
            kind="tceq_os0", expires_at=date.today() + timedelta(days=90)
        ),
        actor_user_id=None,
    )
    await db.commit()

    in_30 = await list_expiring_certifications(db, days=30)
    assert len(in_30) == 1
    assert in_30[0].kind == "dot_medical"


@pytest.mark.asyncio
async def test_patch_certification(db, technician):
    cert = await create_certification(
        db,
        employee_id=technician.id,
        payload=CertificationIn(kind="cdl_class_b"),
        actor_user_id=None,
    )
    await db.commit()
    updated = await patch_certification(
        db,
        cert_id=cert.id,
        payload=CertificationPatch(number="NEW-NUM", status="active"),
        actor_user_id=None,
    )
    await db.commit()
    assert updated.number == "NEW-NUM"


@pytest.mark.asyncio
async def test_patch_unknown_cert_returns_none(db):
    result = await patch_certification(
        db, cert_id=uuid4(), payload=CertificationPatch(number="x"), actor_user_id=None
    )
    assert result is None


@pytest.mark.asyncio
async def test_assign_and_close_truck(db, technician):
    # Create a fake asset id — tests only need a UUID, not FK integrity on sqlite.
    from app.models.asset import Asset
    asset = Asset(name="Truck 1", asset_type="vehicle", category="vacuum_truck")
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    assignment = await assign_truck(
        db,
        employee_id=technician.id,
        payload=TruckAssignmentIn(truck_id=str(asset.id)),
        actor_user_id=None,
    )
    await db.commit()
    assert assignment.unassigned_at is None

    closed = await close_truck_assignment(
        db, assignment_id=assignment.id, actor_user_id=None
    )
    await db.commit()
    assert closed.unassigned_at is not None


@pytest.mark.asyncio
async def test_grant_and_revoke_access(db, technician):
    grant = await grant_access(
        db,
        employee_id=technician.id,
        payload=AccessGrantIn(system="crm", identifier="jdoe@example.com"),
        actor_user_id=None,
    )
    await db.commit()
    assert grant.revoked_at is None

    revoked = await revoke_access(db, grant_id=grant.id, actor_user_id=None)
    await db.commit()
    assert revoked.revoked_at is not None


@pytest.mark.asyncio
async def test_upload_document(db, technician):
    doc = await upload_document(
        db,
        employee_id=technician.id,
        payload=DocumentIn(kind="i9", storage_key="abc.pdf"),
        actor_user_id=None,
    )
    await db.commit()
    assert doc.kind == "i9"
    assert doc.storage_key == "abc.pdf"


@pytest.mark.asyncio
async def test_employee_certifications_admin_api(authed_client, db):
    from app.models.technician import Technician

    tech = Technician(first_name="API", last_name="Tech", email="api@x.com")
    db.add(tech)
    await db.commit()
    await db.refresh(tech)

    # Create
    r = await authed_client.post(
        f"/api/v2/hr/employees/{tech.id}/certifications",
        json={"kind": "cdl_class_b", "number": "CDL-API"},
    )
    assert r.status_code == 201, r.text
    cert_id = r.json()["id"]

    # List
    r = await authed_client.get(f"/api/v2/hr/employees/{tech.id}/certifications")
    assert r.status_code == 200
    assert len(r.json()) == 1

    # Patch
    r = await authed_client.patch(
        f"/api/v2/hr/employees/{tech.id}/certifications/{cert_id}",
        json={"number": "CDL-UPDATED"},
    )
    assert r.status_code == 200
    assert r.json()["number"] == "CDL-UPDATED"


@pytest.mark.asyncio
async def test_unauth_rejected(client):
    r = await client.get(f"/api/v2/hr/employees/{uuid4()}/certifications")
    assert r.status_code == 401
