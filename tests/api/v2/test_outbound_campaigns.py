"""Tests for /api/v2/outbound-campaigns."""
import uuid as uuid_module

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import create_access_token, get_password_hash
from app.database import Base, get_db
from app.main import app as fastapi_app
from app.models.company_entity import CompanyEntity
from app.models.outbound_campaign import (
    OutboundCallAttempt,
    OutboundCallback,
    OutboundCampaign,
    OutboundCampaignContact,
)
from app.models.technician import Technician
from app.models.user import User


TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_outbound.db"
PREFIX = "/api/v2/outbound-campaigns"

_TABLES = [
    CompanyEntity.__table__,
    User.__table__,
    Technician.__table__,
    OutboundCampaign.__table__,
    OutboundCampaignContact.__table__,
    OutboundCallAttempt.__table__,
    OutboundCallback.__table__,
]


def _patch_uuid_for_sqlite():
    """Convert string UUIDs to uuid.UUID on SQLite bind (needed for PG UUID columns)."""
    from sqlalchemy.sql import sqltypes

    _original = sqltypes.Uuid.bind_processor

    def _patched(self, dialect):
        orig = _original(self, dialect)
        if orig is None:
            return None

        def process(value):
            if isinstance(value, str):
                try:
                    value = uuid_module.UUID(value)
                except ValueError:
                    pass
            return orig(value)

        return process

    sqltypes.Uuid.bind_processor = _patched


_patch_uuid_for_sqlite()


@pytest_asyncio.fixture
async def test_db():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=_TABLES)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(test_db: AsyncSession):
    user = User(
        email="dannia@example.com",
        hashed_password=get_password_hash("testpw"),
        first_name="Dannia",
        last_name="Chavez",
        is_active=True,
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def client(test_db: AsyncSession, test_user: User):
    async def override_get_db():
        yield test_db

    fastapi_app.dependency_overrides[get_db] = override_get_db
    token = create_access_token(
        data={"sub": str(test_user.id), "email": test_user.email}
    )
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=True
    ) as ac:
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac
    fastapi_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Campaign list / auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_campaigns_empty(client: AsyncClient):
    r = await client.get(f"{PREFIX}/campaigns")
    assert r.status_code == 200, r.text
    assert r.json() == {"campaigns": []}


@pytest.mark.asyncio
async def test_list_campaigns_requires_auth(test_db: AsyncSession):
    async def override_get_db():
        yield test_db

    fastapi_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get(f"{PREFIX}/campaigns")
    fastapi_app.dependency_overrides.clear()
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Campaign CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_campaign_with_client_id(client: AsyncClient):
    r = await client.post(
        f"{PREFIX}/campaigns",
        json={"id": "my-stable-id", "name": "Test Campaign", "description": "hello"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] == "my-stable-id"
    assert body["name"] == "Test Campaign"
    assert body["counters"]["total"] == 0


@pytest.mark.asyncio
async def test_create_campaign_auto_id(client: AsyncClient):
    r = await client.post(f"{PREFIX}/campaigns", json={"name": "Auto"})
    assert r.status_code == 201
    assert len(r.json()["id"]) > 0


@pytest.mark.asyncio
async def test_update_campaign(client: AsyncClient):
    r = await client.post(f"{PREFIX}/campaigns", json={"id": "c1", "name": "Orig"})
    assert r.status_code == 201
    r = await client.patch(
        f"{PREFIX}/campaigns/c1", json={"name": "Renamed", "status": "active"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"
    assert r.json()["status"] == "active"


@pytest.mark.asyncio
async def test_delete_campaign(client: AsyncClient):
    await client.post(f"{PREFIX}/campaigns", json={"id": "c2", "name": "Gone"})
    r = await client.delete(f"{PREFIX}/campaigns/c2")
    assert r.status_code == 204
    r = await client.get(f"{PREFIX}/campaigns")
    assert all(c["id"] != "c2" for c in r.json()["campaigns"])


# ---------------------------------------------------------------------------
# Contact CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_import_and_list_contacts(client: AsyncClient):
    await client.post(f"{PREFIX}/campaigns", json={"id": "c3", "name": "Bulk"})
    r = await client.post(
        f"{PREFIX}/campaigns/c3/contacts",
        json={
            "contacts": [
                {"id": "ct-1", "account_name": "Alice", "phone": "5550001"},
                {"id": "ct-2", "account_name": "Bob", "phone": "5550002"},
            ]
        },
    )
    assert r.status_code == 201, r.text
    assert len(r.json()["contacts"]) == 2
    r = await client.get(f"{PREFIX}/campaigns/c3/contacts")
    assert r.status_code == 200
    assert len(r.json()["contacts"]) == 2


@pytest.mark.asyncio
async def test_patch_contact(client: AsyncClient):
    await client.post(f"{PREFIX}/campaigns", json={"id": "c4", "name": "Edit"})
    await client.post(
        f"{PREFIX}/campaigns/c4/contacts",
        json={"contacts": [{"id": "ct-edit", "account_name": "Alice", "phone": "1"}]},
    )
    r = await client.patch(f"{PREFIX}/contacts/ct-edit", json={"notes": "careful"})
    assert r.status_code == 200, r.text
    assert r.json()["notes"] == "careful"


@pytest.mark.asyncio
async def test_delete_contact(client: AsyncClient):
    await client.post(f"{PREFIX}/campaigns", json={"id": "c5", "name": "Del"})
    await client.post(
        f"{PREFIX}/campaigns/c5/contacts",
        json={"contacts": [{"id": "ct-del", "account_name": "X", "phone": "1"}]},
    )
    r = await client.delete(f"{PREFIX}/contacts/ct-del")
    assert r.status_code == 204
    r = await client.get(f"{PREFIX}/campaigns/c5/contacts")
    assert len(r.json()["contacts"]) == 0


@pytest.mark.asyncio
async def test_list_contacts_filter_status(client: AsyncClient):
    await client.post(f"{PREFIX}/campaigns", json={"id": "c6", "name": "Filter"})
    await client.post(
        f"{PREFIX}/campaigns/c6/contacts",
        json={
            "contacts": [
                {"id": "ct-a", "account_name": "A", "phone": "1"},
                {"id": "ct-b", "account_name": "B", "phone": "2"},
            ]
        },
    )
    r = await client.get(f"{PREFIX}/campaigns/c6/contacts?status=pending")
    assert r.status_code == 200
    assert len(r.json()["contacts"]) == 2


# ---------------------------------------------------------------------------
# Dispositions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disposition_increments_counters_and_appends_attempt(client: AsyncClient):
    await client.post(f"{PREFIX}/campaigns", json={"id": "c7", "name": "Disp"})
    await client.post(
        f"{PREFIX}/campaigns/c7/contacts",
        json={"contacts": [{"id": "ct-d", "account_name": "X", "phone": "1"}]},
    )
    r = await client.post(
        f"{PREFIX}/contacts/ct-d/dispositions",
        json={"call_status": "connected", "notes": "picked up", "duration_sec": 120},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["contact"]["call_status"] == "connected"
    assert body["contact"]["call_attempts"] == 1
    assert body["contact"]["last_disposition"] == "connected"
    assert body["attempt"]["call_status"] == "connected"
    assert body["attempt"]["duration_sec"] == 120

    r = await client.post(
        f"{PREFIX}/contacts/ct-d/dispositions", json={"call_status": "voicemail"}
    )
    body = r.json()
    assert body["contact"]["call_attempts"] == 2
    assert body["contact"]["call_status"] == "voicemail"


@pytest.mark.asyncio
async def test_disposition_counters_on_campaign(client: AsyncClient):
    await client.post(f"{PREFIX}/campaigns", json={"id": "c8", "name": "Cnt"})
    await client.post(
        f"{PREFIX}/campaigns/c8/contacts",
        json={
            "contacts": [
                {"id": "a", "account_name": "A", "phone": "1"},
                {"id": "b", "account_name": "B", "phone": "2"},
                {"id": "c", "account_name": "C", "phone": "3"},
            ]
        },
    )
    await client.post(f"{PREFIX}/contacts/a/dispositions", json={"call_status": "connected"})
    await client.post(f"{PREFIX}/contacts/b/dispositions", json={"call_status": "voicemail"})
    r = await client.get(f"{PREFIX}/campaigns")
    campaigns = {c["id"]: c for c in r.json()["campaigns"]}
    counters = campaigns["c8"]["counters"]
    assert counters["total"] == 3
    assert counters["pending"] == 1
    assert counters["called"] == 2
    assert counters["connected"] == 1
    assert counters["voicemail"] == 1


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_callback_lifecycle(client: AsyncClient):
    await client.post(f"{PREFIX}/campaigns", json={"id": "c9", "name": "CB"})
    await client.post(
        f"{PREFIX}/campaigns/c9/contacts",
        json={"contacts": [{"id": "cb-ct", "account_name": "X", "phone": "1"}]},
    )
    r = await client.post(
        f"{PREFIX}/callbacks",
        json={
            "contact_id": "cb-ct",
            "campaign_id": "c9",
            "scheduled_for": "2026-04-25T15:00:00Z",
            "notes": "Call back Friday",
        },
    )
    assert r.status_code == 201, r.text
    cb_id = r.json()["id"]
    assert r.json()["status"] == "scheduled"

    r = await client.get(f"{PREFIX}/callbacks")
    assert r.status_code == 200
    assert any(c["id"] == cb_id for c in r.json()["callbacks"])

    r = await client.patch(f"{PREFIX}/callbacks/{cb_id}", json={"status": "completed"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"

    r = await client.delete(f"{PREFIX}/callbacks/{cb_id}")
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrate_local_imports_dirty_contacts(client: AsyncClient):
    await client.post(f"{PREFIX}/campaigns", json={"id": "c10", "name": "Seed"})
    await client.post(
        f"{PREFIX}/campaigns/c10/contacts",
        json={
            "contacts": [
                {"id": "m-1", "account_name": "A", "phone": "1"},
                {"id": "m-2", "account_name": "B", "phone": "2"},
            ]
        },
    )
    payload = {
        "campaigns": [{"id": "c10", "name": "Seed", "status": "active"}],
        "contacts": [
            {
                "id": "m-1",
                "campaign_id": "c10",
                "account_name": "A",
                "phone": "1",
                "call_status": "connected",
                "call_attempts": 2,
                "last_call_date": "2026-04-21T14:30:00Z",
                "last_disposition": "connected",
                "notes": "picked up",
            },
        ],
        "callbacks": [],
    }
    r = await client.post(f"{PREFIX}/migrate-local", json=payload)
    assert r.status_code == 200, r.text
    imported = r.json()["imported"]
    assert imported["contacts"] == 1
    assert imported["attempts"] == 1

    r = await client.get(f"{PREFIX}/campaigns/c10/contacts")
    contacts = {c["id"]: c for c in r.json()["contacts"]}
    assert contacts["m-1"]["call_status"] == "connected"
    assert contacts["m-1"]["call_attempts"] == 2
    assert contacts["m-2"]["call_status"] == "pending"


@pytest.mark.asyncio
async def test_migrate_local_is_idempotent(client: AsyncClient):
    await client.post(f"{PREFIX}/campaigns", json={"id": "c11", "name": "Idem"})
    await client.post(
        f"{PREFIX}/campaigns/c11/contacts",
        json={"contacts": [{"id": "i-1", "account_name": "A", "phone": "1"}]},
    )
    payload = {
        "campaigns": [],
        "contacts": [
            {
                "id": "i-1",
                "campaign_id": "c11",
                "account_name": "A",
                "phone": "1",
                "call_status": "voicemail",
                "call_attempts": 1,
                "last_call_date": "2026-04-21T14:30:00Z",
            },
        ],
        "callbacks": [],
    }
    r1 = await client.post(f"{PREFIX}/migrate-local", json=payload)
    r2 = await client.post(f"{PREFIX}/migrate-local", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["imported"]["attempts"] == 0


@pytest.mark.asyncio
async def test_migrate_local_creates_missing_campaign_and_contacts(client: AsyncClient):
    payload = {
        "campaigns": [{"id": "c-new", "name": "Brand New", "status": "active"}],
        "contacts": [
            {
                "id": "new-1",
                "campaign_id": "c-new",
                "account_name": "New",
                "phone": "9",
                "call_status": "connected",
                "call_attempts": 1,
                "last_call_date": "2026-04-21T14:30:00Z",
            },
        ],
        "callbacks": [],
    }
    r = await client.post(f"{PREFIX}/migrate-local", json=payload)
    assert r.status_code == 200, r.text
    imported = r.json()["imported"]
    assert imported["campaigns"] == 1
    assert imported["contacts"] == 1
    r = await client.get(f"{PREFIX}/campaigns/c-new/contacts")
    assert r.json()["contacts"][0]["call_status"] == "connected"
