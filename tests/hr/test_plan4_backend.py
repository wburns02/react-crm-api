"""Plan 4 backend tests — HR overview, applicant inbox search, template admin."""
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.hr.recruiting.applicant_models import HrRecruitingMessageTemplate


# ── HR Overview ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hr_overview_empty_state(authed_client):
    r = await authed_client.get("/api/v2/hr/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["open_requisitions"] == 0
    assert body["applicants_last_7d"] == 0
    assert body["active_onboardings"] == 0
    assert body["active_offboardings"] == 0
    assert body["expiring_certs_30d"] == 0


@pytest.mark.asyncio
async def test_hr_overview_counts_requisitions(authed_client, db):
    from app.hr.recruiting.models import HrRequisition

    db.add(HrRequisition(slug="o1", title="T1", status="open", employment_type="full_time"))
    db.add(HrRequisition(slug="o2", title="T2", status="open", employment_type="full_time"))
    db.add(HrRequisition(slug="d1", title="T3", status="draft", employment_type="full_time"))
    await db.commit()

    r = await authed_client.get("/api/v2/hr/overview")
    assert r.status_code == 200
    assert r.json()["open_requisitions"] == 2


@pytest.mark.asyncio
async def test_hr_overview_applications_by_stage(authed_client, db):
    # Seed requisition + applicant + application.
    r = await authed_client.post(
        "/api/v2/hr/recruiting/requisitions",
        json={"slug": "over-tech", "title": "T", "status": "open", "employment_type": "full_time"},
    )
    req_id = r.json()["id"]
    r = await authed_client.post(
        "/api/v2/hr/applicants",
        json={"first_name": "A", "last_name": "B", "email": "ab@x.com"},
    )
    ap_id = r.json()["id"]
    await authed_client.post(
        "/api/v2/hr/applications",
        json={"applicant_id": ap_id, "requisition_id": req_id},
    )

    r = await authed_client.get("/api/v2/hr/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["active_applications_by_stage"].get("applied", 0) == 1


# ── Applicant inbox search ────────────────────────────────────────────

@pytest_asyncio.fixture
async def seeded_applicants(authed_client):
    for e in ["alpha@x.com", "beta@x.com", "gamma@y.com"]:
        await authed_client.post(
            "/api/v2/hr/applicants",
            json={
                "first_name": e.split("@")[0].capitalize(),
                "last_name": "Tester",
                "email": e,
                "source": "manual",
            },
        )


@pytest.mark.asyncio
async def test_applicant_inbox_search_by_name(authed_client, seeded_applicants):
    r = await authed_client.get("/api/v2/hr/applicants?q=alpha")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["email"] == "alpha@x.com"


@pytest.mark.asyncio
async def test_applicant_inbox_filter_by_source(authed_client, seeded_applicants):
    r = await authed_client.get("/api/v2/hr/applicants?source=manual")
    assert r.status_code == 200
    assert len(r.json()) == 3


# ── Message template admin ─────────────────────────────────────────────

@pytest_asyncio.fixture
async def seeded_templates(db):
    from app.hr.recruiting.message_templates import DEFAULTS

    for t in DEFAULTS:
        db.add(
            HrRecruitingMessageTemplate(
                stage=t["stage"], channel="sms", body=t["body"], active=True
            )
        )
    await db.commit()


@pytest.mark.asyncio
async def test_list_message_templates(authed_client, seeded_templates):
    r = await authed_client.get("/api/v2/hr/recruiting/message-templates")
    assert r.status_code == 200, r.text
    assert len(r.json()) == 5


@pytest.mark.asyncio
async def test_patch_message_template(authed_client, seeded_templates):
    r = await authed_client.patch(
        "/api/v2/hr/recruiting/message-templates/screen",
        json={"body": "New body {first_name}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["body"] == "New body {first_name}"
    assert r.json()["updated_at"] is not None


@pytest.mark.asyncio
async def test_patch_unknown_template_404(authed_client, seeded_templates):
    r = await authed_client.patch(
        "/api/v2/hr/recruiting/message-templates/nonexistent",
        json={"body": "x"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_deactivate(authed_client, seeded_templates):
    r = await authed_client.patch(
        "/api/v2/hr/recruiting/message-templates/rejected",
        json={"active": False},
    )
    assert r.status_code == 200
    assert r.json()["active"] is False


@pytest.mark.asyncio
async def test_templates_admin_requires_auth(client):
    r = await client.get("/api/v2/hr/recruiting/message-templates")
    assert r.status_code == 401
