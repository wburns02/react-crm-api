import pytest


@pytest.mark.asyncio
async def test_list_applicants_empty(authed_client):
    r = await authed_client.get("/api/v2/hr/applicants")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_and_list_applicants(authed_client):
    r = await authed_client.post(
        "/api/v2/hr/applicants",
        json={"first_name": "Jane", "last_name": "Doe", "email": "jane@example.com"},
    )
    assert r.status_code == 201, r.text
    a_id = r.json()["id"]

    r = await authed_client.get(f"/api/v2/hr/applicants/{a_id}")
    assert r.status_code == 200
    assert r.json()["email"] == "jane@example.com"


@pytest.mark.asyncio
async def test_unauth_rejected(client):
    r = await client.get("/api/v2/hr/applicants")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_detail_404_for_missing(authed_client):
    from uuid import uuid4
    r = await authed_client.get(f"/api/v2/hr/applicants/{uuid4()}")
    assert r.status_code == 404
