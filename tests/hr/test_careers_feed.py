from xml.etree import ElementTree as ET

import pytest

from app.hr.recruiting.models import HrRequisition


@pytest.mark.asyncio
async def test_jobs_feed_only_includes_open(client, db):
    db.add(
        HrRequisition(
            slug="open-1",
            title="Open Job",
            status="open",
            employment_type="full_time",
            location_city="Houston",
            location_state="TX",
        )
    )
    db.add(
        HrRequisition(
            slug="draft-1",
            title="Draft",
            status="draft",
            employment_type="full_time",
        )
    )
    await db.commit()

    r = await client.get("/careers/jobs.xml")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/xml")

    root = ET.fromstring(r.text)
    assert root.tag == "source"
    jobs = root.findall("job")
    assert len(jobs) == 1
    assert jobs[0].findtext("referencenumber") == "open-1"
    assert jobs[0].findtext("city") == "Houston"
    assert jobs[0].findtext("state") == "TX"
    assert jobs[0].findtext("jobtype") == "fulltime"
    assert "Open Job" in jobs[0].findtext("title")


@pytest.mark.asyncio
async def test_jobs_feed_handles_empty(client, db):
    r = await client.get("/careers/jobs.xml")
    assert r.status_code == 200
    root = ET.fromstring(r.text)
    assert root.tag == "source"
    assert root.findall("job") == []


@pytest.mark.asyncio
async def test_jobs_feed_escapes_special_chars(client, db):
    db.add(
        HrRequisition(
            slug="xml-edge",
            title="CDL Driver <urgent>",
            status="open",
            employment_type="contract",
            location_city="A & B",
            location_state="TX",
            description_md="We need 1 driver > 5 years exp.",
        )
    )
    await db.commit()

    r = await client.get("/careers/jobs.xml")
    assert r.status_code == 200
    root = ET.fromstring(r.text)  # must parse cleanly despite special chars
    jobs = root.findall("job")
    assert len(jobs) == 1
    assert jobs[0].findtext("jobtype") == "contract"
    assert "A & B" in jobs[0].findtext("city")
