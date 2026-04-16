# Employee Lifecycle — Plan 2: Recruiting

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working hiring pipeline on top of the Plan 1 foundation — public `/careers/{slug}/apply` form, applicant + application data model, recruiter admin UI with stage pill-tabs, templated candidate SMS on stage change, Indeed-friendly apply tracking.

**Architecture:** Extends the existing `app/hr/` bounded module. Adds `hr_applicants`, `hr_applications`, `hr_application_events`, and `hr_recruiting_message_templates` tables. Public apply endpoint accepts multipart resume uploads, stores via the same `hr.shared.storage` helper used by e-sign. Stage transitions go through a small state machine and emit `hr.applicant.hired` via the Plan 1 `TriggerBus` so Plan 3 can pick it up. Frontend adds `RequisitionDetailPage` with pill-tabs + `ApplicantDetailPage` + HR sidebar nav entry.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2, Jinja2 (apply form SSR), pypdf (already installed), existing `app.services.sms_service.SMSService`, React 19 + TanStack Query + Zod + Tailwind, Playwright.

**Spec:** `docs/superpowers/specs/2026-04-15-employee-lifecycle-design.md` §3.2, §5, §10.

**Prerequisite:** Plan 1 already shipped (migrations 096–100 applied, `HR_MODULE_ENABLED=true` on Railway, `hr_router` mounted, 5 document templates seeded).

---

## File Structure

Files created (backend):

```
app/hr/recruiting/applicant_models.py         ← HrApplicant, HrApplication, HrApplicationEvent
app/hr/recruiting/message_templates.py        ← HrRecruitingMessageTemplate + seed helper
app/hr/recruiting/applicant_schemas.py        ← Pydantic IN/OUT
app/hr/recruiting/applicant_services.py       ← create_applicant, list, get
app/hr/recruiting/application_services.py     ← create_application, transition_stage, list_by_requisition
app/hr/recruiting/applicant_router.py         ← /hr/applicants/*
app/hr/recruiting/application_router.py       ← /hr/applications/*
app/hr/recruiting/public_apply.py             ← public POST apply endpoint (multipart)
app/hr/recruiting/notifications.py            ← SMS send on stage change
app/hr/careers/templates/apply.html           ← REPLACE Plan 1 placeholder with real form
tests/hr/test_applicant_service.py
tests/hr/test_application_service.py
tests/hr/test_applicant_router.py
tests/hr/test_application_router.py
tests/hr/test_public_apply.py
tests/hr/test_recruiting_sms.py

alembic/versions/101_hr_applicant_tables.py
alembic/versions/102_hr_recruiting_message_templates_seed.py
```

Files modified (backend):

```
app/hr/router.py                              ← include applicant_router + application_router
app/main.py                                   ← mount public_apply router on /api/v2/public
app/hr/recruiting/router.py                   ← add PATCH, DELETE, and applicant counts on list
app/hr/recruiting/models.py                   ← no changes (Plan 1 HrRequisition stays as-is)
app/models/__init__.py                        ← register new models
app/hr/careers/router.py                      ← update /{slug}/apply route (form now real)
```

Files created (frontend, `/home/will/ReactCRM`):

```
src/features/hr/recruiting/api-applicants.ts
src/features/hr/recruiting/api-applications.ts
src/features/hr/recruiting/pages/RequisitionDetailPage.tsx
src/features/hr/recruiting/pages/ApplicantDetailPage.tsx
src/features/hr/recruiting/components/PipelinePills.tsx
src/features/hr/recruiting/components/ApplicationRow.tsx
src/features/hr/recruiting/components/StageMenu.tsx
```

Files modified (frontend):

```
src/features/hr/index.ts                      ← re-export new pages
src/features/hr/recruiting/api.ts             ← add PATCH + DELETE + count
src/features/hr/recruiting/pages/RequisitionsListPage.tsx  ← show applicant counts, link to detail
src/routes/app/hr.routes.tsx                  ← add /hr/requisitions/:id and /hr/applicants/:id
src/components/layout/Sidebar.tsx             ← add HR nav entry (path found during A1)
```

Playwright:

```
ReactCRM/e2e/modules/hr-recruiting-flow.spec.ts
```

---

## Phase A — Reconciliation

### Task A1: Inventory existing sidebar + sms infra

**Files:**
- Read only: `src/components/layout/` (find sidebar)
- Read only: `app/services/sms_service.py`
- Read only: `app/models/sms_consent.py`
- Create: `app/hr/recruiting/PLAN_2_NOTES.md`

- [ ] **Step 1: Find the sidebar component**

```bash
cd /home/will/ReactCRM/.worktrees/hr-foundation
grep -rln "Outbound Dialer\|Call Library" src/components/ src/features/ | head -5
```

Inspect the file(s) returned. Document:
- Exact path of the sidebar component.
- How existing sections are grouped (Customer Management, Operations, Communications, etc.).
- Where a new "HR" top-level entry fits (between Marketing and Support is the spec-aligned slot — confirm).

- [ ] **Step 2: Inspect SMS send helper**

```bash
cd /home/will/react-crm-api
sed -n '20,60p' app/services/sms_service.py
```

Document in `PLAN_2_NOTES.md`:
- Exact import path (`from app.services.sms_service import SMSService` vs `send_sms`).
- Whether it's a singleton or instantiated per call.
- Whether it requires a consent check upstream or handles it internally.

- [ ] **Step 3: Inspect SMSConsent model**

```bash
sed -n '1,50p' app/models/sms_consent.py
```

Document: it is keyed to `customer_id`, not applicant. For Plan 2 we will record consent on the applicant row itself (`sms_consent_given`, `sms_consent_ip`, `sms_consent_at`) — **do not** write into `sms_consent` because applicants aren't customers yet. Once an applicant is hired and converted to a customer/user row, Plan 3 is responsible for migrating consent.

- [ ] **Step 4: Commit**

```bash
cd /home/will/react-crm-api
git add app/hr/recruiting/PLAN_2_NOTES.md
git commit -m "hr(plan2): reconciliation notes for sidebar + sms infra"
```

---

## Phase B — Applicant / Application data model

### Task B1: Models + migration 101

**Files:**
- Create: `app/hr/recruiting/applicant_models.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/101_hr_applicant_tables.py`

- [ ] **Step 1: Write the SQLAlchemy models**

```python
# app/hr/recruiting/applicant_models.py
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.sql import func

from app.database import Base


_INET = INET().with_variant(String(45), "sqlite")


class HrApplicant(Base):
    __tablename__ = "hr_applicants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    first_name = Column(String(128), nullable=False)
    last_name = Column(String(128), nullable=False)
    email = Column(String(256), nullable=False)
    phone = Column(String(32), nullable=True)
    resume_storage_key = Column(String(512), nullable=True)
    resume_parsed = Column(JSON, nullable=True)
    source = Column(String(32), nullable=False, default="careers_page")
    source_ref = Column(String(256), nullable=True)
    # SMS/TCPA consent captured at apply time. We keep this on the applicant
    # row (not sms_consent) because applicants are not yet customers/users.
    sms_consent_given = Column(Boolean, nullable=False, default=False)
    sms_consent_ip = Column(_INET, nullable=True)
    sms_consent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_hr_applicants_email", "email"),
        Index("ix_hr_applicants_created_at", "created_at"),
    )


class HrApplication(Base):
    __tablename__ = "hr_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    applicant_id = Column(
        UUID(as_uuid=True), ForeignKey("hr_applicants.id", ondelete="CASCADE"), nullable=False
    )
    requisition_id = Column(
        UUID(as_uuid=True), ForeignKey("hr_requisitions.id"), nullable=False
    )
    stage = Column(String(16), nullable=False, default="applied")  # applied|screen|ride_along|offer|hired|rejected|withdrawn
    stage_entered_at = Column(DateTime, server_default=func.now(), nullable=False)
    assigned_recruiter_id = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    rejection_reason = Column(String(256), nullable=True)
    rating = Column(SmallInteger, nullable=True)
    answers = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("applicant_id", "requisition_id", name="uq_hr_applications_applicant_req"),
        Index("ix_hr_applications_requisition_stage", "requisition_id", "stage"),
        Index("ix_hr_applications_stage", "stage"),
    )


class HrApplicationEvent(Base):
    __tablename__ = "hr_application_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    application_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type = Column(String(32), nullable=False)  # created|stage_changed|note_added|message_sent|resume_uploaded
    user_id = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_hr_application_events_application_created", "application_id", "created_at"),
    )


class HrRecruitingMessageTemplate(Base):
    __tablename__ = "hr_recruiting_message_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    stage = Column(String(16), nullable=False, unique=True)  # keyed by target stage
    channel = Column(String(16), nullable=False, default="sms")  # sms|email
    body = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
```

- [ ] **Step 2: Register in `app/models/__init__.py`**

Append after the existing HR imports:

```python
from app.hr.recruiting.applicant_models import (  # noqa: F401
    HrApplicant,
    HrApplication,
    HrApplicationEvent,
    HrRecruitingMessageTemplate,
)
```

- [ ] **Step 3: Write migration 101 by hand**

```python
# alembic/versions/101_hr_applicant_tables.py
"""hr applicant + application + event + message-template tables

Revision ID: 101
Revises: 100
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, UUID


revision = "101"
down_revision = "100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_applicants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("first_name", sa.String(128), nullable=False),
        sa.Column("last_name", sa.String(128), nullable=False),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("resume_storage_key", sa.String(512), nullable=True),
        sa.Column("resume_parsed", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="careers_page"),
        sa.Column("source_ref", sa.String(256), nullable=True),
        sa.Column("sms_consent_given", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sms_consent_ip", INET(), nullable=True),
        sa.Column("sms_consent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_hr_applicants_email", "hr_applicants", ["email"])
    op.create_index("ix_hr_applicants_created_at", "hr_applicants", ["created_at"])

    op.create_table(
        "hr_applications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "applicant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_applicants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requisition_id", UUID(as_uuid=True), sa.ForeignKey("hr_requisitions.id"), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False, server_default="applied"),
        sa.Column("stage_entered_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("assigned_recruiter_id", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("rejection_reason", sa.String(256), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("answers", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("applicant_id", "requisition_id", name="uq_hr_applications_applicant_req"),
    )
    op.create_index("ix_hr_applications_requisition_stage", "hr_applications", ["requisition_id", "stage"])
    op.create_index("ix_hr_applications_stage", "hr_applications", ["stage"])

    op.create_table(
        "hr_application_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "application_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_hr_application_events_application_created",
        "hr_application_events",
        ["application_id", "created_at"],
    )

    op.create_table(
        "hr_recruiting_message_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("stage", sa.String(16), nullable=False, unique=True),
        sa.Column("channel", sa.String(16), nullable=False, server_default="sms"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("hr_recruiting_message_templates")
    op.drop_index("ix_hr_application_events_application_created", table_name="hr_application_events")
    op.drop_table("hr_application_events")
    op.drop_index("ix_hr_applications_stage", table_name="hr_applications")
    op.drop_index("ix_hr_applications_requisition_stage", table_name="hr_applications")
    op.drop_table("hr_applications")
    op.drop_index("ix_hr_applicants_created_at", table_name="hr_applicants")
    op.drop_index("ix_hr_applicants_email", table_name="hr_applicants")
    op.drop_table("hr_applicants")
```

- [ ] **Step 4: Verify create_all on SQLite**

Run:
```bash
PYTHONPATH=. python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from app.database import Base
import app.models

async def main():
    engine = create_async_engine('sqlite+aiosqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from sqlalchemy import text
        r = await conn.execute(text(\"select name from sqlite_master where type='table' and name like 'hr_%' order by name\"))
        print('\n'.join([x[0] for x in r.all()]))
    await engine.dispose()

asyncio.run(main())
"
```
Expected: `hr_applicants`, `hr_application_events`, `hr_applications`, `hr_recruiting_message_templates` appear in the list alongside the Plan 1 tables (15 pre-existing + 4 new = 19 total).

- [ ] **Step 5: Verify migration on real Postgres**

Start a fresh container:
```bash
docker run -d --name hr-p2-mig --rm -e POSTGRES_PASSWORD=test -e POSTGRES_DB=hrtest -p 5435:5432 postgres:17
until docker exec hr-p2-mig pg_isready -U postgres 2>&1 | grep -q "accepting"; do sleep 1; done
docker exec hr-p2-mig psql -U postgres -d hrtest -c "CREATE EXTENSION IF NOT EXISTS pgcrypto; CREATE TABLE api_users (id SERIAL PRIMARY KEY, email VARCHAR(255)); CREATE TABLE company_entities (id UUID PRIMARY KEY);"
DATABASE_URL=postgresql+asyncpg://postgres:test@localhost:5435/hrtest PYTHONPATH=. alembic stamp 095
DATABASE_URL=postgresql+asyncpg://postgres:test@localhost:5435/hrtest HR_STORAGE_ROOT=/tmp/hr-p2 PYTHONPATH=. alembic upgrade head
```
Expected: all migrations through 101 apply, `hr_applicants`, `hr_applications`, `hr_application_events`, `hr_recruiting_message_templates` present.

Cleanup: `docker stop hr-p2-mig`.

- [ ] **Step 6: Commit**

```bash
git add app/hr/recruiting/applicant_models.py app/models/__init__.py alembic/versions/101_hr_applicant_tables.py
git commit -m "hr(plan2): add applicant/application/event/template models + migration 101"
```

### Task B2: Pydantic schemas

**Files:**
- Create: `app/hr/recruiting/applicant_schemas.py`

- [ ] **Step 1: Write the schemas**

```python
# app/hr/recruiting/applicant_schemas.py
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.types import UUIDStr


Stage = Literal["applied", "screen", "ride_along", "offer", "hired", "rejected", "withdrawn"]
ApplicantSource = Literal[
    "careers_page", "indeed", "ziprecruiter", "facebook", "referral", "manual", "email"
]


class ApplicantIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    email: EmailStr
    phone: str | None = None
    source: ApplicantSource = "manual"
    source_ref: str | None = None


class ApplicantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    first_name: str
    last_name: str
    email: str
    phone: str | None
    resume_storage_key: str | None
    source: ApplicantSource
    source_ref: str | None
    sms_consent_given: bool
    created_at: datetime


class ApplicationIn(BaseModel):
    applicant_id: UUIDStr
    requisition_id: UUIDStr
    stage: Stage = "applied"
    assigned_recruiter_id: int | None = None
    notes: str | None = None
    answers: dict[str, Any] | None = None


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    applicant_id: UUIDStr
    requisition_id: UUIDStr
    stage: Stage
    stage_entered_at: datetime
    assigned_recruiter_id: int | None
    rejection_reason: str | None
    rating: int | None
    notes: str | None
    created_at: datetime


class ApplicationWithApplicantOut(ApplicationOut):
    applicant: ApplicantOut


class StageTransitionIn(BaseModel):
    stage: Stage
    rejection_reason: str | None = None
    note: str | None = None


class ApplicationEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    application_id: UUIDStr
    event_type: str
    user_id: int | None
    payload: dict[str, Any] | None
    created_at: datetime


class PublicApplyIn(BaseModel):
    """JSON body when applying without a resume file (falls back when the
    multipart path is not used — e.g. from a test harness)."""

    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    email: EmailStr
    phone: str | None = None
    answers: dict[str, Any] | None = None
    sms_consent: bool = False
    source: ApplicantSource = "careers_page"
    source_ref: str | None = None
```

- [ ] **Step 2: Smoke-import**

```bash
PYTHONPATH=. python -c "from app.hr.recruiting import applicant_schemas; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add app/hr/recruiting/applicant_schemas.py
git commit -m "hr(plan2): add applicant/application Pydantic schemas"
```

---

## Phase C — Applicant service

### Task C1: Applicant CRUD service

**Files:**
- Create: `app/hr/recruiting/applicant_services.py`
- Create: `tests/hr/test_applicant_service.py`

- [ ] **Step 1: Failing test**

```python
# tests/hr/test_applicant_service.py
import pytest
from sqlalchemy import select

from app.hr.recruiting.applicant_models import HrApplicant
from app.hr.recruiting.applicant_schemas import ApplicantIn
from app.hr.recruiting.applicant_services import (
    create_applicant,
    get_applicant,
    list_applicants,
)


@pytest.mark.asyncio
async def test_create_applicant_persists(db):
    a = await create_applicant(
        db,
        ApplicantIn(
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            source="manual",
        ),
        actor_user_id=None,
    )
    await db.commit()
    row = (await db.execute(select(HrApplicant).where(HrApplicant.id == a.id))).scalar_one()
    assert row.first_name == "Jane"
    assert row.email == "jane@example.com"


@pytest.mark.asyncio
async def test_get_applicant_returns_none_when_missing(db):
    from uuid import uuid4
    assert await get_applicant(db, uuid4()) is None


@pytest.mark.asyncio
async def test_list_applicants_orders_newest_first(db):
    for e in ["a@x.com", "b@x.com", "c@x.com"]:
        await create_applicant(db, ApplicantIn(first_name="X", last_name="Y", email=e), actor_user_id=None)
    await db.commit()

    rows = await list_applicants(db, limit=10)
    assert [r.email for r in rows] == ["c@x.com", "b@x.com", "a@x.com"]
```

- [ ] **Step 2: Run — expect FAIL**

```bash
PYTHONPATH=. pytest tests/hr/test_applicant_service.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# app/hr/recruiting/applicant_services.py
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.recruiting.applicant_models import HrApplicant
from app.hr.recruiting.applicant_schemas import ApplicantIn
from app.hr.shared.audit import write_audit


async def create_applicant(
    db: AsyncSession, payload: ApplicantIn, *, actor_user_id: int | None
) -> HrApplicant:
    row = HrApplicant(**payload.model_dump())
    db.add(row)
    await db.flush()
    await write_audit(
        db,
        entity_type="applicant",
        entity_id=row.id,
        event="created",
        diff={"email": [None, row.email], "source": [None, row.source]},
        actor_user_id=actor_user_id,
    )
    return row


async def get_applicant(db: AsyncSession, applicant_id: UUID) -> HrApplicant | None:
    return (
        await db.execute(select(HrApplicant).where(HrApplicant.id == applicant_id))
    ).scalar_one_or_none()


async def list_applicants(
    db: AsyncSession, *, limit: int = 50, offset: int = 0
) -> list[HrApplicant]:
    stmt = (
        select(HrApplicant)
        .order_by(HrApplicant.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await db.execute(stmt)).scalars().all())
```

- [ ] **Step 4: Run — expect PASS**

```bash
PYTHONPATH=. pytest tests/hr/test_applicant_service.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/hr/recruiting/applicant_services.py tests/hr/test_applicant_service.py
git commit -m "hr(plan2): add applicant CRUD service"
```

### Task C2: Applicant admin router

**Files:**
- Create: `app/hr/recruiting/applicant_router.py`
- Modify: `app/hr/router.py`
- Create: `tests/hr/test_applicant_router.py`

- [ ] **Step 1: Failing test**

```python
# tests/hr/test_applicant_router.py
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
```

- [ ] **Step 2: Run — expect FAIL**

Run the test; expect 404 (route not registered yet).

- [ ] **Step 3: Implement**

```python
# app/hr/recruiting/applicant_router.py
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.hr.recruiting.applicant_schemas import ApplicantIn, ApplicantOut
from app.hr.recruiting.applicant_services import (
    create_applicant,
    get_applicant,
    list_applicants,
)


applicants_router = APIRouter(prefix="/applicants", tags=["hr-applicants"])


@applicants_router.post(
    "", response_model=ApplicantOut, status_code=status.HTTP_201_CREATED
)
async def create(
    payload: ApplicantIn, db: DbSession, user: CurrentUser
) -> ApplicantOut:
    row = await create_applicant(db, payload, actor_user_id=user.id)
    await db.commit()
    return ApplicantOut.model_validate(row)


@applicants_router.get("", response_model=list[ApplicantOut])
async def list_(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ApplicantOut]:
    rows = await list_applicants(db, limit=limit, offset=offset)
    return [ApplicantOut.model_validate(r) for r in rows]


@applicants_router.get("/{applicant_id}", response_model=ApplicantOut)
async def detail(
    applicant_id: UUID, db: DbSession, user: CurrentUser
) -> ApplicantOut:
    row = await get_applicant(db, applicant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="applicant not found")
    return ApplicantOut.model_validate(row)
```

- [ ] **Step 4: Wire into hr_router**

```python
# app/hr/router.py — add import + include
from app.hr.recruiting.applicant_router import applicants_router
hr_router.include_router(applicants_router)
```

- [ ] **Step 5: Run — expect PASS**

```bash
PYTHONPATH=. pytest tests/hr/test_applicant_router.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add app/hr/recruiting/applicant_router.py app/hr/router.py tests/hr/test_applicant_router.py
git commit -m "hr(plan2): add applicant admin router"
```

---

## Phase D — Application service + state machine

### Task D1: Create application + stage transition service

**Files:**
- Create: `app/hr/recruiting/application_services.py`
- Create: `tests/hr/test_application_service.py`

- [ ] **Step 1: Failing test**

```python
# tests/hr/test_application_service.py
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.hr.recruiting.applicant_models import HrApplication, HrApplicationEvent
from app.hr.recruiting.applicant_schemas import ApplicantIn, ApplicationIn
from app.hr.recruiting.applicant_services import create_applicant
from app.hr.recruiting.application_services import (
    ApplicationStateError,
    create_application,
    list_by_requisition,
    transition_stage,
)
from app.hr.recruiting.models import HrRequisition


@pytest.fixture
async def requisition(db):
    r = HrRequisition(slug="q-tech", title="Tech", status="open", employment_type="full_time")
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


@pytest.fixture
async def applicant(db):
    return await create_applicant(
        db,
        ApplicantIn(first_name="A", last_name="B", email="ab@example.com"),
        actor_user_id=None,
    )


@pytest.mark.asyncio
async def test_create_application_starts_at_applied(db, applicant, requisition):
    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()
    assert app.stage == "applied"

    events = (
        await db.execute(
            select(HrApplicationEvent).where(HrApplicationEvent.application_id == app.id)
        )
    ).scalars().all()
    assert any(e.event_type == "created" for e in events)


@pytest.mark.asyncio
async def test_transition_advances_through_pipeline(db, applicant, requisition):
    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()

    for next_stage in ["screen", "ride_along", "offer", "hired"]:
        app = await transition_stage(
            db, application_id=app.id, new_stage=next_stage, actor_user_id=None
        )
        await db.commit()
        assert app.stage == next_stage


@pytest.mark.asyncio
async def test_cannot_transition_from_terminal(db, applicant, requisition):
    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()
    await transition_stage(db, application_id=app.id, new_stage="rejected", actor_user_id=None, reason="not a fit")
    await db.commit()
    with pytest.raises(ApplicationStateError):
        await transition_stage(db, application_id=app.id, new_stage="screen", actor_user_id=None)


@pytest.mark.asyncio
async def test_rejection_requires_reason(db, applicant, requisition):
    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()
    with pytest.raises(ApplicationStateError, match="reason"):
        await transition_stage(db, application_id=app.id, new_stage="rejected", actor_user_id=None)


@pytest.mark.asyncio
async def test_hired_emits_trigger(db, applicant, requisition, monkeypatch):
    from app.hr.workflow.triggers import trigger_bus

    seen = []

    @trigger_bus.on("hr.applicant.hired")
    async def _h(payload):
        seen.append(payload)

    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()
    for s in ["screen", "ride_along", "offer", "hired"]:
        await transition_stage(db, application_id=app.id, new_stage=s, actor_user_id=None)
        await db.commit()

    assert seen, "hr.applicant.hired did not fire"
    payload = seen[0]
    assert payload["application_id"] == str(app.id)
    assert payload["requisition_id"] == str(requisition.id)


@pytest.mark.asyncio
async def test_duplicate_application_rejected(db, applicant, requisition):
    from sqlalchemy.exc import IntegrityError

    await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()
    with pytest.raises((IntegrityError, ApplicationStateError)):
        await create_application(
            db,
            ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
            actor_user_id=None,
        )
        await db.commit()


@pytest.mark.asyncio
async def test_list_by_requisition_filters_by_stage(db, applicant, requisition):
    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()

    rows_applied = await list_by_requisition(db, requisition_id=requisition.id, stage="applied")
    rows_hired = await list_by_requisition(db, requisition_id=requisition.id, stage="hired")
    assert [r.id for r in rows_applied] == [app.id]
    assert rows_hired == []
```

- [ ] **Step 2: Run — expect FAIL**

```bash
PYTHONPATH=. pytest tests/hr/test_application_service.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# app/hr/recruiting/application_services.py
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.recruiting.applicant_models import HrApplication, HrApplicationEvent
from app.hr.recruiting.applicant_schemas import ApplicationIn
from app.hr.shared.audit import write_audit
from app.hr.workflow.triggers import trigger_bus


class ApplicationStateError(Exception):
    pass


TERMINAL = {"hired", "rejected", "withdrawn"}

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "applied": {"screen", "rejected", "withdrawn"},
    "screen": {"ride_along", "rejected", "withdrawn"},
    "ride_along": {"offer", "rejected", "withdrawn"},
    "offer": {"hired", "rejected", "withdrawn"},
    "hired": set(),
    "rejected": set(),
    "withdrawn": set(),
}


async def create_application(
    db: AsyncSession,
    payload: ApplicationIn,
    *,
    actor_user_id: int | None,
) -> HrApplication:
    row = HrApplication(
        applicant_id=UUID(payload.applicant_id),
        requisition_id=UUID(payload.requisition_id),
        stage=payload.stage,
        assigned_recruiter_id=payload.assigned_recruiter_id,
        notes=payload.notes,
        answers=payload.answers,
    )
    db.add(row)
    await db.flush()
    db.add(
        HrApplicationEvent(
            application_id=row.id,
            event_type="created",
            user_id=actor_user_id,
            payload={"stage": row.stage},
        )
    )
    await write_audit(
        db,
        entity_type="application",
        entity_id=row.id,
        event="created",
        diff={"stage": [None, row.stage]},
        actor_user_id=actor_user_id,
    )
    return row


async def transition_stage(
    db: AsyncSession,
    *,
    application_id: UUID,
    new_stage: str,
    actor_user_id: int | None,
    reason: str | None = None,
    note: str | None = None,
) -> HrApplication:
    from datetime import datetime, timezone

    row = (
        await db.execute(
            select(HrApplication)
            .where(HrApplication.id == application_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApplicationStateError(f"application {application_id} not found")

    if new_stage not in _ALLOWED_TRANSITIONS[row.stage]:
        raise ApplicationStateError(
            f"cannot transition from {row.stage} to {new_stage}"
        )
    if new_stage == "rejected" and not reason:
        raise ApplicationStateError("rejection requires a reason")

    old_stage = row.stage
    row.stage = new_stage
    row.stage_entered_at = datetime.now(timezone.utc)
    if new_stage == "rejected":
        row.rejection_reason = reason
    if note:
        row.notes = (row.notes + "\n" if row.notes else "") + note

    db.add(
        HrApplicationEvent(
            application_id=row.id,
            event_type="stage_changed",
            user_id=actor_user_id,
            payload={"from": old_stage, "to": new_stage, "reason": reason},
        )
    )
    await write_audit(
        db,
        entity_type="application",
        entity_id=row.id,
        event="stage_changed",
        diff={"stage": [old_stage, new_stage]},
        actor_user_id=actor_user_id,
    )
    await db.flush()

    if new_stage == "hired":
        await trigger_bus.fire(
            "hr.applicant.hired",
            {
                "application_id": str(row.id),
                "applicant_id": str(row.applicant_id),
                "requisition_id": str(row.requisition_id),
                "actor_user_id": actor_user_id,
            },
        )
    return row


async def list_by_requisition(
    db: AsyncSession,
    *,
    requisition_id: UUID,
    stage: str | None = None,
) -> list[HrApplication]:
    stmt = (
        select(HrApplication)
        .where(HrApplication.requisition_id == requisition_id)
        .order_by(HrApplication.created_at.desc())
    )
    if stage is not None:
        stmt = stmt.where(HrApplication.stage == stage)
    return list((await db.execute(stmt)).scalars().all())


async def get_application(db: AsyncSession, application_id: UUID) -> HrApplication | None:
    return (
        await db.execute(select(HrApplication).where(HrApplication.id == application_id))
    ).scalar_one_or_none()


async def stage_counts_for_requisition(
    db: AsyncSession, *, requisition_id: UUID
) -> dict[str, int]:
    from sqlalchemy import func

    rows = (
        await db.execute(
            select(HrApplication.stage, func.count(HrApplication.id))
            .where(HrApplication.requisition_id == requisition_id)
            .group_by(HrApplication.stage)
        )
    ).all()
    return {stage: n for stage, n in rows}
```

- [ ] **Step 4: Run — expect PASS**

```bash
PYTHONPATH=. pytest tests/hr/test_application_service.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add app/hr/recruiting/application_services.py tests/hr/test_application_service.py
git commit -m "hr(plan2): application service + stage state machine + hire trigger"
```

### Task D2: Application admin router

**Files:**
- Create: `app/hr/recruiting/application_router.py`
- Modify: `app/hr/router.py`
- Create: `tests/hr/test_application_router.py`

- [ ] **Step 1: Failing test**

```python
# tests/hr/test_application_router.py
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
    # Can't jump applied -> hired
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
```

- [ ] **Step 2: Run — expect FAIL**

Run; expect 404.

- [ ] **Step 3: Implement**

```python
# app/hr/recruiting/application_router.py
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.hr.recruiting.applicant_models import HrApplicant, HrApplication
from app.hr.recruiting.applicant_schemas import (
    ApplicationIn,
    ApplicationOut,
    ApplicationWithApplicantOut,
    StageTransitionIn,
)
from app.hr.recruiting.applicant_schemas import ApplicantOut
from app.hr.recruiting.application_services import (
    ApplicationStateError,
    create_application,
    get_application,
    list_by_requisition,
    stage_counts_for_requisition,
    transition_stage,
)


applications_router = APIRouter(prefix="/applications", tags=["hr-applications"])


@applications_router.post(
    "", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED
)
async def create(
    payload: ApplicationIn, db: DbSession, user: CurrentUser
) -> ApplicationOut:
    try:
        row = await create_application(db, payload, actor_user_id=user.id)
    except ApplicationStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return ApplicationOut.model_validate(row)


@applications_router.get("", response_model=list[ApplicationWithApplicantOut])
async def list_(
    db: DbSession,
    user: CurrentUser,
    requisition_id: UUID = Query(...),
    stage: str | None = Query(None),
) -> list[ApplicationWithApplicantOut]:
    rows = await list_by_requisition(db, requisition_id=requisition_id, stage=stage)
    if not rows:
        return []
    applicant_ids = [r.applicant_id for r in rows]
    applicants = {
        a.id: a
        for a in (
            await db.execute(
                select(HrApplicant).where(HrApplicant.id.in_(applicant_ids))
            )
        ).scalars().all()
    }
    return [
        ApplicationWithApplicantOut(
            **ApplicationOut.model_validate(r).model_dump(),
            applicant=ApplicantOut.model_validate(applicants[r.applicant_id]),
        )
        for r in rows
    ]


@applications_router.get("/counts", response_model=dict[str, int])
async def counts(
    db: DbSession, user: CurrentUser, requisition_id: UUID = Query(...)
) -> dict[str, int]:
    return await stage_counts_for_requisition(db, requisition_id=requisition_id)


@applications_router.get("/{application_id}", response_model=ApplicationWithApplicantOut)
async def detail(
    application_id: UUID, db: DbSession, user: CurrentUser
) -> ApplicationWithApplicantOut:
    row = await get_application(db, application_id)
    if row is None:
        raise HTTPException(status_code=404, detail="application not found")
    applicant = (
        await db.execute(select(HrApplicant).where(HrApplicant.id == row.applicant_id))
    ).scalar_one()
    return ApplicationWithApplicantOut(
        **ApplicationOut.model_validate(row).model_dump(),
        applicant=ApplicantOut.model_validate(applicant),
    )


@applications_router.patch("/{application_id}/stage", response_model=ApplicationOut)
async def patch_stage(
    application_id: UUID,
    payload: StageTransitionIn,
    db: DbSession,
    user: CurrentUser,
) -> ApplicationOut:
    try:
        row = await transition_stage(
            db,
            application_id=application_id,
            new_stage=payload.stage,
            actor_user_id=user.id,
            reason=payload.rejection_reason,
            note=payload.note,
        )
    except ApplicationStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return ApplicationOut.model_validate(row)
```

- [ ] **Step 4: Wire into hr_router**

```python
# app/hr/router.py
from app.hr.recruiting.application_router import applications_router
hr_router.include_router(applications_router)
```

- [ ] **Step 5: Run — expect PASS**

```bash
PYTHONPATH=. pytest tests/hr/test_application_router.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add app/hr/recruiting/application_router.py app/hr/router.py tests/hr/test_application_router.py
git commit -m "hr(plan2): application admin router (create, list, transition, counts)"
```

---

## Phase E — Candidate SMS

### Task E1: Message template seed migration 102

**Files:**
- Create: `app/hr/recruiting/message_templates.py`
- Create: `alembic/versions/102_hr_recruiting_message_templates_seed.py`

- [ ] **Step 1: Seed helper**

```python
# app/hr/recruiting/message_templates.py
"""Default candidate SMS templates.

Each template is keyed by the destination stage. `{first_name}`,
`{requisition_title}`, `{company_name}` are the available placeholders —
the renderer does a plain `.format()`.
"""
DEFAULTS: list[dict] = [
    {
        "stage": "screen",
        "body": "Hi {first_name}, thanks for applying for {requisition_title} at {company_name}. "
                "We'd like to schedule a quick screening call. Reply with your best times.",
    },
    {
        "stage": "ride_along",
        "body": "Hi {first_name}, we'd like to have you ride along on a shift. "
                "Reply with dates that work this week.",
    },
    {
        "stage": "offer",
        "body": "Great news {first_name} — we have an offer for {requisition_title}. "
                "Check your email for details and reply here with any questions.",
    },
    {
        "stage": "hired",
        "body": "Welcome to the team, {first_name}! You'll get onboarding paperwork by email shortly.",
    },
    {
        "stage": "rejected",
        "body": "Hi {first_name}, thanks for your interest in {requisition_title}. "
                "We've decided to go with other candidates at this time. Best of luck.",
    },
]
```

- [ ] **Step 2: Data migration**

```python
# alembic/versions/102_hr_recruiting_message_templates_seed.py
"""seed default recruiting message templates

Revision ID: 102
Revises: 101
"""
import uuid

from alembic import op
from sqlalchemy import text


revision = "102"
down_revision = "101"
branch_labels = None
depends_on = None


from app.hr.recruiting.message_templates import DEFAULTS


def upgrade() -> None:
    bind = op.get_bind()
    existing = {
        row[0]
        for row in bind.execute(
            text("SELECT stage FROM hr_recruiting_message_templates")
        ).fetchall()
    }
    insert = text(
        "INSERT INTO hr_recruiting_message_templates "
        "(id, stage, channel, body, active) "
        "VALUES (CAST(:id AS uuid), :stage, 'sms', :body, true)"
    )
    for t in DEFAULTS:
        if t["stage"] in existing:
            continue
        bind.execute(insert, {"id": str(uuid.uuid4()), "stage": t["stage"], "body": t["body"]})


def downgrade() -> None:
    op.execute(
        "DELETE FROM hr_recruiting_message_templates WHERE stage IN ("
        "'screen','ride_along','offer','hired','rejected')"
    )
```

- [ ] **Step 3: Verify on fresh Postgres + idempotency**

Using the same test Postgres container from B1 Step 5 (or a fresh one on port 5435), run:
```bash
DATABASE_URL=postgresql+asyncpg://postgres:test@localhost:5435/hrtest HR_STORAGE_ROOT=/tmp/hr-p2 PYTHONPATH=. alembic upgrade head
DATABASE_URL=postgresql+asyncpg://postgres:test@localhost:5435/hrtest HR_STORAGE_ROOT=/tmp/hr-p2 PYTHONPATH=. alembic upgrade head
docker exec hr-p2-mig psql -U postgres -d hrtest -c "SELECT stage FROM hr_recruiting_message_templates ORDER BY stage;"
```
Expected: 5 rows, no duplicates on second run.

- [ ] **Step 4: Commit**

```bash
git add app/hr/recruiting/message_templates.py alembic/versions/102_hr_recruiting_message_templates_seed.py
git commit -m "hr(plan2): seed default recruiting SMS templates + migration 102"
```

### Task E2: Notification send helper + wire into transitions

**Files:**
- Create: `app/hr/recruiting/notifications.py`
- Modify: `app/hr/recruiting/application_services.py`
- Create: `tests/hr/test_recruiting_sms.py`

- [ ] **Step 1: Failing test**

```python
# tests/hr/test_recruiting_sms.py
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.hr.recruiting.applicant_models import (
    HrApplicant,
    HrApplication,
    HrApplicationEvent,
    HrRecruitingMessageTemplate,
)


async def _seed(db, *, sms_consent: bool):
    from app.hr.recruiting.applicant_schemas import ApplicantIn, ApplicationIn
    from app.hr.recruiting.applicant_services import create_applicant
    from app.hr.recruiting.application_services import create_application
    from app.hr.recruiting.models import HrRequisition

    req = HrRequisition(slug=f"q-{uuid4().hex[:6]}", title="Tech", status="open", employment_type="full_time")
    db.add(req)
    db.add(HrRecruitingMessageTemplate(
        stage="screen", channel="sms", body="Hi {first_name}, about {requisition_title}.", active=True
    ))
    await db.commit()

    a = await create_applicant(
        db,
        ApplicantIn(first_name="Jane", last_name="Doe", email="j@x.com", phone="+15555550100"),
        actor_user_id=None,
    )
    await db.commit()
    if sms_consent:
        a.sms_consent_given = True
        await db.commit()

    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(a.id), requisition_id=str(req.id)),
        actor_user_id=None,
    )
    await db.commit()
    return a, app


@pytest.mark.asyncio
async def test_sms_fires_on_stage_change_when_consented(db, monkeypatch):
    from app.hr.recruiting import notifications

    calls = []

    async def fake_send(to, body):
        calls.append({"to": to, "body": body})

    monkeypatch.setattr(notifications, "_send_sms", fake_send)

    a, app = await _seed(db, sms_consent=True)
    from app.hr.recruiting.application_services import transition_stage

    await transition_stage(db, application_id=app.id, new_stage="screen", actor_user_id=None)
    await db.commit()

    assert len(calls) == 1
    assert calls[0]["to"] == "+15555550100"
    assert "Jane" in calls[0]["body"]
    events = (
        await db.execute(
            select(HrApplicationEvent).where(
                HrApplicationEvent.application_id == app.id,
                HrApplicationEvent.event_type == "message_sent",
            )
        )
    ).scalars().all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_sms_skipped_when_no_consent(db, monkeypatch):
    from app.hr.recruiting import notifications

    calls = []

    async def fake_send(to, body):
        calls.append({"to": to, "body": body})

    monkeypatch.setattr(notifications, "_send_sms", fake_send)

    a, app = await _seed(db, sms_consent=False)
    from app.hr.recruiting.application_services import transition_stage

    await transition_stage(db, application_id=app.id, new_stage="screen", actor_user_id=None)
    await db.commit()

    assert calls == []


@pytest.mark.asyncio
async def test_sms_skipped_when_no_phone(db, monkeypatch):
    from app.hr.recruiting import notifications

    calls = []

    async def fake_send(to, body):
        calls.append({"to": to, "body": body})

    monkeypatch.setattr(notifications, "_send_sms", fake_send)

    a, app = await _seed(db, sms_consent=True)
    a.phone = None
    await db.commit()

    from app.hr.recruiting.application_services import transition_stage

    await transition_stage(db, application_id=app.id, new_stage="screen", actor_user_id=None)
    await db.commit()

    assert calls == []
```

- [ ] **Step 2: Run — expect FAIL**

```bash
PYTHONPATH=. pytest tests/hr/test_recruiting_sms.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement notifications helper**

```python
# app/hr/recruiting/notifications.py
"""Candidate SMS on stage change.

Looks up the per-stage template, runs `.format()` with applicant / requisition
substitutions, sends via the existing `send_sms` helper, and records an
``HrApplicationEvent`` of type ``message_sent``.

Short-circuits silently when:
- the applicant has no phone,
- the applicant has not opted in (``sms_consent_given`` is False),
- no active template exists for the target stage,
- the outbound SMS call raises (logged, event recorded with ``status=error``).
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.recruiting.applicant_models import (
    HrApplicant,
    HrApplication,
    HrApplicationEvent,
    HrRecruitingMessageTemplate,
)
from app.hr.recruiting.models import HrRequisition
from app.services.sms_service import send_sms as _real_send_sms


logger = logging.getLogger(__name__)

_COMPANY_NAME = "Mac Septic"


async def _send_sms(to: str, body: str) -> None:
    """Thin wrapper so tests can monkeypatch this without touching the upstream
    ``app.services.sms_service`` module."""
    await _real_send_sms(to, body)


async def maybe_send_stage_sms(
    db: AsyncSession,
    *,
    application_id,
    new_stage: str,
) -> None:
    application = (
        await db.execute(select(HrApplication).where(HrApplication.id == application_id))
    ).scalar_one_or_none()
    if application is None:
        return

    applicant = (
        await db.execute(select(HrApplicant).where(HrApplicant.id == application.applicant_id))
    ).scalar_one()
    if not applicant.phone or not applicant.sms_consent_given:
        return

    template = (
        await db.execute(
            select(HrRecruitingMessageTemplate).where(
                HrRecruitingMessageTemplate.stage == new_stage,
                HrRecruitingMessageTemplate.active.is_(True),
                HrRecruitingMessageTemplate.channel == "sms",
            )
        )
    ).scalar_one_or_none()
    if template is None:
        return

    requisition = (
        await db.execute(
            select(HrRequisition).where(HrRequisition.id == application.requisition_id)
        )
    ).scalar_one()

    try:
        body = template.body.format(
            first_name=applicant.first_name,
            last_name=applicant.last_name,
            requisition_title=requisition.title,
            company_name=_COMPANY_NAME,
        )
    except KeyError as e:
        logger.warning("hr sms template missing key %s for stage %s", e, new_stage)
        return

    status = "ok"
    try:
        await _send_sms(applicant.phone, body)
    except Exception as e:  # noqa: BLE001 — we never want SMS failure to bubble
        logger.error("hr sms send failed: %s", e)
        status = "error"

    db.add(
        HrApplicationEvent(
            application_id=application.id,
            event_type="message_sent",
            payload={"stage": new_stage, "channel": "sms", "status": status, "to": applicant.phone},
        )
    )
    await db.flush()
```

- [ ] **Step 4: Wire into `transition_stage`**

At the bottom of `transition_stage` in `app/hr/recruiting/application_services.py` (after the `trigger_bus.fire` block for `hired`):

```python
    # Fire SMS on every transition (applied→* and the two terminal stages).
    # `maybe_send_stage_sms` silently no-ops when phone / consent / template are missing.
    from app.hr.recruiting.notifications import maybe_send_stage_sms
    await maybe_send_stage_sms(db, application_id=row.id, new_stage=new_stage)
    return row
```

- [ ] **Step 5: Run — expect PASS**

```bash
PYTHONPATH=. pytest tests/hr/test_recruiting_sms.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add app/hr/recruiting/notifications.py app/hr/recruiting/application_services.py tests/hr/test_recruiting_sms.py
git commit -m "hr(plan2): candidate SMS on stage change (consent-gated)"
```

---

## Phase F — Public apply endpoint + form

### Task F1: Public apply endpoint

**Files:**
- Create: `app/hr/recruiting/public_apply.py`
- Modify: `app/main.py`
- Create: `tests/hr/test_public_apply.py`

- [ ] **Step 1: Failing test**

```python
# tests/hr/test_public_apply.py
import io

import pytest

from app.hr.recruiting.models import HrRequisition


async def _open_req(db, slug="p-tech"):
    r = HrRequisition(slug=slug, title="Public Tech", status="open", employment_type="full_time")
    db.add(r)
    await db.commit()
    return r


@pytest.mark.asyncio
async def test_apply_creates_applicant_and_application(client, db):
    await _open_req(db)

    data = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@public.com",
        "phone": "+15555550100",
        "sms_consent": "true",
    }
    files = {"resume": ("resume.pdf", io.BytesIO(b"%PDF-1.4\n"), "application/pdf")}
    r = await client.post(
        "/api/v2/public/careers/p-tech/apply",
        data=data,
        files=files,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["stage"] == "applied"
    assert "application_id" in body


@pytest.mark.asyncio
async def test_apply_without_resume_succeeds(client, db):
    await _open_req(db, slug="no-resume")
    r = await client.post(
        "/api/v2/public/careers/no-resume/apply",
        data={
            "first_name": "X",
            "last_name": "Y",
            "email": "x@y.com",
            "sms_consent": "false",
        },
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_apply_to_closed_requisition_404(client, db):
    r = HrRequisition(slug="closed", title="Closed", status="closed", employment_type="full_time")
    db.add(r)
    await db.commit()
    r = await client.post(
        "/api/v2/public/careers/closed/apply",
        data={"first_name": "X", "last_name": "Y", "email": "x@y.com"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_apply_rejects_duplicate_for_same_req(client, db):
    await _open_req(db, slug="dup")
    base = {
        "first_name": "Dup",
        "last_name": "Candidate",
        "email": "dup@x.com",
        "sms_consent": "false",
    }
    r1 = await client.post("/api/v2/public/careers/dup/apply", data=base)
    assert r1.status_code == 201
    r2 = await client.post("/api/v2/public/careers/dup/apply", data=base)
    assert r2.status_code == 409
```

- [ ] **Step 2: Run — expect FAIL**

Run; expect 404 (endpoint missing).

- [ ] **Step 3: Implement**

```python
# app/hr/recruiting/public_apply.py
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession
from app.hr.recruiting.applicant_models import HrApplicant, HrApplication, HrApplicationEvent
from app.hr.recruiting.applicant_schemas import ApplicantSource
from app.hr.recruiting.models import HrRequisition
from app.hr.shared import storage
from app.hr.shared.audit import write_audit


public_apply_router = APIRouter(prefix="/careers", tags=["hr-apply-public"])


_ALLOWED_RESUME_MIMES = {"application/pdf", "image/jpeg", "image/png"}
_MAX_RESUME_BYTES = 10 * 1024 * 1024  # 10 MB


@public_apply_router.post(
    "/{slug}/apply",
    status_code=status.HTTP_201_CREATED,
)
async def apply(
    slug: str,
    request: Request,
    db: DbSession,
    first_name: str = Form(..., min_length=1, max_length=128),
    last_name: str = Form(..., min_length=1, max_length=128),
    email: str = Form(..., min_length=3, max_length=256),
    phone: str | None = Form(None, max_length=32),
    sms_consent: bool = Form(False),
    source: ApplicantSource = Form("careers_page"),
    source_ref: str | None = Form(None),
    resume: UploadFile | None = File(None),
) -> dict:
    requisition = (
        await db.execute(
            select(HrRequisition).where(
                HrRequisition.slug == slug, HrRequisition.status == "open"
            )
        )
    ).scalar_one_or_none()
    if requisition is None:
        raise HTTPException(status_code=404, detail="requisition not found or closed")

    # Resume upload — optional but validated when present.
    resume_key: str | None = None
    if resume is not None and resume.filename:
        if resume.content_type not in _ALLOWED_RESUME_MIMES:
            raise HTTPException(status_code=400, detail="resume must be pdf / jpg / png")
        data = await resume.read()
        if len(data) > _MAX_RESUME_BYTES:
            raise HTTPException(status_code=400, detail="resume exceeds 10 MB")
        if data:  # skip empty uploads
            suffix = "." + (resume.filename.rsplit(".", 1)[-1].lower() or "bin")
            resume_key = storage.save_bytes(data, suffix)

    ip = request.client.host if request.client else "unknown"

    # Applicant: re-use if same email already in system; otherwise create.
    applicant = (
        await db.execute(select(HrApplicant).where(HrApplicant.email == email))
    ).scalar_one_or_none()
    if applicant is None:
        applicant = HrApplicant(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            resume_storage_key=resume_key,
            source=source,
            source_ref=source_ref,
            sms_consent_given=sms_consent,
            sms_consent_ip=ip if sms_consent else None,
            sms_consent_at=datetime.now(timezone.utc) if sms_consent else None,
        )
        db.add(applicant)
        await db.flush()
    else:
        # Update phone/resume if newly provided, and upgrade consent on re-apply.
        if phone and not applicant.phone:
            applicant.phone = phone
        if resume_key:
            applicant.resume_storage_key = resume_key
        if sms_consent and not applicant.sms_consent_given:
            applicant.sms_consent_given = True
            applicant.sms_consent_ip = ip
            applicant.sms_consent_at = datetime.now(timezone.utc)

    # Application: unique per (applicant, requisition).
    try:
        application = HrApplication(
            applicant_id=applicant.id,
            requisition_id=requisition.id,
            stage="applied",
        )
        db.add(application)
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="already applied for this role")

    db.add(
        HrApplicationEvent(
            application_id=application.id,
            event_type="created",
            payload={"source": source, "stage": "applied"},
        )
    )
    if resume_key:
        db.add(
            HrApplicationEvent(
                application_id=application.id,
                event_type="resume_uploaded",
                payload={"storage_key": resume_key},
            )
        )
    await write_audit(
        db,
        entity_type="application",
        entity_id=application.id,
        event="created",
        diff={"stage": [None, "applied"], "source": [None, source]},
        actor_ip=ip,
        actor_user_agent=request.headers.get("user-agent", ""),
    )
    await db.commit()

    return {
        "application_id": str(application.id),
        "applicant_id": str(applicant.id),
        "stage": application.stage,
    }
```

- [ ] **Step 4: Mount in main**

```python
# app/main.py — inside the hr_module_enabled() block, near the esign_public_router mount
from app.hr.recruiting.public_apply import public_apply_router

if hr_module_enabled():
    app.include_router(public_apply_router, prefix="/api/v2/public")
```

Also mount in `tests/hr/conftest.py::_mount_hr_router_once()`:

```python
from app.hr.recruiting.public_apply import public_apply_router

apply_mounted = any(
    getattr(r, "path", "").startswith("/api/v2/public/careers")
    for r in fastapi_app.routes
)
if not apply_mounted:
    fastapi_app.include_router(public_apply_router, prefix="/api/v2/public")
```

- [ ] **Step 5: Run — expect PASS**

```bash
PYTHONPATH=. pytest tests/hr/test_public_apply.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add app/hr/recruiting/public_apply.py app/main.py tests/hr/conftest.py tests/hr/test_public_apply.py
git commit -m "hr(plan2): public POST /api/v2/public/careers/{slug}/apply with resume upload"
```

### Task F2: Real apply form on /careers

**Files:**
- Modify: `app/hr/careers/templates/apply.html`
- Modify: `app/hr/careers/router.py` (no logic change; just reconfirm route still 200)

- [ ] **Step 1: Replace the placeholder template**

```html
<!-- app/hr/careers/templates/apply.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Apply — {{ req.title }}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-white text-neutral-900">
  <main class="max-w-xl mx-auto px-6 py-10">
    <a href="/careers/{{ req.slug }}" class="text-sm text-gray-500 hover:underline">← Back to job</a>
    <h1 class="text-2xl font-semibold mt-4">Apply for {{ req.title }}</h1>
    <p class="text-sm text-gray-600 mt-1">All fields marked * are required.</p>

    <form id="apply-form" method="post" enctype="multipart/form-data"
          action="/api/v2/public/careers/{{ req.slug }}/apply" class="mt-6 space-y-4">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <label class="block">
          <span class="text-sm">First name *</span>
          <input name="first_name" required class="w-full border rounded px-3 py-2">
        </label>
        <label class="block">
          <span class="text-sm">Last name *</span>
          <input name="last_name" required class="w-full border rounded px-3 py-2">
        </label>
      </div>
      <label class="block">
        <span class="text-sm">Email *</span>
        <input name="email" type="email" required class="w-full border rounded px-3 py-2">
      </label>
      <label class="block">
        <span class="text-sm">Phone</span>
        <input name="phone" type="tel" class="w-full border rounded px-3 py-2" placeholder="(555) 555-0100">
      </label>
      <label class="block">
        <span class="text-sm">Resume (PDF, JPG, PNG; 10 MB max)</span>
        <input name="resume" type="file" accept=".pdf,.jpg,.jpeg,.png" class="w-full">
      </label>
      <label class="flex items-start gap-3">
        <input type="checkbox" name="sms_consent" value="true" class="mt-1">
        <span class="text-sm text-neutral-700">
          I agree to receive SMS messages about this application from Mac Septic.
          Message &amp; data rates may apply. Reply STOP to opt out.
        </span>
      </label>
      <input type="hidden" name="source" value="careers_page">
      <button id="submit-btn" type="submit"
              class="px-4 py-2 bg-black text-white rounded-lg hover:bg-neutral-800 disabled:opacity-50">
        Submit application
      </button>
      <p id="apply-error" role="alert" class="text-red-600 text-sm hidden"></p>
    </form>

    <div id="apply-success" class="hidden mt-10 p-6 rounded-xl border border-green-200 bg-green-50">
      <h2 class="text-lg font-semibold text-green-900">Application received</h2>
      <p class="text-sm text-green-900 mt-2">
        Thanks — we'll be in touch soon.
      </p>
    </div>

    <script>
      const form = document.getElementById("apply-form");
      const err = document.getElementById("apply-error");
      const ok = document.getElementById("apply-success");
      const btn = document.getElementById("submit-btn");

      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        err.classList.add("hidden");
        btn.disabled = true;
        btn.textContent = "Submitting…";
        try {
          const res = await fetch(form.action, {
            method: "POST",
            body: new FormData(form),
          });
          if (res.status === 201) {
            form.classList.add("hidden");
            ok.classList.remove("hidden");
          } else {
            const data = await res.json().catch(() => ({}));
            err.textContent = data.detail || `Submit failed (${res.status})`;
            err.classList.remove("hidden");
          }
        } catch (_) {
          err.textContent = "Network error. Please try again.";
          err.classList.remove("hidden");
        } finally {
          btn.disabled = false;
          btn.textContent = "Submit application";
        }
      });
    </script>
  </main>
</body>
</html>
```

- [ ] **Step 2: Add Playwright-friendly test**

Append to `tests/hr/test_careers_ssr.py`:

```python
@pytest.mark.asyncio
async def test_apply_page_includes_real_form(client, db):
    db.add(
        HrRequisition(
            slug="apply-form",
            title="Apply Tester",
            status="open",
            employment_type="full_time",
        )
    )
    await db.commit()
    r = await client.get("/careers/apply-form/apply")
    assert r.status_code == 200
    assert 'id="apply-form"' in r.text
    assert 'action="/api/v2/public/careers/apply-form/apply"' in r.text
    assert "Resume" in r.text
    assert "sms_consent" in r.text
```

- [ ] **Step 3: Run — expect PASS**

```bash
PYTHONPATH=. pytest tests/hr/test_careers_ssr.py -v
```
Expected: 5 passed (4 existing + 1 new).

- [ ] **Step 4: Commit**

```bash
git add app/hr/careers/templates/apply.html tests/hr/test_careers_ssr.py
git commit -m "hr(plan2): real apply form on /careers/{slug}/apply"
```

---

## Phase G — Requisition extensions

### Task G1: PATCH/DELETE + applicant counts on list

**Files:**
- Modify: `app/hr/recruiting/services.py`
- Modify: `app/hr/recruiting/schemas.py`
- Modify: `app/hr/recruiting/router.py`
- Modify: `tests/hr/test_requisition_router.py`

- [ ] **Step 1: Extend service**

Append to `app/hr/recruiting/services.py`:

```python
from datetime import datetime, timezone
from uuid import UUID

from app.hr.recruiting.applicant_models import HrApplication


async def update_requisition(
    db: AsyncSession,
    *,
    requisition_id: UUID,
    patch: dict,
    actor_user_id: int | None,
) -> HrRequisition | None:
    row = (
        await db.execute(select(HrRequisition).where(HrRequisition.id == requisition_id))
    ).scalar_one_or_none()
    if row is None:
        return None
    diff = {}
    for key, value in patch.items():
        if getattr(row, key) != value:
            diff[key] = [getattr(row, key), value]
            setattr(row, key, value)
    if diff.get("status") and diff["status"][1] == "open" and row.opened_at is None:
        row.opened_at = datetime.now(timezone.utc)
    if diff.get("status") and diff["status"][1] == "closed":
        row.closed_at = datetime.now(timezone.utc)
    await db.flush()
    if diff:
        await write_audit(
            db,
            entity_type="requisition",
            entity_id=row.id,
            event="updated",
            diff={k: [str(a) if a is not None else None, str(b) if b is not None else None] for k, (a, b) in diff.items()},
            actor_user_id=actor_user_id,
        )
    return row


async def close_requisition(
    db: AsyncSession, *, requisition_id: UUID, actor_user_id: int | None
) -> HrRequisition | None:
    return await update_requisition(
        db,
        requisition_id=requisition_id,
        patch={"status": "closed"},
        actor_user_id=actor_user_id,
    )


async def applicant_counts_for_requisitions(
    db: AsyncSession, *, requisition_ids: list[UUID]
) -> dict[UUID, int]:
    if not requisition_ids:
        return {}
    from sqlalchemy import func

    rows = (
        await db.execute(
            select(HrApplication.requisition_id, func.count(HrApplication.id))
            .where(HrApplication.requisition_id.in_(requisition_ids))
            .group_by(HrApplication.requisition_id)
        )
    ).all()
    return {rid: n for rid, n in rows}
```

- [ ] **Step 2: Extend schemas**

Append to `app/hr/recruiting/schemas.py`:

```python
class RequisitionPatch(BaseModel):
    title: str | None = None
    department: str | None = None
    location_city: str | None = None
    location_state: str | None = None
    employment_type: EmploymentType | None = None
    compensation_display: str | None = None
    description_md: str | None = None
    requirements_md: str | None = None
    benefits_md: str | None = None
    status: Status | None = None
    hiring_manager_id: int | None = None
    onboarding_template_id: UUIDStr | None = None


class RequisitionWithCountsOut(RequisitionOut):
    applicant_count: int = 0
```

- [ ] **Step 3: Extend router**

Modify `app/hr/recruiting/router.py` to return `RequisitionWithCountsOut` from the list endpoint, and add PATCH + DELETE:

```python
# Replace the existing list_ endpoint and add patch_ / delete_
from uuid import UUID

from fastapi import HTTPException

from app.hr.recruiting.schemas import (
    RequisitionIn,
    RequisitionOut,
    RequisitionPatch,
    RequisitionWithCountsOut,
)
from app.hr.recruiting.services import (
    applicant_counts_for_requisitions,
    close_requisition,
    create_requisition,
    list_requisitions,
    update_requisition,
)


@recruiting_router.get("/requisitions", response_model=list[RequisitionWithCountsOut])
async def list_(
    db: DbSession,
    user: CurrentUser,
    status_filter: str | None = Query(None, alias="status"),
) -> list[RequisitionWithCountsOut]:
    rows = await list_requisitions(db, status=status_filter)
    counts = await applicant_counts_for_requisitions(
        db, requisition_ids=[r.id for r in rows]
    )
    return [
        RequisitionWithCountsOut(
            **RequisitionOut.model_validate(r).model_dump(),
            applicant_count=counts.get(r.id, 0),
        )
        for r in rows
    ]


@recruiting_router.patch("/requisitions/{requisition_id}", response_model=RequisitionOut)
async def patch_(
    requisition_id: UUID,
    payload: RequisitionPatch,
    db: DbSession,
    user: CurrentUser,
) -> RequisitionOut:
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    row = await update_requisition(
        db, requisition_id=requisition_id, patch=data, actor_user_id=user.id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    await db.commit()
    return RequisitionOut.model_validate(row)


@recruiting_router.delete("/requisitions/{requisition_id}", response_model=RequisitionOut)
async def delete_(
    requisition_id: UUID, db: DbSession, user: CurrentUser
) -> RequisitionOut:
    # Soft-delete: transition status to "closed". Open requisitions with
    # applications should never be truly deleted for audit reasons.
    row = await close_requisition(db, requisition_id=requisition_id, actor_user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    await db.commit()
    return RequisitionOut.model_validate(row)
```

- [ ] **Step 4: Extend tests**

Append to `tests/hr/test_requisition_router.py`:

```python
@pytest.mark.asyncio
async def test_list_includes_applicant_counts(authed_client):
    r = await authed_client.post(
        "/api/v2/hr/recruiting/requisitions",
        json={"slug": "counts-tech", "title": "X", "status": "open", "employment_type": "full_time"},
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
        json={"slug": "p-req", "title": "Draft", "status": "draft", "employment_type": "full_time"},
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
        json={"slug": "del-req", "title": "D", "status": "open", "employment_type": "full_time"},
    )
    rid = r.json()["id"]
    r = await authed_client.delete(f"/api/v2/hr/recruiting/requisitions/{rid}")
    assert r.status_code == 200
    assert r.json()["status"] == "closed"
```

- [ ] **Step 5: Run — expect PASS**

```bash
PYTHONPATH=. pytest tests/hr/test_requisition_router.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add app/hr/recruiting/services.py app/hr/recruiting/schemas.py app/hr/recruiting/router.py tests/hr/test_requisition_router.py
git commit -m "hr(plan2): requisition PATCH/DELETE + applicant counts on list"
```

---

## Phase H — Frontend

### Task H1: API hooks for applicants + applications

**Files (in `/home/will/ReactCRM/.worktrees/hr-foundation`):**
- Create: `src/features/hr/recruiting/api-applicants.ts`
- Create: `src/features/hr/recruiting/api-applications.ts`
- Modify: `src/features/hr/recruiting/api.ts`
- Create: `src/features/hr/recruiting/__tests__/api-applicants.contract.test.ts`

- [ ] **Step 1: Applicant hooks**

```tsx
// src/features/hr/recruiting/api-applicants.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { apiClient } from "@/api/client";
import { validateResponse } from "@/api/validateResponse";


export const applicantSchema = z.object({
  id: z.string(),
  first_name: z.string(),
  last_name: z.string(),
  email: z.string(),
  phone: z.string().nullable(),
  resume_storage_key: z.string().nullable(),
  source: z.enum([
    "careers_page", "indeed", "ziprecruiter", "facebook", "referral", "manual", "email",
  ]),
  source_ref: z.string().nullable(),
  sms_consent_given: z.boolean(),
  created_at: z.string(),
});
export type Applicant = z.infer<typeof applicantSchema>;


export const applicantInputSchema = z.object({
  first_name: z.string().min(1).max(128),
  last_name: z.string().min(1).max(128),
  email: z.string().email(),
  phone: z.string().optional().nullable(),
  source: applicantSchema.shape.source.default("manual"),
  source_ref: z.string().optional().nullable(),
});
export type ApplicantInput = z.infer<typeof applicantInputSchema>;


export const applicantKeys = {
  all: ["hr", "applicants"] as const,
  list: (limit: number, offset: number) =>
    [...applicantKeys.all, "list", limit, offset] as const,
  detail: (id: string) => [...applicantKeys.all, "detail", id] as const,
};


export function useApplicants(limit = 50, offset = 0) {
  return useQuery({
    queryKey: applicantKeys.list(limit, offset),
    queryFn: async () => {
      const { data } = await apiClient.get("/hr/applicants", {
        params: { limit, offset },
      });
      return validateResponse(z.array(applicantSchema), data, "/hr/applicants");
    },
    staleTime: 30_000,
  });
}


export function useApplicant(id: string | undefined) {
  return useQuery({
    enabled: !!id,
    queryKey: applicantKeys.detail(id ?? ""),
    queryFn: async () => {
      const { data } = await apiClient.get(`/hr/applicants/${id}`);
      return validateResponse(applicantSchema, data, `/hr/applicants/${id}`);
    },
  });
}


export function useCreateApplicant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: ApplicantInput) => {
      const { data } = await apiClient.post("/hr/applicants", payload);
      return validateResponse(applicantSchema, data, "/hr/applicants (create)");
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: applicantKeys.all }),
  });
}
```

- [ ] **Step 2: Application hooks**

```tsx
// src/features/hr/recruiting/api-applications.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { apiClient } from "@/api/client";
import { validateResponse } from "@/api/validateResponse";
import { applicantSchema } from "./api-applicants";


export const STAGES = [
  "applied",
  "screen",
  "ride_along",
  "offer",
  "hired",
  "rejected",
  "withdrawn",
] as const;
export type Stage = (typeof STAGES)[number];


export const applicationSchema = z.object({
  id: z.string(),
  applicant_id: z.string(),
  requisition_id: z.string(),
  stage: z.enum(STAGES),
  stage_entered_at: z.string(),
  assigned_recruiter_id: z.number().nullable(),
  rejection_reason: z.string().nullable(),
  rating: z.number().nullable(),
  notes: z.string().nullable(),
  created_at: z.string(),
});
export type Application = z.infer<typeof applicationSchema>;


export const applicationWithApplicantSchema = applicationSchema.extend({
  applicant: applicantSchema,
});
export type ApplicationWithApplicant = z.infer<
  typeof applicationWithApplicantSchema
>;


export const applicationKeys = {
  all: ["hr", "applications"] as const,
  byReq: (reqId: string, stage?: string) =>
    [...applicationKeys.all, "list", reqId, stage ?? "all"] as const,
  counts: (reqId: string) =>
    [...applicationKeys.all, "counts", reqId] as const,
  detail: (id: string) => [...applicationKeys.all, "detail", id] as const,
};


export function useApplicationsForRequisition(reqId: string | undefined, stage?: Stage) {
  return useQuery({
    enabled: !!reqId,
    queryKey: applicationKeys.byReq(reqId ?? "", stage),
    queryFn: async () => {
      const { data } = await apiClient.get("/hr/applications", {
        params: { requisition_id: reqId, stage },
      });
      return validateResponse(
        z.array(applicationWithApplicantSchema),
        data,
        "/hr/applications",
      );
    },
  });
}


export function useApplicationStageCounts(reqId: string | undefined) {
  return useQuery({
    enabled: !!reqId,
    queryKey: applicationKeys.counts(reqId ?? ""),
    queryFn: async () => {
      const { data } = await apiClient.get("/hr/applications/counts", {
        params: { requisition_id: reqId },
      });
      return validateResponse(
        z.record(z.string(), z.number()),
        data,
        "/hr/applications/counts",
      );
    },
  });
}


export function useApplication(id: string | undefined) {
  return useQuery({
    enabled: !!id,
    queryKey: applicationKeys.detail(id ?? ""),
    queryFn: async () => {
      const { data } = await apiClient.get(`/hr/applications/${id}`);
      return validateResponse(
        applicationWithApplicantSchema,
        data,
        `/hr/applications/${id}`,
      );
    },
  });
}


export function useTransitionStage(applicationId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      stage: Stage;
      rejection_reason?: string;
      note?: string;
    }) => {
      const { data } = await apiClient.patch(
        `/hr/applications/${applicationId}/stage`,
        input,
      );
      return validateResponse(applicationSchema, data, "transition stage");
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: applicationKeys.all });
    },
  });
}
```

- [ ] **Step 3: Extend existing requisitions api.ts**

Modify `src/features/hr/recruiting/api.ts`: add PATCH + DELETE + `applicant_count` to the schema.

Replace the existing `requisitionSchema` definition with:

```tsx
export const requisitionSchema = z.object({
  id: z.string(),
  slug: z.string(),
  title: z.string(),
  department: z.string().nullable(),
  location_city: z.string().nullable(),
  location_state: z.string().nullable(),
  employment_type: z.enum(["full_time", "part_time", "contract"]),
  compensation_display: z.string().nullable(),
  description_md: z.string().nullable(),
  requirements_md: z.string().nullable(),
  benefits_md: z.string().nullable(),
  status: z.enum(["draft", "open", "paused", "closed"]),
  opened_at: z.string().nullable(),
  closed_at: z.string().nullable(),
  hiring_manager_id: z.number().nullable(),
  onboarding_template_id: z.string().nullable(),
  created_at: z.string(),
  applicant_count: z.number().optional(),  // server adds on list endpoint
});
```

Append:

```tsx
export function useUpdateRequisition(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (patch: Partial<RequisitionInput>) => {
      const { data } = await apiClient.patch(
        `/hr/recruiting/requisitions/${id}`,
        patch,
      );
      return requisitionSchema.parse(data);
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: [...hrKeys.all, "requisitions"] }),
  });
}


export function useCloseRequisition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { data } = await apiClient.delete(
        `/hr/recruiting/requisitions/${id}`,
      );
      return requisitionSchema.parse(data);
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: [...hrKeys.all, "requisitions"] }),
  });
}


export function useRequisitionById(id: string | undefined) {
  return useQuery({
    enabled: !!id,
    queryKey: [...hrKeys.all, "requisition", id],
    queryFn: async () => {
      const { data } = await apiClient.get(`/hr/recruiting/requisitions`, {
        params: {},
      });
      const list = z.array(requisitionSchema).parse(data);
      const found = list.find((r) => r.id === id);
      if (!found) throw new Error("requisition not found");
      return found;
    },
  });
}
```

- [ ] **Step 4: Contract test**

```tsx
// src/features/hr/recruiting/__tests__/api-applicants.contract.test.ts
import { describe, expect, it } from "vitest";

import {
  applicantSchema,
  applicantInputSchema,
} from "../api-applicants";
import {
  applicationSchema,
  applicationWithApplicantSchema,
} from "../api-applications";


describe("applicantSchema", () => {
  it("parses a full applicant payload", () => {
    const a = applicantSchema.parse({
      id: "11111111-1111-1111-1111-111111111111",
      first_name: "Jane",
      last_name: "Doe",
      email: "jane@example.com",
      phone: "+15555550100",
      resume_storage_key: "r.pdf",
      source: "careers_page",
      source_ref: null,
      sms_consent_given: true,
      created_at: "2026-04-16T00:00:00Z",
    });
    expect(a.email).toBe("jane@example.com");
  });

  it("rejects invalid email on input", () => {
    expect(() =>
      applicantInputSchema.parse({
        first_name: "J",
        last_name: "D",
        email: "not-email",
      }),
    ).toThrow();
  });
});


describe("applicationSchema", () => {
  it("parses valid stages", () => {
    const app = applicationSchema.parse({
      id: "22222222-2222-2222-2222-222222222222",
      applicant_id: "11111111-1111-1111-1111-111111111111",
      requisition_id: "33333333-3333-3333-3333-333333333333",
      stage: "ride_along",
      stage_entered_at: "2026-04-16T00:00:00Z",
      assigned_recruiter_id: null,
      rejection_reason: null,
      rating: null,
      notes: null,
      created_at: "2026-04-16T00:00:00Z",
    });
    expect(app.stage).toBe("ride_along");
  });

  it("rejects an unknown stage", () => {
    expect(() =>
      applicationSchema.parse({
        id: "22222222-2222-2222-2222-222222222222",
        applicant_id: "11111111-1111-1111-1111-111111111111",
        requisition_id: "33333333-3333-3333-3333-333333333333",
        stage: "martian",
        stage_entered_at: "x",
        assigned_recruiter_id: null,
        rejection_reason: null,
        rating: null,
        notes: null,
        created_at: "x",
      }),
    ).toThrow();
  });
});


describe("applicationWithApplicantSchema", () => {
  it("composes", () => {
    const combined = applicationWithApplicantSchema.parse({
      id: "22222222-2222-2222-2222-222222222222",
      applicant_id: "11111111-1111-1111-1111-111111111111",
      requisition_id: "33333333-3333-3333-3333-333333333333",
      stage: "applied",
      stage_entered_at: "2026-04-16T00:00:00Z",
      assigned_recruiter_id: null,
      rejection_reason: null,
      rating: null,
      notes: null,
      created_at: "2026-04-16T00:00:00Z",
      applicant: {
        id: "11111111-1111-1111-1111-111111111111",
        first_name: "Jane",
        last_name: "Doe",
        email: "jane@example.com",
        phone: null,
        resume_storage_key: null,
        source: "careers_page",
        source_ref: null,
        sms_consent_given: false,
        created_at: "2026-04-16T00:00:00Z",
      },
    });
    expect(combined.applicant.first_name).toBe("Jane");
  });
});
```

- [ ] **Step 5: Run — expect PASS**

```bash
cd /home/will/ReactCRM/.worktrees/hr-foundation
npx vitest run src/features/hr/recruiting/__tests__
```
Expected: all tests pass (existing 4 + new 5 = 9).

- [ ] **Step 6: Commit**

```bash
git add src/features/hr/recruiting/api-applicants.ts src/features/hr/recruiting/api-applications.ts src/features/hr/recruiting/api.ts src/features/hr/recruiting/__tests__/api-applicants.contract.test.ts
git commit -m "hr(plan2): frontend hooks + Zod schemas for applicants/applications"
```

### Task H2: PipelinePills + RequisitionDetailPage

**Files:**
- Create: `src/features/hr/recruiting/components/PipelinePills.tsx`
- Create: `src/features/hr/recruiting/components/ApplicationRow.tsx`
- Create: `src/features/hr/recruiting/pages/RequisitionDetailPage.tsx`
- Modify: `src/features/hr/index.ts`
- Modify: `src/routes/app/hr.routes.tsx`

- [ ] **Step 1: PipelinePills (re-uses the StagePipeline from Plan 1)**

```tsx
// src/features/hr/recruiting/components/PipelinePills.tsx
import { StagePipeline } from "@/features/hr/shared/StagePipeline";

import { STAGES, type Stage } from "../api-applications";

const LABEL: Record<Stage, string> = {
  applied: "Applied",
  screen: "Screen",
  ride_along: "Ride-Along",
  offer: "Offer",
  hired: "Hired",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};


export function PipelinePills({
  counts,
  activeStage,
  onChange,
}: {
  counts: Record<string, number>;
  activeStage: Stage;
  onChange: (s: Stage) => void;
}) {
  const stages = STAGES.map((id) => ({
    id,
    label: LABEL[id],
    count: counts[id] ?? 0,
  }));
  return (
    <StagePipeline
      stages={stages}
      activeStageId={activeStage}
      onStageClick={(id) => onChange(id as Stage)}
    />
  );
}
```

- [ ] **Step 2: ApplicationRow**

```tsx
// src/features/hr/recruiting/components/ApplicationRow.tsx
import { Link } from "react-router-dom";
import {
  STAGES,
  useTransitionStage,
  type ApplicationWithApplicant,
  type Stage,
} from "../api-applications";


const NEXT_STAGES: Record<Stage, Stage[]> = {
  applied: ["screen", "rejected", "withdrawn"],
  screen: ["ride_along", "rejected", "withdrawn"],
  ride_along: ["offer", "rejected", "withdrawn"],
  offer: ["hired", "rejected", "withdrawn"],
  hired: [],
  rejected: [],
  withdrawn: [],
};


export function ApplicationRow({ app }: { app: ApplicationWithApplicant }) {
  const transition = useTransitionStage(app.id);

  async function move(next: Stage) {
    let reason: string | undefined;
    if (next === "rejected") {
      reason = window.prompt("Rejection reason?") ?? undefined;
      if (!reason) return;
    }
    await transition.mutateAsync({ stage: next, rejection_reason: reason });
  }

  return (
    <li className="p-4 flex items-center justify-between gap-4 border-b last:border-b-0">
      <div className="min-w-0">
        <Link
          to={`/hr/applicants/${app.applicant.id}`}
          className="font-medium hover:underline"
        >
          {app.applicant.first_name} {app.applicant.last_name}
        </Link>
        <div className="text-sm text-neutral-500">
          {app.applicant.email}
          {app.applicant.phone && (
            <>
              {" · "}
              {app.applicant.phone}
            </>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {NEXT_STAGES[app.stage].map((next) => (
          <button
            key={next}
            type="button"
            disabled={transition.isPending}
            onClick={() => move(next)}
            className="px-3 py-1.5 text-sm border rounded-lg hover:bg-neutral-50 disabled:opacity-50"
            aria-label={`Move to ${next}`}
          >
            → {next.replace("_", " ")}
          </button>
        ))}
      </div>
    </li>
  );
}
```

- [ ] **Step 3: RequisitionDetailPage**

```tsx
// src/features/hr/recruiting/pages/RequisitionDetailPage.tsx
import { useState } from "react";
import { useParams } from "react-router-dom";

import {
  useApplicationStageCounts,
  useApplicationsForRequisition,
  type Stage,
} from "../api-applications";
import { useRequisitionById } from "../api";
import { ApplicationRow } from "../components/ApplicationRow";
import { PipelinePills } from "../components/PipelinePills";


export function RequisitionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const req = useRequisitionById(id);
  const counts = useApplicationStageCounts(id);
  const [stage, setStage] = useState<Stage>("applied");
  const apps = useApplicationsForRequisition(id, stage);

  if (req.isLoading) return <div className="p-6">Loading requisition…</div>;
  if (req.error) return <div className="p-6 text-red-600">{req.error.message}</div>;
  if (!req.data) return null;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-semibold">{req.data.title}</h1>
      <div className="text-sm text-neutral-500 mt-1">
        {req.data.slug} · {req.data.status} ·{" "}
        {req.data.location_city ?? "—"} {req.data.location_state ?? ""}
      </div>

      <section className="mt-6">
        <PipelinePills
          counts={counts.data ?? {}}
          activeStage={stage}
          onChange={setStage}
        />
      </section>

      <section className="mt-6 border rounded-lg">
        {apps.isLoading && <div className="p-4 text-sm">Loading…</div>}
        {apps.error && (
          <div className="p-4 text-red-600 text-sm">{apps.error.message}</div>
        )}
        {apps.data && apps.data.length === 0 && (
          <div className="p-6 text-sm text-neutral-500">
            No applications in <b>{stage.replace("_", " ")}</b> yet.
          </div>
        )}
        {apps.data && apps.data.length > 0 && (
          <ul className="divide-y">
            {apps.data.map((a) => (
              <ApplicationRow key={a.id} app={a} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Update exports + route**

```tsx
// src/features/hr/index.ts — append
export { RequisitionDetailPage } from "./recruiting/pages/RequisitionDetailPage";
```

```tsx
// src/routes/app/hr.routes.tsx — add
const RequisitionDetailPage = lazy(() =>
  import("@/features/hr").then((m) => ({ default: m.RequisitionDetailPage })),
);

// inside HrRoutes():
<Route
  path="hr/requisitions/:id"
  element={
    <Suspense fallback={<PageLoader />}>
      <RequisitionDetailPage />
    </Suspense>
  }
/>
```

- [ ] **Step 5: Build check**

```bash
npm run build
```
Expected: build succeeds, no TS errors.

- [ ] **Step 6: Commit**

```bash
git add src/features/hr/recruiting/components/PipelinePills.tsx src/features/hr/recruiting/components/ApplicationRow.tsx src/features/hr/recruiting/pages/RequisitionDetailPage.tsx src/features/hr/index.ts src/routes/app/hr.routes.tsx
git commit -m "hr(plan2): RequisitionDetailPage with pipeline pills + stage actions"
```

### Task H3: ApplicantDetailPage

**Files:**
- Create: `src/features/hr/recruiting/pages/ApplicantDetailPage.tsx`
- Modify: `src/features/hr/index.ts`
- Modify: `src/routes/app/hr.routes.tsx`

- [ ] **Step 1: Page**

```tsx
// src/features/hr/recruiting/pages/ApplicantDetailPage.tsx
import { Link, useParams } from "react-router-dom";

import { useApplicant } from "../api-applicants";


export function ApplicantDetailPage() {
  const { id } = useParams<{ id: string }>();
  const a = useApplicant(id);

  if (a.isLoading) return <div className="p-6">Loading applicant…</div>;
  if (a.error) return <div className="p-6 text-red-600">{a.error.message}</div>;
  if (!a.data) return null;

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <Link to="/hr/requisitions" className="text-sm text-neutral-500 hover:underline">
        ← Back to requisitions
      </Link>
      <h1 className="text-2xl font-semibold mt-3">
        {a.data.first_name} {a.data.last_name}
      </h1>
      <div className="mt-2 space-y-1 text-sm">
        <div>
          <span className="text-neutral-500">Email:</span>{" "}
          <a className="underline" href={`mailto:${a.data.email}`}>{a.data.email}</a>
        </div>
        {a.data.phone && (
          <div>
            <span className="text-neutral-500">Phone:</span>{" "}
            <a className="underline" href={`tel:${a.data.phone}`}>{a.data.phone}</a>
          </div>
        )}
        <div>
          <span className="text-neutral-500">Source:</span> {a.data.source}
        </div>
        <div>
          <span className="text-neutral-500">SMS consent:</span>{" "}
          {a.data.sms_consent_given ? "Yes" : "No"}
        </div>
        <div>
          <span className="text-neutral-500">Applied at:</span>{" "}
          {new Date(a.data.created_at).toLocaleString()}
        </div>
      </div>

      {a.data.resume_storage_key ? (
        <div className="mt-6 p-4 border rounded-lg">
          <div className="text-sm text-neutral-500">Resume on file</div>
          <div className="text-xs text-neutral-400 font-mono mt-1 break-all">
            {a.data.resume_storage_key}
          </div>
        </div>
      ) : (
        <p className="mt-6 text-sm text-neutral-500">No resume uploaded.</p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Export + wire route**

```tsx
// src/features/hr/index.ts — append
export { ApplicantDetailPage } from "./recruiting/pages/ApplicantDetailPage";
```

```tsx
// src/routes/app/hr.routes.tsx — add
const ApplicantDetailPage = lazy(() =>
  import("@/features/hr").then((m) => ({ default: m.ApplicantDetailPage })),
);

// inside HrRoutes()
<Route
  path="hr/applicants/:id"
  element={
    <Suspense fallback={<PageLoader />}>
      <ApplicantDetailPage />
    </Suspense>
  }
/>
```

- [ ] **Step 3: Build**

```bash
npm run build
```
Expected: success.

- [ ] **Step 4: Commit**

```bash
git add src/features/hr/recruiting/pages/ApplicantDetailPage.tsx src/features/hr/index.ts src/routes/app/hr.routes.tsx
git commit -m "hr(plan2): ApplicantDetailPage"
```

### Task H4: Update RequisitionsListPage with counts + detail link

**Files:**
- Modify: `src/features/hr/recruiting/pages/RequisitionsListPage.tsx`

- [ ] **Step 1: Update the page**

Replace the list `<li>` body with a link to the detail page and a count badge:

```tsx
// inside rows.map(r => ...)
<li key={r.id} className="p-4 flex items-center justify-between gap-4">
  <div className="min-w-0">
    <Link
      to={`/hr/requisitions/${r.id}`}
      className="font-medium hover:underline"
    >
      {r.title}
    </Link>
    <div className="text-sm text-neutral-500">
      {r.slug} — {r.status}
    </div>
  </div>
  <div className="flex items-center gap-3 shrink-0">
    {typeof r.applicant_count === "number" && r.applicant_count > 0 && (
      <span className="text-xs bg-indigo-100 text-indigo-800 rounded-full px-2 py-0.5">
        {r.applicant_count} applicant{r.applicant_count === 1 ? "" : "s"}
      </span>
    )}
    <span className="text-sm">{r.compensation_display ?? ""}</span>
  </div>
</li>
```

- [ ] **Step 2: Build**

```bash
npm run build
```
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add src/features/hr/recruiting/pages/RequisitionsListPage.tsx
git commit -m "hr(plan2): show applicant counts + link to detail on requisitions list"
```

### Task H5: HR sidebar nav entry

**Files:**
- Modify: `<sidebar component>` (exact path determined during A1)

- [ ] **Step 1: Add the entry**

Locate the sidebar file found during A1. Add an HR section matching the existing pattern — typically:
1. A top-level entry with an icon + label "HR" + a collapsible sub-list.
2. Sub-items: "Requisitions" → `/hr/requisitions`.

Concrete edit — for a sidebar using the same pattern as existing sections (from `src/components/layout/Sidebar.tsx` or wherever A1 surfaced):

```tsx
// Add near the other section blocks (e.g. after MARKETING, before SUPPORT).
// The exact JSX structure depends on the sidebar file — inspect first, then
// copy the adjacent block and fill these values.
{
  section: "HR",
  icon: "briefcase",
  items: [
    { label: "Requisitions", path: "/hr/requisitions" },
  ],
}
```

Engineer: if the sidebar is data-driven (config array), add to the array. If it's hand-rolled JSX, copy the nearest sibling block.

- [ ] **Step 2: Manually verify (dev server)**

```bash
npm run dev
```
Navigate to `http://localhost:5173`, log in as admin, check the sidebar shows "HR → Requisitions". Click it; confirm the URL becomes `/hr/requisitions`.

- [ ] **Step 3: Build check**

```bash
npm run build
```
Expected: success.

- [ ] **Step 4: Commit**

```bash
git add <sidebar-file>
git commit -m "hr(plan2): add HR nav entry to sidebar"
```

---

## Phase I — Playwright E2E

### Task I1: Full apply → hired flow

**Files:**
- Create: `e2e/modules/hr-recruiting-flow.spec.ts`

- [ ] **Step 1: Test**

```ts
// e2e/modules/hr-recruiting-flow.spec.ts
import { test, expect, request as apiRequest } from "@playwright/test";

const API_URL =
  process.env.API_URL || "https://react-crm-api-production.up.railway.app";
const FRONTEND_URL = process.env.BASE_URL || "https://react.ecbtx.com";


test.describe.configure({ mode: "serial" });

test.describe("HR recruiting full flow", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  const slug = `e2e-recruit-${Date.now()}`;
  let authToken: string | undefined;
  let reqId: string | undefined;
  let applicationId: string | undefined;

  test("public apply page renders form (no auth)", async ({ page }) => {
    // Seed a requisition via the authed API first.
    const login = await (await apiRequest.newContext({ baseURL: API_URL })).post("/api/v2/auth/login", {
      data: {
        email: process.env.TEST_EMAIL || "test@macseptic.com",
        password: process.env.TEST_PASSWORD || "TestPassword123",
      },
    });
    test.skip(login.status() !== 200, "test user login unavailable on prod; pre-existing infra gap");
    authToken = (await login.json()).access_token;

    const authed = await apiRequest.newContext({
      baseURL: API_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${authToken}` },
    });
    const r = await authed.post("/api/v2/hr/recruiting/requisitions", {
      data: {
        slug,
        title: "E2E Recruit",
        status: "open",
        employment_type: "full_time",
        location_city: "Houston",
        location_state: "TX",
      },
    });
    expect(r.status(), await r.text()).toBe(201);
    reqId = (await r.json()).id;

    await page.goto(`${API_URL}/careers/${slug}/apply`);
    await page.waitForLoadState("domcontentloaded");
    await expect(page.locator("#apply-form")).toBeVisible();
    await expect(page.locator('input[name="email"]')).toBeVisible();
  });

  test("applicant submits the form", async ({ page }) => {
    test.skip(!reqId, "requisition seed skipped");
    await page.goto(`${API_URL}/careers/${slug}/apply`);
    await page.waitForLoadState("domcontentloaded");
    await page.fill('input[name="first_name"]', "E2E");
    await page.fill('input[name="last_name"]', "Applicant");
    await page.fill('input[name="email"]', `e2e-${Date.now()}@example.com`);
    await page.fill('input[name="phone"]', "+15555550199");
    await page.check('input[name="sms_consent"]');
    await page.click('button[type="submit"]');
    await expect(page.locator("#apply-success")).toBeVisible({ timeout: 10000 });
  });

  test("recruiter sees the application and transitions to hired", async ({
    request,
  }) => {
    test.skip(!authToken || !reqId, "auth or seed skipped");
    const authed = await apiRequest.newContext({
      baseURL: API_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${authToken}` },
    });

    const list = await authed.get(
      `/api/v2/hr/applications?requisition_id=${reqId}`,
    );
    expect(list.status()).toBe(200);
    const body = await list.json();
    expect(body.length).toBeGreaterThan(0);
    applicationId = body[0].id;

    for (const s of ["screen", "ride_along", "offer", "hired"] as const) {
      const r = await authed.patch(
        `/api/v2/hr/applications/${applicationId}/stage`,
        { data: { stage: s } },
      );
      expect(r.status(), await r.text()).toBe(200);
      expect((await r.json()).stage).toBe(s);
    }
  });

  test("counts endpoint reflects the hire", async ({ request }) => {
    test.skip(!authToken || !reqId, "auth or seed skipped");
    const authed = await apiRequest.newContext({
      baseURL: API_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${authToken}` },
    });
    const r = await authed.get(
      `/api/v2/hr/applications/counts?requisition_id=${reqId}`,
    );
    expect(r.status()).toBe(200);
    const counts = await r.json();
    expect(counts.hired ?? 0).toBeGreaterThanOrEqual(1);
  });
});
```

- [ ] **Step 2: Add to the standalone playwright config**

Modify `playwright-hr-standalone.config.ts` to include this new spec:

```ts
testMatch: /hr-(foundation|admin-flow|recruiting-flow)\.spec\.ts/,
// inside the hr-public project:
grep: /public careers|admin frontend|HR recruiting/,
```

- [ ] **Step 3: Run — expect PASS**

```bash
npx playwright test --config=playwright-hr-standalone.config.ts --reporter=list
```
Expected: all HR specs pass. Recruiting flow tests that depend on `auth.setup` may skip cleanly via `test.skip(...)`; public-apply rendering and counts via API must pass.

- [ ] **Step 4: Commit**

```bash
git add e2e/modules/hr-recruiting-flow.spec.ts playwright-hr-standalone.config.ts
git commit -m "hr(plan2): e2e apply-to-hired flow + counts verification"
```

---

## Phase J — Deploy + live verification

### Task J1: Push + migrate + verify

- [ ] **Step 1: Backend test sweep**

```bash
cd /home/will/react-crm-api/.worktrees/hr-foundation
PYTHONPATH=. HR_MODULE_ENABLED=true pytest tests/hr/ -v
```
Expected: all HR tests pass (Plan 1's 48 + Plan 2's new tests).

- [ ] **Step 2: Frontend vitest**

```bash
cd /home/will/ReactCRM/.worktrees/hr-foundation
npx vitest run src/features/hr/
```
Expected: all contract tests pass.

- [ ] **Step 3: Merge to master (both repos) + push**

```bash
cd /home/will/react-crm-api
git checkout master
git merge --no-ff feature/hr-foundation -m "Merge Plan 2: recruiting (applicants, applications, apply form, SMS)"
git push origin master

cd /home/will/ReactCRM
git checkout master
git merge --no-ff feature/hr-foundation -m "Merge Plan 2: recruiting frontend"
git push origin master
```

- [ ] **Step 4: Wait for Railway redeploy + run migrations**

```bash
until curl -sf https://react-crm-api-production.up.railway.app/health >/dev/null; do sleep 10; done
curl -s -X POST https://react-crm-api-production.up.railway.app/health/db/migrate-hr | python -m json.tool
```
Expected: `version_after: "102"`, migration applied cleanly.

If the Procfile ran `alembic upgrade head` already (which it does on deploy), `/health/db/migrate-hr` is a no-op and just reports `version_after: "102"` with `hr_tables_present_before: true`.

- [ ] **Step 5: Smoke-test public apply on live**

```bash
SLUG="smoke-$(date +%s)"
# Create an open requisition via admin (requires valid auth — skip if not
# available; flip status=open in Railway dashboard instead).
# Then:
curl -s https://react-crm-api-production.up.railway.app/careers/${SLUG}/apply | grep -q "apply-form" && echo "APPLY_FORM_OK"
```

- [ ] **Step 6: Playwright run against live**

```bash
cd /home/will/ReactCRM
npx playwright test --config=playwright-hr-standalone.config.ts --reporter=list
```
Expected: all HR Playwright specs pass.

- [ ] **Step 7: Milestone commit**

```bash
cd /home/will/react-crm-api
git commit --allow-empty -m "hr: Plan 2 recruiting shipped"
git push origin master
```

---

## Self-Review Checklist

- [x] Spec §3.2 recruiting tables: `hr_applicants`, `hr_applications`, `hr_application_events` + supporting `hr_recruiting_message_templates`.
- [x] Spec §5.1 pipeline stages all seven represented in `STAGES` and the state machine.
- [x] Spec §5.2 apply form on careers page (real HTML form + JS submit).
- [x] Spec §5.4 applicant sources (careers_page/indeed/ziprecruiter/facebook/referral/manual/email) in both schemas.
- [x] Spec §5.5 resume storage in place; parsing deferred to v1.1+ (noted in spec).
- [x] Spec §5.6 candidate SMS with templated per-stage messages (5 defaults seeded in migration 102).
- [x] Spec §10 pipeline pills — `PipelinePills` reuses Plan 1 `StagePipeline`.
- [x] Spec §10 detail page with applicant list + stage actions.
- [x] Hire emits `hr.applicant.hired` on `TriggerBus` for Plan 3 to pick up.
- [x] SMS consent captured at apply time (TCPA disclosure in the form), stored on applicant (not `sms_consent` — applicants aren't customers).
- [x] TCPA disclosure checkbox is opt-in (`sms_consent` checkbox must be ticked).
- [x] Existing email-consent / phone normalization guarded against (phone can be null; no crash).
- [x] Migrations 101 + 102 follow the numeric pattern; 102 is idempotent.
- [x] Test DB is SQLite; INET falls back via `with_variant(String(45), "sqlite")`.
- [x] `EmailStr` dependency: `email-validator` is already installed (Plan 1 verified).
- [x] User's backend rules: `async_session_maker`, `selectinload` where we load relationships, `UUIDStr`, migration reversibility.
- [x] User's frontend rules: Zod validation, mobile responsiveness (Tailwind responsive classes), no `/app/` prefix in routes, no double `/api`.
- [x] User's Railway rules: git push only, verify `/health` after deploy, env vars not via CLI except where already documented for HR_MODULE_ENABLED.
- [x] No placeholders except one flagged `<sidebar-file>` in Task H5 which is intentional — resolved during A1 inspection.

### Deferred to Plan 3 or v1.1+

- Resume LLM parsing (spec §5.5 — v1.1).
- Message template editing UI (spec §5.6 — v1.1; v1 uses seeded defaults only).
- Rejection reason picklist with seeded reasons (currently free-text).
- Recruiter assignment UI (column exists; UI in Plan 3's employee-detail context).
- Candidate email as secondary copy (SMS-first in Plan 2; email templating tracked for v1.1).
- Applicant dedupe by phone (currently dedupe by email only).
- Rate limiting on public apply endpoint (existing global rate limiter may already cover; verify in A1).
- Connection of `hr.applicant.hired` → onboarding instance spawn (Plan 3).

---

## Plan complete.
