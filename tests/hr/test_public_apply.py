import io

import pytest

from app.hr.recruiting.models import HrRequisition


async def _open_req(db, slug="p-tech"):
    r = HrRequisition(slug=slug, title="Public Tech", status="open", employment_type="full_time")
    db.add(r)
    await db.commit()
    return r


@pytest.mark.asyncio
async def test_apply_creates_applicant_and_application(client, db):
    await _open_req(db)

    data = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@public.com",
        "phone": "+15555550100",
        "sms_consent": "true",
    }
    files = {"resume": ("resume.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")}
    r = await client.post(
        "/api/v2/public/careers/p-tech/apply",
        data=data,
        files=files,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["stage"] == "applied"
    assert "application_id" in body


@pytest.mark.asyncio
async def test_apply_without_resume_succeeds(client, db):
    await _open_req(db, slug="no-resume")
    r = await client.post(
        "/api/v2/public/careers/no-resume/apply",
        data={
            "first_name": "X",
            "last_name": "Y",
            "email": "x@y.com",
            "sms_consent": "false",
        },
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_apply_to_closed_requisition_404(client, db):
    req = HrRequisition(
        slug="closed-req",
        title="Closed",
        status="closed",
        employment_type="full_time",
    )
    db.add(req)
    await db.commit()
    r = await client.post(
        "/api/v2/public/careers/closed-req/apply",
        data={"first_name": "X", "last_name": "Y", "email": "x@y.com"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_apply_rejects_duplicate_for_same_req(client, db):
    await _open_req(db, slug="dup")
    base = {
        "first_name": "Dup",
        "last_name": "Candidate",
        "email": "dup@x.com",
        "sms_consent": "false",
    }
    r1 = await client.post("/api/v2/public/careers/dup/apply", data=base)
    assert r1.status_code == 201
    r2 = await client.post("/api/v2/public/careers/dup/apply", data=base)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_apply_rejects_too_large_resume(client, db):
    await _open_req(db, slug="big")
    data = {
        "first_name": "B",
        "last_name": "I",
        "email": "big@x.com",
    }
    # 11 MB payload
    big = b"\x00" * (11 * 1024 * 1024)
    files = {"resume": ("big.pdf", io.BytesIO(big), "application/pdf")}
    r = await client.post("/api/v2/public/careers/big/apply", data=data, files=files)
    assert r.status_code == 400
