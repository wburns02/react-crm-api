"""Data integrity tests for FK cascades, SET NULL behavior, timestamp defaults,
and Pydantic schema validation.

These tests use the real SQLAlchemy models against an in-memory SQLite database
with foreign key enforcement enabled.

NOTE on UUID handling:
    SQLite stores SQLAlchemy UUID(as_uuid=True) columns as 32-character hex
    strings (no hyphens).  When issuing raw SQL queries with ``text()``, we must
    pass ``uuid_obj.hex`` rather than ``str(uuid_obj)`` so the WHERE clause
    matches the stored value.
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base

# Models
from app.models.customer import Customer
from app.models.work_order import WorkOrder
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.quote import Quote
from app.models.activity import Activity
from app.models.equipment import Equipment
from app.models.contract import Contract
from app.models.call_log import CallLog
from app.models.message import Message
from app.models.work_order_photo import WorkOrderPhoto
from app.models.technician import Technician

# Import all models so Base.metadata includes every table (avoids FK target errors)
import app.models  # noqa: F401

# Schemas
from app.schemas.customer import CustomerCreate
from app.schemas.invoice import InvoiceCreate, InvoiceUpdate
from app.schemas.payment import PaymentBase, PaymentUpdate
from app.schemas.quote import QuoteCreate

# ---------------------------------------------------------------------------
# Fixture: test database with FK enforcement
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite://"


@pytest_asyncio.fixture
async def test_db():
    """Create a fresh in-memory SQLite database with FK enforcement."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable SQLite foreign key enforcement on every raw connection
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hex(uid: uuid.UUID) -> str:
    """Return the 32-char hex representation that SQLite stores for UUIDs."""
    return uid.hex


async def _create_customer(session: AsyncSession) -> Customer:
    """Insert a minimal customer and return it."""
    customer = Customer(
        id=uuid.uuid4(),
        first_name="Jane",
        last_name="Doe",
        email="jane@example.com",
        phone="(555) 123-4567",
    )
    session.add(customer)
    await session.flush()
    return customer


async def _create_work_order(session: AsyncSession, customer_id: uuid.UUID) -> WorkOrder:
    """Insert a work order linked to *customer_id*."""
    wo = WorkOrder(
        id=uuid.uuid4(),
        customer_id=customer_id,
        job_type="pumping",
        status="scheduled",
    )
    session.add(wo)
    await session.flush()
    return wo


# ============================================================================
# 1. FK CASCADE behavior  --  deleting a customer cascades to children
# ============================================================================


class TestCustomerCascadeDelete:
    """When a customer row is deleted, child rows with ondelete=CASCADE
    must be removed from the database automatically."""

    @pytest.mark.asyncio
    async def test_work_orders_cascade_deleted(self, test_db: AsyncSession):
        """Work orders should be cascade-deleted when customer is deleted."""
        customer = await _create_customer(test_db)
        wo = await _create_work_order(test_db, customer.id)
        await test_db.commit()

        wo_id = wo.id
        # Delete via raw SQL to bypass ORM relationship cascades and test
        # the database-level ON DELETE CASCADE constraint directly.
        await test_db.execute(
            text("DELETE FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )
        await test_db.commit()

        row = (await test_db.execute(
            text("SELECT id FROM work_orders WHERE id = :wid"),
            {"wid": _hex(wo_id)},
        )).first()
        assert row is None, "Work order should be cascade-deleted with customer"

    @pytest.mark.asyncio
    async def test_invoices_cascade_deleted(self, test_db: AsyncSession):
        """Invoices should be cascade-deleted when customer is deleted."""
        customer = await _create_customer(test_db)
        invoice = Invoice(
            id=uuid.uuid4(),
            customer_id=customer.id,
            invoice_number="INV-0001",
            amount=Decimal("150.00"),
            status="draft",
        )
        test_db.add(invoice)
        await test_db.commit()

        inv_id = invoice.id
        await test_db.execute(
            text("DELETE FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )
        await test_db.commit()

        row = (await test_db.execute(
            text("SELECT id FROM invoices WHERE id = :iid"),
            {"iid": _hex(inv_id)},
        )).first()
        assert row is None, "Invoice should be cascade-deleted with customer"

    @pytest.mark.asyncio
    async def test_quotes_cascade_deleted(self, test_db: AsyncSession):
        """Quotes should be cascade-deleted when customer is deleted."""
        customer = await _create_customer(test_db)
        quote = Quote(
            id=uuid.uuid4(),
            customer_id=customer.id,
            quote_number="QT-0001",
            status="draft",
        )
        test_db.add(quote)
        await test_db.commit()

        qt_id = quote.id
        await test_db.execute(
            text("DELETE FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )
        await test_db.commit()

        row = (await test_db.execute(
            text("SELECT id FROM quotes WHERE id = :qid"),
            {"qid": _hex(qt_id)},
        )).first()
        assert row is None, "Quote should be cascade-deleted with customer"

    @pytest.mark.asyncio
    async def test_activities_cascade_deleted(self, test_db: AsyncSession):
        """Activities should be cascade-deleted when customer is deleted."""
        customer = await _create_customer(test_db)
        activity = Activity(
            id=uuid.uuid4(),
            customer_id=customer.id,
            activity_type="note",
            description="Initial site visit notes.",
        )
        test_db.add(activity)
        await test_db.commit()

        act_id = activity.id
        await test_db.execute(
            text("DELETE FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )
        await test_db.commit()

        row = (await test_db.execute(
            text("SELECT id FROM activities WHERE id = :aid"),
            {"aid": _hex(act_id)},
        )).first()
        assert row is None, "Activity should be cascade-deleted with customer"

    @pytest.mark.asyncio
    async def test_equipment_cascade_deleted(self, test_db: AsyncSession):
        """Equipment should be cascade-deleted when customer is deleted."""
        customer = await _create_customer(test_db)
        equip = Equipment(
            id=uuid.uuid4(),
            customer_id=customer.id,
            equipment_type="septic_tank",
        )
        test_db.add(equip)
        await test_db.commit()

        eq_id = equip.id
        await test_db.execute(
            text("DELETE FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )
        await test_db.commit()

        row = (await test_db.execute(
            text("SELECT id FROM equipment WHERE id = :eid"),
            {"eid": _hex(eq_id)},
        )).first()
        assert row is None, "Equipment should be cascade-deleted with customer"

    @pytest.mark.asyncio
    async def test_contracts_cascade_deleted(self, test_db: AsyncSession):
        """Contracts should be cascade-deleted when customer is deleted."""
        customer = await _create_customer(test_db)
        contract = Contract(
            id=uuid.uuid4(),
            customer_id=customer.id,
            contract_number="CTR-0001",
            name="Annual Maintenance",
            contract_type="maintenance",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            status="active",
        )
        test_db.add(contract)
        await test_db.commit()

        ctr_id = contract.id
        await test_db.execute(
            text("DELETE FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )
        await test_db.commit()

        row = (await test_db.execute(
            text("SELECT id FROM contracts WHERE id = :cid"),
            {"cid": _hex(ctr_id)},
        )).first()
        assert row is None, "Contract should be cascade-deleted with customer"

    @pytest.mark.asyncio
    async def test_multiple_children_all_cascade_deleted(self, test_db: AsyncSession):
        """Deleting a customer with multiple child types should remove all."""
        customer = await _create_customer(test_db)
        cust_id = customer.id

        # Create one record of each CASCADE type
        wo = await _create_work_order(test_db, cust_id)
        invoice = Invoice(
            id=uuid.uuid4(), customer_id=cust_id,
            invoice_number="INV-MULTI", amount=Decimal("100"), status="draft",
        )
        quote = Quote(
            id=uuid.uuid4(), customer_id=cust_id,
            quote_number="QT-MULTI", status="draft",
        )
        activity = Activity(
            id=uuid.uuid4(), customer_id=cust_id,
            activity_type="call", description="Follow-up call.",
        )
        equip = Equipment(
            id=uuid.uuid4(), customer_id=cust_id,
            equipment_type="pump",
        )
        contract = Contract(
            id=uuid.uuid4(), customer_id=cust_id,
            contract_number="CTR-MULTI", name="Full Service",
            contract_type="service",
            start_date=date(2025, 6, 1), end_date=date(2026, 5, 31),
        )
        test_db.add_all([invoice, quote, activity, equip, contract])
        await test_db.commit()

        ids = {
            "work_orders": _hex(wo.id),
            "invoices": _hex(invoice.id),
            "quotes": _hex(quote.id),
            "activities": _hex(activity.id),
            "equipment": _hex(equip.id),
            "contracts": _hex(contract.id),
        }

        await test_db.execute(
            text("DELETE FROM customers WHERE id = :cid"),
            {"cid": _hex(cust_id)},
        )
        await test_db.commit()

        for table, row_id in ids.items():
            row = (await test_db.execute(
                text(f"SELECT id FROM {table} WHERE id = :rid"),  # noqa: S608
                {"rid": row_id},
            )).first()
            assert row is None, f"{table} row should be cascade-deleted with customer"


# ============================================================================
# 1b. FK CASCADE  --  work order photos cascade when work order is deleted
# ============================================================================


class TestWorkOrderPhotoCascadeDelete:
    """Work order photos should be cascade-deleted when the parent work order
    is deleted."""

    @pytest.mark.asyncio
    async def test_photos_cascade_deleted_with_work_order(self, test_db: AsyncSession):
        """Deleting a work order should cascade-delete its photos."""
        customer = await _create_customer(test_db)
        wo = await _create_work_order(test_db, customer.id)

        photo = WorkOrderPhoto(
            id=uuid.uuid4(),
            work_order_id=wo.id,
            photo_type="before",
            data="base64encodedimagedata",
            timestamp=datetime.utcnow(),
        )
        test_db.add(photo)
        await test_db.commit()

        photo_id = photo.id
        # Delete the work order directly (leave the customer alive)
        await test_db.execute(
            text("DELETE FROM work_orders WHERE id = :wid"),
            {"wid": _hex(wo.id)},
        )
        await test_db.commit()

        row = (await test_db.execute(
            text("SELECT id FROM work_order_photos WHERE id = :pid"),
            {"pid": _hex(photo_id)},
        )).first()
        assert row is None, "Photo should be cascade-deleted with work order"

    @pytest.mark.asyncio
    async def test_multiple_photos_cascade_deleted(self, test_db: AsyncSession):
        """All photos linked to a work order should be deleted together."""
        customer = await _create_customer(test_db)
        wo = await _create_work_order(test_db, customer.id)

        photo_ids = []
        for ptype in ("before", "during", "after"):
            photo = WorkOrderPhoto(
                id=uuid.uuid4(),
                work_order_id=wo.id,
                photo_type=ptype,
                data=f"data-{ptype}",
                timestamp=datetime.utcnow(),
            )
            test_db.add(photo)
            photo_ids.append(photo.id)

        await test_db.commit()

        await test_db.execute(
            text("DELETE FROM work_orders WHERE id = :wid"),
            {"wid": _hex(wo.id)},
        )
        await test_db.commit()

        for pid in photo_ids:
            row = (await test_db.execute(
                text("SELECT id FROM work_order_photos WHERE id = :pid"),
                {"pid": _hex(pid)},
            )).first()
            assert row is None, f"Photo {pid} should be cascade-deleted with work order"

    @pytest.mark.asyncio
    async def test_photos_cascade_through_customer_delete(self, test_db: AsyncSession):
        """Deleting a customer should cascade to work orders, which in turn
        cascade to photos (transitive cascade)."""
        customer = await _create_customer(test_db)
        wo = await _create_work_order(test_db, customer.id)

        photo = WorkOrderPhoto(
            id=uuid.uuid4(),
            work_order_id=wo.id,
            photo_type="issue",
            data="cracked-pipe-photo",
            timestamp=datetime.utcnow(),
        )
        test_db.add(photo)
        await test_db.commit()

        photo_id = photo.id
        wo_id = wo.id

        await test_db.execute(
            text("DELETE FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )
        await test_db.commit()

        wo_row = (await test_db.execute(
            text("SELECT id FROM work_orders WHERE id = :wid"),
            {"wid": _hex(wo_id)},
        )).first()
        assert wo_row is None, "Work order should be cascade-deleted with customer"

        photo_row = (await test_db.execute(
            text("SELECT id FROM work_order_photos WHERE id = :pid"),
            {"pid": _hex(photo_id)},
        )).first()
        assert photo_row is None, "Photo should be transitively cascade-deleted"


# ============================================================================
# 2. FK SET NULL behavior  --  child rows survive but lose their customer_id
# ============================================================================


class TestSetNullOnCustomerDelete:
    """When a customer is deleted, rows in call_logs, messages, and payments
    should survive with their customer_id set to NULL."""

    @pytest.mark.asyncio
    async def test_call_log_customer_id_set_null(self, test_db: AsyncSession):
        """call_logs.customer_id should become NULL when customer is deleted."""
        customer = await _create_customer(test_db)
        call = CallLog(
            id=uuid.uuid4(),
            customer_id=customer.id,
            caller_number="5551234567",
            called_number="5559876543",
            direction="inbound",
            user_id="1",
        )
        test_db.add(call)
        await test_db.commit()

        call_id = call.id
        await test_db.execute(
            text("DELETE FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )
        await test_db.commit()

        row = (await test_db.execute(
            text("SELECT id, customer_id FROM call_logs WHERE id = :clid"),
            {"clid": _hex(call_id)},
        )).first()
        assert row is not None, "Call log should still exist after customer deletion"
        assert row[1] is None, "call_logs.customer_id should be NULL"

    @pytest.mark.asyncio
    async def test_message_customer_id_set_null(self, test_db: AsyncSession):
        """messages.customer_id should become NULL when customer is deleted.

        Note: The Customer ORM model declares ``cascade="all, delete-orphan"``
        on the messages relationship, which would delete messages via the ORM.
        However, the Message FK column specifies ``ondelete='SET NULL'`` at the
        database level.  To test the *database-level* constraint in isolation,
        we insert the message via raw SQL (bypassing the ORM relationship
        entirely) and then delete the customer via raw SQL.
        """
        customer = await _create_customer(test_db)
        await test_db.commit()

        msg_id = uuid.uuid4()
        # Insert message via raw SQL so the ORM identity map has no knowledge
        # of this message and therefore cannot cascade-delete it.
        await test_db.execute(
            text(
                "INSERT INTO messages (id, customer_id, message_type, direction, content) "
                "VALUES (:mid, :cid, 'sms', 'outbound', 'Appointment reminder.')"
            ),
            {"mid": _hex(msg_id), "cid": _hex(customer.id)},
        )
        await test_db.commit()

        await test_db.execute(
            text("DELETE FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )
        await test_db.commit()

        row = (await test_db.execute(
            text("SELECT id, customer_id FROM messages WHERE id = :mid"),
            {"mid": _hex(msg_id)},
        )).first()
        assert row is not None, "Message should still exist after customer deletion"
        assert row[1] is None, "messages.customer_id should be NULL"

    @pytest.mark.asyncio
    async def test_payment_customer_id_set_null(self, test_db: AsyncSession):
        """payments.customer_id should become NULL when customer is deleted."""
        customer = await _create_customer(test_db)
        payment = Payment(
            id=uuid.uuid4(),
            customer_id=customer.id,
            amount=Decimal("250.00"),
            status="completed",
            payment_method="card",
        )
        test_db.add(payment)
        await test_db.commit()

        pay_id = payment.id
        await test_db.execute(
            text("DELETE FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )
        await test_db.commit()

        row = (await test_db.execute(
            text("SELECT id, customer_id FROM payments WHERE id = :pid"),
            {"pid": _hex(pay_id)},
        )).first()
        assert row is not None, "Payment should still exist after customer deletion"
        assert row[1] is None, "payments.customer_id should be NULL"

    @pytest.mark.asyncio
    async def test_set_null_preserves_other_fields(self, test_db: AsyncSession):
        """SET NULL should only null the FK column, not other payment data."""
        customer = await _create_customer(test_db)
        payment = Payment(
            id=uuid.uuid4(),
            customer_id=customer.id,
            amount=Decimal("99.99"),
            status="completed",
            payment_method="cash",
            description="Quarterly pumping service",
        )
        test_db.add(payment)
        await test_db.commit()

        pay_id = payment.id
        await test_db.execute(
            text("DELETE FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )
        await test_db.commit()

        row = (await test_db.execute(
            text(
                "SELECT customer_id, amount, status, payment_method, description "
                "FROM payments WHERE id = :pid"
            ),
            {"pid": _hex(pay_id)},
        )).first()
        assert row is not None
        assert row[0] is None, "customer_id should be NULL"
        assert float(row[1]) == pytest.approx(99.99)
        assert row[2] == "completed"
        assert row[3] == "cash"
        assert row[4] == "Quarterly pumping service"

    @pytest.mark.asyncio
    async def test_multiple_set_null_records(self, test_db: AsyncSession):
        """Multiple call logs for one customer should all get SET NULL."""
        customer = await _create_customer(test_db)
        call_ids = []
        for i in range(3):
            call = CallLog(
                id=uuid.uuid4(),
                customer_id=customer.id,
                caller_number=f"555000000{i}",
                called_number="5559999999",
                direction="outbound",
                user_id="1",
            )
            test_db.add(call)
            call_ids.append(call.id)
        await test_db.commit()

        await test_db.execute(
            text("DELETE FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )
        await test_db.commit()

        for cid in call_ids:
            row = (await test_db.execute(
                text("SELECT customer_id FROM call_logs WHERE id = :clid"),
                {"clid": _hex(cid)},
            )).first()
            assert row is not None, "Call log should survive deletion"
            assert row[0] is None, "customer_id should be NULL"


# ============================================================================
# 3. Timestamp defaults  --  server_default=func.now() auto-populates
# ============================================================================


class TestTimestampDefaults:
    """created_at should be auto-populated by the database via server_default."""

    @pytest.mark.asyncio
    async def test_customer_created_at_auto_populated(self, test_db: AsyncSession):
        """Customer.created_at should be set automatically on insert."""
        customer = Customer(
            id=uuid.uuid4(),
            first_name="Auto",
            last_name="Timestamp",
        )
        test_db.add(customer)
        await test_db.commit()

        row = (await test_db.execute(
            text("SELECT created_at FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )).first()
        assert row is not None
        assert row[0] is not None, "Customer created_at should be auto-populated"

    @pytest.mark.asyncio
    async def test_customer_created_at_is_reasonable(self, test_db: AsyncSession):
        """Customer.created_at should be close to the current time."""
        # SQLite CURRENT_TIMESTAMP has second-level precision, so we truncate
        # our reference timestamps to the nearest second to avoid sub-second
        # mismatches.
        before = datetime.utcnow().replace(microsecond=0)
        customer = Customer(
            id=uuid.uuid4(),
            first_name="Time",
            last_name="Check",
        )
        test_db.add(customer)
        await test_db.commit()
        # Add 1 second buffer to account for truncation
        after = datetime.utcnow().replace(microsecond=0) + timedelta(seconds=1)

        row = (await test_db.execute(
            text("SELECT created_at FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )).first()
        ts_str = row[0]
        # SQLite stores datetimes as strings; parse them
        if isinstance(ts_str, str):
            created = datetime.fromisoformat(ts_str)
        else:
            created = ts_str

        assert before <= created <= after, (
            f"created_at ({created}) should be between {before} and {after}"
        )

    @pytest.mark.asyncio
    async def test_technician_created_at_auto_populated(self, test_db: AsyncSession):
        """Technician.created_at should be set automatically on insert."""
        tech = Technician(
            id=uuid.uuid4(),
            first_name="Bob",
            last_name="Builder",
        )
        test_db.add(tech)
        await test_db.commit()

        row = (await test_db.execute(
            text("SELECT created_at FROM technicians WHERE id = :tid"),
            {"tid": _hex(tech.id)},
        )).first()
        assert row is not None
        assert row[0] is not None, "Technician created_at should be auto-populated"

    @pytest.mark.asyncio
    async def test_customer_created_at_not_overwritten(self, test_db: AsyncSession):
        """If created_at is explicitly provided, the explicit value should be used."""
        explicit_ts = datetime(2020, 1, 15, 10, 30, 0)
        customer = Customer(
            id=uuid.uuid4(),
            first_name="Explicit",
            last_name="Time",
            created_at=explicit_ts,
        )
        test_db.add(customer)
        await test_db.commit()

        row = (await test_db.execute(
            text("SELECT created_at FROM customers WHERE id = :cid"),
            {"cid": _hex(customer.id)},
        )).first()
        ts_str = row[0]
        if isinstance(ts_str, str):
            created = datetime.fromisoformat(ts_str)
        else:
            created = ts_str

        assert created == explicit_ts, (
            "Explicit created_at should be preserved, not overwritten by server_default"
        )

    @pytest.mark.asyncio
    async def test_invoice_created_at_auto_populated(self, test_db: AsyncSession):
        """Invoice.created_at should be set automatically on insert."""
        customer = await _create_customer(test_db)
        invoice = Invoice(
            id=uuid.uuid4(),
            customer_id=customer.id,
            invoice_number="INV-TS-001",
            amount=Decimal("50.00"),
            status="draft",
        )
        test_db.add(invoice)
        await test_db.commit()

        row = (await test_db.execute(
            text("SELECT created_at FROM invoices WHERE id = :iid"),
            {"iid": _hex(invoice.id)},
        )).first()
        assert row is not None
        assert row[0] is not None, "Invoice created_at should be auto-populated"


# ============================================================================
# 4. Schema validation  --  Pydantic rejects invalid data
# ============================================================================


class TestEmailValidation:
    """Customer email must contain '@' and '.'."""

    def test_valid_email_accepted(self):
        """A well-formed email should be accepted."""
        schema = CustomerCreate(
            first_name="Valid",
            last_name="Email",
            email="valid@example.com",
        )
        assert schema.email == "valid@example.com"

    def test_email_missing_at_sign_rejected(self):
        """An email without '@' should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CustomerCreate(
                first_name="Bad",
                last_name="Email",
                email="not-an-email.com",
            )
        errors = exc_info.value.errors()
        assert any("email" in str(e).lower() for e in errors)

    def test_email_missing_dot_rejected(self):
        """An email without '.' should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CustomerCreate(
                first_name="Bad",
                last_name="Email",
                email="user@localhost",
            )
        errors = exc_info.value.errors()
        assert any("email" in str(e).lower() for e in errors)

    def test_empty_email_becomes_none(self):
        """An empty string email should be normalized to None."""
        schema = CustomerCreate(
            first_name="Empty",
            last_name="Email",
            email="",
        )
        assert schema.email is None

    def test_whitespace_email_becomes_none(self):
        """A whitespace-only email should be normalized to None."""
        schema = CustomerCreate(
            first_name="Space",
            last_name="Email",
            email="   ",
        )
        assert schema.email is None


class TestPhoneValidation:
    """Customer phone must have 10 or 11 digits."""

    def test_valid_10_digit_phone_accepted(self):
        """A 10-digit US phone should be accepted and normalized."""
        schema = CustomerCreate(
            first_name="Good",
            last_name="Phone",
            phone="5551234567",
        )
        assert schema.phone == "(555) 123-4567"

    def test_valid_11_digit_phone_accepted(self):
        """An 11-digit phone starting with 1 should be accepted."""
        schema = CustomerCreate(
            first_name="Good",
            last_name="Phone",
            phone="15551234567",
        )
        assert schema.phone == "(555) 123-4567"

    def test_too_few_digits_rejected(self):
        """A phone with fewer than 10 digits should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CustomerCreate(
                first_name="Bad",
                last_name="Phone",
                phone="555123",
            )
        errors = exc_info.value.errors()
        assert any("phone" in str(e).lower() or "digit" in str(e).lower() for e in errors)

    def test_too_many_digits_rejected(self):
        """A phone with more than 11 digits should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CustomerCreate(
                first_name="Bad",
                last_name="Phone",
                phone="155512345678901",
            )
        errors = exc_info.value.errors()
        assert any("phone" in str(e).lower() or "digit" in str(e).lower() for e in errors)

    def test_formatted_phone_accepted(self):
        """A pre-formatted phone like (555) 123-4567 should be accepted."""
        schema = CustomerCreate(
            first_name="Formatted",
            last_name="Phone",
            phone="(555) 123-4567",
        )
        assert schema.phone == "(555) 123-4567"

    def test_none_phone_accepted(self):
        """A None phone value should be accepted (phone is optional)."""
        schema = CustomerCreate(
            first_name="No",
            last_name="Phone",
            phone=None,
        )
        assert schema.phone is None


class TestInvoiceStatusValidation:
    """Invoice status must be one of the allowed literal values."""

    def test_valid_invoice_status_accepted(self):
        """'draft' should be accepted as a valid invoice status."""
        schema = InvoiceCreate(
            customer_id=str(uuid.uuid4()),
            status="draft",
            amount=Decimal("100"),
        )
        assert schema.status == "draft"

    def test_all_valid_invoice_statuses(self):
        """All defined invoice statuses should be accepted."""
        for status in ("draft", "sent", "paid", "overdue", "void"):
            schema = InvoiceCreate(
                customer_id=str(uuid.uuid4()),
                status=status,
                amount=Decimal("0"),
            )
            assert schema.status == status

    def test_invalid_invoice_status_rejected(self):
        """An unrecognized invoice status should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            InvoiceCreate(
                customer_id=str(uuid.uuid4()),
                status="bogus_status",
                amount=Decimal("100"),
            )
        errors = exc_info.value.errors()
        assert any("status" in str(e).lower() for e in errors)

    def test_invalid_invoice_update_status_rejected(self):
        """InvoiceUpdate should also reject invalid status values."""
        with pytest.raises(ValidationError) as exc_info:
            InvoiceUpdate(status="cancelled")
        errors = exc_info.value.errors()
        assert any("status" in str(e).lower() for e in errors)


class TestPaymentStatusValidation:
    """Payment status must be one of the allowed literal values."""

    def test_valid_payment_status_accepted(self):
        """'completed' should be accepted as a valid payment status."""
        schema = PaymentBase(
            amount=50.0,
            status="completed",
        )
        assert schema.status == "completed"

    def test_all_valid_payment_statuses(self):
        """All defined payment statuses should be accepted."""
        for status in ("pending", "completed", "failed", "refunded", "cancelled"):
            schema = PaymentBase(amount=10.0, status=status)
            assert schema.status == status

    def test_invalid_payment_status_rejected(self):
        """An unrecognized payment status should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PaymentBase(amount=10.0, status="processing")
        errors = exc_info.value.errors()
        assert any("status" in str(e).lower() for e in errors)


class TestQuoteStatusValidation:
    """Quote status must be one of the allowed literal values."""

    def test_valid_quote_status_accepted(self):
        """'sent' should be accepted as a valid quote status."""
        schema = QuoteCreate(
            customer_id=str(uuid.uuid4()),
            status="sent",
        )
        assert schema.status == "sent"

    def test_all_valid_quote_statuses(self):
        """All defined quote statuses should be accepted."""
        for status in ("draft", "sent", "accepted", "declined", "expired"):
            schema = QuoteCreate(
                customer_id=str(uuid.uuid4()),
                status=status,
            )
            assert schema.status == status

    def test_invalid_quote_status_rejected(self):
        """An unrecognized quote status should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            QuoteCreate(
                customer_id=str(uuid.uuid4()),
                status="approved",
            )
        errors = exc_info.value.errors()
        assert any("status" in str(e).lower() for e in errors)


class TestNegativeAmountValidation:
    """Negative monetary amounts should be rejected."""

    def test_invoice_negative_amount_rejected(self):
        """InvoiceCreate should reject negative amounts."""
        with pytest.raises(ValidationError) as exc_info:
            InvoiceCreate(
                customer_id=str(uuid.uuid4()),
                amount=Decimal("-50.00"),
            )
        errors = exc_info.value.errors()
        assert any("amount" in str(e).lower() for e in errors)

    def test_invoice_zero_amount_accepted(self):
        """InvoiceCreate should accept a zero amount."""
        schema = InvoiceCreate(
            customer_id=str(uuid.uuid4()),
            amount=Decimal("0"),
        )
        assert schema.amount == Decimal("0")

    def test_invoice_update_negative_amount_rejected(self):
        """InvoiceUpdate should reject negative amounts."""
        with pytest.raises(ValidationError) as exc_info:
            InvoiceUpdate(amount=Decimal("-1"))
        errors = exc_info.value.errors()
        assert any("amount" in str(e).lower() for e in errors)

    def test_invoice_update_negative_paid_amount_rejected(self):
        """InvoiceUpdate should reject negative paid_amount."""
        with pytest.raises(ValidationError) as exc_info:
            InvoiceUpdate(paid_amount=Decimal("-10"))
        errors = exc_info.value.errors()
        assert any("amount" in str(e).lower() for e in errors)

    def test_payment_negative_amount_rejected(self):
        """PaymentBase should reject a negative amount via ge=0 constraint."""
        with pytest.raises(ValidationError) as exc_info:
            PaymentBase(amount=-25.0)
        errors = exc_info.value.errors()
        assert any("amount" in str(e).lower() for e in errors)

    def test_payment_zero_amount_accepted(self):
        """PaymentBase should accept a zero amount."""
        schema = PaymentBase(amount=0.0)
        assert schema.amount == 0.0

    def test_payment_update_negative_amount_rejected(self):
        """PaymentUpdate should reject negative amounts."""
        with pytest.raises(ValidationError) as exc_info:
            PaymentUpdate(amount=-100.0)
        errors = exc_info.value.errors()
        assert any("amount" in str(e).lower() for e in errors)

    def test_payment_positive_amount_accepted(self):
        """PaymentBase should accept a normal positive amount."""
        schema = PaymentBase(amount=199.99)
        assert schema.amount == pytest.approx(199.99)
