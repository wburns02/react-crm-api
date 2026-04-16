import pytest


@pytest.mark.asyncio
async def test_create_requisition(authed_client):
    payload = {
        "slug": "field-tech",
        "title": "Field Technician",
        "status": "open",
        "employment_type": "full_time",
        "compensation_display": "$20-$28/hr + OT",
    }
    r = await authed_client.post(
        "/api/v2/hr/recruiting/requisitions", json=payload
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "field-tech"
    assert body["status"] == "open"
    assert body["compensation_display"] == "$20-$28/hr + OT"


@pytest.mark.asyncio
async def test_list_requisitions_filters_status(authed_client):
    for s in ["draft", "open", "closed"]:
        r = await authed_client.post(
            "/api/v2/hr/recruiting/requisitions",
            json={"slug": f"r-{s}", "title": s.title(), "status": s},
        )
        assert r.status_code == 201, r.text

    r = await authed_client.get("/api/v2/hr/recruiting/requisitions?status=open")
    assert r.status_code == 200
    slugs = {row["slug"] for row in r.json()}
    assert slugs == {"r-open"}


@pytest.mark.asyncio
async def test_list_includes_applicant_counts(authed_client):
    r = await authed_client.post(
        "/api/v2/hr/recruiting/requisitions",
        json={
            "slug": "counts-tech",
            "title": "X",
            "status": "open",
            "employment_type": "full_time",
        },
    )
    req_id = r.json()["id"]

    r = await authed_client.post(
        "/api/v2/hr/applicants",
        json={"first_name": "J", "last_name": "D", "email": "j@d.com"},
    )
    ap_id = r.json()["id"]

    await authed_client.post(
        "/api/v2/hr/applications",
        json={"applicant_id": ap_id, "requisition_id": req_id},
    )

    r = await authed_client.get("/api/v2/hr/recruiting/requisitions?status=open")
    assert r.status_code == 200
    rec = next(x for x in r.json() if x["slug"] == "counts-tech")
    assert rec["applicant_count"] == 1


@pytest.mark.asyncio
async def test_patch_requisition(authed_client):
    r = await authed_client.post(
        "/api/v2/hr/recruiting/requisitions",
        json={
            "slug": "p-req",
            "title": "Draft",
            "status": "draft",
            "employment_type": "full_time",
        },
    )
    rid = r.json()["id"]
    r = await authed_client.patch(
        f"/api/v2/hr/recruiting/requisitions/{rid}",
        json={"title": "Final Title", "status": "open"},
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Final Title"
    assert r.json()["status"] == "open"
    assert r.json()["opened_at"] is not None


@pytest.mark.asyncio
async def test_delete_requisition_soft_closes(authed_client):
    r = await authed_client.post(
        "/api/v2/hr/recruiting/requisitions",
        json={
            "slug": "del-req",
            "title": "D",
            "status": "open",
            "employment_type": "full_time",
        },
    )
    rid = r.json()["id"]
    r = await authed_client.delete(f"/api/v2/hr/recruiting/requisitions/{rid}")
    assert r.status_code == 200
    assert r.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_patch_404_for_missing(authed_client):
    from uuid import uuid4
    r = await authed_client.patch(
        f"/api/v2/hr/recruiting/requisitions/{uuid4()}", json={"title": "x"}
    )
    assert r.status_code == 404
