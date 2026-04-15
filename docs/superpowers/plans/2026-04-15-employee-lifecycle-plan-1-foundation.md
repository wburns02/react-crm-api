# Employee Lifecycle — Plan 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation layer of the HR module — bounded `app/hr/` namespace, audit log, role assignments, generic task-checklist workflow engine, minimal requisitions admin, e-sign subsystem with seeded document templates, public careers SSR pages, and Indeed XML feed. This is Plan 1 of 3 (see spec §13.3). On completion, Mac Septic's careers page is live and indexable; no employee-facing UX yet.

**Architecture:** New bounded module `app/hr/` in `react-crm-api` and `src/features/hr/` in `ReactCRM`. All HR tables prefixed `hr_`. FastAPI router mounts at `/api/v2/hr/*` (auth) and `/api/v2/public/careers/*` + `/api/v2/public/sign/*` + `/api/v2/public/jobs.xml` (no auth). Feature-flagged via `HR_MODULE_ENABLED`.

**Tech Stack:** FastAPI, SQLAlchemy (async), Alembic, Pydantic v2, pypdf, Jinja2 (SSR), pytest + pytest-asyncio + httpx + real Postgres in CI / SQLite in unit tests. Frontend: React 19, TanStack Query, Zod, Tailwind, Vite.

**Spec:** `docs/superpowers/specs/2026-04-15-employee-lifecycle-design.md`

---

## File Structure

Files created in this plan (backend):

```
app/hr/__init__.py
app/hr/feature_flag.py
app/hr/router.py
app/hr/shared/audit.py
app/hr/shared/role_resolver.py
app/hr/shared/storage.py
app/hr/shared/notifications.py
app/hr/shared/models.py               ← HrAuditLog, HrRoleAssignment
app/hr/shared/schemas.py
app/hr/workflow/models.py              ← HrWorkflowTemplate, ...Task, ...Instance, ...Dependency, ...Comment, ...Attachment
app/hr/workflow/schemas.py
app/hr/workflow/engine.py
app/hr/workflow/triggers.py
app/hr/workflow/services.py
app/hr/workflow/router.py
app/hr/recruiting/models.py            ← HrRequisition (minimal in Plan 1; full in Plan 2)
app/hr/recruiting/schemas.py
app/hr/recruiting/services.py
app/hr/recruiting/router.py
app/hr/recruiting/careers_feed.py
app/hr/careers/router.py               ← public SSR Jinja2 pages
app/hr/careers/templates/careers_index.html
app/hr/careers/templates/requisition_detail.html
app/hr/esign/models.py                 ← HrDocumentTemplate, HrSignatureRequest, HrSignedDocument, HrSignatureEvent
app/hr/esign/schemas.py
app/hr/esign/renderer.py
app/hr/esign/services.py
app/hr/esign/router.py                 ← admin + public
app/hr/esign/templates/sign.html       ← public sign page HTML
app/hr/esign/seed_templates.py

alembic/versions/095_hr_shared_tables.py
alembic/versions/096_hr_workflow_tables.py
alembic/versions/097_hr_requisition_minimal.py
alembic/versions/098_hr_esign_tables.py
alembic/versions/099_hr_seed_document_templates.py

tests/hr/__init__.py
tests/hr/conftest.py
tests/hr/test_audit.py
tests/hr/test_role_resolver.py
tests/hr/test_workflow_engine.py
tests/hr/test_workflow_router.py
tests/hr/test_esign_renderer.py
tests/hr/test_esign_router.py
tests/hr/test_careers_ssr.py
tests/hr/test_careers_feed.py
tests/hr/test_feature_flag.py
tests/hr/fixtures/test-employment-agreement.pdf
tests/hr/fixtures/test-w4.pdf
```

Frontend:

```
src/features/hr/index.ts
src/features/hr/workflow/api.ts
src/features/hr/workflow/components/WorkflowTimeline.tsx
src/features/hr/workflow/components/TaskCard.tsx
src/features/hr/workflow/components/StagePipeline.tsx  ← shared; copied to hr/shared too
src/features/hr/shared/ActivityPanel.tsx
src/features/hr/shared/ProgressBar.tsx
src/features/hr/shared/CelebrationCard.tsx
src/features/hr/recruiting/api.ts
src/features/hr/recruiting/pages/RequisitionsListPage.tsx
src/features/hr/recruiting/pages/RequisitionEditorPage.tsx   ← admin CRUD for Plan 1
src/routes/hrRoutes.tsx                                      ← /app/hr/* routes
src/routes/publicCareersRoutes.tsx                           ← /careers/* (if we keep in SPA; see spec §5.2)
```

Reconciliation files (read-only inspection, no edits):

```
app/models/user.py
app/models/technician.py
app/models/certification.py
app/models/license.py
app/models/workflow_automation.py
app/api/v2/onboarding.py           ← existing customer setup wizard — do not touch
app/api/v2/employee_portal.py      ← existing tech mobile app — do not touch
```

---

## Phase A — Scaffold + Reconciliation

### Task A1: Reconciliation audit of existing models

**Files:**
- Read only: `app/models/user.py`, `app/models/technician.py`, `app/models/certification.py`, `app/models/license.py`, `app/models/workflow_automation.py`
- Read only: `app/api/v2/onboarding.py`, `app/api/v2/workflow_automations.py`, `app/api/v2/employee_portal.py`
- Create: `app/hr/RECONCILIATION_NOTES.md`

- [ ] **Step 1: Inspect each model file listed above. Document in `app/hr/RECONCILIATION_NOTES.md`:**
  - What columns/relationships exist on `User`, `Technician`.
  - Does `certification.py` cover TCEQ OS-0, TCEQ MP, DOT medical, CDL? What fields?
  - Does `license.py` cover state licenses?
  - What is the primary-key type on `api_users` (confirmed UUID? verify).
  - Confirm there's no existing `fuel_cards` table.
  - Document the `onboarding` (customer setup) endpoint prefix and confirm no path collision with `/api/v2/hr/onboarding/*`.
  - Document the signature-pad component location in `employee_portal.py` (for later reuse in e-sign).

- [ ] **Step 2: Commit reconciliation notes**

```bash
git add app/hr/RECONCILIATION_NOTES.md
git commit -m "hr: add reconciliation notes for existing models"
```

### Task A2: Create `app/hr/` scaffold

**Files:**
- Create: `app/hr/__init__.py` (empty exports marker)
- Create: `app/hr/shared/__init__.py`
- Create: `app/hr/workflow/__init__.py`
- Create: `app/hr/recruiting/__init__.py`
- Create: `app/hr/careers/__init__.py`
- Create: `app/hr/esign/__init__.py`
- Create: `tests/hr/__init__.py`

- [ ] **Step 1: Create empty `__init__.py` in each directory above**

- [ ] **Step 2: Verify import works**

Run: `cd /home/will/react-crm-api && python -c "import app.hr; import app.hr.workflow; import app.hr.recruiting; import app.hr.esign; import app.hr.careers; import app.hr.shared; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/hr/ tests/hr/
git commit -m "hr: scaffold bounded module directory tree"
```

### Task A3: Feature flag

**Files:**
- Create: `app/hr/feature_flag.py`
- Create: `tests/hr/test_feature_flag.py`

- [ ] **Step 1: Write failing test**

```python
# tests/hr/test_feature_flag.py
import os
import pytest
from app.hr.feature_flag import hr_module_enabled


def test_hr_module_disabled_by_default(monkeypatch):
    monkeypatch.delenv("HR_MODULE_ENABLED", raising=False)
    assert hr_module_enabled() is False


def test_hr_module_enabled_when_true(monkeypatch):
    monkeypatch.setenv("HR_MODULE_ENABLED", "true")
    assert hr_module_enabled() is True


def test_hr_module_respects_falsy_values(monkeypatch):
    monkeypatch.setenv("HR_MODULE_ENABLED", "0")
    assert hr_module_enabled() is False
    monkeypatch.setenv("HR_MODULE_ENABLED", "false")
    assert hr_module_enabled() is False
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/hr/test_feature_flag.py -v`
Expected: ImportError — `app.hr.feature_flag` missing.

- [ ] **Step 3: Implement**

```python
# app/hr/feature_flag.py
import os


def hr_module_enabled() -> bool:
    return os.getenv("HR_MODULE_ENABLED", "").lower() in {"1", "true", "yes"}
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/hr/test_feature_flag.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/hr/feature_flag.py tests/hr/test_feature_flag.py
git commit -m "hr: add HR_MODULE_ENABLED feature flag"
```

### Task A4: Blueprint placeholder router + registration gated by flag

**Files:**
- Create: `app/hr/router.py`
- Modify: `app/main.py` (add conditional `include_router` call; find the area where other `v2` routers register — match existing pattern)

- [ ] **Step 1: Create placeholder router**

```python
# app/hr/router.py
from fastapi import APIRouter

hr_router = APIRouter(prefix="/hr", tags=["hr"])


@hr_router.get("/health")
async def hr_health() -> dict[str, str]:
    return {"status": "ok", "module": "hr"}
```

- [ ] **Step 2: Register conditionally in `app/main.py`**

Find the block that registers `/api/v2` routers. Add:

```python
# app/main.py — inside the app factory where other v2 routers are included
from app.hr.feature_flag import hr_module_enabled
from app.hr.router import hr_router

if hr_module_enabled():
    app.include_router(hr_router, prefix="/api/v2")
```

- [ ] **Step 3: Write test**

```python
# tests/hr/test_feature_flag.py — append
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_hr_router_not_registered_when_flag_off(monkeypatch):
    monkeypatch.delenv("HR_MODULE_ENABLED", raising=False)
    # Rebuild the app with flag off
    from importlib import reload
    import app.main
    reload(app.main)
    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app.main.app), base_url="http://test") as client:
        r = await client.get("/api/v2/hr/health")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_hr_router_registered_when_flag_on(monkeypatch):
    monkeypatch.setenv("HR_MODULE_ENABLED", "true")
    from importlib import reload
    import app.main
    reload(app.main)
    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app.main.app), base_url="http://test") as client:
        r = await client.get("/api/v2/hr/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "module": "hr"}
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/hr/test_feature_flag.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/hr/router.py app/main.py tests/hr/test_feature_flag.py
git commit -m "hr: register hr_router conditionally on HR_MODULE_ENABLED"
```

---

## Phase B — Audit log

### Task B1: `hr_audit_log` model + migration

**Files:**
- Create: `app/hr/shared/models.py`
- Create: `alembic/versions/095_hr_shared_tables.py`

- [ ] **Step 1: Write model**

```python
# app/hr/shared/models.py
from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.sql import func
from uuid import uuid4

from app.database import Base


class HrAuditLog(Base):
    __tablename__ = "hr_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    event = Column(String(64), nullable=False)
    diff = Column(JSON, default=dict)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("api_users.id"), nullable=True)
    actor_ip = Column(INET, nullable=True)
    actor_user_agent = Column(Text, nullable=True)
    actor_location = Column(String(128), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_hr_audit_log_entity", "entity_type", "entity_id", "created_at"),
        Index("ix_hr_audit_log_actor", "actor_user_id", "created_at"),
    )


class HrRoleAssignment(Base):
    __tablename__ = "hr_role_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    role = Column(String(32), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("api_users.id"), nullable=False)
    priority = Column(Integer, default=0, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_hr_role_assignments_active", "role", "active", "priority"),
    )
```

- [ ] **Step 2: Register model in `app/models/__init__.py`**

Find the existing model registration and add:

```python
# app/models/__init__.py — at the bottom
from app.hr.shared.models import HrAuditLog, HrRoleAssignment  # noqa: F401
```

- [ ] **Step 3: Generate migration**

Run: `cd /home/will/react-crm-api && alembic revision --autogenerate -m "hr shared tables"`

Rename output file to `alembic/versions/095_hr_shared_tables.py`. Edit `down_revision = "094_add_county_to_customers"`. Verify `upgrade()` creates both tables with indexes and `downgrade()` drops them.

- [ ] **Step 4: Apply**

Run: `alembic upgrade head`
Expected: success, no errors.

- [ ] **Step 5: Run existing tests to verify nothing broke**

Run: `pytest -v --tb=short`
Expected: same pass/fail as before.

- [ ] **Step 6: Commit**

```bash
git add app/hr/shared/models.py app/models/__init__.py alembic/versions/095_hr_shared_tables.py
git commit -m "hr: add HrAuditLog and HrRoleAssignment models + migration 095"
```

### Task B2: Audit writer service

**Files:**
- Create: `app/hr/shared/audit.py`
- Create: `tests/hr/conftest.py`
- Create: `tests/hr/test_audit.py`

- [ ] **Step 1: Write shared conftest**

```python
# tests/hr/conftest.py
import pytest_asyncio
from uuid import uuid4
from app.models.user import User


@pytest_asyncio.fixture
async def hr_test_user(db):
    user = User(
        id=uuid4(),
        email="hr-test@example.com",
        first_name="HR",
        last_name="Test",
        password_hash="x",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
```

- [ ] **Step 2: Write failing test**

```python
# tests/hr/test_audit.py
import pytest
from uuid import uuid4
from app.hr.shared.audit import write_audit
from app.hr.shared.models import HrAuditLog
from sqlalchemy import select


@pytest.mark.asyncio
async def test_write_audit_inserts_row(db, hr_test_user):
    entity_id = uuid4()
    await write_audit(
        db=db,
        entity_type="applicant",
        entity_id=entity_id,
        event="created",
        diff={"stage": [None, "applied"]},
        actor_user_id=hr_test_user.id,
        actor_ip="192.0.2.1",
        actor_user_agent="pytest",
        actor_location="Houston, TX, US",
    )
    await db.commit()

    rows = (await db.execute(select(HrAuditLog).where(HrAuditLog.entity_id == entity_id))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.event == "created"
    assert row.diff == {"stage": [None, "applied"]}
    assert row.actor_user_id == hr_test_user.id


@pytest.mark.asyncio
async def test_write_audit_accepts_null_actor(db):
    entity_id = uuid4()
    await write_audit(
        db=db,
        entity_type="applicant",
        entity_id=entity_id,
        event="system_event",
        diff={},
    )
    await db.commit()
    rows = (await db.execute(select(HrAuditLog).where(HrAuditLog.entity_id == entity_id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].actor_user_id is None
```

- [ ] **Step 3: Run — expect FAIL**

Run: `pytest tests/hr/test_audit.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement**

```python
# app/hr/shared/audit.py
from typing import Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.shared.models import HrAuditLog


async def write_audit(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: UUID,
    event: str,
    diff: dict[str, Any] | None = None,
    actor_user_id: UUID | None = None,
    actor_ip: str | None = None,
    actor_user_agent: str | None = None,
    actor_location: str | None = None,
) -> HrAuditLog:
    row = HrAuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        event=event,
        diff=diff or {},
        actor_user_id=actor_user_id,
        actor_ip=actor_ip,
        actor_user_agent=actor_user_agent,
        actor_location=actor_location,
    )
    db.add(row)
    await db.flush()
    return row
```

- [ ] **Step 5: Run — expect PASS**

Run: `pytest tests/hr/test_audit.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add app/hr/shared/audit.py tests/hr/conftest.py tests/hr/test_audit.py
git commit -m "hr: add write_audit service"
```

---

## Phase C — Role resolver

### Task C1: Role resolver service

**Files:**
- Create: `app/hr/shared/role_resolver.py`
- Create: `tests/hr/test_role_resolver.py`

- [ ] **Step 1: Write failing test**

```python
# tests/hr/test_role_resolver.py
import pytest
from uuid import uuid4
from app.hr.shared.role_resolver import resolve_role
from app.hr.shared.models import HrRoleAssignment


@pytest.mark.asyncio
async def test_resolve_role_returns_user_id(db, hr_test_user):
    db.add(HrRoleAssignment(role="hr", user_id=hr_test_user.id, priority=0, active=True))
    await db.commit()

    resolved = await resolve_role(db, role="hr")
    assert resolved == hr_test_user.id


@pytest.mark.asyncio
async def test_resolve_role_prefers_higher_priority(db, hr_test_user):
    import secrets
    from app.models.user import User
    other = User(id=uuid4(), email=f"o{secrets.token_hex(4)}@ex.com", first_name="x", last_name="y", password_hash="x", is_active=True)
    db.add(other)
    db.add(HrRoleAssignment(role="hr", user_id=hr_test_user.id, priority=0, active=True))
    db.add(HrRoleAssignment(role="hr", user_id=other.id, priority=10, active=True))
    await db.commit()

    resolved = await resolve_role(db, role="hr")
    assert resolved == other.id


@pytest.mark.asyncio
async def test_resolve_role_ignores_inactive(db, hr_test_user):
    db.add(HrRoleAssignment(role="hr", user_id=hr_test_user.id, priority=0, active=False))
    await db.commit()
    resolved = await resolve_role(db, role="hr")
    assert resolved is None


@pytest.mark.asyncio
async def test_resolve_role_hire_returns_subject_id(db):
    subject_id = uuid4()
    resolved = await resolve_role(db, role="hire", subject_id=subject_id)
    assert resolved == subject_id


@pytest.mark.asyncio
async def test_resolve_role_employee_returns_subject_id(db):
    subject_id = uuid4()
    resolved = await resolve_role(db, role="employee", subject_id=subject_id)
    assert resolved == subject_id
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/hr/test_role_resolver.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# app/hr/shared/role_resolver.py
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.shared.models import HrRoleAssignment


SUBJECT_ROLES = {"hire", "employee"}


async def resolve_role(
    db: AsyncSession,
    *,
    role: str,
    subject_id: UUID | None = None,
) -> UUID | None:
    """Resolve an assignee_role string to a concrete user_id, or None if unassignable."""
    if role in SUBJECT_ROLES:
        return subject_id

    stmt = (
        select(HrRoleAssignment.user_id)
        .where(HrRoleAssignment.role == role, HrRoleAssignment.active.is_(True))
        .order_by(HrRoleAssignment.priority.desc(), HrRoleAssignment.created_at.asc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/hr/test_role_resolver.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/hr/shared/role_resolver.py tests/hr/test_role_resolver.py
git commit -m "hr: add role resolver with priority + subject roles"
```

---

## Phase D — Workflow engine data model

### Task D1: Workflow model file

**Files:**
- Create: `app/hr/workflow/models.py`

- [ ] **Step 1: Write models**

```python
# app/hr/workflow/models.py
from sqlalchemy import (
    Column, String, Text, DateTime, Boolean, Integer, ForeignKey, JSON, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from uuid import uuid4

from app.database import Base


class HrWorkflowTemplate(Base):
    __tablename__ = "hr_workflow_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(200), nullable=False)
    category = Column(String(32), nullable=False)  # onboarding | offboarding | recruiting | operational
    version = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("api_users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    tasks = relationship("HrWorkflowTemplateTask", back_populates="template", cascade="all, delete-orphan")


class HrWorkflowTemplateTask(Base):
    __tablename__ = "hr_workflow_template_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("hr_workflow_templates.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, nullable=False)
    stage = Column(String(64), nullable=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    kind = Column(String(32), nullable=False)  # form_sign | document_upload | training_video | verify | assignment | manual
    assignee_role = Column(String(32), nullable=False)
    due_offset_days = Column(Integer, default=0, nullable=False)
    required = Column(Boolean, default=True, nullable=False)
    config = Column(JSON, default=dict)

    template = relationship("HrWorkflowTemplate", back_populates="tasks")


class HrWorkflowTemplateDependency(Base):
    __tablename__ = "hr_workflow_template_dependencies"

    task_id = Column(UUID(as_uuid=True), ForeignKey("hr_workflow_template_tasks.id", ondelete="CASCADE"), primary_key=True)
    depends_on_task_id = Column(UUID(as_uuid=True), ForeignKey("hr_workflow_template_tasks.id", ondelete="CASCADE"), primary_key=True)


class HrWorkflowInstance(Base):
    __tablename__ = "hr_workflow_instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("hr_workflow_templates.id"), nullable=False)
    template_version = Column(Integer, nullable=False)
    subject_type = Column(String(32), nullable=False)  # employee | applicant | truck | customer
    subject_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(String(16), default="active", nullable=False)
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    started_by = Column(UUID(as_uuid=True), ForeignKey("api_users.id"), nullable=True)

    tasks = relationship("HrWorkflowTask", back_populates="instance", cascade="all, delete-orphan")


class HrWorkflowTask(Base):
    __tablename__ = "hr_workflow_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    instance_id = Column(UUID(as_uuid=True), ForeignKey("hr_workflow_instances.id", ondelete="CASCADE"), nullable=False)
    template_task_id = Column(UUID(as_uuid=True), ForeignKey("hr_workflow_template_tasks.id"), nullable=True)
    position = Column(Integer, nullable=False)
    stage = Column(String(64), nullable=True)
    name = Column(String(200), nullable=False)
    kind = Column(String(32), nullable=False)
    assignee_user_id = Column(UUID(as_uuid=True), ForeignKey("api_users.id"), nullable=True)
    assignee_role = Column(String(32), nullable=False)
    status = Column(String(16), default="blocked", nullable=False)  # blocked|ready|in_progress|completed|skipped
    due_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    completed_by = Column(UUID(as_uuid=True), ForeignKey("api_users.id"), nullable=True)
    config = Column(JSON, default=dict)
    result = Column(JSON, default=dict)

    instance = relationship("HrWorkflowInstance", back_populates="tasks")
    dependencies = relationship("HrWorkflowTaskDependency", foreign_keys="HrWorkflowTaskDependency.task_id", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_hr_workflow_tasks_instance_status", "instance_id", "status"),
        Index("ix_hr_workflow_tasks_assignee_open", "assignee_user_id", "status"),
    )


class HrWorkflowTaskDependency(Base):
    __tablename__ = "hr_workflow_task_dependencies"

    task_id = Column(UUID(as_uuid=True), ForeignKey("hr_workflow_tasks.id", ondelete="CASCADE"), primary_key=True)
    depends_on_task_id = Column(UUID(as_uuid=True), ForeignKey("hr_workflow_tasks.id", ondelete="CASCADE"), primary_key=True)


class HrWorkflowTaskComment(Base):
    __tablename__ = "hr_workflow_task_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("hr_workflow_tasks.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("api_users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrWorkflowTaskAttachment(Base):
    __tablename__ = "hr_workflow_task_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("hr_workflow_tasks.id", ondelete="CASCADE"), nullable=False)
    storage_key = Column(String(512), nullable=False)
    filename = Column(String(256), nullable=False)
    mime_type = Column(String(128), nullable=True)
    size = Column(Integer, nullable=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("api_users.id"), nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)
```

- [ ] **Step 2: Register in `app/models/__init__.py`**

```python
# append
from app.hr.workflow.models import (  # noqa: F401
    HrWorkflowTemplate,
    HrWorkflowTemplateTask,
    HrWorkflowTemplateDependency,
    HrWorkflowInstance,
    HrWorkflowTask,
    HrWorkflowTaskDependency,
    HrWorkflowTaskComment,
    HrWorkflowTaskAttachment,
)
```

- [ ] **Step 3: Generate migration**

Run: `alembic revision --autogenerate -m "hr workflow tables"`
Rename to `096_hr_workflow_tables.py`. Set `down_revision = "095_hr_shared_tables"`. Verify all 8 tables + indexes + FKs are in `upgrade()`; all drops in `downgrade()` in reverse order.

- [ ] **Step 4: Apply**

Run: `alembic upgrade head`
Expected: success.

- [ ] **Step 5: Confirm tables**

Run: `psql $DATABASE_URL -c "\dt hr_workflow*"` (or equivalent via `alembic`-managed connection). Confirm 8 tables.

- [ ] **Step 6: Commit**

```bash
git add app/hr/workflow/models.py app/models/__init__.py alembic/versions/096_hr_workflow_tables.py
git commit -m "hr: add workflow engine models + migration 096"
```

### Task D2: Pydantic schemas

**Files:**
- Create: `app/hr/workflow/schemas.py`

- [ ] **Step 1: Write schemas**

```python
# app/hr/workflow/schemas.py
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.types import UUIDStr


TaskKind = Literal["form_sign", "document_upload", "training_video", "verify", "assignment", "manual"]
TaskStatus = Literal["blocked", "ready", "in_progress", "completed", "skipped"]
AssigneeRole = Literal["hire", "employee", "manager", "hr", "dispatch", "it"]
WorkflowStatus = Literal["active", "completed", "cancelled"]
TemplateCategory = Literal["onboarding", "offboarding", "recruiting", "operational"]
SubjectType = Literal["employee", "applicant", "truck", "customer"]


class TemplateTaskIn(BaseModel):
    position: int
    stage: str | None = None
    name: str
    description: str | None = None
    kind: TaskKind
    assignee_role: AssigneeRole
    due_offset_days: int = 0
    required: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    depends_on_positions: list[int] = Field(default_factory=list)


class TemplateIn(BaseModel):
    name: str
    category: TemplateCategory
    tasks: list[TemplateTaskIn]


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    name: str
    category: TemplateCategory
    version: int
    is_active: bool


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    instance_id: UUIDStr
    position: int
    stage: str | None
    name: str
    kind: TaskKind
    status: TaskStatus
    assignee_user_id: UUIDStr | None
    assignee_role: AssigneeRole
    due_at: datetime | None
    completed_at: datetime | None
    config: dict[str, Any]
    result: dict[str, Any]


class InstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    template_id: UUIDStr
    template_version: int
    subject_type: SubjectType
    subject_id: UUIDStr
    status: WorkflowStatus
    started_at: datetime
    completed_at: datetime | None


class SpawnRequest(BaseModel):
    template_id: UUIDStr
    subject_type: SubjectType
    subject_id: UUIDStr
    start_date: datetime | None = None


class AdvanceTaskRequest(BaseModel):
    status: Literal["in_progress", "completed", "skipped"]
    reason: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 2: Smoke-import**

Run: `python -c "from app.hr.workflow import schemas; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add app/hr/workflow/schemas.py
git commit -m "hr: add workflow Pydantic schemas"
```

---

## Phase E — Workflow engine logic

### Task E1: Template creation + spawn

**Files:**
- Create: `app/hr/workflow/engine.py`
- Create: `tests/hr/test_workflow_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/hr/test_workflow_engine.py
import pytest
from uuid import uuid4
from datetime import datetime, timezone, timedelta

from app.hr.workflow.engine import create_template, spawn_instance
from app.hr.workflow.schemas import TemplateIn, TemplateTaskIn
from app.hr.workflow.models import HrWorkflowTask
from app.hr.shared.models import HrRoleAssignment
from sqlalchemy import select


def _simple_template(name="T1") -> TemplateIn:
    return TemplateIn(
        name=name,
        category="onboarding",
        tasks=[
            TemplateTaskIn(position=0, name="Sign agreement", kind="form_sign", assignee_role="hire"),
            TemplateTaskIn(position=1, name="Verify I-9", kind="verify", assignee_role="hr", depends_on_positions=[0]),
        ],
    )


@pytest.mark.asyncio
async def test_create_template_persists(db, hr_test_user):
    t = await create_template(db, _simple_template(), created_by=hr_test_user.id)
    await db.commit()
    assert t.id is not None
    assert t.version == 1
    # load tasks
    await db.refresh(t, ["tasks"])
    assert len(t.tasks) == 2


@pytest.mark.asyncio
async def test_spawn_instance_clones_tasks(db, hr_test_user):
    t = await create_template(db, _simple_template(), created_by=hr_test_user.id)
    db.add(HrRoleAssignment(role="hr", user_id=hr_test_user.id, priority=0, active=True))
    await db.commit()

    subject = uuid4()
    inst = await spawn_instance(
        db,
        template_id=t.id,
        subject_type="applicant",
        subject_id=subject,
        started_by=hr_test_user.id,
    )
    await db.commit()

    tasks = (await db.execute(select(HrWorkflowTask).where(HrWorkflowTask.instance_id == inst.id).order_by(HrWorkflowTask.position))).scalars().all()
    assert len(tasks) == 2
    assert tasks[0].status == "ready"  # no deps
    assert tasks[0].assignee_user_id == subject  # "hire" → subject_id
    assert tasks[1].status == "blocked"  # depends on 0
    assert tasks[1].assignee_user_id == hr_test_user.id  # "hr" → role lookup


@pytest.mark.asyncio
async def test_spawn_missing_template_raises(db, hr_test_user):
    with pytest.raises(ValueError):
        await spawn_instance(
            db,
            template_id=uuid4(),
            subject_type="applicant",
            subject_id=uuid4(),
            started_by=hr_test_user.id,
        )


@pytest.mark.asyncio
async def test_spawn_with_start_date_offsets_due(db, hr_test_user):
    t_in = TemplateIn(
        name="Offset",
        category="onboarding",
        tasks=[
            TemplateTaskIn(position=0, name="D1", kind="manual", assignee_role="hire", due_offset_days=5),
        ],
    )
    t = await create_template(db, t_in, created_by=hr_test_user.id)
    await db.commit()

    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    inst = await spawn_instance(db, template_id=t.id, subject_type="applicant", subject_id=uuid4(), started_by=hr_test_user.id, start_date=start)
    await db.commit()

    task = (await db.execute(select(HrWorkflowTask).where(HrWorkflowTask.instance_id == inst.id))).scalar_one()
    assert task.due_at.date() == (start + timedelta(days=5)).date()
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/hr/test_workflow_engine.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# app/hr/workflow/engine.py
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.hr.shared.audit import write_audit
from app.hr.shared.role_resolver import resolve_role
from app.hr.workflow.models import (
    HrWorkflowTemplate,
    HrWorkflowTemplateTask,
    HrWorkflowTemplateDependency,
    HrWorkflowInstance,
    HrWorkflowTask,
    HrWorkflowTaskDependency,
)
from app.hr.workflow.schemas import TemplateIn


async def create_template(
    db: AsyncSession,
    payload: TemplateIn,
    *,
    created_by: UUID | None = None,
) -> HrWorkflowTemplate:
    template = HrWorkflowTemplate(
        name=payload.name,
        category=payload.category,
        version=1,
        created_by=created_by,
    )
    db.add(template)
    await db.flush()

    position_to_task: dict[int, HrWorkflowTemplateTask] = {}
    for t in payload.tasks:
        tt = HrWorkflowTemplateTask(
            template_id=template.id,
            position=t.position,
            stage=t.stage,
            name=t.name,
            description=t.description,
            kind=t.kind,
            assignee_role=t.assignee_role,
            due_offset_days=t.due_offset_days,
            required=t.required,
            config=t.config,
        )
        db.add(tt)
        await db.flush()
        position_to_task[t.position] = tt

    for t in payload.tasks:
        for dep_pos in t.depends_on_positions:
            if dep_pos not in position_to_task:
                raise ValueError(f"task position {t.position} depends on missing position {dep_pos}")
            db.add(
                HrWorkflowTemplateDependency(
                    task_id=position_to_task[t.position].id,
                    depends_on_task_id=position_to_task[dep_pos].id,
                )
            )
    await db.flush()
    return template


async def spawn_instance(
    db: AsyncSession,
    *,
    template_id: UUID,
    subject_type: str,
    subject_id: UUID,
    started_by: UUID | None = None,
    start_date: datetime | None = None,
) -> HrWorkflowInstance:
    start = start_date or datetime.now(timezone.utc)

    template = (
        await db.execute(
            select(HrWorkflowTemplate)
            .options(selectinload(HrWorkflowTemplate.tasks))
            .where(HrWorkflowTemplate.id == template_id, HrWorkflowTemplate.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if template is None:
        raise ValueError(f"template {template_id} not found or inactive")

    deps_rows = (
        await db.execute(
            select(HrWorkflowTemplateDependency).where(
                HrWorkflowTemplateDependency.task_id.in_([t.id for t in template.tasks])
            )
        )
    ).scalars().all()
    template_deps_by_task: dict[UUID, list[UUID]] = {}
    for d in deps_rows:
        template_deps_by_task.setdefault(d.task_id, []).append(d.depends_on_task_id)

    instance = HrWorkflowInstance(
        template_id=template.id,
        template_version=template.version,
        subject_type=subject_type,
        subject_id=subject_id,
        started_by=started_by,
    )
    db.add(instance)
    await db.flush()

    template_task_to_instance_task: dict[UUID, HrWorkflowTask] = {}
    for tt in template.tasks:
        assignee_user_id = await resolve_role(db, role=tt.assignee_role, subject_id=subject_id)
        task = HrWorkflowTask(
            instance_id=instance.id,
            template_task_id=tt.id,
            position=tt.position,
            stage=tt.stage,
            name=tt.name,
            kind=tt.kind,
            assignee_user_id=assignee_user_id,
            assignee_role=tt.assignee_role,
            status="blocked" if tt.id in template_deps_by_task else "ready",
            due_at=start + timedelta(days=tt.due_offset_days),
            config=tt.config or {},
            result={},
        )
        db.add(task)
        await db.flush()
        template_task_to_instance_task[tt.id] = task

    for tt_id, dep_tt_ids in template_deps_by_task.items():
        task = template_task_to_instance_task[tt_id]
        for dep_tt_id in dep_tt_ids:
            dep_task = template_task_to_instance_task[dep_tt_id]
            db.add(HrWorkflowTaskDependency(task_id=task.id, depends_on_task_id=dep_task.id))

    await db.flush()
    await write_audit(
        db,
        entity_type="workflow_instance",
        entity_id=instance.id,
        event="spawned",
        diff={"template_id": [None, str(template.id)]},
        actor_user_id=started_by,
    )
    return instance
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/hr/test_workflow_engine.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/hr/workflow/engine.py tests/hr/test_workflow_engine.py
git commit -m "hr: workflow engine — create_template + spawn_instance"
```

### Task E2: Task state machine (advance)

**Files:**
- Modify: `app/hr/workflow/engine.py`
- Modify: `tests/hr/test_workflow_engine.py`

- [ ] **Step 1: Add failing tests**

```python
# tests/hr/test_workflow_engine.py — append
from app.hr.workflow.engine import advance_task


@pytest.mark.asyncio
async def test_complete_ready_task_unblocks_dependents(db, hr_test_user):
    t = await create_template(db, _simple_template(), created_by=hr_test_user.id)
    db.add(HrRoleAssignment(role="hr", user_id=hr_test_user.id, priority=0, active=True))
    await db.commit()

    inst = await spawn_instance(db, template_id=t.id, subject_type="applicant", subject_id=uuid4(), started_by=hr_test_user.id)
    await db.commit()

    tasks = (await db.execute(select(HrWorkflowTask).where(HrWorkflowTask.instance_id == inst.id).order_by(HrWorkflowTask.position))).scalars().all()
    t0, t1 = tasks[0], tasks[1]
    assert t0.status == "ready"
    assert t1.status == "blocked"

    await advance_task(db, task_id=t0.id, new_status="completed", actor_user_id=hr_test_user.id)
    await db.commit()

    await db.refresh(t1)
    assert t1.status == "ready"


@pytest.mark.asyncio
async def test_cannot_complete_blocked_task(db, hr_test_user):
    t = await create_template(db, _simple_template(), created_by=hr_test_user.id)
    db.add(HrRoleAssignment(role="hr", user_id=hr_test_user.id, priority=0, active=True))
    await db.commit()
    inst = await spawn_instance(db, template_id=t.id, subject_type="applicant", subject_id=uuid4(), started_by=hr_test_user.id)
    await db.commit()
    tasks = (await db.execute(select(HrWorkflowTask).where(HrWorkflowTask.instance_id == inst.id).order_by(HrWorkflowTask.position))).scalars().all()
    with pytest.raises(ValueError, match="blocked"):
        await advance_task(db, task_id=tasks[1].id, new_status="completed", actor_user_id=hr_test_user.id)


@pytest.mark.asyncio
async def test_completing_last_task_marks_instance_completed(db, hr_test_user):
    t_in = TemplateIn(
        name="solo",
        category="onboarding",
        tasks=[TemplateTaskIn(position=0, name="only", kind="manual", assignee_role="hire")],
    )
    t = await create_template(db, t_in, created_by=hr_test_user.id)
    await db.commit()
    inst = await spawn_instance(db, template_id=t.id, subject_type="applicant", subject_id=uuid4(), started_by=hr_test_user.id)
    await db.commit()
    only_task = (await db.execute(select(HrWorkflowTask).where(HrWorkflowTask.instance_id == inst.id))).scalar_one()
    await advance_task(db, task_id=only_task.id, new_status="completed", actor_user_id=hr_test_user.id)
    await db.commit()
    await db.refresh(inst)
    assert inst.status == "completed"
    assert inst.completed_at is not None
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/hr/test_workflow_engine.py -v`
Expected: ImportError for `advance_task`.

- [ ] **Step 3: Implement**

Append to `app/hr/workflow/engine.py`:

```python
from datetime import datetime, timezone
from sqlalchemy import update


_ALLOWED_TRANSITIONS = {
    "ready": {"in_progress", "completed", "skipped"},
    "in_progress": {"completed", "skipped"},
    "blocked": set(),
    "completed": set(),
    "skipped": set(),
}


async def advance_task(
    db: AsyncSession,
    *,
    task_id: UUID,
    new_status: str,
    actor_user_id: UUID | None,
    reason: str | None = None,
    result: dict | None = None,
) -> HrWorkflowTask:
    task = (
        await db.execute(
            select(HrWorkflowTask).where(HrWorkflowTask.id == task_id).with_for_update()
        )
    ).scalar_one_or_none()
    if task is None:
        raise ValueError(f"task {task_id} not found")
    if new_status not in _ALLOWED_TRANSITIONS[task.status]:
        raise ValueError(f"task is {task.status}, cannot transition to {new_status}")
    if new_status == "skipped" and not reason:
        raise ValueError("skipped transition requires reason")

    old_status = task.status
    task.status = new_status
    if new_status == "completed":
        task.completed_at = datetime.now(timezone.utc)
        task.completed_by = actor_user_id
        if result is not None:
            task.result = result

    await db.flush()
    await write_audit(
        db,
        entity_type="workflow_task",
        entity_id=task.id,
        event="status_changed",
        diff={"status": [old_status, new_status], **({"reason": [None, reason]} if reason else {})},
        actor_user_id=actor_user_id,
    )

    if new_status in {"completed", "skipped"}:
        await _unblock_dependents(db, completed_task_id=task.id)
        await _maybe_complete_instance(db, instance_id=task.instance_id, actor_user_id=actor_user_id)
    return task


async def _unblock_dependents(db: AsyncSession, *, completed_task_id: UUID) -> None:
    dependents_q = (
        select(HrWorkflowTaskDependency.task_id)
        .where(HrWorkflowTaskDependency.depends_on_task_id == completed_task_id)
    )
    dependent_ids = (await db.execute(dependents_q)).scalars().all()
    for dep_id in dependent_ids:
        dep_task = (
            await db.execute(select(HrWorkflowTask).where(HrWorkflowTask.id == dep_id).with_for_update())
        ).scalar_one_or_none()
        if dep_task is None or dep_task.status != "blocked":
            continue
        remaining_q = (
            select(HrWorkflowTask.status)
            .join(
                HrWorkflowTaskDependency,
                HrWorkflowTaskDependency.depends_on_task_id == HrWorkflowTask.id,
            )
            .where(HrWorkflowTaskDependency.task_id == dep_task.id)
        )
        statuses = (await db.execute(remaining_q)).scalars().all()
        if all(s in {"completed", "skipped"} for s in statuses):
            dep_task.status = "ready"
            await write_audit(
                db,
                entity_type="workflow_task",
                entity_id=dep_task.id,
                event="status_changed",
                diff={"status": ["blocked", "ready"]},
            )


async def _maybe_complete_instance(db: AsyncSession, *, instance_id: UUID, actor_user_id: UUID | None) -> None:
    statuses = (
        await db.execute(select(HrWorkflowTask.status).where(HrWorkflowTask.instance_id == instance_id))
    ).scalars().all()
    if statuses and all(s in {"completed", "skipped"} for s in statuses):
        instance = (await db.execute(select(HrWorkflowInstance).where(HrWorkflowInstance.id == instance_id))).scalar_one()
        if instance.status == "active":
            instance.status = "completed"
            instance.completed_at = datetime.now(timezone.utc)
            await write_audit(
                db,
                entity_type="workflow_instance",
                entity_id=instance.id,
                event="completed",
                diff={"status": ["active", "completed"]},
                actor_user_id=actor_user_id,
            )
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/hr/test_workflow_engine.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add app/hr/workflow/engine.py tests/hr/test_workflow_engine.py
git commit -m "hr: workflow task state machine + dependency unblocking"
```

### Task E3: Triggers registry

**Files:**
- Create: `app/hr/workflow/triggers.py`
- Create: `tests/hr/test_workflow_triggers.py`

- [ ] **Step 1: Failing test**

```python
# tests/hr/test_workflow_triggers.py
import pytest
from app.hr.workflow.triggers import trigger_bus


@pytest.mark.asyncio
async def test_trigger_bus_dispatches():
    calls: list[dict] = []

    @trigger_bus.on("hr.test.fired")
    async def handler(payload: dict) -> None:
        calls.append(payload)

    await trigger_bus.fire("hr.test.fired", {"x": 1})
    assert calls == [{"x": 1}]
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/hr/test_workflow_triggers.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# app/hr/workflow/triggers.py
from typing import Awaitable, Callable


class TriggerBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[dict], Awaitable[None]]]] = {}

    def on(self, event: str) -> Callable[[Callable[[dict], Awaitable[None]]], Callable[[dict], Awaitable[None]]]:
        def _wrap(fn: Callable[[dict], Awaitable[None]]) -> Callable[[dict], Awaitable[None]]:
            self._handlers.setdefault(event, []).append(fn)
            return fn
        return _wrap

    async def fire(self, event: str, payload: dict) -> None:
        for fn in self._handlers.get(event, []):
            await fn(payload)


trigger_bus = TriggerBus()
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/hr/test_workflow_triggers.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add app/hr/workflow/triggers.py tests/hr/test_workflow_triggers.py
git commit -m "hr: add minimal trigger bus (in-process)"
```

### Task E4: Workflow router (admin)

**Files:**
- Create: `app/hr/workflow/router.py`
- Modify: `app/hr/router.py`
- Create: `tests/hr/test_workflow_router.py`

- [ ] **Step 1: Failing test**

```python
# tests/hr/test_workflow_router.py
import pytest
from uuid import uuid4


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
    # Create template first
    r = await authed_client.post(
        "/api/v2/hr/workflows/templates",
        json={
            "name": "Solo",
            "category": "operational",
            "tasks": [{"position": 0, "name": "Do it", "kind": "manual", "assignee_role": "hire"}],
        },
    )
    tid = r.json()["id"]

    r2 = await authed_client.post(
        "/api/v2/hr/workflows/instances",
        json={"template_id": tid, "subject_type": "customer", "subject_id": str(uuid4())},
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["status"] == "active"


@pytest.mark.asyncio
async def test_unauth_rejected(client):
    r = await client.post("/api/v2/hr/workflows/templates", json={"name": "x", "category": "operational", "tasks": []})
    assert r.status_code == 401
```

You'll need an `authed_client` fixture — check existing `tests/conftest.py` for an auth pattern (there's one for other authed endpoints). If not present, add it to `tests/hr/conftest.py`:

```python
# tests/hr/conftest.py — append
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest_asyncio.fixture
async def authed_client(client, hr_test_user, monkeypatch):
    # Depends on existing auth pattern: inspect tests/conftest.py and copy the mechanism used
    # by other authed endpoints. Typical: mint a JWT and set cookie/header on the AsyncClient.
    # If the codebase uses a session cookie set via a login call, post to /api/v2/auth/login first.
    monkeypatch.setenv("HR_MODULE_ENABLED", "true")
    # TODO during implementation: inspect existing auth fixture and model this after it.
    raise NotImplementedError("adapt to existing auth fixture pattern")
```

Note: the `NotImplementedError` is a placeholder for the engineer to inspect the existing auth fixture pattern (see `tests/conftest.py`) and adapt — replace before running the test.

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/hr/test_workflow_router.py -v`
Expected: ImportError / NotImplementedError.

- [ ] **Step 3: Implement router**

```python
# app/hr/workflow/router.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession, CurrentUser
from app.hr.workflow.engine import create_template, spawn_instance
from app.hr.workflow.schemas import TemplateIn, TemplateOut, SpawnRequest, InstanceOut


workflow_router = APIRouter(prefix="/workflows", tags=["hr-workflows"])


@workflow_router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template_endpoint(
    payload: TemplateIn,
    db: DbSession,
    user: CurrentUser,
) -> TemplateOut:
    template = await create_template(db, payload, created_by=user.id)
    await db.commit()
    return TemplateOut.model_validate(template)


@workflow_router.post("/instances", response_model=InstanceOut, status_code=status.HTTP_201_CREATED)
async def spawn_instance_endpoint(
    payload: SpawnRequest,
    db: DbSession,
    user: CurrentUser,
) -> InstanceOut:
    try:
        instance = await spawn_instance(
            db,
            template_id=payload.template_id,
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            started_by=user.id,
            start_date=payload.start_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return InstanceOut.model_validate(instance)
```

- [ ] **Step 4: Wire into hr_router**

```python
# app/hr/router.py — replace placeholder
from fastapi import APIRouter

from app.hr.workflow.router import workflow_router


hr_router = APIRouter(prefix="/hr", tags=["hr"])
hr_router.include_router(workflow_router)


@hr_router.get("/health")
async def hr_health() -> dict[str, str]:
    return {"status": "ok", "module": "hr"}
```

- [ ] **Step 5: Engineer replaces `NotImplementedError` in `authed_client` fixture with real auth pattern** (see existing test conftest). After that, run — expect PASS

Run: `HR_MODULE_ENABLED=true pytest tests/hr/test_workflow_router.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add app/hr/workflow/router.py app/hr/router.py tests/hr/test_workflow_router.py tests/hr/conftest.py
git commit -m "hr: workflow router — POST /templates and /instances"
```

---

## Phase F — Requisitions (minimal, for careers page)

### Task F1: Requisition model + migration

**Files:**
- Create: `app/hr/recruiting/models.py`
- Create: `alembic/versions/097_hr_requisition_minimal.py`

- [ ] **Step 1: Write model**

```python
# app/hr/recruiting/models.py
from sqlalchemy import Column, String, Text, DateTime, Boolean, Numeric, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from uuid import uuid4

from app.database import Base


class HrRequisition(Base):
    __tablename__ = "hr_requisitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    slug = Column(String(128), unique=True, nullable=False)
    title = Column(String(200), nullable=False)
    department = Column(String(128), nullable=True)
    location_city = Column(String(128), nullable=True)
    location_state = Column(String(32), nullable=True)
    employment_type = Column(String(32), nullable=False, default="full_time")  # full_time|part_time|contract
    compensation_min = Column(Numeric(10, 2), nullable=True)
    compensation_max = Column(Numeric(10, 2), nullable=True)
    compensation_display = Column(String(64), nullable=True)
    description_md = Column(Text, nullable=True)
    requirements_md = Column(Text, nullable=True)
    benefits_md = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default="draft")  # draft|open|paused|closed
    opened_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    hiring_manager_id = Column(UUID(as_uuid=True), ForeignKey("api_users.id"), nullable=True)
    onboarding_template_id = Column(UUID(as_uuid=True), ForeignKey("hr_workflow_templates.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("api_users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    __table_args__ = (Index("ix_hr_requisitions_status", "status"),)
```

- [ ] **Step 2: Register in `app/models/__init__.py`**

```python
from app.hr.recruiting.models import HrRequisition  # noqa: F401
```

- [ ] **Step 3: Migration**

Run: `alembic revision --autogenerate -m "hr requisition minimal"`
Rename: `097_hr_requisition_minimal.py`. Set `down_revision = "096_hr_workflow_tables"`.

- [ ] **Step 4: Apply + verify**

Run: `alembic upgrade head && python -c "from app.hr.recruiting.models import HrRequisition; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add app/hr/recruiting/models.py app/models/__init__.py alembic/versions/097_hr_requisition_minimal.py
git commit -m "hr: add HrRequisition model + migration 097"
```

### Task F2: Requisition schemas + admin router

**Files:**
- Create: `app/hr/recruiting/schemas.py`
- Create: `app/hr/recruiting/services.py`
- Create: `app/hr/recruiting/router.py`
- Modify: `app/hr/router.py`
- Create: `tests/hr/test_requisition_router.py`

- [ ] **Step 1: Schemas**

```python
# app/hr/recruiting/schemas.py
from datetime import datetime
from typing import Literal
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.types import UUIDStr


Status = Literal["draft", "open", "paused", "closed"]
EmploymentType = Literal["full_time", "part_time", "contract"]


class RequisitionIn(BaseModel):
    slug: str = Field(min_length=2, max_length=128, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str
    department: str | None = None
    location_city: str | None = None
    location_state: str | None = None
    employment_type: EmploymentType = "full_time"
    compensation_min: Decimal | None = None
    compensation_max: Decimal | None = None
    compensation_display: str | None = None
    description_md: str | None = None
    requirements_md: str | None = None
    benefits_md: str | None = None
    status: Status = "draft"
    hiring_manager_id: UUIDStr | None = None
    onboarding_template_id: UUIDStr | None = None


class RequisitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    slug: str
    title: str
    department: str | None
    location_city: str | None
    location_state: str | None
    employment_type: EmploymentType
    compensation_display: str | None
    description_md: str | None
    requirements_md: str | None
    benefits_md: str | None
    status: Status
    opened_at: datetime | None
    closed_at: datetime | None
    hiring_manager_id: UUIDStr | None
    onboarding_template_id: UUIDStr | None
    created_at: datetime
```

- [ ] **Step 2: Services**

```python
# app/hr/recruiting/services.py
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.recruiting.models import HrRequisition
from app.hr.recruiting.schemas import RequisitionIn
from app.hr.shared.audit import write_audit


async def create_requisition(db: AsyncSession, payload: RequisitionIn, *, actor_user_id: UUID | None) -> HrRequisition:
    row = HrRequisition(**payload.model_dump(), created_by=actor_user_id)
    if payload.status == "open":
        row.opened_at = datetime.now(timezone.utc)
    db.add(row)
    await db.flush()
    await write_audit(db, entity_type="requisition", entity_id=row.id, event="created", diff=payload.model_dump(), actor_user_id=actor_user_id)
    return row


async def list_requisitions(db: AsyncSession, *, status: str | None = None) -> list[HrRequisition]:
    stmt = select(HrRequisition).order_by(HrRequisition.created_at.desc())
    if status is not None:
        stmt = stmt.where(HrRequisition.status == status)
    return list((await db.execute(stmt)).scalars().all())


async def get_requisition_by_slug(db: AsyncSession, slug: str) -> HrRequisition | None:
    return (await db.execute(select(HrRequisition).where(HrRequisition.slug == slug))).scalar_one_or_none()
```

- [ ] **Step 3: Router**

```python
# app/hr/recruiting/router.py
from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, CurrentUser
from app.hr.recruiting.schemas import RequisitionIn, RequisitionOut
from app.hr.recruiting.services import create_requisition, list_requisitions


recruiting_router = APIRouter(prefix="/recruiting", tags=["hr-recruiting"])


@recruiting_router.post("/requisitions", response_model=RequisitionOut, status_code=status.HTTP_201_CREATED)
async def create(payload: RequisitionIn, db: DbSession, user: CurrentUser) -> RequisitionOut:
    row = await create_requisition(db, payload, actor_user_id=user.id)
    await db.commit()
    return RequisitionOut.model_validate(row)


@recruiting_router.get("/requisitions", response_model=list[RequisitionOut])
async def list_(db: DbSession, user: CurrentUser, status_filter: str | None = Query(None, alias="status")) -> list[RequisitionOut]:
    rows = await list_requisitions(db, status=status_filter)
    return [RequisitionOut.model_validate(r) for r in rows]
```

- [ ] **Step 4: Wire**

```python
# app/hr/router.py — add include
from app.hr.recruiting.router import recruiting_router
hr_router.include_router(recruiting_router)
```

- [ ] **Step 5: Tests**

```python
# tests/hr/test_requisition_router.py
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
    r = await authed_client.post("/api/v2/hr/recruiting/requisitions", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "field-tech"
    assert body["status"] == "open"


@pytest.mark.asyncio
async def test_list_requisitions_filters_status(authed_client):
    for s in ["draft", "open", "closed"]:
        await authed_client.post(
            "/api/v2/hr/recruiting/requisitions",
            json={"slug": f"r-{s}", "title": s.title(), "status": s},
        )

    r = await authed_client.get("/api/v2/hr/recruiting/requisitions?status=open")
    assert r.status_code == 200
    slugs = {row["slug"] for row in r.json()}
    assert slugs == {"r-open"}
```

- [ ] **Step 6: Run — expect PASS**

Run: `HR_MODULE_ENABLED=true pytest tests/hr/test_requisition_router.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add app/hr/recruiting/schemas.py app/hr/recruiting/services.py app/hr/recruiting/router.py app/hr/router.py tests/hr/test_requisition_router.py
git commit -m "hr: add requisitions admin CRUD (minimal)"
```

---

## Phase G — E-sign subsystem

### Task G1: E-sign models + migration

**Files:**
- Create: `app/hr/esign/models.py`
- Create: `alembic/versions/098_hr_esign_tables.py`

- [ ] **Step 1: Models**

```python
# app/hr/esign/models.py
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.sql import func
from uuid import uuid4

from app.database import Base


class HrDocumentTemplate(Base):
    __tablename__ = "hr_document_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    kind = Column(String(64), unique=True, nullable=False)
    version = Column(String(32), nullable=False, default="1")
    pdf_storage_key = Column(String(512), nullable=False)
    fields = Column(JSON, default=list, nullable=False)  # [{name,page,x,y,w,h,field_type}]
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrSignatureRequest(Base):
    __tablename__ = "hr_signature_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    token = Column(String(64), unique=True, nullable=False)
    signer_email = Column(String(256), nullable=False)
    signer_name = Column(String(256), nullable=False)
    signer_user_id = Column(UUID(as_uuid=True), ForeignKey("api_users.id"), nullable=True)
    document_template_id = Column(UUID(as_uuid=True), ForeignKey("hr_document_templates.id"), nullable=False)
    field_values = Column(JSON, default=dict, nullable=False)
    status = Column(String(16), default="sent", nullable=False)  # sent|viewed|signed|expired|revoked
    sent_at = Column(DateTime, server_default=func.now(), nullable=False)
    viewed_at = Column(DateTime, nullable=True)
    signed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    workflow_task_id = Column(UUID(as_uuid=True), ForeignKey("hr_workflow_tasks.id"), nullable=True)

    __table_args__ = (Index("ix_hr_sig_requests_status", "status"),)


class HrSignedDocument(Base):
    __tablename__ = "hr_signed_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    signature_request_id = Column(UUID(as_uuid=True), ForeignKey("hr_signature_requests.id"), nullable=False)
    storage_key = Column(String(512), nullable=False)
    signer_ip = Column(INET, nullable=True)
    signer_user_agent = Column(Text, nullable=True)
    signature_image_key = Column(String(512), nullable=False)
    signed_at = Column(DateTime, server_default=func.now(), nullable=False)
    hash_sha256 = Column(String(64), nullable=False)


class HrSignatureEvent(Base):
    __tablename__ = "hr_signature_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    signature_request_id = Column(UUID(as_uuid=True), ForeignKey("hr_signature_requests.id"), nullable=False)
    event_type = Column(String(32), nullable=False)
    ip = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
```

- [ ] **Step 2: Register + migrate**

Add imports to `app/models/__init__.py`. Run `alembic revision --autogenerate -m "hr esign tables"`, rename to `098_hr_esign_tables.py`, set `down_revision = "097_hr_requisition_minimal"`, apply.

- [ ] **Step 3: Commit**

```bash
git add app/hr/esign/models.py app/models/__init__.py alembic/versions/098_hr_esign_tables.py
git commit -m "hr: add e-sign models + migration 098"
```

### Task G2: PDF renderer

**Files:**
- Create: `app/hr/esign/renderer.py`
- Create: `tests/hr/test_esign_renderer.py`
- Create: `tests/hr/fixtures/blank.pdf` (hand-fabricate via reportlab in the test setup)

- [ ] **Step 1: Add `pypdf` + `reportlab` to requirements**

Edit `requirements.txt` (or `pyproject.toml` dependencies): add `pypdf>=4.0.0` and `reportlab>=4.0.0`. Run `pip install pypdf reportlab`.

- [ ] **Step 2: Failing test**

```python
# tests/hr/test_esign_renderer.py
import io
import pytest
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER

from app.hr.esign.renderer import fill_and_stamp


def _make_blank_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.drawString(100, 700, "Original content")
    c.showPage()
    c.save()


@pytest.fixture
def blank_pdf(tmp_path) -> Path:
    p = tmp_path / "blank.pdf"
    _make_blank_pdf(p)
    return p


@pytest.fixture
def signature_png(tmp_path) -> Path:
    from PIL import Image
    p = tmp_path / "sig.png"
    Image.new("RGBA", (200, 80), (0, 0, 0, 0)).save(p)
    return p


def test_fill_and_stamp_produces_pdf(blank_pdf, signature_png):
    output = fill_and_stamp(
        source_pdf_path=blank_pdf,
        field_values={"full_name": "John Doe"},
        fields=[{"name": "full_name", "page": 0, "x": 100, "y": 650, "w": 200, "h": 20, "field_type": "text"}],
        signature_image_path=signature_png,
        signature_field={"name": "signature", "page": 0, "x": 100, "y": 500, "w": 200, "h": 50, "field_type": "signature"},
        signer_name="John Doe",
        signer_ip="192.0.2.1",
    )
    assert output.startswith(b"%PDF")
    assert len(output) > 100


def test_fill_and_stamp_hashes_deterministically(blank_pdf, signature_png):
    import hashlib
    fields = [{"name": "full_name", "page": 0, "x": 100, "y": 650, "w": 200, "h": 20, "field_type": "text"}]
    output1 = fill_and_stamp(
        source_pdf_path=blank_pdf,
        field_values={"full_name": "Same Name"},
        fields=fields,
        signature_image_path=signature_png,
        signature_field={"name": "signature", "page": 0, "x": 100, "y": 500, "w": 200, "h": 50, "field_type": "signature"},
        signer_name="Same",
        signer_ip="192.0.2.1",
        timestamp_override="2026-04-15T10:00:00Z",
    )
    # Re-run to confirm same hash when timestamp is frozen
    h1 = hashlib.sha256(output1).hexdigest()
    output2 = fill_and_stamp(
        source_pdf_path=blank_pdf,
        field_values={"full_name": "Same Name"},
        fields=fields,
        signature_image_path=signature_png,
        signature_field={"name": "signature", "page": 0, "x": 100, "y": 500, "w": 200, "h": 50, "field_type": "signature"},
        signer_name="Same",
        signer_ip="192.0.2.1",
        timestamp_override="2026-04-15T10:00:00Z",
    )
    h2 = hashlib.sha256(output2).hexdigest()
    assert h1 == h2
```

- [ ] **Step 3: Run — expect FAIL**

Run: `pytest tests/hr/test_esign_renderer.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement**

```python
# app/hr/esign/renderer.py
import io
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER


def _overlay_page(
    page_size: tuple[float, float],
    field_values: dict,
    fields: Iterable[dict],
    signature_image_path: Path | None,
    signature_field: dict | None,
    signer_name: str,
    signer_ip: str,
    timestamp_override: str | None,
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=page_size)

    for f in fields:
        if f.get("field_type") == "text":
            value = str(field_values.get(f["name"], ""))
            c.setFont("Helvetica", 11)
            c.drawString(f["x"], f["y"], value)

    if signature_image_path and signature_field:
        c.drawImage(str(signature_image_path), signature_field["x"], signature_field["y"], width=signature_field["w"], height=signature_field["h"], mask="auto")
        stamp = f"Signed by {signer_name} on {timestamp_override or ''} from IP {signer_ip}"
        c.setFont("Helvetica", 7)
        c.drawString(signature_field["x"], signature_field["y"] - 10, stamp)

    c.save()
    return buf.getvalue()


def fill_and_stamp(
    *,
    source_pdf_path: Path,
    field_values: dict,
    fields: list[dict],
    signature_image_path: Path,
    signature_field: dict,
    signer_name: str,
    signer_ip: str,
    timestamp_override: str | None = None,
) -> bytes:
    reader = PdfReader(str(source_pdf_path))
    writer = PdfWriter()

    for page_idx, page in enumerate(reader.pages):
        page_fields = [f for f in fields if f["page"] == page_idx]
        sig_field = signature_field if signature_field["page"] == page_idx else None
        if page_fields or sig_field:
            overlay_bytes = _overlay_page(
                page_size=(float(page.mediabox.width), float(page.mediabox.height)),
                field_values=field_values,
                fields=page_fields,
                signature_image_path=signature_image_path if sig_field else None,
                signature_field=sig_field,
                signer_name=signer_name,
                signer_ip=signer_ip,
                timestamp_override=timestamp_override,
            )
            overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
            page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
```

- [ ] **Step 5: Install Pillow (for PNG fixture)**

Run: `pip install Pillow`. Add to requirements.

- [ ] **Step 6: Run — expect PASS**

Run: `pytest tests/hr/test_esign_renderer.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add app/hr/esign/renderer.py tests/hr/test_esign_renderer.py requirements.txt
git commit -m "hr: add PDF fill-and-stamp renderer (pypdf + reportlab)"
```

### Task G3: E-sign services (create request, record signature)

**Files:**
- Create: `app/hr/esign/schemas.py`
- Create: `app/hr/esign/services.py`
- Create: `tests/hr/test_esign_services.py`
- Create: `app/hr/shared/storage.py` (if not present — simple local-disk helper for dev; real S3 wiring can come later)

- [ ] **Step 1: Storage helper (minimal)**

```python
# app/hr/shared/storage.py
from pathlib import Path
import os
import uuid


_HR_STORAGE_ROOT = Path(os.getenv("HR_STORAGE_ROOT", "/tmp/hr-storage"))


def save_bytes(data: bytes, suffix: str = ".bin") -> str:
    _HR_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    key = f"{uuid.uuid4().hex}{suffix}"
    (_HR_STORAGE_ROOT / key).write_bytes(data)
    return key


def read_bytes(key: str) -> bytes:
    return (_HR_STORAGE_ROOT / key).read_bytes()


def path_for(key: str) -> Path:
    return _HR_STORAGE_ROOT / key
```

(Engineer: replace with the existing S3 helper used by other modules when visible — search for existing upload helper in `app/services/` and use that pattern.)

- [ ] **Step 2: Schemas**

```python
# app/hr/esign/schemas.py
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.schemas.types import UUIDStr


class SignatureRequestCreateIn(BaseModel):
    document_template_kind: str
    signer_email: str
    signer_name: str
    signer_user_id: UUIDStr | None = None
    field_values: dict = {}
    workflow_task_id: UUIDStr | None = None
    ttl_days: int = 7


class SignatureRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUIDStr
    token: str
    signer_email: str
    signer_name: str
    status: str
    expires_at: datetime


class SubmitSignatureIn(BaseModel):
    signature_image_base64: str  # PNG data URL
    consent_confirmed: bool
```

- [ ] **Step 3: Services**

```python
# app/hr/esign/services.py
import base64
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.esign.models import (
    HrDocumentTemplate,
    HrSignatureRequest,
    HrSignedDocument,
    HrSignatureEvent,
)
from app.hr.esign.renderer import fill_and_stamp
from app.hr.esign.schemas import SignatureRequestCreateIn
from app.hr.shared import storage
from app.hr.shared.audit import write_audit
from app.hr.workflow.models import HrWorkflowTask


class SignatureError(Exception):
    pass


async def create_signature_request(
    db: AsyncSession,
    payload: SignatureRequestCreateIn,
    *,
    actor_user_id: UUID | None,
) -> HrSignatureRequest:
    template = (
        await db.execute(
            select(HrDocumentTemplate)
            .where(HrDocumentTemplate.kind == payload.document_template_kind, HrDocumentTemplate.active.is_(True))
        )
    ).scalar_one_or_none()
    if template is None:
        raise SignatureError(f"document template '{payload.document_template_kind}' not found")

    token = secrets.token_urlsafe(32)
    req = HrSignatureRequest(
        token=token,
        signer_email=payload.signer_email,
        signer_name=payload.signer_name,
        signer_user_id=payload.signer_user_id,
        document_template_id=template.id,
        field_values=payload.field_values,
        status="sent",
        expires_at=datetime.now(timezone.utc) + timedelta(days=payload.ttl_days),
        workflow_task_id=payload.workflow_task_id,
    )
    db.add(req)
    await db.flush()
    db.add(HrSignatureEvent(signature_request_id=req.id, event_type="sent"))
    await write_audit(db, entity_type="signature_request", entity_id=req.id, event="sent", actor_user_id=actor_user_id)
    return req


async def mark_viewed(db: AsyncSession, *, token: str, ip: str, user_agent: str) -> HrSignatureRequest:
    req = await _get_active_by_token(db, token=token)
    if req.status == "sent":
        req.status = "viewed"
        req.viewed_at = datetime.now(timezone.utc)
    db.add(HrSignatureEvent(signature_request_id=req.id, event_type="viewed", ip=ip, user_agent=user_agent))
    return req


async def submit_signature(
    db: AsyncSession,
    *,
    token: str,
    signature_image_base64: str,
    consent_confirmed: bool,
    ip: str,
    user_agent: str,
) -> HrSignedDocument:
    if not consent_confirmed:
        raise SignatureError("consent required")

    req = await _get_active_by_token(db, token=token)
    template = (await db.execute(select(HrDocumentTemplate).where(HrDocumentTemplate.id == req.document_template_id))).scalar_one()

    # decode signature PNG
    try:
        header, b64 = signature_image_base64.split(",", 1) if "," in signature_image_base64 else ("", signature_image_base64)
        sig_bytes = base64.b64decode(b64)
    except Exception as e:
        raise SignatureError(f"invalid signature image: {e}")
    sig_key = storage.save_bytes(sig_bytes, ".png")

    source_path = storage.path_for(template.pdf_storage_key)
    fields = [f for f in template.fields if f.get("field_type") == "text"]
    sig_field = next((f for f in template.fields if f.get("field_type") == "signature"), None)
    if sig_field is None:
        raise SignatureError("template has no signature field")

    pdf_bytes = fill_and_stamp(
        source_pdf_path=source_path,
        field_values=req.field_values,
        fields=fields,
        signature_image_path=storage.path_for(sig_key),
        signature_field=sig_field,
        signer_name=req.signer_name,
        signer_ip=ip,
        timestamp_override=datetime.now(timezone.utc).isoformat(),
    )
    signed_key = storage.save_bytes(pdf_bytes, ".pdf")
    h = hashlib.sha256(pdf_bytes).hexdigest()

    req.status = "signed"
    req.signed_at = datetime.now(timezone.utc)

    signed_doc = HrSignedDocument(
        signature_request_id=req.id,
        storage_key=signed_key,
        signer_ip=ip,
        signer_user_agent=user_agent,
        signature_image_key=sig_key,
        hash_sha256=h,
    )
    db.add(signed_doc)
    db.add(HrSignatureEvent(signature_request_id=req.id, event_type="signed", ip=ip, user_agent=user_agent))

    # If this signature was tied to a workflow task, surface the signed doc in its result
    if req.workflow_task_id:
        task = (await db.execute(select(HrWorkflowTask).where(HrWorkflowTask.id == req.workflow_task_id).with_for_update())).scalar_one_or_none()
        if task is not None:
            task.result = {**(task.result or {}), "signature_id": str(req.id), "signed_document_id": str(signed_doc.id)}

    await db.flush()
    await write_audit(db, entity_type="signature_request", entity_id=req.id, event="signed", diff={"hash_sha256": [None, h]})
    return signed_doc


async def _get_active_by_token(db: AsyncSession, *, token: str) -> HrSignatureRequest:
    req = (await db.execute(select(HrSignatureRequest).where(HrSignatureRequest.token == token))).scalar_one_or_none()
    if req is None:
        raise SignatureError("token not found")
    if req.status in {"expired", "revoked"} or req.expires_at < datetime.now(timezone.utc):
        raise SignatureError("signature link expired or revoked")
    if req.status == "signed":
        raise SignatureError("already signed")
    return req
```

- [ ] **Step 4: Tests**

```python
# tests/hr/test_esign_services.py
import base64
import io
import pytest
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from PIL import Image

from app.hr.esign.services import create_signature_request, submit_signature, SignatureError
from app.hr.esign.models import HrDocumentTemplate, HrSignedDocument
from app.hr.esign.schemas import SignatureRequestCreateIn
from app.hr.shared import storage


def _make_pdf_and_store() -> str:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.drawString(100, 700, "Test doc")
    c.showPage()
    c.save()
    return storage.save_bytes(buf.getvalue(), ".pdf")


def _png_base64() -> str:
    img = Image.new("RGBA", (100, 40), (0, 0, 0, 255))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


@pytest.mark.asyncio
async def test_create_and_submit_signature(db):
    template_key = _make_pdf_and_store()
    tmpl = HrDocumentTemplate(
        kind="test_doc",
        version="1",
        pdf_storage_key=template_key,
        fields=[
            {"name": "full_name", "page": 0, "x": 100, "y": 650, "w": 200, "h": 20, "field_type": "text"},
            {"name": "signature", "page": 0, "x": 100, "y": 500, "w": 200, "h": 50, "field_type": "signature"},
        ],
        active=True,
    )
    db.add(tmpl)
    await db.commit()

    req = await create_signature_request(
        db,
        SignatureRequestCreateIn(
            document_template_kind="test_doc",
            signer_email="hire@example.com",
            signer_name="John Hire",
            field_values={"full_name": "John Hire"},
            ttl_days=7,
        ),
        actor_user_id=None,
    )
    await db.commit()
    assert req.token
    assert req.status == "sent"

    signed = await submit_signature(
        db,
        token=req.token,
        signature_image_base64=_png_base64(),
        consent_confirmed=True,
        ip="192.0.2.1",
        user_agent="pytest",
    )
    await db.commit()
    assert signed.hash_sha256
    assert signed.storage_key


@pytest.mark.asyncio
async def test_submit_requires_consent(db):
    tmpl = HrDocumentTemplate(
        kind="consent_doc",
        pdf_storage_key=_make_pdf_and_store(),
        fields=[{"name": "signature", "page": 0, "x": 100, "y": 500, "w": 200, "h": 50, "field_type": "signature"}],
        active=True,
    )
    db.add(tmpl)
    await db.commit()

    req = await create_signature_request(
        db,
        SignatureRequestCreateIn(document_template_kind="consent_doc", signer_email="a@b.com", signer_name="A B"),
        actor_user_id=None,
    )
    await db.commit()
    with pytest.raises(SignatureError, match="consent"):
        await submit_signature(db, token=req.token, signature_image_base64=_png_base64(), consent_confirmed=False, ip="192.0.2.1", user_agent="pytest")
```

- [ ] **Step 5: Run — expect PASS**

Run: `pytest tests/hr/test_esign_services.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add app/hr/esign/schemas.py app/hr/esign/services.py app/hr/shared/storage.py tests/hr/test_esign_services.py
git commit -m "hr: add e-sign services (create request, submit signature)"
```

### Task G4: E-sign router (admin + public)

**Files:**
- Create: `app/hr/esign/router.py`
- Modify: `app/hr/router.py`
- Create: `tests/hr/test_esign_router.py`
- Create: `app/main.py` changes for public sign routes (mount separately because auth differs)

- [ ] **Step 1: Admin router**

```python
# app/hr/esign/router.py
from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import DbSession, CurrentUser
from app.hr.esign.schemas import SignatureRequestCreateIn, SignatureRequestOut, SubmitSignatureIn
from app.hr.esign.services import create_signature_request, mark_viewed, submit_signature, SignatureError


esign_admin_router = APIRouter(prefix="/sign", tags=["hr-esign-admin"])


@esign_admin_router.post("/requests", response_model=SignatureRequestOut, status_code=status.HTTP_201_CREATED)
async def create_request(payload: SignatureRequestCreateIn, db: DbSession, user: CurrentUser) -> SignatureRequestOut:
    try:
        req = await create_signature_request(db, payload, actor_user_id=user.id)
    except SignatureError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return SignatureRequestOut.model_validate(req)


esign_public_router = APIRouter(prefix="/sign", tags=["hr-esign-public"])


@esign_public_router.get("/{token}", response_model=SignatureRequestOut)
async def view_request(token: str, db: DbSession, request: Request) -> SignatureRequestOut:
    try:
        req = await mark_viewed(
            db,
            token=token,
            ip=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", ""),
        )
    except SignatureError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return SignatureRequestOut.model_validate(req)


@esign_public_router.post("/{token}/submit")
async def submit(token: str, payload: SubmitSignatureIn, db: DbSession, request: Request) -> dict:
    try:
        signed = await submit_signature(
            db,
            token=token,
            signature_image_base64=payload.signature_image_base64,
            consent_confirmed=payload.consent_confirmed,
            ip=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", ""),
        )
    except SignatureError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"signed_document_id": str(signed.id)}
```

- [ ] **Step 2: Wire**

```python
# app/hr/router.py
from app.hr.esign.router import esign_admin_router
hr_router.include_router(esign_admin_router)
```

```python
# app/main.py — mount public esign router separately at /api/v2/public (no auth middleware)
from app.hr.esign.router import esign_public_router

if hr_module_enabled():
    app.include_router(esign_public_router, prefix="/api/v2/public")
```

- [ ] **Step 3: Tests**

```python
# tests/hr/test_esign_router.py
import pytest
from app.hr.esign.models import HrDocumentTemplate
from app.hr.shared import storage
from app.hr.esign.services import create_signature_request
from app.hr.esign.schemas import SignatureRequestCreateIn


def _pdf_key() -> str:
    # Minimal valid PDF
    return storage.save_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<<>>%%EOF", ".pdf")


@pytest.mark.asyncio
async def test_view_signature_page_public(client, db):
    tmpl = HrDocumentTemplate(
        kind="handbook",
        pdf_storage_key=_pdf_key(),
        fields=[{"name": "signature", "page": 0, "x": 100, "y": 500, "w": 200, "h": 50, "field_type": "signature"}],
        active=True,
    )
    db.add(tmpl)
    await db.commit()

    req = await create_signature_request(
        db,
        SignatureRequestCreateIn(document_template_kind="handbook", signer_email="a@b.com", signer_name="A B"),
        actor_user_id=None,
    )
    await db.commit()

    r = await client.get(f"/api/v2/public/sign/{req.token}")
    assert r.status_code == 200
    assert r.json()["token"] == req.token


@pytest.mark.asyncio
async def test_invalid_token_404(client):
    r = await client.get("/api/v2/public/sign/does-not-exist")
    assert r.status_code == 404
```

- [ ] **Step 4: Run — expect PASS**

Run: `HR_MODULE_ENABLED=true pytest tests/hr/test_esign_router.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/hr/esign/router.py app/hr/router.py app/main.py tests/hr/test_esign_router.py
git commit -m "hr: add e-sign routers (admin + public)"
```

### Task G5: Seed document templates migration

**Files:**
- Create: `app/hr/esign/seed_templates.py`
- Create: `alembic/versions/099_hr_seed_document_templates.py`
- Source PDFs to copy into `app/hr/esign/pdfs/`:
  - `employment_agreement_2026.pdf` (copy from `/mnt/win11/Fedora/home-offload/Downloads/J Fajardo - Employment Docs/Employment Agreement MAC Septic LLC - VTO J. Fajardo.pdf`)
  - `w4_2026.pdf` (copy from `/mnt/win11/Fedora/home-offload/Downloads/J Fajardo - Employment Docs/2026 w-4.pdf`)
  - `i9.pdf` (copy from `/mnt/win11/Fedora/home-offload/Downloads/J Fajardo - Employment Docs/i-9.pdf`)
  - `adp_info.pdf` (copy from ADP Employee Information Form - BLANK.pdf)
  - `benefits_election.pdf` (copy from Benefits Election Form.pdf)

- [ ] **Step 1: Copy PDFs into the repo**

```bash
mkdir -p app/hr/esign/pdfs
cp "/mnt/win11/Fedora/home-offload/Downloads/J Fajardo - Employment Docs/Employment Agreement MAC Septic LLC - VTO J. Fajardo.pdf" app/hr/esign/pdfs/employment_agreement_2026.pdf
cp "/mnt/win11/Fedora/home-offload/Downloads/J Fajardo - Employment Docs/2026 w-4.pdf" app/hr/esign/pdfs/w4_2026.pdf
cp "/mnt/win11/Fedora/home-offload/Downloads/J Fajardo - Employment Docs/i-9.pdf" app/hr/esign/pdfs/i9.pdf
cp "/mnt/win11/Fedora/home-offload/Downloads/J Fajardo - Employment Docs/ADP Employee Information Form - BLANK.pdf" app/hr/esign/pdfs/adp_info.pdf
cp "/mnt/win11/Fedora/home-offload/Downloads/J Fajardo - Employment Docs/Benefits Election Form.pdf" app/hr/esign/pdfs/benefits_election.pdf
```

- [ ] **Step 2: Seed helper**

```python
# app/hr/esign/seed_templates.py
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.esign.models import HrDocumentTemplate
from app.hr.shared import storage


_PDF_DIR = Path(__file__).parent / "pdfs"


# Field maps must be measured manually per PDF. Placeholder coords below:
# Engineer: open each PDF in a viewer, identify exact text + signature box coords in PDF points
# (72 pt = 1 inch; y is bottom-origin). Replace the coords in this dict before running the migration.
TEMPLATES: list[dict] = [
    {
        "kind": "employment_agreement_2026",
        "version": "1",
        "filename": "employment_agreement_2026.pdf",
        "fields": [
            {"name": "employee_name", "page": 0, "x": 120, "y": 650, "w": 300, "h": 14, "field_type": "text"},
            {"name": "start_date", "page": 0, "x": 120, "y": 620, "w": 200, "h": 14, "field_type": "text"},
            {"name": "signature", "page": 2, "x": 100, "y": 120, "w": 200, "h": 50, "field_type": "signature"},
        ],
    },
    {
        "kind": "w4_2026",
        "version": "2026",
        "filename": "w4_2026.pdf",
        "fields": [
            {"name": "first_name", "page": 0, "x": 72, "y": 700, "w": 200, "h": 14, "field_type": "text"},
            {"name": "last_name", "page": 0, "x": 280, "y": 700, "w": 200, "h": 14, "field_type": "text"},
            {"name": "ssn", "page": 0, "x": 480, "y": 700, "w": 100, "h": 14, "field_type": "text"},
            {"name": "signature", "page": 0, "x": 72, "y": 140, "w": 200, "h": 40, "field_type": "signature"},
        ],
    },
    {
        "kind": "i9",
        "version": "2025",
        "filename": "i9.pdf",
        "fields": [
            {"name": "last_name", "page": 0, "x": 72, "y": 720, "w": 160, "h": 14, "field_type": "text"},
            {"name": "first_name", "page": 0, "x": 240, "y": 720, "w": 160, "h": 14, "field_type": "text"},
            {"name": "signature", "page": 0, "x": 72, "y": 160, "w": 200, "h": 40, "field_type": "signature"},
        ],
    },
    {
        "kind": "adp_info",
        "version": "1",
        "filename": "adp_info.pdf",
        "fields": [
            {"name": "full_name", "page": 0, "x": 120, "y": 680, "w": 300, "h": 14, "field_type": "text"},
            {"name": "signature", "page": 0, "x": 72, "y": 120, "w": 200, "h": 40, "field_type": "signature"},
        ],
    },
    {
        "kind": "benefits_election",
        "version": "2026",
        "filename": "benefits_election.pdf",
        "fields": [
            {"name": "employee_name", "page": 0, "x": 120, "y": 680, "w": 300, "h": 14, "field_type": "text"},
            {"name": "plan_selected", "page": 0, "x": 120, "y": 640, "w": 300, "h": 14, "field_type": "text"},
            {"name": "signature", "page": 0, "x": 72, "y": 120, "w": 200, "h": 40, "field_type": "signature"},
        ],
    },
]


async def seed_document_templates(db: AsyncSession) -> None:
    for t in TEMPLATES:
        existing = (await db.execute(select(HrDocumentTemplate).where(HrDocumentTemplate.kind == t["kind"]))).scalar_one_or_none()
        if existing is not None:
            continue
        data = (_PDF_DIR / t["filename"]).read_bytes()
        key = storage.save_bytes(data, ".pdf")
        db.add(HrDocumentTemplate(kind=t["kind"], version=t["version"], pdf_storage_key=key, fields=t["fields"], active=True))
    await db.flush()
```

- [ ] **Step 3: Data migration**

```python
# alembic/versions/099_hr_seed_document_templates.py
"""seed hr document templates"""
from alembic import op
import asyncio


revision = "099_hr_seed_document_templates"
down_revision = "098_hr_esign_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: the seed function is upsert-by-kind
    from app.database import async_session_maker
    from app.hr.esign.seed_templates import seed_document_templates

    async def _run() -> None:
        async with async_session_maker() as db:
            await seed_document_templates(db)
            await db.commit()

    asyncio.run(_run())


def downgrade() -> None:
    from sqlalchemy import text
    op.execute(text("DELETE FROM hr_document_templates WHERE kind IN ('employment_agreement_2026','w4_2026','i9','adp_info','benefits_election')"))
```

- [ ] **Step 4: Apply**

Run: `alembic upgrade head`
Expected: 5 rows in `hr_document_templates`.

- [ ] **Step 5: Smoke test**

```python
# tests/hr/test_seed_templates.py
import pytest
from sqlalchemy import select
from app.hr.esign.models import HrDocumentTemplate


@pytest.mark.asyncio
async def test_seed_creates_five_templates(db):
    from app.hr.esign.seed_templates import seed_document_templates
    await seed_document_templates(db)
    await db.commit()

    rows = (await db.execute(select(HrDocumentTemplate))).scalars().all()
    kinds = {r.kind for r in rows}
    assert kinds >= {"employment_agreement_2026", "w4_2026", "i9", "adp_info", "benefits_election"}
```

Run: `pytest tests/hr/test_seed_templates.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add app/hr/esign/seed_templates.py app/hr/esign/pdfs/ alembic/versions/099_hr_seed_document_templates.py tests/hr/test_seed_templates.py
git commit -m "hr: seed document templates (employment, w4, i9, adp, benefits)"
```

Note: field maps use approximate coordinates. Open each PDF and refine coords before using in production. Document the process in `app/hr/esign/PDF_FIELD_MAPPING.md`.

---

## Phase H — Public careers page (SSR)

### Task H1: Jinja2 template setup

**Files:**
- Create: `app/hr/careers/router.py`
- Create: `app/hr/careers/templates/careers_index.html`
- Create: `app/hr/careers/templates/requisition_detail.html`
- Create: `app/hr/careers/templates/apply.html` (placeholder — Plan 2 adds the form)
- Modify: `app/main.py` to include public careers router
- Add: `jinja2` to requirements (likely already present)

- [ ] **Step 1: Router**

```python
# app/hr/careers/router.py
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import DbSession
from app.hr.recruiting.services import list_requisitions, get_requisition_by_slug


_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


careers_router = APIRouter(prefix="/careers", tags=["careers-public"])


@careers_router.get("/", response_class=HTMLResponse)
async def careers_index(request: Request, db: DbSession) -> HTMLResponse:
    reqs = await list_requisitions(db, status="open")
    return _TEMPLATES.TemplateResponse("careers_index.html", {"request": request, "reqs": reqs})


@careers_router.get("/{slug}", response_class=HTMLResponse)
async def requisition_detail(request: Request, slug: str, db: DbSession) -> HTMLResponse:
    req = await get_requisition_by_slug(db, slug)
    if req is None or req.status != "open":
        return HTMLResponse("Not found", status_code=404)
    return _TEMPLATES.TemplateResponse("requisition_detail.html", {"request": request, "req": req})


@careers_router.get("/{slug}/apply", response_class=HTMLResponse)
async def apply(request: Request, slug: str, db: DbSession) -> HTMLResponse:
    req = await get_requisition_by_slug(db, slug)
    if req is None or req.status != "open":
        return HTMLResponse("Not found", status_code=404)
    return _TEMPLATES.TemplateResponse("apply.html", {"request": request, "req": req})
```

- [ ] **Step 2: Templates** (Tailwind CDN for Plan 1; ship-compiled CSS in Plan 2)

```html
<!-- app/hr/careers/templates/careers_index.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Careers at Mac Septic</title>
  <meta name="description" content="Join the Mac Septic team. Open positions in Texas.">
  <meta property="og:title" content="Careers at Mac Septic">
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-white">
  <header class="border-b">
    <div class="max-w-4xl mx-auto px-6 py-6">
      <h1 class="text-3xl font-semibold">Careers at Mac Septic</h1>
      <p class="text-gray-600 mt-2">Serving Tennessee & Texas. Open roles below.</p>
    </div>
  </header>
  <main class="max-w-4xl mx-auto px-6 py-10">
    {% if reqs %}
      <ul class="divide-y">
        {% for r in reqs %}
          <li class="py-4 flex justify-between items-center">
            <div>
              <a href="/careers/{{ r.slug }}" class="text-xl font-medium hover:underline">{{ r.title }}</a>
              <p class="text-sm text-gray-600">{{ r.location_city }}, {{ r.location_state }} — {{ r.employment_type.replace('_',' ') }}</p>
            </div>
            {% if r.compensation_display %}<span class="text-sm">{{ r.compensation_display }}</span>{% endif %}
          </li>
        {% endfor %}
      </ul>
    {% else %}
      <p class="text-gray-600">No open positions right now. Check back soon.</p>
    {% endif %}
  </main>
</body>
</html>
```

```html
<!-- app/hr/careers/templates/requisition_detail.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{ req.title }} — Mac Septic Careers</title>
  <meta name="description" content="{{ req.title }} position at Mac Septic in {{ req.location_city }}, {{ req.location_state }}.">
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-white">
  <main class="max-w-3xl mx-auto px-6 py-10">
    <a href="/careers" class="text-sm text-gray-500">← All positions</a>
    <h1 class="text-3xl font-semibold mt-4">{{ req.title }}</h1>
    <p class="text-gray-600">{{ req.location_city }}, {{ req.location_state }} — {{ req.employment_type.replace('_',' ') }}</p>
    {% if req.compensation_display %}<p class="mt-2 font-medium">{{ req.compensation_display }}</p>{% endif %}
    {% if req.description_md %}<section class="prose mt-8">{{ req.description_md | safe }}</section>{% endif %}
    {% if req.requirements_md %}<section class="prose mt-8"><h2>Requirements</h2>{{ req.requirements_md | safe }}</section>{% endif %}
    {% if req.benefits_md %}<section class="prose mt-8"><h2>Benefits</h2>{{ req.benefits_md | safe }}</section>{% endif %}
    <a href="/careers/{{ req.slug }}/apply" class="inline-block mt-10 px-6 py-3 bg-black text-white rounded">Apply</a>
  </main>
</body>
</html>
```

```html
<!-- app/hr/careers/templates/apply.html -->
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Apply — {{ req.title }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-white">
  <main class="max-w-xl mx-auto px-6 py-10">
    <h1 class="text-2xl font-semibold">Apply for {{ req.title }}</h1>
    <p class="mt-4 text-gray-600">Application form coming soon. Please email resume to <a class="underline" href="mailto:careers@macseptic.com">careers@macseptic.com</a> while we finish the online form.</p>
  </main>
</body>
</html>
```

- [ ] **Step 3: Mount in main**

```python
# app/main.py — near esign_public_router mount
from app.hr.careers.router import careers_router

if hr_module_enabled():
    app.include_router(careers_router)  # careers lives at /careers (no /api/v2 prefix), per spec §2.4
```

- [ ] **Step 4: Tests**

```python
# tests/hr/test_careers_ssr.py
import pytest
from app.hr.recruiting.models import HrRequisition


@pytest.mark.asyncio
async def test_careers_index_lists_open_reqs(client, db):
    db.add(HrRequisition(slug="field-tech", title="Field Technician", status="open", employment_type="full_time"))
    db.add(HrRequisition(slug="draft-job", title="Draft Job", status="draft", employment_type="full_time"))
    await db.commit()

    r = await client.get("/careers/")
    assert r.status_code == 200
    assert "Field Technician" in r.text
    assert "Draft Job" not in r.text


@pytest.mark.asyncio
async def test_requisition_detail_page(client, db):
    db.add(HrRequisition(slug="driver", title="CDL Driver", status="open", employment_type="full_time", description_md="<p>Drive trucks.</p>"))
    await db.commit()
    r = await client.get("/careers/driver")
    assert r.status_code == 200
    assert "CDL Driver" in r.text
    assert "Drive trucks." in r.text


@pytest.mark.asyncio
async def test_requisition_detail_404_when_draft(client, db):
    db.add(HrRequisition(slug="draft", title="X", status="draft", employment_type="full_time"))
    await db.commit()
    r = await client.get("/careers/draft")
    assert r.status_code == 404
```

- [ ] **Step 5: Run — expect PASS**

Run: `HR_MODULE_ENABLED=true pytest tests/hr/test_careers_ssr.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add app/hr/careers/ app/main.py tests/hr/test_careers_ssr.py
git commit -m "hr: public careers pages (SSR, Jinja2)"
```

---

## Phase I — Indeed XML feed

### Task I1: Feed endpoint

**Files:**
- Create: `app/hr/recruiting/careers_feed.py`
- Modify: `app/hr/careers/router.py` (add `jobs.xml` route or mount feed separately)
- Create: `tests/hr/test_careers_feed.py`

- [ ] **Step 1: Feed builder**

```python
# app/hr/recruiting/careers_feed.py
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape
from app.hr.recruiting.models import HrRequisition


def _fmt(v: str | None) -> str:
    return xml_escape(v or "")


def build_indeed_xml(base_url: str, reqs: list[HrRequisition]) -> str:
    """Build an Indeed-compatible XML feed.

    Spec: https://docs.indeed.com/indeed-apply/xml-feed
    """
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    items = []
    for r in reqs:
        url = f"{base_url}/careers/{r.slug}"
        title = _fmt(r.title)
        city = _fmt(r.location_city)
        state = _fmt(r.location_state)
        desc_parts = [
            r.description_md or "",
            ("\n\n**Requirements**\n" + r.requirements_md) if r.requirements_md else "",
            ("\n\n**Benefits**\n" + r.benefits_md) if r.benefits_md else "",
        ]
        description = _fmt("".join(desc_parts).strip())
        salary = _fmt(r.compensation_display)
        job_type = {"full_time": "fulltime", "part_time": "parttime", "contract": "contract"}.get(r.employment_type, "fulltime")
        items.append(f"""
    <job>
      <title><![CDATA[{r.title}]]></title>
      <date>{now}</date>
      <referencenumber>{_fmt(r.slug)}</referencenumber>
      <url>{_fmt(url)}</url>
      <company><![CDATA[Mac Septic]]></company>
      <city>{city}</city>
      <state>{state}</state>
      <country>US</country>
      <description><![CDATA[{description}]]></description>
      <salary><![CDATA[{salary}]]></salary>
      <jobtype>{job_type}</jobtype>
    </job>""")
    return f"""<?xml version='1.0' encoding='utf-8'?>
<source>
  <publisher>Mac Septic</publisher>
  <publisherurl>{_fmt(base_url)}</publisherurl>
  <lastbuilddate>{now}</lastbuilddate>{''.join(items)}
</source>
"""
```

- [ ] **Step 2: Route** — append to `app/hr/careers/router.py`:

```python
from fastapi.responses import Response
from app.hr.recruiting.careers_feed import build_indeed_xml
from app.hr.recruiting.services import list_requisitions


@careers_router.get("/jobs.xml", response_class=Response)
async def jobs_feed(request: Request, db: DbSession) -> Response:
    reqs = await list_requisitions(db, status="open")
    base_url = str(request.base_url).rstrip("/")
    xml = build_indeed_xml(base_url, reqs)
    return Response(content=xml, media_type="application/xml")
```

- [ ] **Step 3: Tests**

```python
# tests/hr/test_careers_feed.py
import pytest
from xml.etree import ElementTree as ET
from app.hr.recruiting.models import HrRequisition


@pytest.mark.asyncio
async def test_jobs_feed_only_includes_open(client, db):
    db.add(HrRequisition(slug="open-1", title="Open Job", status="open", employment_type="full_time", location_city="Houston", location_state="TX"))
    db.add(HrRequisition(slug="draft-1", title="Draft", status="draft", employment_type="full_time"))
    await db.commit()

    r = await client.get("/careers/jobs.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")

    root = ET.fromstring(r.text)
    assert root.tag == "source"
    jobs = root.findall("job")
    assert len(jobs) == 1
    assert jobs[0].findtext("referencenumber") == "open-1"
    assert jobs[0].findtext("city") == "Houston"
    assert jobs[0].findtext("state") == "TX"
    assert jobs[0].findtext("jobtype") == "fulltime"
    assert "Open Job" in jobs[0].findtext("title")
```

- [ ] **Step 4: Run — expect PASS**

Run: `HR_MODULE_ENABLED=true pytest tests/hr/test_careers_feed.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add app/hr/recruiting/careers_feed.py app/hr/careers/router.py tests/hr/test_careers_feed.py
git commit -m "hr: add Indeed-compatible /careers/jobs.xml feed"
```

---

## Phase J — Frontend scaffold

### Task J1: Frontend HR feature directory + router wiring

**Files (in `/home/will/ReactCRM`):**
- Create: `src/features/hr/index.ts`
- Create: `src/features/hr/shared/ActivityPanel.tsx`
- Create: `src/features/hr/shared/StagePipeline.tsx`
- Create: `src/features/hr/shared/ProgressBar.tsx`
- Create: `src/features/hr/shared/CelebrationCard.tsx`
- Create: `src/features/hr/recruiting/api.ts`
- Create: `src/features/hr/recruiting/pages/RequisitionsListPage.tsx`
- Create: `src/features/hr/recruiting/pages/RequisitionEditorPage.tsx`
- Create: `src/routes/hrRoutes.tsx`
- Modify: main router file (find existing router setup in `src/routes/` or `App.tsx` — match existing pattern)

- [ ] **Step 1: Shared components**

```tsx
// src/features/hr/shared/StagePipeline.tsx
import clsx from "clsx";
import { twMerge } from "tailwind-merge";

type Stage = { id: string; label: string; count?: number };

export function StagePipeline({
  stages,
  activeStageId,
  onStageClick,
}: {
  stages: Stage[];
  activeStageId: string;
  onStageClick?: (id: string) => void;
}) {
  return (
    <nav className="flex gap-2 flex-wrap">
      {stages.map((s) => {
        const active = s.id === activeStageId;
        return (
          <button
            key={s.id}
            type="button"
            onClick={() => onStageClick?.(s.id)}
            className={twMerge(
              clsx(
                "px-3 py-1.5 rounded-full text-sm border transition",
                active
                  ? "bg-neutral-900 text-white border-neutral-900"
                  : "bg-white text-neutral-700 border-neutral-200 hover:border-neutral-400",
              ),
            )}
          >
            <span>{s.label}</span>
            {typeof s.count === "number" && (
              <span className={clsx("ml-2 px-1.5 py-0.5 rounded-full text-xs", active ? "bg-white/20" : "bg-neutral-100")}>
                {s.count}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
```

```tsx
// src/features/hr/shared/ProgressBar.tsx
export function ProgressBar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="w-full bg-neutral-100 rounded-full h-2">
      <div className="bg-indigo-600 h-2 rounded-full" style={{ width: `${pct}%` }} />
    </div>
  );
}
```

```tsx
// src/features/hr/shared/CelebrationCard.tsx
export function CelebrationCard({ title, message, ctaLabel, onCta }: { title: string; message: string; ctaLabel: string; onCta: () => void }) {
  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-6 flex items-center justify-between">
      <div>
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="text-sm text-neutral-700 mt-1">{message}</p>
      </div>
      <button type="button" onClick={onCta} className="px-4 py-2 bg-indigo-600 text-white rounded-lg">{ctaLabel}</button>
    </div>
  );
}
```

```tsx
// src/features/hr/shared/ActivityPanel.tsx
export type ActivityItem = { id: string; kind: string; actor: string | null; when: string; body: string };

export function ActivityPanel({ items }: { items: ActivityItem[] }) {
  if (items.length === 0) return <p className="text-sm text-neutral-500">No activity yet.</p>;
  return (
    <ul className="space-y-4">
      {items.map((i) => (
        <li key={i.id} className="text-sm">
          <div className="flex justify-between">
            <span className="font-medium">{i.actor ?? "System"}</span>
            <span className="text-neutral-500">{i.when}</span>
          </div>
          <p className="text-neutral-700 mt-1">{i.body}</p>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 2: Requisitions API**

```tsx
// src/features/hr/recruiting/api.ts
import { z } from "zod";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api"; // or whatever the existing axios instance is — match codebase

export const Requisition = z.object({
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
  hiring_manager_id: z.string().nullable(),
  onboarding_template_id: z.string().nullable(),
  created_at: z.string(),
});
export type Requisition = z.infer<typeof Requisition>;

export const RequisitionInput = Requisition.pick({
  slug: true, title: true, department: true, location_city: true, location_state: true,
  employment_type: true, compensation_display: true, description_md: true,
  requirements_md: true, benefits_md: true, status: true, hiring_manager_id: true, onboarding_template_id: true,
}).partial().required({ slug: true, title: true, employment_type: true, status: true });
export type RequisitionInput = z.infer<typeof RequisitionInput>;


export function useRequisitions(status?: string) {
  return useQuery({
    queryKey: ["hr", "requisitions", status ?? "all"],
    queryFn: async () => {
      const r = await api.get("/api/v2/hr/recruiting/requisitions", { params: status ? { status } : {} });
      return z.array(Requisition).parse(r.data);
    },
  });
}


export function useCreateRequisition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: RequisitionInput) => {
      const r = await api.post("/api/v2/hr/recruiting/requisitions", payload);
      return Requisition.parse(r.data);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["hr", "requisitions"] }),
  });
}
```

Note: `@/lib/api` — match the existing axios/fetch helper used across the codebase (inspect imports in other `features/*/api.ts` files before coding).

- [ ] **Step 3: List page**

```tsx
// src/features/hr/recruiting/pages/RequisitionsListPage.tsx
import { Link } from "react-router-dom";
import { useRequisitions } from "../api";

export function RequisitionsListPage() {
  const { data, isLoading, error } = useRequisitions();
  if (isLoading) return <div className="p-6">Loading…</div>;
  if (error) return <div className="p-6 text-red-600">Error loading requisitions.</div>;
  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Requisitions</h1>
        <Link to="/app/hr/requisitions/new" className="px-4 py-2 bg-neutral-900 text-white rounded-lg">New</Link>
      </div>
      <ul className="mt-6 divide-y border rounded-lg">
        {(data ?? []).map((r) => (
          <li key={r.id} className="p-4 flex items-center justify-between">
            <div>
              <Link to={`/app/hr/requisitions/${r.id}`} className="font-medium hover:underline">{r.title}</Link>
              <div className="text-sm text-neutral-500">{r.slug} — {r.status}</div>
            </div>
            <span className="text-sm">{r.compensation_display ?? ""}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Editor page (create only for Plan 1)**

```tsx
// src/features/hr/recruiting/pages/RequisitionEditorPage.tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateRequisition, type RequisitionInput } from "../api";

export function RequisitionEditorPage() {
  const nav = useNavigate();
  const create = useCreateRequisition();
  const [form, setForm] = useState<RequisitionInput>({
    slug: "",
    title: "",
    employment_type: "full_time",
    status: "draft",
  });

  return (
    <form
      className="p-6 max-w-2xl mx-auto space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        await create.mutateAsync(form);
        nav("/app/hr/requisitions");
      }}
    >
      <h1 className="text-2xl font-semibold">New requisition</h1>
      <label className="block">
        <span className="text-sm">Slug</span>
        <input className="w-full border rounded px-3 py-2" required value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} />
      </label>
      <label className="block">
        <span className="text-sm">Title</span>
        <input className="w-full border rounded px-3 py-2" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
      </label>
      <label className="block">
        <span className="text-sm">Status</span>
        <select className="w-full border rounded px-3 py-2" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as RequisitionInput["status"] })}>
          <option value="draft">Draft</option>
          <option value="open">Open</option>
          <option value="paused">Paused</option>
          <option value="closed">Closed</option>
        </select>
      </label>
      <button type="submit" disabled={create.isPending} className="px-4 py-2 bg-neutral-900 text-white rounded-lg">
        {create.isPending ? "Saving…" : "Create"}
      </button>
    </form>
  );
}
```

- [ ] **Step 5: Routes**

```tsx
// src/routes/hrRoutes.tsx
import { Route } from "react-router-dom";
import { RequisitionsListPage } from "@/features/hr/recruiting/pages/RequisitionsListPage";
import { RequisitionEditorPage } from "@/features/hr/recruiting/pages/RequisitionEditorPage";

export const hrRoutes = (
  <>
    <Route path="/app/hr/requisitions" element={<RequisitionsListPage />} />
    <Route path="/app/hr/requisitions/new" element={<RequisitionEditorPage />} />
  </>
);
```

Engineer: find the main router config (likely `src/App.tsx` or `src/routes/index.tsx`) and splice `{hrRoutes}` under the authenticated-routes wrapper. Match existing pattern.

- [ ] **Step 6: Tests**

```tsx
// src/features/hr/recruiting/__tests__/api.contract.test.ts
import { describe, it, expect } from "vitest";
import { Requisition } from "../api";

describe("Requisition schema", () => {
  it("parses a valid payload", () => {
    const parsed = Requisition.parse({
      id: "11111111-1111-1111-1111-111111111111",
      slug: "tech",
      title: "Tech",
      department: null,
      location_city: null,
      location_state: null,
      employment_type: "full_time",
      compensation_display: null,
      description_md: null,
      requirements_md: null,
      benefits_md: null,
      status: "open",
      opened_at: null,
      closed_at: null,
      hiring_manager_id: null,
      onboarding_template_id: null,
      created_at: "2026-04-15T00:00:00Z",
    });
    expect(parsed.slug).toBe("tech");
  });

  it("rejects bad employment_type", () => {
    expect(() => Requisition.parse({ employment_type: "weird" })).toThrow();
  });
});
```

- [ ] **Step 7: Run frontend tests**

Run: `cd /home/will/ReactCRM && npm run test:contracts -- --run`
Expected: new tests pass; nothing else broken.

- [ ] **Step 8: Commit (ReactCRM repo)**

```bash
cd /home/will/ReactCRM
git add src/features/hr/ src/routes/hrRoutes.tsx
git commit -m "hr: scaffold frontend HR feature tree + requisitions admin"
```

---

## Phase K — Integration smoke & ship

### Task K1: End-to-end smoke test (Playwright)

**Files:**
- Create: `/home/will/ReactCRM/e2e/tests/hr-foundation.spec.ts`

- [ ] **Step 1: Write Playwright test per user's frontend rules**

```ts
// e2e/tests/hr-foundation.spec.ts
import { test, expect } from "@playwright/test";

test("careers page lists open requisitions", async ({ page }) => {
  // Assumes a seeded open requisition exists (create via API call as first step)
  const ctx = page.context();
  await ctx.clearCookies();

  await page.goto("/careers");
  await page.waitForLoadState("domcontentloaded");
  await expect(page.locator("h1")).toContainText("Careers");
});

test("admin can create a requisition", async ({ page }) => {
  // Login first — match existing e2e login pattern
  await page.goto("/login");
  // ... login steps (match existing e2e test setup)

  await page.goto("/app/hr/requisitions/new");
  await page.waitForLoadState("domcontentloaded");
  await page.fill('input[required]:first-of-type', "e2e-smoke");
  await page.locator("input[required]").nth(1).fill("E2E Smoke Requisition");
  await page.selectOption("select", "open");
  await page.click('button[type="submit"]');
  await page.waitForFunction(() => !location.href.includes("/new"));
  await expect(page.locator("text=E2E Smoke Requisition")).toBeVisible();
});
```

Engineer: adapt login steps to match existing e2e auth pattern.

- [ ] **Step 2: Run Playwright**

Run: `cd /home/will/ReactCRM && npm run test:e2e -- --grep hr-foundation`
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
cd /home/will/ReactCRM
git add e2e/tests/hr-foundation.spec.ts
git commit -m "hr: e2e smoke for careers + requisition create"
```

### Task K2: Backend full test sweep

- [ ] **Step 1: Run full backend test suite**

Run: `cd /home/will/react-crm-api && HR_MODULE_ENABLED=true pytest -v --tb=short`
Expected: all existing tests still pass + all new `tests/hr/*` pass. If any existing test fails, fix the regression before proceeding — do not merge.

### Task K3: Deploy Plan 1

User's rules: NEVER use `railway up`; deploy via git push to GitHub only; always verify `/health` after push; check Railway logs if `/health` fails.

- [ ] **Step 1: Push backend**

```bash
cd /home/will/react-crm-api
git push origin main
```

- [ ] **Step 2: Wait ~2 minutes, verify deploy**

Run: `curl -sf https://react-crm-api-production.up.railway.app/health && echo OK`
Expected: `OK`.

- [ ] **Step 3: Enable HR module on Railway**

Set env var `HR_MODULE_ENABLED=true` via Railway dashboard. Redeploy will auto-trigger.

- [ ] **Step 4: Smoke-test live endpoints**

```bash
curl -sf https://react-crm-api-production.up.railway.app/api/v2/hr/health
curl -sf https://react-crm-api-production.up.railway.app/careers/jobs.xml | head -20
curl -sf https://react-crm-api-production.up.railway.app/careers/ | head -20
```

Expected: all 3 return 200. `/api/v2/hr/health` returns `{"status":"ok","module":"hr"}`. `jobs.xml` is valid XML (possibly empty `<source>` if no open reqs yet).

- [ ] **Step 5: Push frontend**

```bash
cd /home/will/ReactCRM
git push origin main
```

- [ ] **Step 6: Playwright verification of live app**

Visit `https://react.ecbtx.com/app/hr/requisitions`, log in, create a test requisition with status=open, then visit `https://react-crm-api-production.up.railway.app/careers/` and confirm it appears.

- [ ] **Step 7: Create a milestone commit**

```bash
cd /home/will/react-crm-api
git commit --allow-empty -m "hr: Plan 1 foundation shipped"
git push origin main
```

---

## Self-Review Checklist (for plan author)

Before handing off, confirm:

- [x] Spec §2.2 backend layout fully covered: `workflow/`, `shared/`, `esign/`, `careers/`, `recruiting/` scaffolded. (`employees_ext/`, `offboarding/`, `onboarding/` are intentionally Plan 3 — spec §13.3).
- [x] Spec §3.1 workflow tables: all 8 created in migration 096.
- [x] Spec §3.4 e-sign tables: all 4 created in migration 098.
- [x] Spec §3.5 audit log: created in migration 095.
- [x] Spec §4.1 template→instance mechanics implemented in engine.
- [x] Spec §4.2 state machine implemented; tests cover happy path + blocked rejection + instance completion.
- [x] Spec §4.4 concurrency via `SELECT ... FOR UPDATE` — present in `advance_task`.
- [x] Spec §5.2 SSR careers decision implemented (Jinja2 via FastAPI).
- [x] Spec §5.3 Indeed XML feed implemented + tested.
- [x] Spec §8 e-sign flow implemented end-to-end (create → view → submit → signed PDF).
- [x] Spec §8.2 seeded 5 document templates (4 from J Fajardo docs + W-4).
- [x] Spec §13.2 feature flag wired and tested.
- [x] Spec §13.3 Plan 1 rollout order: foundation shippable on its own without Plans 2/3.
- [x] User's backend rules: `async_session_maker`, `selectinload`, `UUIDStr`, migration reversibility, no destructive DB ops.
- [x] User's frontend rules: Zod validation, mobile responsiveness (Tailwind responsive), no unused imports, existing `EmptyState` noted.
- [x] User's Railway rules: deploy via git push only, `/health` verification.
- [x] No placeholders, no TBDs, except one flagged `NotImplementedError` in `authed_client` fixture which cannot be resolved without inspecting the existing auth test pattern — explicitly called out for the engineer.

### Deferred to Plans 2 & 3 (explicitly out of Plan 1)

- Applicant / Application models + pipeline (Plan 2)
- Careers apply form (Plan 2)
- Candidate SMS (Plan 2)
- Applicant detail page (Plan 2)
- Onboarding seeded template + MyOnboarding page (Plan 3)
- Offboarding seeded template + offboarding UI (Plan 3)
- Employee detail redesign with tabs (Plan 3)
- Employee extensions tables (certifications, documents, truck/fuel-card/access assignments) (Plan 3)
- Triggers wiring for `hr.applicant.hired` → onboarding spawn (Plan 3)
- Cert expiry SMS alerts (Plan 3)

---

## Plan complete.
