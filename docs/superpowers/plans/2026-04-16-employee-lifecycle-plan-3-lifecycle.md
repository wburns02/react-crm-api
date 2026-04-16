# Employee Lifecycle — Plan 3: Lifecycle

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the employee-lifecycle half of the HR module on top of Plans 1 + 2 — seeded "New Field Tech Onboarding" (23 tasks) and "Tech Separation" (14 tasks) templates, `hr.applicant.hired` → onboarding spawn trigger, employee extension tables (certifications, documents, truck/fuel-card/access assignments), public MyOnboarding self-service page where new hires complete their paperwork packet, admin employee + offboarding detail pages, and a scheduled cert-expiry SMS alerter.

**Architecture:** Reuses the Plan 1 workflow engine (templates → instances → tasks → e-sign integration). New tables are all prefixed `hr_`. The onboarding/offboarding seed is a single data migration (103) that inserts two `hr_workflow_templates` plus their `hr_workflow_template_tasks` + dependencies. Extension tables land as migration 103. The hire trigger handler is a module-level function registered at import time via `@trigger_bus.on("hr.applicant.hired")`. MyOnboarding is a tokened public view (similar to the esign token flow); admin pages are authed frontend routes.

**Tech Stack:** Same as Plan 1/2.

**Spec:** §3.3, §4.3, §6, §7, §10.3, §13.3.

**Prerequisite:** Plan 2 shipped (migrations through 102 applied, `HR_MODULE_ENABLED=true`, recruiting pipeline live).

---

## File Structure

Backend (new):

```
app/hr/employees/models.py              ← HrEmployeeCertification, HrEmployeeDocument,
                                          HrFuelCard, HrFuelCardAssignment, HrTruckAssignment,
                                          HrAccessGrant
app/hr/employees/schemas.py
app/hr/employees/services.py            ← cert CRUD, expiry queries
app/hr/employees/router.py              ← /hr/employees/{id}/*
app/hr/onboarding/seed.py               ← TEMPLATES_ONBOARDING + TEMPLATES_OFFBOARDING
app/hr/onboarding/triggers.py           ← on('hr.applicant.hired') spawn handler
app/hr/onboarding/public_token.py       ← opaque token model for MyOnboarding
app/hr/onboarding/public_router.py      ← /api/v2/public/onboarding/{token}/*
app/hr/onboarding/router.py             ← admin-side endpoints
app/hr/careers/templates/my_onboarding.html   ← public SSR (or SPA island)
app/hr/shared/cert_expiry_job.py        ← APScheduler-compatible function

alembic/versions/103_hr_employee_extensions.py
alembic/versions/104_hr_seed_lifecycle_templates.py

tests/hr/test_employee_extensions.py
tests/hr/test_hire_trigger.py
tests/hr/test_onboarding_template_seed.py
tests/hr/test_offboarding_template_seed.py
tests/hr/test_myonboarding_public.py
tests/hr/test_cert_expiry_job.py
```

Backend (modified):

```
app/main.py                             ← register hire trigger; include employees + onboarding routers
app/hr/router.py                        ← include employees_router + onboarding admin router
app/hr/careers/router.py                ← add /onboarding/{token} GET route for MyOnboarding SSR
app/models/__init__.py                  ← register new models
app/tasks/*.py                          ← register cert expiry APScheduler job
```

Frontend (new, `/home/will/ReactCRM`):

```
src/features/hr/employees/api.ts
src/features/hr/employees/pages/EmployeeDetailPage.tsx
src/features/hr/employees/components/EmployeeTabs.tsx
src/features/hr/onboarding/api.ts
src/features/hr/onboarding/pages/OnboardingDetailPage.tsx
src/features/hr/onboarding/pages/OffboardingDetailPage.tsx
src/features/hr/shared/WorkflowTimeline.tsx   ← renders any workflow instance
```

Frontend (modified):

```
src/features/hr/index.ts                ← re-export new pages
src/routes/app/hr.routes.tsx            ← add /hr/employees/:id, /hr/onboarding/:instanceId, /hr/offboarding/:instanceId
src/components/layout/navConfig.ts      ← Employees + Onboarding nav entries
```

Playwright:

```
e2e/modules/hr-lifecycle-flow.spec.ts   ← apply→hire→onboarding spawn→MyOnboarding, 2 unauth+3 authed
```

---

## Phase A — Employee extension tables

### Task A1: HrEmployeeCertification + HrEmployeeDocument + assignment models + migration 103

**Files:**
- Create: `app/hr/employees/__init__.py`
- Create: `app/hr/employees/models.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/103_hr_employee_extensions.py`

- [ ] **Step 1:** Write models (employee_id points to `technicians.id` since that's the canonical employee row per Plan 1 RECONCILIATION_NOTES §2):

```python
# app/hr/employees/models.py
from uuid import uuid4
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base


class HrEmployeeCertification(Base):
    __tablename__ = "hr_employee_certifications"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=False)
    kind = Column(String(32), nullable=False)  # tceq_os0|tceq_mp|cdl_class_b|dot_medical|first_aid|other
    number = Column(String(128), nullable=True)
    issued_at = Column(Date, nullable=True)
    expires_at = Column(Date, nullable=True)
    issuing_authority = Column(String(128), nullable=True)
    document_storage_key = Column(String(512), nullable=True)
    status = Column(String(16), nullable=False, default="active")  # active|expired|pending
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)
    __table_args__ = (
        Index("ix_hr_emp_cert_employee", "employee_id"),
        Index("ix_hr_emp_cert_expires", "expires_at"),
    )


class HrEmployeeDocument(Base):
    __tablename__ = "hr_employee_documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=False)
    kind = Column(String(32), nullable=False)  # i9|w4|handbook_ack|direct_deposit|drug_test|dot_med_card|cdl|license|other
    storage_key = Column(String(512), nullable=False)
    signed_document_id = Column(UUID(as_uuid=True), ForeignKey("hr_signed_documents.id"), nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    expires_at = Column(Date, nullable=True)
    __table_args__ = (Index("ix_hr_emp_doc_employee_kind", "employee_id", "kind"),)


class HrFuelCard(Base):
    __tablename__ = "hr_fuel_cards"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    card_number_masked = Column(String(32), nullable=False)  # e.g. "****1234"
    vendor = Column(String(64), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrFuelCardAssignment(Base):
    __tablename__ = "hr_fuel_card_assignments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=False)
    card_id = Column(UUID(as_uuid=True), ForeignKey("hr_fuel_cards.id"), nullable=False)
    assigned_at = Column(DateTime, server_default=func.now(), nullable=False)
    unassigned_at = Column(DateTime, nullable=True)
    assigned_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    unassigned_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    __table_args__ = (Index("ix_hr_fuel_assign_employee_open", "employee_id", "unassigned_at"),)


class HrTruckAssignment(Base):
    __tablename__ = "hr_truck_assignments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=False)
    # assets table already exists; asset_type filtered at application level per PLAN_CORRECTIONS.
    truck_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    assigned_at = Column(DateTime, server_default=func.now(), nullable=False)
    unassigned_at = Column(DateTime, nullable=True)
    assigned_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    unassigned_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    __table_args__ = (Index("ix_hr_truck_assign_employee_open", "employee_id", "unassigned_at"),)


class HrAccessGrant(Base):
    __tablename__ = "hr_access_grants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("technicians.id"), nullable=False)
    system = Column(String(32), nullable=False)  # crm|ringcentral|google_workspace|samsara|adp
    identifier = Column(String(256), nullable=True)
    granted_at = Column(DateTime, server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    granted_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    revoked_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    __table_args__ = (Index("ix_hr_access_employee_system", "employee_id", "system"),)
```

- [ ] **Step 2:** Register in `app/models/__init__.py`:

```python
from app.hr.employees.models import (  # noqa: F401
    HrEmployeeCertification,
    HrEmployeeDocument,
    HrFuelCard,
    HrFuelCardAssignment,
    HrTruckAssignment,
    HrAccessGrant,
)
```

- [ ] **Step 3:** Write migration 103 mirroring the models (see file structure above, same `CREATE TABLE` pattern as migration 101 — UUID PKs via `gen_random_uuid()`, integer FKs to `api_users.id`, UUID FKs to `technicians.id` and `assets.id`, indexes per model).

- [ ] **Step 4:** Verify on SQLite (`create_all`) and real Postgres 17 container (`alembic upgrade head`). Confirm downgrade drops cleanly and re-upgrade is idempotent.

- [ ] **Step 5:** Update `/health/db/migrate-hr` detection block to recognise `hr_employee_certifications` → stamp to 103.

- [ ] **Step 6:** Commit: `hr(plan3): add employee extension tables + migration 103`.

### Task A2: Employee extension schemas + services + admin router

**Files:**
- Create: `app/hr/employees/schemas.py`
- Create: `app/hr/employees/services.py`
- Create: `app/hr/employees/router.py`
- Modify: `app/hr/router.py`
- Create: `tests/hr/test_employee_extensions.py`

Scope:
- Pydantic IN/OUT for each model.
- Services: `create_certification`, `list_certifications_for_employee`, `list_expiring_certifications(days)`, `upload_document`, `list_documents_for_employee`, `assign_truck`, `close_truck_assignment`, `assign_fuel_card`, `close_fuel_card_assignment`, `grant_access`, `revoke_access`.
- Admin router: `GET /hr/employees/{tech_id}/certifications`, `POST /hr/employees/{tech_id}/certifications`, `PATCH /hr/employees/{tech_id}/certifications/{cert_id}`; analogous for documents, truck-assignments, fuel-card-assignments, access-grants.
- Every mutation writes audit via `write_audit`.
- All authed (use `CurrentUser`).

Tests (8-10):
- Create + list certs round-trip.
- Expiring query returns only within `days` window.
- Open truck assignment closed when calling `close_truck_assignment`.
- Access grant/revoke updates `revoked_at`.
- 401 for unauth; 404 for unknown tech id.

- [ ] Commit: `hr(plan3): employee extension CRUD (certs, docs, truck/fuel-card/access)`.

---

## Phase B — Seeded lifecycle workflow templates

### Task B1: Migration 104 — seed "New Field Tech Onboarding" + "Tech Separation"

**Files:**
- Create: `app/hr/onboarding/__init__.py`
- Create: `app/hr/onboarding/seed.py`
- Create: `alembic/versions/104_hr_seed_lifecycle_templates.py`
- Create: `tests/hr/test_onboarding_template_seed.py`
- Create: `tests/hr/test_offboarding_template_seed.py`

- [ ] **Step 1:** Write `seed.py` with two Python data structures (no DB imports, just dicts):

```python
# app/hr/onboarding/seed.py
"""Seed data for the two lifecycle workflow templates.

Each entry is a dict consumed by migration 104; same shape as the TemplateIn
schema so the engine can clone from it directly (v1.1 admin editor wraps the
same shape).
"""
from typing import TypedDict


class TemplateTaskSpec(TypedDict, total=False):
    position: int
    name: str
    kind: str
    assignee_role: str
    stage: str
    due_offset_days: int
    required: bool
    config: dict
    depends_on: list[int]  # list of positions


ONBOARDING_TEMPLATE = {
    "name": "New Field Tech Onboarding",
    "category": "onboarding",
    "tasks": [
        # Pre-Day 1
        {"position": 1, "stage": "pre_day_one", "name": "Sign Employment Agreement",
         "kind": "form_sign", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"document_template_kind": "employment_agreement_2026"}},
        {"position": 2, "stage": "pre_day_one", "name": "Sign I-9 Section 1",
         "kind": "form_sign", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"document_template_kind": "i9"}},
        {"position": 3, "stage": "pre_day_one", "name": "Sign W-4 2026",
         "kind": "form_sign", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"document_template_kind": "w4_2026"}},
        {"position": 4, "stage": "pre_day_one", "name": "Complete ADP Employee Information Form",
         "kind": "form_sign", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"document_template_kind": "adp_info"}},
        {"position": 5, "stage": "pre_day_one", "name": "Elect AFA health plan",
         "kind": "form_sign", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"document_template_kind": "benefits_election"}},
        {"position": 6, "stage": "pre_day_one", "name": "Submit direct deposit authorization",
         "kind": "form_sign", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"document_template_kind": "adp_info"}},
        {"position": 7, "stage": "pre_day_one", "name": "Upload copy of driver's license",
         "kind": "document_upload", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"doc_kind": "license"}},
        {"position": 8, "stage": "pre_day_one", "name": "Upload DOT medical card",
         "kind": "document_upload", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"doc_kind": "dot_med_card"}},
        {"position": 9, "stage": "pre_day_one", "name": "Upload CDL (if applicable)",
         "kind": "document_upload", "assignee_role": "hire", "due_offset_days": 0,
         "required": False, "config": {"doc_kind": "cdl"}},
        {"position": 10, "stage": "pre_day_one", "name": "Verify I-9 Section 2",
         "kind": "verify", "assignee_role": "hr", "due_offset_days": 0,
         "depends_on": [2, 7]},
        {"position": 11, "stage": "pre_day_one", "name": "Run background check",
         "kind": "manual", "assignee_role": "hr", "due_offset_days": 0},
        {"position": 12, "stage": "pre_day_one", "name": "Schedule drug test",
         "kind": "manual", "assignee_role": "hr", "due_offset_days": 0},
        # Day 1
        {"position": 13, "stage": "day_1", "name": "Uniform + PPE fitting",
         "kind": "manual", "assignee_role": "manager", "due_offset_days": 1},
        {"position": 14, "stage": "day_1", "name": "Create CRM account",
         "kind": "assignment", "assignee_role": "it", "due_offset_days": 1,
         "config": {"system": "crm"}},
        {"position": 15, "stage": "day_1", "name": "Issue company phone + Google Workspace account",
         "kind": "assignment", "assignee_role": "it", "due_offset_days": 1,
         "config": {"system": "google_workspace"}},
        {"position": 16, "stage": "day_1", "name": "Assign truck",
         "kind": "assignment", "assignee_role": "manager", "due_offset_days": 1,
         "depends_on": [7], "config": {"asset_type": "vehicle"}},
        {"position": 17, "stage": "day_1", "name": "Issue fuel card",
         "kind": "assignment", "assignee_role": "manager", "due_offset_days": 1,
         "config": {"asset_type": "fuel_card"}},
        {"position": 18, "stage": "day_1", "name": "Sign Employee Handbook Acknowledgement",
         "kind": "form_sign", "assignee_role": "hire", "due_offset_days": 1,
         "config": {"document_template_kind": "adp_info"}},
        {"position": 19, "stage": "day_1", "name": "Watch safety training videos",
         "kind": "training_video", "assignee_role": "hire", "due_offset_days": 1,
         "config": {"video_count": 4}},
        # Week 1
        {"position": 20, "stage": "week_1", "name": "3-day ride-along check-in",
         "kind": "verify", "assignee_role": "manager", "due_offset_days": 3},
        {"position": 21, "stage": "week_1", "name": "Complete TCEQ OS-0 study materials",
         "kind": "training_video", "assignee_role": "hire", "due_offset_days": 7},
        # Month 1
        {"position": 22, "stage": "month_1", "name": "30-day review",
         "kind": "manual", "assignee_role": "manager", "due_offset_days": 30},
        {"position": 23, "stage": "month_1", "name": "Confirm all certs logged",
         "kind": "verify", "assignee_role": "hr", "due_offset_days": 30,
         "depends_on": [8, 9]},
    ],
}


OFFBOARDING_TEMPLATE = {
    "name": "Tech Separation",
    "category": "offboarding",
    "tasks": [
        {"position": 1, "name": "Record separation reason + last day",
         "kind": "manual", "assignee_role": "hr", "due_offset_days": 0},
        {"position": 2, "name": "Exit interview",
         "kind": "form_sign", "assignee_role": "employee", "due_offset_days": 0},
        {"position": 3, "name": "Return company truck",
         "kind": "verify", "assignee_role": "manager", "due_offset_days": 0,
         "config": {"close": "hr_truck_assignments"}},
        {"position": 4, "name": "Return company phone",
         "kind": "verify", "assignee_role": "manager", "due_offset_days": 0},
        {"position": 5, "name": "Return uniforms + PPE",
         "kind": "verify", "assignee_role": "manager", "due_offset_days": 0},
        {"position": 6, "name": "Inventory audit of truck stock",
         "kind": "verify", "assignee_role": "manager", "due_offset_days": 0,
         "depends_on": [3]},
        {"position": 7, "name": "Kill fuel card",
         "kind": "assignment", "assignee_role": "it", "due_offset_days": 0,
         "config": {"close": "hr_fuel_card_assignments"}},
        {"position": 8, "name": "Revoke CRM access",
         "kind": "assignment", "assignee_role": "it", "due_offset_days": 0,
         "config": {"system": "crm", "close_grant": True}},
        {"position": 9, "name": "Revoke Google Workspace",
         "kind": "assignment", "assignee_role": "it", "due_offset_days": 0,
         "config": {"system": "google_workspace", "close_grant": True}},
        {"position": 10, "name": "Revoke RingCentral",
         "kind": "assignment", "assignee_role": "it", "due_offset_days": 0,
         "config": {"system": "ringcentral", "close_grant": True}},
        {"position": 11, "name": "Revoke Samsara",
         "kind": "assignment", "assignee_role": "it", "due_offset_days": 0,
         "config": {"system": "samsara", "close_grant": True}},
        {"position": 12, "name": "Final paycheck cut in ADP",
         "kind": "manual", "assignee_role": "hr", "due_offset_days": 1},
        {"position": 13, "name": "Send COBRA notification",
         "kind": "form_sign", "assignee_role": "hr", "due_offset_days": 1},
        {"position": 14, "name": "Terminate in ADP + mark inactive in CRM",
         "kind": "manual", "assignee_role": "hr", "due_offset_days": 2,
         "depends_on": [12]},
    ],
}
```

- [ ] **Step 2:** Write migration 104 (data migration) — insert both templates + their tasks + dependencies using `op.get_bind()` + raw `INSERT` (same pattern as migration 100). Idempotent (check template name first).

- [ ] **Step 3:** Tests — `seed_lifecycle_templates` helper inserts both and we assert (a) 23 tasks on onboarding with correct kinds, (b) 14 tasks on offboarding, (c) dependencies wired (task 10 depends on 2+7; task 6 depends on 3; etc.), (d) idempotent re-run.

- [ ] Commit: `hr(plan3): seed onboarding (23) + offboarding (14) workflow templates + migration 104`.

---

## Phase C — Hire trigger → spawn onboarding

### Task C1: Register `hr.applicant.hired` handler

**Files:**
- Create: `app/hr/onboarding/triggers.py`
- Modify: `app/main.py` (import the module so handlers register)
- Create: `tests/hr/test_hire_trigger.py`

Scope:
- `handle_applicant_hired(payload)`:
  1. Look up the onboarding template by name (`"New Field Tech Onboarding"`).
  2. Load the requisition's `onboarding_template_id` — if set, use that, otherwise fall back to the default.
  3. Resolve the hire's subject_id. Plan 2 applicants aren't yet `technicians` rows; for v1 we either (a) promote here (create a technician row copying applicant bio) or (b) pass `subject_type="applicant"` with the applicant id. Spec says "employee → technicians.id". Decision: create a technicians row on hire, return its id as subject_id.
  4. Call `spawn_instance(db, template_id=..., subject_type="employee", subject_id=technician_id, started_by=actor)`.
  5. Write audit.

- [ ] **Step 1:** Applicant → technician promotion helper (simple copy: first/last/email/phone → technician row with `is_active=True`).
- [ ] **Step 2:** Trigger handler + `trigger_bus.on("hr.applicant.hired")(handle_applicant_hired)`.
- [ ] **Step 3:** Import the module in `app/main.py` so the handler registers at process start. Gate behind `HR_MODULE_ENABLED`.
- [ ] **Step 4:** Test: seed templates, create applicant + application, transition to hired, assert technician row created + onboarding instance spawned with 23 tasks.
- [ ] Commit: `hr(plan3): wire hr.applicant.hired → promote applicant + spawn onboarding instance`.

---

## Phase D — MyOnboarding public self-service

### Task D1: Public onboarding token model + public router

**Files:**
- Create: `app/hr/onboarding/public_token.py` (HrOnboardingToken model: id, instance_id, token, expires_at)
- Modify: `alembic/versions/103_hr_employee_extensions.py` to ALSO create `hr_onboarding_tokens` table (or split into 103a; simpler to keep in 103).
- Create: `app/hr/onboarding/public_router.py` — `GET /api/v2/public/onboarding/{token}` returns instance state; `POST /api/v2/public/onboarding/{token}/tasks/{task_id}/advance` lets the hire move their own `form_sign`/`document_upload`/`training_video` tasks forward.
- Modify: `app/hr/careers/router.py` — SSR page `GET /onboarding/{token}` renders shell HTML with Tailwind + a vanilla-JS flow (similar pattern to the apply form). Lists pending tasks, renders an iframe or in-place esign for each `form_sign`, and a file picker for each `document_upload`.
- Create: `app/hr/careers/templates/my_onboarding.html`.
- Create: `tests/hr/test_myonboarding_public.py`.

- [ ] **Step 1:** Token model + generator (`secrets.token_urlsafe(32)`, 30-day expiry).
- [ ] **Step 2:** On onboarding spawn, create a token linked to the instance; surface on the spawn trigger event (enqueue a welcome SMS/email with `/onboarding/{token}` URL — v1 just logs; actual send wired in Plan 4 polish).
- [ ] **Step 3:** Public router — 3 endpoints: GET state, POST start (mark viewed), POST advance-task (gated to the hire-role tasks only).
- [ ] **Step 4:** SSR page rendering the current task list, progress bar, and individual-task links that open e-sign tokens for `form_sign`.
- [ ] **Step 5:** Tests: full happy path (load token → complete first ready task → verify instance advances).
- [ ] Commit: `hr(plan3): public MyOnboarding token flow`.

---

## Phase E — Admin lifecycle detail pages + API

### Task E1: Admin onboarding + offboarding router

**Files:**
- Create: `app/hr/onboarding/router.py`
- Modify: `app/hr/router.py`
- Create: `tests/hr/test_onboarding_admin.py`

Endpoints:
- `GET /hr/onboarding/instances?subject_id={tech_id}&category=onboarding|offboarding` — list instances.
- `GET /hr/onboarding/instances/{id}` — detail with tasks + events.
- `POST /hr/onboarding/instances/{id}/spawn-offboarding` — convenience endpoint for manager to kick off offboarding.
- `PATCH /hr/onboarding/instances/{id}/tasks/{task_id}` — proxy to workflow engine `advance_task`.

Tests: create instance manually, advance task via API, list returns it.

- [ ] Commit: `hr(plan3): admin onboarding/offboarding router`.

### Task E2: EmployeeDetailPage + OnboardingDetailPage + OffboardingDetailPage (frontend)

**Files (ReactCRM):**
- Create: `src/features/hr/employees/api.ts` (certs, docs, assignments hooks)
- Create: `src/features/hr/employees/pages/EmployeeDetailPage.tsx` (tabs: Overview / Files / Workflows / Activity)
- Create: `src/features/hr/onboarding/api.ts`
- Create: `src/features/hr/onboarding/pages/OnboardingDetailPage.tsx` (uses Plan 1 `StagePipeline` for stage filter; each task row shows status + advance button)
- Create: `src/features/hr/onboarding/pages/OffboardingDetailPage.tsx`
- Create: `src/features/hr/shared/WorkflowTimeline.tsx` (reused on all three pages)
- Modify: `src/features/hr/index.ts`, `src/routes/app/hr.routes.tsx` (routes: `/hr/employees/:id`, `/hr/onboarding/:instanceId`, `/hr/offboarding/:instanceId`)
- Modify: `src/components/layout/navConfig.ts` — add "Employees" and "Onboarding" entries in the HR nav group

- [ ] Build + vitest + commit: `hr(plan3): frontend employee + lifecycle detail pages`.

---

## Phase F — Cert expiry SMS alerter

### Task F1: Scheduled job

**Files:**
- Create: `app/hr/shared/cert_expiry_job.py`
- Modify: appropriate APScheduler-wiring file (find `apscheduler` usage, matches existing pattern — inspect during A1 of Plan 3)
- Create: `tests/hr/test_cert_expiry_job.py`

Scope:
- Run daily at 07:00 local.
- Query certs expiring in exactly 30, 7, 1 days.
- For each cert, look up owning technician → their phone → look up "hr_role_assignments" role "manager" as well (cc the manager).
- Send SMS via the Plan 2 `send_sms` helper. Skip when consent missing.
- Write audit.

- [ ] Commit: `hr(plan3): cert expiry SMS scheduled job`.

---

## Phase G — Integration tests + Playwright

### Task G1: End-to-end flow test

**Files:**
- Create: `e2e/modules/hr-lifecycle-flow.spec.ts` (ReactCRM)

Asserts:
1. Public careers + apply (existing Plan 2 coverage, one smoke).
2. Admin hires applicant via authed API → subject technician row created.
3. Onboarding instance spawns with 23 tasks.
4. MyOnboarding token page loads, shows tasks.
5. Completing a `form_sign` task via public API advances the instance.
6. Cert-expiry SMS job dry-run reports 0 notifications when no certs near expiry.

- [ ] Commit: `hr(plan3): lifecycle e2e flow`.

---

## Phase H — Deploy

### Task H1: Merge, push, migrate, verify

1. Merge worktree → master.
2. `git push origin master`.
3. Wait for Railway build.
4. `curl -X POST .../health/db/migrate-hr` → expect `version_after: "104"`.
5. Run Playwright suite.
6. Commit milestone.

---

## Self-Review

- [x] Spec §6 (onboarding): 23 tasks seeded with stage, deps, config.
- [x] Spec §7 (offboarding): 14 tasks seeded, deps (6 depends on 3; 14 depends on 12).
- [x] Spec §3.3 (employee extensions): 6 tables.
- [x] Spec §4.3 (triggers): `hr.applicant.hired` registered + handler promotes + spawns.
- [x] Spec §10.3 (detail page tabs): Overview/Files/Workflows/Activity.
- [x] Spec §13.3 Plan 3 rollout criteria: full lifecycle ends at "tech in the truck ready to work".
- [x] User rules: async sessions, naive UTC datetimes (carry Plan 2 fix forward), Integer FKs to api_users, UUID FKs to technicians/assets.

### Deferred to Plan 4 / v1.1

- Admin template editor UI (users edit seed templates without a migration).
- Admin PDF field-drawing UI.
- DocuSign integration (high-value docs).
- Structured interview scorecards.
- ADP API auto-provisioning.
- Applicant resume LLM parsing (Plan 2 left it unwired).
