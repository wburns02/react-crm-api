"""Cert expiry SMS job tests."""
from datetime import date, timedelta

import pytest
import pytest_asyncio

from app.hr.employees.services import create_certification
from app.hr.employees.schemas import CertificationIn
from app.models.technician import Technician


@pytest_asyncio.fixture
async def technician_with_phone(db):
    tech = Technician(
        first_name="Exp",
        last_name="iring",
        email="expire@example.com",
        phone="+15555550200",
    )
    db.add(tech)
    await db.commit()
    await db.refresh(tech)
    return tech


@pytest.mark.asyncio
async def test_notifies_cert_expiring_in_exactly_30_days(db, technician_with_phone, monkeypatch):
    from app.hr.shared import cert_expiry_job

    calls = []

    async def fake_send(to, body):
        calls.append({"to": to, "body": body})

    monkeypatch.setattr(cert_expiry_job, "_send", fake_send)

    await create_certification(
        db,
        employee_id=technician_with_phone.id,
        payload=CertificationIn(
            kind="dot_medical", expires_at=date.today() + timedelta(days=30)
        ),
        actor_user_id=None,
    )
    await db.commit()

    results = await cert_expiry_job.run_once_for_today(db)
    assert len(calls) == 1
    assert "DOT MEDICAL" in calls[0]["body"]
    assert "30 days" in calls[0]["body"]
    assert any(r["status"] == "ok" for r in results)


@pytest.mark.asyncio
async def test_does_not_notify_certs_outside_windows(db, technician_with_phone, monkeypatch):
    from app.hr.shared import cert_expiry_job

    calls = []

    async def fake_send(to, body):
        calls.append({"to": to, "body": body})

    monkeypatch.setattr(cert_expiry_job, "_send", fake_send)

    # 45 days out → no notification.
    await create_certification(
        db,
        employee_id=technician_with_phone.id,
        payload=CertificationIn(
            kind="tceq_os0", expires_at=date.today() + timedelta(days=45)
        ),
        actor_user_id=None,
    )
    await db.commit()
    await cert_expiry_job.run_once_for_today(db)
    assert calls == []


@pytest.mark.asyncio
async def test_skips_when_tech_has_no_phone(db, monkeypatch):
    from app.hr.shared import cert_expiry_job

    tech = Technician(first_name="No", last_name="Phone", email="nophone@x.com")
    db.add(tech)
    await db.commit()
    await db.refresh(tech)

    await create_certification(
        db,
        employee_id=tech.id,
        payload=CertificationIn(
            kind="cdl_class_b", expires_at=date.today() + timedelta(days=7)
        ),
        actor_user_id=None,
    )
    await db.commit()

    calls = []

    async def fake_send(to, body):
        calls.append({"to": to, "body": body})

    monkeypatch.setattr(cert_expiry_job, "_send", fake_send)

    results = await cert_expiry_job.run_once_for_today(db)
    assert calls == []
    assert any(r["reason"] == "no_phone" for r in results)


@pytest.mark.asyncio
async def test_hits_all_three_windows(db, technician_with_phone, monkeypatch):
    from app.hr.shared import cert_expiry_job

    for days in (30, 7, 1):
        await create_certification(
            db,
            employee_id=technician_with_phone.id,
            payload=CertificationIn(
                kind="dot_medical", expires_at=date.today() + timedelta(days=days)
            ),
            actor_user_id=None,
        )
    await db.commit()

    calls = []

    async def fake_send(to, body):
        calls.append(body)

    monkeypatch.setattr(cert_expiry_job, "_send", fake_send)

    await cert_expiry_job.run_once_for_today(db)
    assert len(calls) == 3
