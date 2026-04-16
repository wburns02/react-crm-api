import pytest

from app.hr.recruiting.models import HrRequisition


@pytest.mark.asyncio
async def test_careers_index_lists_open_reqs(client, db):
    db.add(
        HrRequisition(
            slug="field-tech",
            title="Field Technician",
            status="open",
            employment_type="full_time",
            location_city="Houston",
            location_state="TX",
        )
    )
    db.add(
        HrRequisition(
            slug="draft-job",
            title="Draft Job",
            status="draft",
            employment_type="full_time",
        )
    )
    await db.commit()

    r = await client.get("/careers")
    assert r.status_code == 200, r.text
    assert "Field Technician" in r.text
    assert "Draft Job" not in r.text
    assert "Houston, TX" in r.text


@pytest.mark.asyncio
async def test_requisition_detail_page(client, db):
    db.add(
        HrRequisition(
            slug="driver",
            title="CDL Driver",
            status="open",
            employment_type="full_time",
            description_md="<p>Drive trucks.</p>",
        )
    )
    await db.commit()

    r = await client.get("/careers/driver")
    assert r.status_code == 200, r.text
    assert "CDL Driver" in r.text
    assert "Drive trucks." in r.text


@pytest.mark.asyncio
async def test_requisition_detail_404_when_draft(client, db):
    db.add(
        HrRequisition(
            slug="draft",
            title="X",
            status="draft",
            employment_type="full_time",
        )
    )
    await db.commit()

    r = await client.get("/careers/draft")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_careers_index_handles_empty_state(client, db):
    r = await client.get("/careers")
    assert r.status_code == 200
    assert "No open positions" in r.text
