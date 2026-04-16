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
