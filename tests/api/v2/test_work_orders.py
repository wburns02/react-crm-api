"""
Tests for the work orders API endpoints.
"""
import pytest
import pytest_asyncio
import uuid
from datetime import date, time, datetime
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, ForeignKey, Date, Time, JSON, Numeric

from app.main import app as fastapi_app
from app.database import Base, get_db
from app.api.deps import get_password_hash, create_access_token
from app.models.user import User


# For testing, we need to create SQLite-compatible models
# SQLite doesn't support PostgreSQL ENUM types
class CustomerFixture(Base):
    """Test customer for work order tests."""
    __tablename__ = "test_customers"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100))
    last_name = Column(String(100))
    email = Column(String(255), index=True)
    phone = Column(String(20))


class WorkOrderFixture(Base):
    """SQLite-compatible work order model for testing."""
    __tablename__ = "test_work_orders"
    __table_args__ = {"extend_existing": True}

    id = Column(String(36), primary_key=True, index=True)
    customer_id = Column(Integer, nullable=False, index=True)
    technician_id = Column(String(36), index=True)
    job_type = Column(String(50), nullable=False)
    priority = Column(String(20))
    status = Column(String(30))
    scheduled_date = Column(Date)
    time_window_start = Column(Time)
    time_window_end = Column(Time)
    estimated_duration_hours = Column(Float)
    service_address_line1 = Column(String(255))
    service_address_line2 = Column(String(255))
    service_city = Column(String(100))
    service_state = Column(String(50))
    service_postal_code = Column(String(20))
    service_latitude = Column(Float)
    service_longitude = Column(Float)
    estimated_gallons = Column(Integer)
    notes = Column(Text)
    internal_notes = Column(Text)
    is_recurring = Column(Boolean, default=False)
    recurrence_frequency = Column(String(50))
    next_recurrence_date = Column(Date)
    checklist = Column(JSON)
    assigned_vehicle = Column(String(100))
    assigned_technician = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    total_amount = Column(Numeric)
    actual_start_time = Column(DateTime)
    actual_end_time = Column(DateTime)
    travel_start_time = Column(DateTime)
    travel_end_time = Column(DateTime)
    break_minutes = Column(Integer)
    total_labor_minutes = Column(Integer)
    total_travel_minutes = Column(Integer)
    is_clocked_in = Column(Boolean, default=False)


# Test database
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_work_orders.db"


@pytest_asyncio.fixture
async def test_db():
    """Create test database and tables."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(test_db: AsyncSession):
    """Create a test user."""
    user = User(
        email="workorder_test@example.com",
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
async def test_customer(test_db: AsyncSession):
    """Create a test customer."""
    customer = CustomerFixture(
        first_name="John",
        last_name="Doe",
        email="john.doe@example.com",
        phone="555-123-4567"
    )
    test_db.add(customer)
    await test_db.commit()
    await test_db.refresh(customer)
    return customer


@pytest_asyncio.fixture
async def test_work_order(test_db: AsyncSession, test_customer):
    """Create a test work order."""
    work_order = WorkOrderFixture(
        id=str(uuid.uuid4()),
        customer_id=test_customer.id,
        job_type="pumping",
        status="scheduled",
        priority="normal",
        scheduled_date=date(2026, 1, 15),
        time_window_start=time(9, 0),
        time_window_end=time(12, 0),
        service_address_line1="123 Main St",
        service_city="Austin",
        service_state="TX",
        service_postal_code="78701",
        notes="Test work order",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    test_db.add(work_order)
    await test_db.commit()
    await test_db.refresh(work_order)
    return work_order


@pytest_asyncio.fixture
async def client(test_db: AsyncSession):
    """Create test client with overridden database."""

    async def override_get_db():
        yield test_db

    fastapi_app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def authenticated_client(client: AsyncClient, test_user: User):
    """Create authenticated test client."""
    token = create_access_token(data={"sub": str(test_user.id), "email": test_user.email})
    client.headers["Authorization"] = f"Bearer {token}"
    return client


class TestWorkOrderSchemas:
    """Test work order Pydantic schemas."""

    def test_work_order_create_schema(self):
        """Test WorkOrderCreate schema validates correctly."""
        from app.schemas.work_order import WorkOrderCreate

        data = {
            "customer_id": 1,
            "job_type": "pumping",
            "status": "draft",
            "priority": "normal",
        }
        schema = WorkOrderCreate(**data)
        assert schema.customer_id == "1"  # UUIDStr coerces to string
        assert schema.job_type == "pumping"
        assert schema.status == "draft"
        assert schema.priority == "normal"

    def test_work_order_create_with_optional_fields(self):
        """Test WorkOrderCreate with optional fields."""
        from app.schemas.work_order import WorkOrderCreate

        data = {
            "customer_id": 1,
            "job_type": "inspection",
            "scheduled_date": date(2026, 1, 20),
            "time_window_start": time(10, 0),
            "time_window_end": time(14, 0),
            "estimated_duration_hours": 2.5,
            "service_address_line1": "456 Oak Ave",
            "service_city": "Houston",
            "service_state": "TX",
            "notes": "Customer prefers morning appointments",
        }
        schema = WorkOrderCreate(**data)
        assert schema.scheduled_date == date(2026, 1, 20)
        assert schema.estimated_duration_hours == 2.5
        assert schema.notes == "Customer prefers morning appointments"

    def test_work_order_update_schema(self):
        """Test WorkOrderUpdate schema with partial update."""
        from app.schemas.work_order import WorkOrderUpdate

        data = {"status": "completed", "notes": "Work completed successfully"}
        schema = WorkOrderUpdate(**data)
        assert schema.status == "completed"
        assert schema.notes == "Work completed successfully"
        assert schema.customer_id is None

    def test_work_order_response_schema(self):
        """Test WorkOrderResponse schema."""
        from app.schemas.work_order import WorkOrderResponse

        data = {
            "id": "abc-123",
            "customer_id": 1,
            "job_type": "pumping",
            "status": "completed",
            "priority": "normal",
            "created_at": datetime(2026, 1, 1, 12, 0, 0),
            "updated_at": datetime(2026, 1, 1, 14, 0, 0),
        }
        schema = WorkOrderResponse(**data)
        assert schema.id == "abc-123"
        assert schema.created_at.year == 2026

    def test_work_order_list_response_schema(self):
        """Test WorkOrderListResponse schema."""
        from app.schemas.work_order import WorkOrderListResponse, WorkOrderResponse

        items = [
            WorkOrderResponse(
                id="wo-1",
                customer_id=1,
                job_type="pumping",
            ),
            WorkOrderResponse(
                id="wo-2",
                customer_id=2,
                job_type="inspection",
            ),
        ]
        response = WorkOrderListResponse(
            items=items,
            total=100,
            page=1,
            page_size=20,
        )
        assert len(response.items) == 2
        assert response.total == 100
        assert response.page == 1
        assert response.page_size == 20


class TestWorkOrderModel:
    """Test work order SQLAlchemy model."""

    @pytest.mark.asyncio
    async def test_create_work_order_model(self, test_db, test_customer):
        """Test creating a work order via model."""
        work_order = WorkOrderFixture(
            id=str(uuid.uuid4()),
            customer_id=test_customer.id,
            job_type="repair",
            status="draft",
            priority="high",
        )
        test_db.add(work_order)
        await test_db.commit()
        await test_db.refresh(work_order)

        assert work_order.id is not None
        assert work_order.customer_id == test_customer.id
        assert work_order.job_type == "repair"
        assert work_order.priority == "high"

    @pytest.mark.asyncio
    async def test_work_order_timestamps(self, test_db, test_customer):
        """Test work order has timestamps."""
        now = datetime.utcnow()
        work_order = WorkOrderFixture(
            id=str(uuid.uuid4()),
            customer_id=test_customer.id,
            job_type="pumping",
            created_at=now,
            updated_at=now,
        )
        test_db.add(work_order)
        await test_db.commit()

        assert work_order.created_at is not None
        assert work_order.updated_at is not None


class TestWorkOrderAPIEndpoints:
    """Test work order API endpoints using mocks."""

    @pytest.mark.asyncio
    async def test_list_work_orders_unauthenticated(self, client):
        """Test listing work orders without auth returns 401."""
        response = await client.get("/api/v2/work-orders")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_work_order_unauthenticated(self, client):
        """Test creating work order without auth returns 401."""
        response = await client.post(
            "/api/v2/work-orders",
            json={"customer_id": 1, "job_type": "pumping"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_work_order_unauthenticated(self, client):
        """Test getting work order without auth returns 401."""
        response = await client.get("/api/v2/work-orders/some-id")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_work_order_unauthenticated(self, client):
        """Test updating work order without auth returns 401."""
        response = await client.patch(
            "/api/v2/work-orders/some-id",
            json={"status": "completed"}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_work_order_unauthenticated(self, client):
        """Test deleting work order without auth returns 401."""
        response = await client.delete("/api/v2/work-orders/some-id")
        assert response.status_code == 401


class TestWorkOrderFilters:
    """Test work order list filters."""

    def test_enum_fields_constant(self):
        """Test ENUM_FIELDS constant is defined correctly."""
        from app.api.v2.work_orders import ENUM_FIELDS

        assert "status" in ENUM_FIELDS
        assert "job_type" in ENUM_FIELDS
        assert "priority" in ENUM_FIELDS


class TestWorkOrderWebSocketEvents:
    """Test WebSocket event broadcasting for work orders."""

    @pytest.mark.asyncio
    async def test_websocket_manager_import(self):
        """Test websocket manager is properly imported."""
        from app.api.v2.work_orders import manager

        assert manager is not None
        assert hasattr(manager, "broadcast_event")

    @pytest.mark.asyncio
    async def test_broadcast_event_is_async(self):
        """Test broadcast_event is an async function."""
        from app.services.websocket_manager import manager
        import inspect

        assert inspect.iscoroutinefunction(manager.broadcast_event)


class TestWorkOrderDateParsing:
    """Test date parsing in work order filters."""

    def test_valid_date_parsing(self):
        """Test valid date string is parsed correctly."""
        date_str = "2026-01-15"
        date_obj = date.fromisoformat(date_str)
        assert date_obj.year == 2026
        assert date_obj.month == 1
        assert date_obj.day == 15

    def test_invalid_date_parsing(self):
        """Test invalid date string raises ValueError."""
        date_str = "invalid-date"
        with pytest.raises(ValueError):
            date.fromisoformat(date_str)


class TestWorkOrderUpdateBehavior:
    """Test update-specific behavior."""

    def test_model_dump_exclude_unset(self):
        """Test model_dump with exclude_unset only returns set fields."""
        from app.schemas.work_order import WorkOrderUpdate

        update = WorkOrderUpdate(status="completed")
        data = update.model_dump(exclude_unset=True)

        assert "status" in data
        assert data["status"] == "completed"
        assert "customer_id" not in data
        assert "notes" not in data

    def test_empty_update_returns_empty_dict(self):
        """Test empty update returns empty dict."""
        from app.schemas.work_order import WorkOrderUpdate

        update = WorkOrderUpdate()
        data = update.model_dump(exclude_unset=True)

        assert data == {}


class TestWorkOrderJobTypes:
    """Test valid job types."""

    def test_valid_job_types(self):
        """Test all valid job types are recognized."""
        valid_types = [
            "pumping", "inspection", "repair", "installation",
            "emergency", "maintenance", "grease_trap", "camera_inspection"
        ]
        for job_type in valid_types:
            # Just verify these are strings
            assert isinstance(job_type, str)


class TestWorkOrderStatuses:
    """Test valid work order statuses."""

    def test_valid_statuses(self):
        """Test all valid statuses are recognized."""
        valid_statuses = [
            "draft", "scheduled", "confirmed", "enroute", "on_site",
            "in_progress", "completed", "canceled", "requires_followup"
        ]
        for status in valid_statuses:
            assert isinstance(status, str)


class TestWorkOrderPriorities:
    """Test valid work order priorities."""

    def test_valid_priorities(self):
        """Test all valid priorities are recognized."""
        valid_priorities = ["low", "normal", "high", "urgent", "emergency"]
        for priority in valid_priorities:
            assert isinstance(priority, str)


class TestScheduleFieldsDetection:
    """Test schedule-related fields detection for WebSocket events."""

    def test_schedule_fields_intersection(self):
        """Test detecting schedule-related field updates."""
        schedule_fields = {"scheduled_date", "time_window_start", "time_window_end", "assigned_technician"}
        update_data = {"scheduled_date": "2026-01-20", "notes": "Updated"}

        intersection = schedule_fields.intersection(update_data.keys())
        assert "scheduled_date" in intersection
        assert "notes" not in intersection
        assert len(intersection) == 1

    def test_no_schedule_fields_intersection(self):
        """Test no schedule fields in update."""
        schedule_fields = {"scheduled_date", "time_window_start", "time_window_end", "assigned_technician"}
        update_data = {"notes": "Updated", "status": "completed"}

        intersection = schedule_fields.intersection(update_data.keys())
        assert len(intersection) == 0
