import pytest


async def _seed(authed_client):
    r = await authed_client.post(
        "/api/v2/hr/recruiting/requisitions",
        json={
            "slug": "route-tech",
            "title": "Route Tech",
            "status": "open",
            "employment_type": "full_time",
        },
    )
    req_id = r.json()["id"]

    r = await authed_client.post(
        "/api/v2/hr/applicants",
        json={"first_name": "Jane", "last_name": "Doe", "email": "j@x.com"},
    )
    ap_id = r.json()["id"]
    return req_id, ap_id


@pytest.mark.asyncio
async def test_create_application(authed_client):
    req_id, ap_id = await _seed(authed_client)
    r = await authed_client.post(
        "/api/v2/hr/applications",
        json={"applicant_id": ap_id, "requisition_id": req_id},
    )
    assert r.status_code == 201, r.text
    assert r.json()["stage"] == "applied"


@pytest.mark.asyncio
async def test_transition_stage(authed_client):
    req_id, ap_id = await _seed(authed_client)
    r = await authed_client.post(
        "/api/v2/hr/applications",
        json={"applicant_id": ap_id, "requisition_id": req_id},
    )
    app_id = r.json()["id"]

    r = await authed_client.patch(
        f"/api/v2/hr/applications/{app_id}/stage", json={"stage": "screen"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "screen"


@pytest.mark.asyncio
async def test_invalid_transition_returns_400(authed_client):
    req_id, ap_id = await _seed(authed_client)
    r = await authed_client.post(
        "/api/v2/hr/applications",
        json={"applicant_id": ap_id, "requisition_id": req_id},
    )
    app_id = r.json()["id"]
    r = await authed_client.patch(
        f"/api/v2/hr/applications/{app_id}/stage", json={"stage": "hired"}
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_list_by_requisition(authed_client):
    req_id, ap_id = await _seed(authed_client)
    await authed_client.post(
        "/api/v2/hr/applications",
        json={"applicant_id": ap_id, "requisition_id": req_id},
    )
    r = await authed_client.get(
        f"/api/v2/hr/applications?requisition_id={req_id}"
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["applicant"]["email"] == "j@x.com"


@pytest.mark.asyncio
async def test_stage_counts(authed_client):
    req_id, ap_id = await _seed(authed_client)
    await authed_client.post(
        "/api/v2/hr/applications",
        json={"applicant_id": ap_id, "requisition_id": req_id},
    )
    r = await authed_client.get(
        f"/api/v2/hr/applications/counts?requisition_id={req_id}"
    )
    assert r.status_code == 200
    assert r.json() == {"applied": 1}
