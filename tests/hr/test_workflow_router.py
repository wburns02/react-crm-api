from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_create_template_via_api(authed_client):
    payload = {
        "name": "Test Onboarding",
        "category": "onboarding",
        "tasks": [
            {"position": 0, "name": "Sign", "kind": "form_sign", "assignee_role": "hire"},
        ],
    }
    r = await authed_client.post("/api/v2/hr/workflows/templates", json=payload)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "Test Onboarding"
    assert data["category"] == "onboarding"
    assert data["version"] == 1


@pytest.mark.asyncio
async def test_spawn_instance_via_api(authed_client):
    r = await authed_client.post(
        "/api/v2/hr/workflows/templates",
        json={
            "name": "Solo",
            "category": "operational",
            "tasks": [
                {"position": 0, "name": "Do it", "kind": "manual", "assignee_role": "hire"}
            ],
        },
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    r2 = await authed_client.post(
        "/api/v2/hr/workflows/instances",
        json={
            "template_id": tid,
            "subject_type": "customer",
            "subject_id": str(uuid4()),
        },
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["status"] == "active"


@pytest.mark.asyncio
async def test_unauth_rejected(client):
    r = await client.post(
        "/api/v2/hr/workflows/templates",
        json={"name": "x", "category": "operational", "tasks": []},
    )
    assert r.status_code == 401
