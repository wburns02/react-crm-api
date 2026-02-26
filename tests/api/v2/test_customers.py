"""
Tests for the customers API endpoints (/api/v2/customers).

Note: Tests that need a specific customer ID (GET/PATCH/DELETE by ID) create
the customer through the API (POST) rather than inserting directly via
SQLAlchemy.  This avoids PostgreSQL UUID vs SQLite UUID compatibility issues
that arise when the SQLAlchemy UUID(as_uuid=True) column type processes
string bind parameters in the SQLite test dialect.
"""
import pytest
import pytest_asyncio
import uuid as uuid_module
from datetime import datetime
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import event

from app.main import app as fastapi_app
from app.database import Base, get_db
from app.api.deps import get_password_hash, create_access_token
from app.models.customer import Customer
from app.models.user import User
from app.models.company_entity import CompanyEntity
from app.models.technician import Technician


# ---------------------------------------------------------------------------
# Isolated test database (avoids SQLite lock with shared test.db)
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_customers.db"

CUSTOMERS_PREFIX = "/api/v2/customers"

# Only the tables needed for customer tests
_CUSTOMER_TABLES = [
    CompanyEntity.__table__,
    User.__table__,
    Technician.__table__,
    Customer.__table__,
]


def _patch_uuid_for_sqlite():
    """Monkey-patch SQLAlchemy's Uuid type to handle string inputs gracefully.

    When PostgreSQL UUID(as_uuid=True) columns are used with SQLite, the
    bind_processor expects uuid.UUID objects but API endpoints pass strings.
    This patch makes the bind_processor convert strings to UUID objects first.
    """
    from sqlalchemy.sql import sqltypes

    _original_bind_processor = sqltypes.Uuid.bind_processor

    def _patched_bind_processor(self, dialect):
        original_processor = _original_bind_processor(self, dialect)
        if original_processor is None:
            return None

        def process(value):
            if isinstance(value, str):
                try:
                    value = uuid_module.UUID(value)
                except ValueError:
                    pass
            return original_processor(value)

        return process

    sqltypes.Uuid.bind_processor = _patched_bind_processor


# Apply the patch at module load time for SQLite test compatibility
_patch_uuid_for_sqlite()


@pytest_asyncio.fixture
async def test_db():
    """Create an isolated test database for customer tests."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_CUSTOMER_TABLES)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=_CUSTOMER_TABLES)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(test_db: AsyncSession):
    """Create a test user."""
    user = User(
        email="test@example.com",
        hashed_password=get_password_hash("testpassword123"),
        first_name="Test",
        last_name="User",
        is_active=True,
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def client(test_db: AsyncSession):
    """Create test client with overridden database."""

    async def override_get_db():
        yield test_db

    fastapi_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as ac:
        yield ac
    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def authenticated_client(client: AsyncClient, test_user: User):
    """Create authenticated test client."""
    token = create_access_token(data={"sub": str(test_user.id), "email": test_user.email})
    client.headers["Authorization"] = f"Bearer {token}"
    return client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_customer_payload(**overrides) -> dict:
    """Build a valid customer creation payload, with optional overrides."""
    defaults = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane.doe@example.com",
        "phone": "5551234567",
        "address_line1": "123 Main St",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78701",
        "customer_type": "residential",
    }
    defaults.update(overrides)
    return defaults


async def _create_customer_via_api(
    client: AsyncClient, **overrides
) -> dict:
    """Create a customer through the API and return the response dict.

    This avoids SQLite UUID compatibility issues that arise when inserting
    directly via SQLAlchemy with PostgreSQL UUID columns.
    """
    payload = _make_customer_payload(**overrides)
    response = await client.post(CUSTOMERS_PREFIX, json=payload)
    assert response.status_code == 201, f"Customer creation failed: {response.text}"
    return response.json()


async def _create_customer_in_db(db: AsyncSession, **overrides) -> Customer:
    """Insert a customer directly into the database.

    Used only for tests that need DB-level setup (e.g., listing, filtering)
    where the exact UUID is not subsequently used for GET-by-ID lookups.
    """
    defaults = {
        "id": uuid_module.uuid4(),
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane.doe@example.com",
        "phone": "(555) 123-4567",
        "address_line1": "123 Main St",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78701",
        "customer_type": "residential",
        "is_active": True,
        "is_archived": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    customer = Customer(**defaults)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


# ---------------------------------------------------------------------------
# Authorization checks
# ---------------------------------------------------------------------------


class TestCustomerAuthorization:
    """Verify that unauthenticated requests are rejected."""

    @pytest.mark.asyncio
    async def test_list_customers_unauthenticated(self, client: AsyncClient):
        """GET /customers without auth returns 401."""
        response = await client.get(CUSTOMERS_PREFIX)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_customer_unauthenticated(self, client: AsyncClient):
        """GET /customers/:id without auth returns 401."""
        response = await client.get(f"{CUSTOMERS_PREFIX}/{uuid_module.uuid4()}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_customer_unauthenticated(self, client: AsyncClient):
        """POST /customers without auth returns 401."""
        response = await client.post(
            CUSTOMERS_PREFIX,
            json=_make_customer_payload(),
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_customer_unauthenticated(self, client: AsyncClient):
        """PATCH /customers/:id without auth returns 401."""
        response = await client.patch(
            f"{CUSTOMERS_PREFIX}/{uuid_module.uuid4()}",
            json={"first_name": "Updated"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_customer_unauthenticated(self, client: AsyncClient):
        """DELETE /customers/:id without auth returns 401."""
        response = await client.delete(f"{CUSTOMERS_PREFIX}/{uuid_module.uuid4()}")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /customers - Create
# ---------------------------------------------------------------------------


class TestCreateCustomer:
    """Tests for POST /customers."""

    @pytest.mark.asyncio
    async def test_create_customer_success(self, authenticated_client: AsyncClient):
        """Creating a customer with valid data returns 201."""
        payload = _make_customer_payload()
        response = await authenticated_client.post(CUSTOMERS_PREFIX, json=payload)
        assert response.status_code == 201, response.text
        data = response.json()

        assert data["first_name"] == "Jane"
        assert data["last_name"] == "Doe"
        assert data["email"] == "jane.doe@example.com"
        assert data["customer_type"] == "residential"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_customer_minimal_fields(self, authenticated_client: AsyncClient):
        """Only first_name and last_name are required."""
        payload = {"first_name": "Min", "last_name": "Imal"}
        response = await authenticated_client.post(CUSTOMERS_PREFIX, json=payload)
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["first_name"] == "Min"
        assert data["last_name"] == "Imal"

    @pytest.mark.asyncio
    async def test_create_customer_missing_first_name(self, authenticated_client: AsyncClient):
        """Missing first_name returns 422 validation error."""
        payload = {"last_name": "NoFirst"}
        response = await authenticated_client.post(CUSTOMERS_PREFIX, json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_customer_missing_last_name(self, authenticated_client: AsyncClient):
        """Missing last_name returns 422 validation error."""
        payload = {"first_name": "NoLast"}
        response = await authenticated_client.post(CUSTOMERS_PREFIX, json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_customer_empty_names(self, authenticated_client: AsyncClient):
        """Empty string names should be rejected (min_length=1)."""
        payload = {"first_name": "", "last_name": ""}
        response = await authenticated_client.post(CUSTOMERS_PREFIX, json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_customer_name_title_cased(self, authenticated_client: AsyncClient):
        """Names are title-cased by the schema validator."""
        payload = _make_customer_payload(first_name="john", last_name="doe")
        response = await authenticated_client.post(CUSTOMERS_PREFIX, json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == "John"
        assert data["last_name"] == "Doe"

    @pytest.mark.asyncio
    async def test_create_customer_phone_normalized(self, authenticated_client: AsyncClient):
        """US phone numbers are normalized to (XXX) XXX-XXXX."""
        payload = _make_customer_payload(phone="5551234567")
        response = await authenticated_client.post(CUSTOMERS_PREFIX, json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["phone"] == "(555) 123-4567"

    @pytest.mark.asyncio
    async def test_create_customer_empty_email_coerced_to_none(self, authenticated_client: AsyncClient):
        """Empty-string email is coerced to null by the schema."""
        payload = _make_customer_payload(email="")
        response = await authenticated_client.post(CUSTOMERS_PREFIX, json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["email"] is None

    @pytest.mark.asyncio
    async def test_create_customer_returns_id(self, authenticated_client: AsyncClient):
        """Response includes a UUID id field."""
        payload = _make_customer_payload()
        response = await authenticated_client.post(CUSTOMERS_PREFIX, json=payload)
        assert response.status_code == 201
        data = response.json()
        # UUID as string is 32 hex chars (possibly with dashes = 36 chars)
        assert len(data["id"]) >= 32


# ---------------------------------------------------------------------------
# GET /customers - List
# ---------------------------------------------------------------------------


class TestListCustomers:
    """Tests for GET /customers."""

    @pytest.mark.asyncio
    async def test_list_customers_empty(self, authenticated_client: AsyncClient):
        """Empty database returns zero items."""
        response = await authenticated_client.get(CUSTOMERS_PREFIX)
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_customers_returns_items(self, authenticated_client: AsyncClient):
        """Customers created via API appear in the list."""
        await _create_customer_via_api(authenticated_client, first_name="Alice", last_name="Smith", email="alice@test.com")
        await _create_customer_via_api(authenticated_client, first_name="Bob", last_name="Jones", email="bob@test.com")

        response = await authenticated_client.get(CUSTOMERS_PREFIX)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_customers_pagination(self, authenticated_client: AsyncClient):
        """Pagination parameters (page, page_size) are respected."""
        for i in range(5):
            await _create_customer_via_api(
                authenticated_client,
                first_name=f"User{i}",
                last_name="Test",
                email=f"user{i}@test.com",
            )

        # Request page 1 with page_size=2
        response = await authenticated_client.get(
            CUSTOMERS_PREFIX, params={"page": 1, "page_size": 2}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) == 2

        # Request page 3 - should have 1 item
        response = await authenticated_client.get(
            CUSTOMERS_PREFIX, params={"page": 3, "page_size": 2}
        )
        data = response.json()
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_customers_search_by_name(self, authenticated_client: AsyncClient):
        """Search query filters customers by name."""
        await _create_customer_via_api(authenticated_client, first_name="Alice", last_name="Smith", email="alice@test.com")
        await _create_customer_via_api(authenticated_client, first_name="Bob", last_name="Jones", email="bob@test.com")

        response = await authenticated_client.get(
            CUSTOMERS_PREFIX, params={"search": "Alice"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["first_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_list_customers_search_by_email(self, authenticated_client: AsyncClient):
        """Search query filters customers by email."""
        await _create_customer_via_api(authenticated_client, first_name="Alice", last_name="Smith", email="alice@test.com")
        await _create_customer_via_api(authenticated_client, first_name="Bob", last_name="Jones", email="bob@test.com")

        response = await authenticated_client.get(
            CUSTOMERS_PREFIX, params={"search": "bob@test"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["first_name"] == "Bob"

    @pytest.mark.asyncio
    async def test_list_customers_search_by_full_name(self, authenticated_client: AsyncClient):
        """Search query matches against concatenated full name."""
        await _create_customer_via_api(authenticated_client, first_name="Alice", last_name="Smith", email="alice@test.com")
        await _create_customer_via_api(authenticated_client, first_name="Bob", last_name="Jones", email="bob@test.com")

        response = await authenticated_client.get(
            CUSTOMERS_PREFIX, params={"search": "Alice Smith"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_customers_filter_by_type(self, authenticated_client: AsyncClient):
        """Filter by customer_type query parameter."""
        await _create_customer_via_api(
            authenticated_client, first_name="Res", last_name="Client", email="res@test.com", customer_type="residential"
        )
        await _create_customer_via_api(
            authenticated_client, first_name="Com", last_name="Client", email="com@test.com", customer_type="commercial"
        )

        response = await authenticated_client.get(
            CUSTOMERS_PREFIX, params={"customer_type": "commercial"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["customer_type"] == "commercial"

    @pytest.mark.asyncio
    async def test_list_customers_default_excludes_inactive(
        self, authenticated_client: AsyncClient, test_db: AsyncSession
    ):
        """By default, inactive customers are excluded."""
        await _create_customer_via_api(authenticated_client, first_name="Active", last_name="One", email="active@test.com")

        # Create an inactive customer directly in DB (can't make inactive via API easily)
        await _create_customer_in_db(test_db, first_name="Inactive", last_name="One", email="inactive@test.com", is_active=False)

        response = await authenticated_client.get(CUSTOMERS_PREFIX)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["first_name"] == "Active"

    @pytest.mark.asyncio
    async def test_list_customers_include_all(
        self, authenticated_client: AsyncClient, test_db: AsyncSession
    ):
        """include_all=true returns both active and inactive customers."""
        await _create_customer_via_api(authenticated_client, first_name="Active", last_name="One", email="active@test.com")
        await _create_customer_in_db(test_db, first_name="Inactive", last_name="One", email="inactive@test.com", is_active=False)

        response = await authenticated_client.get(
            CUSTOMERS_PREFIX, params={"include_all": True}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    @pytest.mark.asyncio
    async def test_list_customers_default_excludes_archived(
        self, authenticated_client: AsyncClient, test_db: AsyncSession
    ):
        """By default, archived customers are excluded."""
        await _create_customer_via_api(authenticated_client, first_name="Normal", last_name="One", email="normal@test.com")
        await _create_customer_in_db(test_db, first_name="Archived", last_name="One", email="archived@test.com", is_archived=True)

        response = await authenticated_client.get(CUSTOMERS_PREFIX)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["first_name"] == "Normal"


# ---------------------------------------------------------------------------
# GET /customers/:id - Get single
# ---------------------------------------------------------------------------


class TestGetCustomer:
    """Tests for GET /customers/:id."""

    @pytest.mark.asyncio
    async def test_get_customer_success(self, authenticated_client: AsyncClient):
        """Fetching an existing customer returns 200 with full data."""
        created = await _create_customer_via_api(authenticated_client)
        customer_id = created["id"]

        response = await authenticated_client.get(f"{CUSTOMERS_PREFIX}/{customer_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == customer_id
        assert data["first_name"] == "Jane"
        assert data["last_name"] == "Doe"
        assert data["email"] == "jane.doe@example.com"

    @pytest.mark.asyncio
    async def test_get_customer_not_found(self, authenticated_client: AsyncClient):
        """Fetching a non-existent customer returns 404."""
        fake_id = str(uuid_module.uuid4())
        response = await authenticated_client.get(f"{CUSTOMERS_PREFIX}/{fake_id}")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_customer_response_schema(self, authenticated_client: AsyncClient):
        """Response contains expected fields from CustomerResponse schema."""
        created = await _create_customer_via_api(authenticated_client)

        response = await authenticated_client.get(f"{CUSTOMERS_PREFIX}/{created['id']}")
        data = response.json()
        # Required fields from CustomerResponse
        assert "id" in data
        assert "first_name" in data
        assert "last_name" in data
        assert "email" in data
        assert "phone" in data
        assert "is_active" in data
        assert "customer_type" in data


# ---------------------------------------------------------------------------
# PATCH /customers/:id - Update
# ---------------------------------------------------------------------------


class TestUpdateCustomer:
    """Tests for PATCH /customers/:id."""

    @pytest.mark.asyncio
    async def test_update_customer_success(self, authenticated_client: AsyncClient):
        """Updating a customer with valid partial data returns 200."""
        created = await _create_customer_via_api(authenticated_client)

        response = await authenticated_client.patch(
            f"{CUSTOMERS_PREFIX}/{created['id']}",
            json={"first_name": "Updated", "city": "Dallas"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Updated"
        assert data["city"] == "Dallas"
        # Unchanged field should remain
        assert data["last_name"] == "Doe"

    @pytest.mark.asyncio
    async def test_update_customer_not_found(self, authenticated_client: AsyncClient):
        """Updating a non-existent customer returns 404."""
        fake_id = str(uuid_module.uuid4())
        response = await authenticated_client.patch(
            f"{CUSTOMERS_PREFIX}/{fake_id}",
            json={"first_name": "Ghost"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_customer_partial(self, authenticated_client: AsyncClient):
        """PATCH only updates the fields provided, leaving others untouched."""
        created = await _create_customer_via_api(
            authenticated_client,
            first_name="Original",
            last_name="Name",
            email="orig@test.com",
            phone="5551112222",
        )

        response = await authenticated_client.patch(
            f"{CUSTOMERS_PREFIX}/{created['id']}",
            json={"email": "updated@test.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "updated@test.com"
        assert data["first_name"] == "Original"
        assert data["last_name"] == "Name"
        assert data["phone"] == "(555) 111-2222"

    @pytest.mark.asyncio
    async def test_update_customer_name_title_cased(self, authenticated_client: AsyncClient):
        """Updated names are title-cased by the schema."""
        created = await _create_customer_via_api(authenticated_client)

        response = await authenticated_client.patch(
            f"{CUSTOMERS_PREFIX}/{created['id']}",
            json={"first_name": "alice", "last_name": "wonderland"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Alice"
        assert data["last_name"] == "Wonderland"


# ---------------------------------------------------------------------------
# DELETE /customers/:id - Delete (soft delete)
# ---------------------------------------------------------------------------


class TestDeleteCustomer:
    """Tests for DELETE /customers/:id."""

    @pytest.mark.asyncio
    async def test_delete_customer_success(self, authenticated_client: AsyncClient):
        """Deleting an existing customer returns 204 No Content."""
        created = await _create_customer_via_api(authenticated_client)

        response = await authenticated_client.delete(
            f"{CUSTOMERS_PREFIX}/{created['id']}"
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_customer_not_found(self, authenticated_client: AsyncClient):
        """Deleting a non-existent customer returns 404."""
        fake_id = str(uuid_module.uuid4())
        response = await authenticated_client.delete(f"{CUSTOMERS_PREFIX}/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_customer_is_soft_delete(self, authenticated_client: AsyncClient):
        """Delete performs a soft delete -- the customer is hidden from default list but not destroyed."""
        created = await _create_customer_via_api(authenticated_client)
        customer_id = created["id"]

        response = await authenticated_client.delete(f"{CUSTOMERS_PREFIX}/{customer_id}")
        assert response.status_code == 204

        # The customer should no longer appear in the default list (is_active=False)
        list_resp = await authenticated_client.get(CUSTOMERS_PREFIX)
        ids = [c["id"] for c in list_resp.json()["items"]]
        assert customer_id not in ids

        # But should still appear when explicitly including all
        list_all_resp = await authenticated_client.get(
            CUSTOMERS_PREFIX, params={"include_all": True}
        )
        all_ids = [c["id"] for c in list_all_resp.json()["items"]]
        assert customer_id in all_ids


# ---------------------------------------------------------------------------
# POST /customers/:id/archive and /unarchive
# ---------------------------------------------------------------------------


class TestArchiveCustomer:
    """Tests for POST /customers/:id/archive and /unarchive."""

    @pytest.mark.asyncio
    async def test_archive_customer(self, authenticated_client: AsyncClient):
        """Archiving a customer sets is_archived=True."""
        created = await _create_customer_via_api(authenticated_client)

        response = await authenticated_client.post(
            f"{CUSTOMERS_PREFIX}/{created['id']}/archive"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_archived"] is True

    @pytest.mark.asyncio
    async def test_unarchive_customer(self, authenticated_client: AsyncClient):
        """Unarchiving a previously archived customer sets is_archived=False."""
        created = await _create_customer_via_api(authenticated_client)
        # Archive first
        await authenticated_client.post(f"{CUSTOMERS_PREFIX}/{created['id']}/archive")

        response = await authenticated_client.post(
            f"{CUSTOMERS_PREFIX}/{created['id']}/unarchive"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_archived"] is False

    @pytest.mark.asyncio
    async def test_archive_nonexistent_customer(self, authenticated_client: AsyncClient):
        """Archiving a non-existent customer returns 404."""
        fake_id = str(uuid_module.uuid4())
        response = await authenticated_client.post(
            f"{CUSTOMERS_PREFIX}/{fake_id}/archive"
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestCustomerSchemas:
    """Test Pydantic schema validation for customers."""

    def test_customer_create_requires_names(self):
        """CustomerCreate requires first_name and last_name."""
        from app.schemas.customer import CustomerCreate

        with pytest.raises(Exception):
            CustomerCreate()

    def test_customer_create_title_cases_names(self):
        """CustomerCreate title-cases first_name and last_name."""
        from app.schemas.customer import CustomerCreate

        c = CustomerCreate(first_name="john", last_name="doe")
        assert c.first_name == "John"
        assert c.last_name == "Doe"

    def test_customer_update_all_optional(self):
        """CustomerUpdate allows all fields to be optional."""
        from app.schemas.customer import CustomerUpdate

        update = CustomerUpdate()
        data = update.model_dump(exclude_unset=True)
        assert data == {}

    def test_customer_update_partial(self):
        """CustomerUpdate only includes set fields in model_dump."""
        from app.schemas.customer import CustomerUpdate

        update = CustomerUpdate(first_name="New")
        data = update.model_dump(exclude_unset=True)
        assert "first_name" in data
        assert "last_name" not in data

    def test_customer_create_phone_normalization(self):
        """Phone numbers are normalized to (XXX) XXX-XXXX format."""
        from app.schemas.customer import CustomerCreate

        c = CustomerCreate(first_name="Test", last_name="User", phone="5551234567")
        assert c.phone == "(555) 123-4567"

    def test_customer_create_empty_email_to_none(self):
        """Empty-string email is coerced to None."""
        from app.schemas.customer import CustomerCreate

        c = CustomerCreate(first_name="Test", last_name="User", email="")
        assert c.email is None

    def test_customer_response_from_attributes(self):
        """CustomerResponse has from_attributes=True for ORM compatibility."""
        from app.schemas.customer import CustomerResponse

        assert CustomerResponse.model_config.get("from_attributes") is True

    def test_customer_list_response(self):
        """CustomerListResponse wraps items, total, page, page_size."""
        from app.schemas.customer import CustomerListResponse, CustomerResponse

        resp = CustomerListResponse(
            items=[
                CustomerResponse(
                    id="abc-123",
                    first_name="Test",
                    last_name="User",
                )
            ],
            total=1,
            page=1,
            page_size=20,
        )
        assert len(resp.items) == 1
        assert resp.total == 1
        assert resp.page == 1
        assert resp.page_size == 20
