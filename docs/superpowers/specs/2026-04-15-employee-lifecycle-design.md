# Employee Lifecycle Module — Design

**Date:** 2026-04-15
**Scope:** Recruiting → Onboarding → Active Employee → Offboarding, built on a generic task-checklist workflow engine with a template library.
**Target repos:**
- Backend: `/home/will/react-crm-api/` (FastAPI + SQLAlchemy + Alembic)
- Frontend: `/home/will/ReactCRM/` (React 19 + TS + Vite + TanStack Query + Zod + Tailwind)
- Database: Postgres (Railway), UUID primary keys, shared with the rest of the CRM
**Deployment:** Railway auto-deploy on git push to main

> **Naming note:** The active CRM already has `onboarding` (customer/user CRM setup wizard) and `workflow_automations` (Zapier-style event→nodes→edges automation builder). This module is namespaced `hr` (alt: `employee_lifecycle`) and introduces a **separate** workflow primitive — an ordered task checklist — that complements rather than replaces `workflow_automations`.

---

## 1. Goals & Non-Goals

### Goals
- Replace today's email-driven new-hire flow (ADP form + W-4 + I-9 + benefits + employment agreement PDFs via Gmail) with a tracked, auditable, self-service onboarding experience.
- Publish open roles to a public careers page and to Indeed / ZipRecruiter / Facebook Jobs via a standard job-feed XML.
- Track applicants through a pipeline (Applied → Screen → Ride-Along → Offer → Hired) that auto-spawns an onboarding workflow on hire.
- Give every employee a detail page that shows stage, active workflows, documents, certifications, truck/fuel-card assignments, and audit history.
- Offboard employees with a teardown workflow (fuel card kill, truck + inventory return, access revoke, final pay, COBRA).
- Workflow engine is generic: the same primitive later powers non-HR task-checklist workflows (truck commissioning, annual DOT inspection, customer onboarding cases beyond the existing CRM setup wizard).
- Clean `hr` namespace (routers, models, migrations, services) so the module can later be lifted to a shared HR service used by the other CRMs (Brewery, Eminence, Landscape, Hman).

### Non-Goals (v1)
- No payroll calculation. HR fires `employee.hired` / `employee.terminated` events; existing payroll integration (ADP) reacts.
- No replacement of the existing `workflow_automations` (Zapier-style event engine). Two distinct primitives coexist:
  - `workflow_automations`: event → nodes → edges, arbitrary side effects
  - `hr_workflows` (this spec): ordered checklist of typed tasks with assignees, dependencies, due dates
- No replacement of the existing `onboarding` (customer setup wizard). HR onboarding is a separate concept with a separate UI.
- No redesign of the existing `employee_portal` (tech mobile app). HR onboarding tasks that target a hire surface in a new `MyOnboarding` page; the portal itself is untouched.
- No DocuSign integration. Roll-your-own e-sign; door left open for DocuSign later for high-stakes docs.
- No direct ATS integrations beyond the Indeed XML feed (ZipRecruiter + Facebook Jobs consume the same feed for free).
- No health-insurance enrollment automation. v1 captures the AFA plan election as a signed PDF only.
- No structured interview scorecards. v1 uses freeform notes + 1-5 rating.

---

## 2. Architecture

### 2.1 Bounded module inside the existing FastAPI app
All HR code lives under `app/hr/` on the backend and `src/features/hr/` on the frontend. Routers mount at `/api/v2/hr/*` (authenticated) and `/api/v2/public/careers/*` + `/api/v2/public/sign/*` (no auth). The rest of the app only interacts with HR through HTTP or a narrow `app.hr.services` Python interface. This is the seam for future extraction into a shared microservice.

### 2.2 Backend layout (`react-crm-api`)

```
app/
  hr/                                  ← new bounded subsystem
    __init__.py
    workflow/                          ← generic task-checklist engine
      models.py                        ← HrWorkflowTemplate, HrWorkflowInstance, HrWorkflowTask, HrTaskDependency, HrTaskAttachment, HrTaskComment
      schemas.py                       ← Pydantic schemas (use UUIDStr from app/schemas/types.py)
      engine.py                        ← template→instance cloning, state machine, due-date math, role routing
      templates.py                     ← seed loader for stock templates
      triggers.py                      ← event handlers: applicant.hired → spawn onboarding
      services.py                      ← public service interface
      router.py                        ← /api/v2/hr/workflows/*
    recruiting/
      models.py                        ← HrRequisition, HrApplicant, HrApplication, HrApplicationEvent
      schemas.py
      services.py
      router.py                        ← /api/v2/hr/requisitions, /hr/applicants, /hr/applications
      careers_feed.py                  ← Indeed-compatible XML feed (also valid for ZipRecruiter, Facebook Jobs)
      resume_parser.py                 ← OpenAI structured-output resume extraction
    careers/                           ← PUBLIC
      router.py                        ← /api/v2/public/careers/*, /api/v2/public/jobs.xml, /api/v2/public/apply
      (HTML rendered by frontend — SSR question addressed in §5.2)
    onboarding/                        ← HR onboarding (NOT the existing customer setup onboarding)
      templates.py                     ← seed: "New Field Tech Onboarding" (23 tasks)
      router.py                        ← /api/v2/hr/onboarding/*, /api/v2/me/hr/onboarding
    offboarding/
      templates.py                     ← seed: "Tech Separation Checklist" (14 tasks)
      router.py                        ← /api/v2/hr/offboarding/*
    esign/
      models.py                        ← HrSignatureRequest, HrSignedDocument, HrSignatureEvent, HrDocumentTemplate
      schemas.py
      renderer.py                      ← PDF field-fill via pypdf + signature image overlay + audit stamping
      services.py
      router.py                        ← /api/v2/hr/sign/* (admin), /api/v2/public/sign/<token> (public token-gated)
    employees_ext/                     ← extensions to existing user/technician models
      models.py                        ← HrEmployeeCertification (if not already in certification.py), HrEmployeeDocument, HrTruckAssignment, HrFuelCardAssignment, HrAccessGrant
      schemas.py
      services.py
      router.py                        ← /api/v2/hr/employees/<id>/certifications, /documents, /assignments, /access
    shared/
      notifications.py                 ← email (existing transport) + SMS (existing RingCentral) wrappers
      storage.py                       ← file upload helper (reuses existing pattern)
      audit.py                         ← HrAuditLog writer (who/what/when/where/before/after)
      role_resolver.py                 ← assignee_role → user_id at instance spawn time

app/migrations/versions/               ← Alembic revisions (live alongside existing ones)
  <rev>_hr_workflow_tables.py
  <rev>_hr_recruiting_tables.py
  <rev>_hr_employees_ext_tables.py
  <rev>_hr_esign_tables.py
  <rev>_hr_seed_stock_templates.py    ← idempotent data migration: seed templates + document templates
```

### 2.3 Frontend layout (`ReactCRM`)

```
src/features/hr/                       ← new feature tree; does not conflict with existing "onboarding" (customer setup) or "employee" (portal)
  workflow/
    api.ts                             ← TanStack Query hooks, Zod schemas
    components/
      WorkflowTimeline.tsx             ← stage pipeline pills + collapsible task sections
      TaskCard.tsx
      TemplateEditor.tsx               ← admin UI (v1 read-only; full edit in v1.1)
  recruiting/
    api.ts
    pages/
      RequisitionsListPage.tsx
      RequisitionDetailPage.tsx        ← pipeline pill-tabs with counts + candidate list
      ApplicantDetailPage.tsx          ← header + stage pipeline + tabs (Overview/Interviews/Activity/Docs/Comments)
      JobBoardAdminPage.tsx            ← posting performance metrics
  careers/
    pages/
      CareersPage.tsx                  ← public; uses react-helmet-async for SEO <head>
      RequisitionPublicPage.tsx        ← /careers/<slug>
      ApplyFormPage.tsx                ← mobile-first; submits to /api/v2/public/apply
  onboarding/                          ← HR onboarding (file naming avoids collision by living under hr/)
    api.ts
    pages/
      OnboardingListPage.tsx           ← all active onboardings; per-tech progress bars
      OnboardingDetailPage.tsx         ← manager view
      MyOnboardingPage.tsx             ← tech self-service view (linked from employee portal)
  offboarding/
    api.ts
    pages/
      OffboardingListPage.tsx
      OffboardingDetailPage.tsx
  employees/
    api.ts
    pages/
      EmployeesListPage.tsx            ← Rippling-style list with avatars, dept, status
      EmployeeDetailPage.tsx           ← header + tabs: Overview / Assignments / Certifications / Documents / Workflows / Activity
  shared/
    StagePipeline.tsx                  ← reusable pill-tab strip with live counts
    ActivityPanel.tsx                  ← right-side audit/comment feed
    ProgressBar.tsx
    CelebrationCard.tsx                ← milestone celebration + CTA
    (EmptyState already exists at src/components/ui/EmptyState.tsx — reuse, do not recreate)

src/features/careers-public/           ← OPTIONAL: bare public entry w/ minimal chrome
  (If we decide to keep the careers page inside the React SPA instead of SSR; see §5.2)
```

### 2.4 Route mounting

- `/api/v2/hr/*` — authenticated (cookie auth, existing middleware). All HR admin endpoints.
- `/api/v2/me/hr/*` — authenticated, scoped to the logged-in user's own HR records.
- `/api/v2/public/careers/*` — public, no auth, cacheable at edge.
- `/api/v2/public/jobs.xml` — public Indeed/ZR/FB-compatible XML feed.
- `/api/v2/public/sign/<token>` — public, token-scoped, 7-day default expiry.
- Frontend routes follow React Router structure under `/app/hr/*` and `/app/me/onboarding`. Public routes at `/careers`, `/careers/:slug`, `/apply/:slug`, `/sign/:token`.

### 2.5 Distinguishing the two workflow primitives
The CRM will have two different "workflow" concepts going forward. Clear naming rule to prevent confusion:

| Concept | Model | Router | Purpose |
|---|---|---|---|
| Zapier-style automation (existing) | `WorkflowAutomation`, `WorkflowExecution` | `/api/v2/workflow-automations/*` | Event-driven side effects (when X, do Y) |
| Task checklist (this spec) | `HrWorkflowTemplate`, `HrWorkflowInstance`, `HrWorkflowTask` | `/api/v2/hr/workflows/*` | Ordered list of typed tasks with assignees, dependencies, due dates |

UI surface naming: "Automations" for the existing one, "Checklists" or "Workflows" for the HR one. Docs must always disambiguate.

---

## 3. Data Model

Stack conventions per user's backend rules:
- UUID PKs (native Postgres `uuid`).
- `async_session_maker` for DB sessions.
- `selectinload()` on all relationships to avoid N+1.
- Pydantic schemas use `UUIDStr` from `app/schemas/types.py` for UUID↔str coercion.
- New tables prefixed `hr_` to stay clearly namespaced.

### 3.1 Workflow engine (generic, HR-prefixed but reusable)

```
hr_workflow_templates
  id uuid PK
  name text                      -- "New Field Tech Onboarding"
  category text                  -- "onboarding" | "offboarding" | "recruiting" | "operational"
  version int                    -- clone-on-edit versioning
  is_active bool default true
  created_by uuid FK api_users
  created_at, updated_at

hr_workflow_template_tasks
  id uuid PK
  template_id uuid FK hr_workflow_templates
  position int
  stage text                     -- "Pre-Day-1" | "Day 1" | "Week 1" | "Month 1"
  name text                      -- "Collect signed I-9"
  description text
  kind text                      -- "form_sign" | "document_upload" | "training_video" | "verify" | "assignment" | "manual"
  assignee_role text             -- "hire" | "manager" | "hr" | "dispatch" | "it"
  due_offset_days int            -- relative to workflow start
  required bool default true
  config jsonb                   -- kind-specific; e.g. {"document_template_id": "<uuid>"}

hr_workflow_template_dependencies
  task_id uuid FK hr_workflow_template_tasks
  depends_on_task_id uuid FK hr_workflow_template_tasks
  PRIMARY KEY (task_id, depends_on_task_id)

hr_workflow_instances
  id uuid PK
  template_id uuid FK hr_workflow_templates
  template_version int
  subject_type text              -- "employee" | "applicant" | "truck" | "customer"
  subject_id uuid                -- polymorphic FK (no DB-level FK; validated at app level)
  status text                    -- "active" | "completed" | "cancelled"
  started_at, completed_at, cancelled_at timestamptz
  started_by uuid FK api_users

hr_workflow_tasks
  id uuid PK
  instance_id uuid FK hr_workflow_instances
  template_task_id uuid FK hr_workflow_template_tasks
  position int
  stage text
  name text
  kind text
  assignee_user_id uuid FK api_users nullable
  assignee_role text             -- resolved to user at spawn time; retained for re-resolve on role change
  status text                    -- "blocked" | "ready" | "in_progress" | "completed" | "skipped"
  due_at timestamptz
  completed_at timestamptz nullable
  completed_by uuid FK api_users nullable
  config jsonb
  result jsonb                   -- e.g. {"signature_id": "...", "document_id": "..."}
  INDEX (instance_id, status)
  INDEX (assignee_user_id, status) WHERE status IN ('ready', 'in_progress')

hr_workflow_task_comments
  id uuid PK
  task_id uuid FK hr_workflow_tasks
  user_id uuid FK api_users
  body text
  created_at timestamptz

hr_workflow_task_attachments
  id uuid PK
  task_id uuid FK hr_workflow_tasks
  storage_key text
  filename text
  mime_type text
  size int
  uploaded_by uuid FK api_users
  uploaded_at timestamptz
```

**Task state machine:** `blocked → ready → in_progress → completed` (or `skipped`). A task moves from `blocked` to `ready` when all its dependencies are `completed` or `skipped`. Re-evaluated on every dependency state change.

**Role routing:** `assignee_role` strings ("manager", "hr", "dispatch", "it") resolve to specific users via `hr_role_assignments`. For `hire`/`employee`, the resolver uses the workflow's `subject_id`.

```
hr_role_assignments
  id uuid PK
  role text                      -- "hr" | "dispatch" | "it" | "default_manager"
  user_id uuid FK api_users
  priority int default 0         -- first active+highest-priority match wins
  active bool default true
  created_at
```

### 3.2 Recruiting

```
hr_requisitions
  id uuid PK
  slug text UNIQUE               -- /careers/<slug>
  title text                     -- "Field Technician"
  department text
  location_city, location_state text
  employment_type text           -- "full_time" | "part_time" | "contract"
  compensation_min, compensation_max numeric(10,2)
  compensation_display text      -- free-text: "$20-$28/hr + OT"
  description_md text
  requirements_md text
  benefits_md text
  status text                    -- "draft" | "open" | "paused" | "closed"
  opened_at, closed_at timestamptz
  hiring_manager_id uuid FK api_users
  onboarding_template_id uuid FK hr_workflow_templates
  created_by, created_at, updated_at

hr_applicants
  id uuid PK
  first_name, last_name text
  email, phone text
  resume_storage_key text nullable
  resume_parsed jsonb            -- LLM-extracted structured data
  source text                    -- "indeed" | "careers_page" | "referral" | "facebook" | "manual" | "email"
  source_ref text                -- external id if known
  created_at

hr_applications
  id uuid PK
  applicant_id uuid FK hr_applicants
  requisition_id uuid FK hr_requisitions
  stage text                     -- "applied" | "screen" | "ride_along" | "offer" | "hired" | "rejected" | "withdrawn"
  stage_entered_at timestamptz
  assigned_recruiter_id uuid FK api_users nullable
  rejection_reason text nullable
  rating smallint nullable       -- 1-5
  answers jsonb                  -- screening question answers
  notes text
  created_at, updated_at
  UNIQUE (applicant_id, requisition_id)

hr_application_events
  id uuid PK
  application_id uuid FK hr_applications
  event_type text                -- "created" | "stage_changed" | "note_added" | "message_sent"
  user_id uuid FK api_users nullable
  payload jsonb
  created_at
```

### 3.3 Employee extensions

Before creating new tables, reuse what exists. Existing models at `app/models/`:
- `user.py`, `technician.py` — identity
- `certification.py`, `license.py` — possibly already covers some of what `hr_employee_certifications` would.

**Design decision:** read these existing models during Plan 1 implementation. If `certification.py`/`license.py` covers TCEQ/CDL/DOT medical adequately, extend them rather than duplicate. If not, create HR-scoped tables below. Spec proceeds assuming net-new until reconciliation step.

```
hr_employee_certifications                -- maybe merged into certification.py; decided in impl
  id uuid PK
  employee_id uuid FK api_users           -- or whatever the active employee FK pattern is
  kind text                               -- "tceq_os0" | "tceq_mp" | "cdl_class_b" | "dot_medical" | "first_aid"
  number text
  issued_at date, expires_at date
  issuing_authority text
  document_id uuid FK hr_employee_documents nullable
  status text                             -- "active" | "expired" | "pending"

hr_employee_documents
  id uuid PK
  employee_id uuid FK api_users
  kind text                               -- "i9" | "w4" | "handbook_ack" | "direct_deposit" | "drug_test" | "dot_med_card" | "cdl" | "other"
  storage_key text
  signed_document_id uuid FK hr_signed_documents nullable
  uploaded_at, uploaded_by
  expires_at date nullable

hr_truck_assignments
  id uuid PK
  employee_id uuid FK api_users
  truck_id uuid FK <existing trucks/fleet table>
  assigned_at timestamptz, unassigned_at timestamptz nullable
  assigned_by, unassigned_by uuid FK api_users

hr_fuel_card_assignments
  id uuid PK
  employee_id uuid FK
  card_id uuid FK hr_fuel_cards  -- new table; or existing if one exists
  assigned_at, unassigned_at nullable

hr_access_grants
  id uuid PK
  employee_id uuid FK api_users
  system text                    -- "crm" | "ringcentral" | "google_workspace" | "samsara" | "adp"
  identifier text                -- username/email in that system
  granted_at, revoked_at nullable
  granted_by, revoked_by
```

### 3.4 E-sign

```
hr_document_templates
  id uuid PK
  kind text UNIQUE               -- "i9" | "w4_2026" | "adp_info" | "handbook_ack" | "direct_deposit" | "benefits_election" | "employment_agreement" | "cobra_notice"
  version text
  pdf_storage_key text
  fields jsonb                   -- [{name, page, x, y, w, h, field_type}]
  active bool default true

hr_signature_requests
  id uuid PK
  token text UNIQUE              -- cryptographically random, URL-safe
  signer_email, signer_name text
  signer_user_id uuid FK api_users nullable  -- null for pre-hire applicants
  document_template_id uuid FK hr_document_templates
  field_values jsonb             -- pre-filled fields merged with defaults
  status text                    -- "sent" | "viewed" | "signed" | "expired" | "revoked"
  sent_at, viewed_at, signed_at, expires_at timestamptz
  workflow_task_id uuid FK hr_workflow_tasks nullable

hr_signed_documents
  id uuid PK
  signature_request_id uuid FK hr_signature_requests
  storage_key text               -- final signed PDF
  signer_ip inet
  signer_user_agent text
  signature_image_key text
  signed_at timestamptz
  hash_sha256 text

hr_signature_events
  id uuid PK
  signature_request_id uuid FK hr_signature_requests
  event_type text                -- "sent" | "viewed" | "signed" | "expired" | "revoked"
  ip inet, user_agent text, payload jsonb
  created_at
```

### 3.5 Universal audit log

```
hr_audit_log
  id uuid PK
  entity_type text               -- "applicant" | "application" | "requisition" | "employee" | "workflow_task" | "signature_request" | ...
  entity_id uuid
  event text                     -- "created" | "updated" | "stage_changed" | "assigned" | "completed" | "revoked"
  diff jsonb                     -- {field: [old, new]}
  actor_user_id uuid FK api_users nullable
  actor_ip inet
  actor_user_agent text
  actor_location text            -- geoip: "Houston, TX, US"
  created_at timestamptz
  INDEX (entity_type, entity_id, created_at DESC)
  INDEX (actor_user_id, created_at DESC)
```

Feeds the right-side `ActivityPanel` and the Change History tab.

---

## 4. Workflow Engine Mechanics

### 4.1 Template → Instance spawn
`HrWorkflowEngine.spawn(template_id, subject_type, subject_id, context)`:
1. Clone template + tasks + dependencies into `hr_workflow_instances` + `hr_workflow_tasks`.
2. Snapshot `template_version`.
3. Resolve `assignee_role` → `assignee_user_id` via `hr_role_assignments` + subject lookup.
4. Compute each task's `due_at` from `due_offset_days` relative to `context.start_date` (defaults to `now()`; for onboarding, uses the hire's start date).
5. Tasks with no dependencies: `status=ready`. Rest: `status=blocked`.
6. Write `hr_audit_log` start event.
7. Fire notifications to initial `ready` task assignees (email + SMS).

### 4.2 Task state transitions
- `blocked → ready`: all dependencies are `completed` or `skipped` (re-evaluated on every downstream transition).
- `ready → in_progress`: assignee opens the task (click-through recorded).
- `in_progress → completed`: kind-specific completion rules:
  - `form_sign`: linked `hr_signature_request` has `status = signed`.
  - `document_upload`: at least one `hr_workflow_task_attachment` exists.
  - `training_video`: explicit "I watched this" with timestamp + optional quiz score.
  - `verify`: manager clicks "Verified" with optional note.
  - `assignment`: linked row in `hr_truck_assignments` / `hr_fuel_card_assignments` / `hr_access_grants` created.
  - `manual`: explicit completion checkbox.
- `* → skipped`: requires role `manager` or `hr` + reason (audit).
- Instance `status=completed` when all non-skipped tasks are `completed`; fires post-completion triggers.

### 4.3 Triggers (auto-spawn)
Event bus of named events (plain Python for v1; upgrade to queue-backed later):
- `hr.applicant.hired` → spawn requisition's `onboarding_template_id`.
- `hr.employee.terminated` → spawn standard offboarding template.
- `hr.certification.expires_soon` (30/7/1 days) → send SMS + email to employee + manager.
- `hr.workflow_instance.completed` → optional follow-up spawn (configurable per template).

Triggers live in `app/hr/workflow/triggers.py` as plain functions registered with a simple dispatcher. Later: back with RQ/Celery/Redis without API change.

### 4.4 Concurrency
Task state transitions use `SELECT ... FOR UPDATE` row-level locking to prevent double-completion races when multiple tabs are open.

### 4.5 Missing role assignments
If `assignee_role` can't be resolved at spawn, create the task with `assignee_user_id = NULL`, `status = ready`, and write a warning to `hr_audit_log`. Admin dashboard surfaces an "Unassigned Tasks" queue.

---

## 5. Recruiting Specifics

### 5.1 Pipeline stages (v1, fixed)
**Applied → Screen → Ride-Along → Offer → Hired** plus terminal states `Rejected` and `Withdrawn`. Ride-Along is septic-industry specific (candidate rides a shift before hire).

Each requisition's `RequisitionDetailPage` shows stage pill-tabs at the top with live counts. Clicking a pill scopes the candidate list below.

### 5.2 Careers page + SEO
**Decision:** SSR the public careers pages via a lightweight approach — FastAPI serves HTML templates for `/careers` and `/careers/<slug>`, using a static template renderer (Jinja2 included with FastAPI). The application form itself is a React-rendered island for interactivity (resume upload, validation). Rationale:
- Google still indexes SSR HTML faster and more reliably than JS-heavy SPAs.
- The careers surface is mostly static content — only the apply form needs React.
- Avoids standing up Next.js or a separate SSR app just for 2-3 pages.

Mac Septic branding loaded from existing tenant config table (logo, primary color, address, phone).

### 5.3 Indeed XML feed
Public endpoint `GET /api/v2/public/jobs.xml` produces the Indeed XML spec. ZipRecruiter, Facebook Jobs, Google for Jobs all consume this format. Indeed crawls on its schedule (typically 1-4x daily).

- `<url>` points to the careers page for that requisition (not the apply form directly) so click-through tracking works.
- `<referencenumber>` = requisition `slug`.
- Draft requisitions are excluded; only `status='open'` appears.

### 5.4 Applicant sources (v1)
- **Careers page apply form** → `source='careers_page'`
- **Indeed / ZipRecruiter / Facebook Jobs referrers** → `source='indeed'` / `'ziprecruiter'` / `'facebook'` via UTM param on careers URLs
- **Manual entry** by recruiter → `source='manual'`

### 5.5 Resume parsing
On resume upload, queue an async OpenAI structured-output call to extract: work history, certifications (CDL, TCEQ, DOT), years of experience, distance from service area (geocode). Stored in `applicants.resume_parsed`. Surfaces as an "AI summary" card on the applicant page. On failure: log, leave null, continue — resume file itself is always stored.

### 5.6 Candidate communication
SMS-first via existing RingCentral integration. Email as secondary copy (existing transport). Templated messages per stage change, stored in a small `hr_recruiting_message_templates` table, editable via settings UI in v1.1 (v1 seeds defaults only).

---

## 6. Onboarding — "New Field Tech" seeded template (23 tasks)

**Pre-Day 1:**
1. [hire] Sign Employment Agreement (`form_sign`)
2. [hire] Sign I-9 Section 1 (`form_sign`)
3. [hire] Sign W-4 2026 (`form_sign`)
4. [hire] Complete ADP Employee Information Form (`form_sign`)
5. [hire] Elect AFA health plan (`form_sign` — chosen plan PDF attached)
6. [hire] Submit direct deposit authorization (`form_sign`)
7. [hire] Upload copy of driver's license (`document_upload`)
8. [hire] Upload DOT medical card (`document_upload`)
9. [hire] Upload CDL (if applicable) (`document_upload`)
10. [hr] Verify I-9 Section 2 (`verify`; depends on 2 + 7)
11. [hr] Run background check (`manual`)
12. [hr] Schedule drug test (`manual`)

**Day 1:**
13. [manager] Uniform + PPE fitting (`manual`)
14. [it] Create CRM account (`assignment` → `hr_access_grants`)
15. [it] Issue company phone + Google Workspace account (`assignment`)
16. [manager] Assign truck (`assignment` → `hr_truck_assignments`; depends on 7)
17. [manager] Issue fuel card (`assignment` → `hr_fuel_card_assignments`)
18. [hire] Sign Employee Handbook Acknowledgement (`form_sign`)
19. [hire] Watch safety training videos (`training_video`, 4 videos)

**Week 1:**
20. [manager] 3-day ride-along check-in (`verify`)
21. [hire] Complete TCEQ OS-0 study materials (`training_video`)

**Month 1:**
22. [manager] 30-day review (`manual`, links to existing performance-review table)
23. [hr] Confirm all certs logged (`verify`)

Each task has a `due_offset_days` relative to the hire's start date. Dependencies wired in the seed migration. Template is cloneable; v1 edits via seed migration, v1.1 gets admin editor UI.

---

## 7. Offboarding — "Tech Separation" seeded template (14 tasks)

1. [hr] Record separation reason + last day (`manual`)
2. [employee] Exit interview (`form_sign`)
3. [manager] Return company property: truck (`verify` → closes `hr_truck_assignments`)
4. [manager] Return company property: phone (`verify`)
5. [manager] Return company property: uniforms + PPE (`verify`)
6. [manager] Inventory audit of truck stock (`verify`)
7. [it] Kill fuel card (`assignment` → close `hr_fuel_card_assignments`)
8. [it] Revoke CRM access (`assignment`)
9. [it] Revoke Google Workspace (`assignment`)
10. [it] Revoke RingCentral (`assignment`)
11. [it] Revoke Samsara (`assignment`)
12. [hr] Final paycheck cut in ADP (`manual`)
13. [hr] Send COBRA notification (`form_sign`)
14. [hr] Terminate in ADP + mark inactive in CRM (`manual`)

Manager and IT tasks run in parallel. HR owns the terminal state.

---

## 8. E-sign Subsystem

### 8.1 Flow
1. A `form_sign` task creates an `hr_signature_request` with secure random `token` (32 bytes URL-safe base64).
2. Notification (email + SMS) sends link `https://react.ecbtx.com/sign/<token>`.
3. Public sign page (no login): renders filled PDF as images, shows signature pad, shows ESIGN Act consent checkbox.
4. On submit: save signature PNG, stamp PDF with signature image + "Signed by <name> on <date> from IP <ip>", compute SHA-256, store `hr_signed_documents`, mark linked `hr_workflow_tasks` complete, fire `hr.signature.completed` event.

### 8.2 Seeded document templates
- I-9 (2025 edition — use current USCIS PDF)
- W-4 2026
- ADP Employee Information Form
- Mac Septic Employment Agreement (templatable fields: name, start date, rate, truck assignment)
- Benefits Election Form (from `J Fajardo - Employment Docs/`)
- Handbook Acknowledgement
- Direct Deposit Authorization
- COBRA Notice

Field maps (JSON of `{name, page, x, y, w, h, field_type}`) built manually during Plan 1 by measuring the actual PDFs at `/mnt/win11/Fedora/home-offload/Downloads/J Fajardo - Employment Docs/`. Future admin UI for drawing fields is v1.1+.

### 8.3 Legal defensibility (ESIGN Act)
- Explicit intent-to-sign checkbox with the legal language block.
- Signed copy delivered to signer's email.
- Full audit trail: IP, user-agent, geoip, timestamps on every view and signature event.
- SHA-256 content hash for tamper detection.
- Originals retained: unsigned PDF, signed PDF, raw signature PNG — stored separately.

High-stakes docs (separation agreements, NDAs, non-competes) deferred to a future DocuSign integration.

---

## 9. Integration Points

- **Existing `app/models/user.py` and `technician.py`:** identity; HR tables FK to these. No schema change.
- **Existing `certification.py` / `license.py`:** reconcile in impl — may be sufficient for TCEQ/CDL/DOT; merge rather than duplicate.
- **Existing `employee_portal.py`:** the tech mobile app. The `MyOnboarding` page is a new surface reachable from the portal; no edits to the portal routes. Signature pad + checklist UX there is reusable inspiration.
- **Existing `onboarding` (customer setup wizard):** untouched. Different namespace, different purpose.
- **Existing `workflow_automations`:** untouched. Different primitive. Could be used in future to fire an HR task as a side effect of arbitrary events (optional Plan 4 bridge).
- **Existing payroll integration (ADP):** HR emits `hr.employee.hired` and `hr.employee.terminated`; payroll subscribes. No HR code touches ADP directly in v1.
- **Existing fleet / trucks:** `hr_truck_assignments` FKs the existing trucks table. Fleet feature surfaces assignment history read-only.
- **Existing RingCentral SMS:** HR uses existing transport for all SMS.
- **Existing email transport:** same.
- **Cookie auth + WebSocket (`/api/v2/ws`):** HR routers use the existing middleware; real-time updates to HR lists use the existing WS pattern.
- **Existing file storage pattern:** reuse the helper used by documents/attachments elsewhere in the app.

---

## 10. Frontend Patterns (Rippling-inspired)

1. **Stage pipeline pills with live counts** at the top of Requisition, Application, Onboarding, Offboarding detail pages.
2. **Detail page header:** name + ID + status chip + key metrics row + ⋯ overflow (Cancel/Transfer/Request AI Analysis).
3. **Tabs within detail pages:** Overview / Files / Workflows / Activity History / Settings.
4. **Right-side ActivityPanel:** audit feed + @mention comments (reusable component).
5. **Celebration cards** at stage transitions.
6. **Empty states with illustration + CTA** (reuse existing `EmptyState` at `src/components/ui/EmptyState.tsx`).
7. **Progress bars** for bounded work (onboarding progress %, cert countdown).
8. **Drawer modals** for quick actions — preserve list context.
9. **Process Overview page** per module: KPIs (open reqs, active onboardings, expiring certs) + mixed pending-items inbox.

Mobile responsiveness is mandatory (per user's frontend rules). Candidates apply from phones; techs complete onboarding tasks from phones.

---

## 11. Error Handling

- **Existing API error envelope** continues in use: HTTP status + detail body. HR-specific codes: `hr.template_not_found`, `hr.task_not_ready`, `hr.signature_expired`, `hr.role_unassigned`, `hr.document_hash_mismatch`.
- **Signature token expiry:** expired tokens show friendly "Request a new link" page + auto-alert assignee.
- **Storage failures on upload:** retry with exponential backoff in upload helper; user-facing error only after 3 attempts.
- **LLM resume parsing failure:** swallow, log to `logs/hr.log`, leave `resume_parsed=null`. Resume file always stored.
- **Concurrency:** row-level locking on task transitions.
- **Missing role assignment:** create task with `NULL` assignee, `ready` status, warning in audit log; admin unassigned queue surfaces these.
- **Zod validation (frontend):** every API response validated; violations surfaced via existing error filter (matches user's frontend rules).

---

## 12. Testing

Follows user's testing rules. Playwright tests: `page.evaluate(async () => fetch(..., {credentials:"include"}))` for API, login as first `test()` (not `beforeAll`), `clearCookies()`, `waitForTimeout(2000)`, `domcontentloaded` waits, filter known console errors.

### 12.1 Backend (pytest, real Postgres)
- `tests/hr/test_workflow_engine.py`: template clone, dependency resolution, state machine, trigger firing, concurrency lock.
- `tests/hr/test_recruiting.py`: requisition CRUD, stage transitions, event logging, XML feed schema, draft exclusion.
- `tests/hr/test_onboarding_template.py`: spawn "New Tech Onboarding" fixture, advance all 23 tasks, verify audit, verify auto-unassign triggers fire downstream.
- `tests/hr/test_offboarding_template.py`: spawn "Tech Separation", verify `hr_truck_assignments` + `hr_fuel_card_assignments` + `hr_access_grants` closed.
- `tests/hr/test_esign.py`: PDF fill, signature request lifecycle, token expiry, hash tamper detection, ESIGN consent required.
- `tests/hr/test_careers_feed.py`: Indeed XML schema validation, URL correctness, `status='open'` filter.
- `tests/hr/test_audit.py`: every mutation writes audit with correct diff.

### 12.2 Frontend
- Zod contract tests for every new endpoint (matches existing `test:contracts`).
- Component tests for `StagePipeline`, `WorkflowTimeline`, `ActivityPanel`.
- Playwright E2E happy paths:
  - Apply from careers → appears in Applied → recruiter advances to Hired → onboarding auto-spawns.
  - New hire signs 6 documents → all signatures land in `hr_signed_documents` with audit rows.
  - Offboarding: terminate → IT revokes → all assignments closed.
  - Visual regression via existing Percy setup for careers page + pipeline.

### 12.3 Regression budget
Must not break: `employee_portal` (3,516 lines), `onboarding` (customer setup wizard — 545 lines), `workflow_automations`, existing auth, existing WebSocket, existing file storage. Add integration smoke tests for the intersections.

---

## 13. Migration & Rollout

### 13.1 Schema migration
One Alembic revision per logical group: workflow tables, recruiting tables, employee extensions, e-sign tables, seed stock templates + document templates. All reversible. All idempotent where reasonable (seed data migrations especially).

### 13.2 Feature flag
Env var `HR_MODULE_ENABLED=true`. When false:
- Routers conditionally register (or respond 404).
- React routes 404 at the router level.
- Triggers don't fire.

Lets us ship behind a flag and turn on per-environment.

### 13.3 Rollout order — 3 shippable plans
This design is one spec but decomposes into three shippable plans. Each ends in a usable state.

- **Plan 1 — Foundation.** Workflow engine + e-sign subsystem + careers page + Indeed XML feed + role assignments + audit log + minimal admin UI. No customer-visible CRM UX yet. Ends with: a public careers page live, jobs indexable on Indeed.
- **Plan 2 — Recruiting.** Requisitions CRUD, applicants, applications, pipeline pill-tabs, applicant detail page, candidate SMS, apply form on careers page. Ends with: full hiring pipeline, but no onboarding auto-spawn yet.
- **Plan 3 — Lifecycle.** Seed "New Field Tech Onboarding" + "Tech Separation" templates, wire `hr.applicant.hired` → onboarding spawn trigger, build Employee Detail redesign with tabs, build MyOnboarding self-service page for new hires, build OffboardingDetail page. Ends with: full employee lifecycle live.

Plans 2 and 3 can be parallelized after Plan 1 ships.

### 13.4 Out of scope (v1.1+ backlog)
- DocuSign integration for high-stakes docs.
- Admin template editor (v1 edits via seed migrations).
- Admin PDF field-drawing UI.
- Multi-tenant lift-out to shared HR service.
- Structured interview scorecards.
- ADP API auto-provisioning.
- Applicant video-interview scheduling.
- AI interview summaries.
- Health insurance enrollment automation.
- Reconciliation with existing `certification.py` / `license.py` — may merge or keep HR-scoped separately.

---

## 14. Success Criteria

- A new hire can complete the entire paperwork packet (8 signed docs) without an email chain, on their phone.
- Time from "offer accepted" to "tech in the truck ready to work" drops 50% (baseline: ~7 days; target: ≤3.5 days).
- Every cert expiration produces SMS at 30/7/1 days and none slip past active.
- Offboarding never leaves a fuel card active more than 24 hours after last day.
- A new job posting appears on Indeed within 24 hours, zero manual effort.
- Every HR action writes an audit row; audit is readable on the entity detail page.

---

## 15. Open Reconciliation Items (resolve during Plan 1 implementation, not now)

1. `certification.py` / `license.py`: do these already cover TCEQ/CDL/DOT medical adequately? If yes, extend rather than create `hr_employee_certifications`.
2. Existing fuel card data: is there already a `fuel_cards` table? If yes, `hr_fuel_card_assignments` FKs to it rather than introducing `hr_fuel_cards`.
3. Existing `workflow_automations` (Zapier-style): consider a Plan 4 bridge letting an automation fire `hr_workflow_task.complete` as a side effect — probably v1.1+, not v1.
4. Existing `employee_portal` signature pad: reuse component for e-sign pad or build new? Prefer reuse.
5. Confirm the email transport in use (SendGrid vs Mailgun vs SMTP) before Plan 1.
