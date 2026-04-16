# Employee Lifecycle — Plan 4: Polish & v1.1 essentials

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the user-facing polish tier on top of Plans 1 + 2 + 3 — a top-level **HR Overview** page with KPIs and a mixed pending-items inbox, a **Global Applicant Inbox** (all applicants across all requisitions with filters), a **Recruiting Message Template admin** (view + inline edit the 5 seeded SMS templates without a migration), and a mobile pass over all HR pages so techs and applicants on phones are not second-class.

**Architecture:** No new tables. Reuses all Plan 1–3 services. The message-template admin is a thin PATCH on `hr_recruiting_message_templates`. The HR overview page is a single read-optimised admin endpoint (`GET /hr/overview`) that aggregates KPIs. The applicant inbox is a pagination-friendly variant of the existing list endpoint.

**Tech Stack:** Same as Plan 1/2/3.

**Spec:** §10.9 (Process Overview page), §5.6 (message templates — admin surface bumped from v1.1 to Plan 4), §13.4 (v1.1 backlog picks).

**Prerequisite:** Plan 3 shipped.

---

## File Structure

Backend (new):

```
app/hr/dashboard/overview.py            ← aggregator service
app/hr/dashboard/schemas.py
app/hr/dashboard/router.py
app/hr/recruiting/templates_admin_router.py
app/hr/recruiting/templates_admin_schemas.py
tests/hr/test_hr_overview.py
tests/hr/test_message_templates_admin.py
tests/hr/test_applicant_inbox.py
```

Backend (modified):

```
app/hr/router.py                        ← include new routers
app/hr/recruiting/applicant_router.py   ← add inbox filter/search query params
app/hr/recruiting/applicant_services.py ← paginated search with joins
```

Frontend (new):

```
src/features/hr/dashboard/api.ts
src/features/hr/dashboard/pages/HrOverviewPage.tsx
src/features/hr/recruiting/pages/ApplicantInboxPage.tsx
src/features/hr/recruiting/pages/MessageTemplatesAdminPage.tsx
src/features/hr/recruiting/api-templates.ts
src/features/hr/shared/KpiCard.tsx
src/features/hr/shared/PendingItemsList.tsx
```

Frontend (modified):

```
src/features/hr/index.ts                ← re-export new pages
src/routes/app/hr.routes.tsx            ← /hr, /hr/inbox, /hr/settings/message-templates
src/components/layout/navConfig.ts      ← Overview (/hr) as first item, Inbox, Settings sub-group
```

Playwright:

```
e2e/modules/hr-polish.spec.ts
```

---

## Phase A — HR Overview page

### Task A1: Backend overview aggregator

**Files:**
- Create: `app/hr/dashboard/overview.py` — single async function `async def build_overview(db) -> dict` returning:
  - `open_requisitions: int`
  - `applicants_last_7d: int`
  - `active_onboardings: int`
  - `active_offboardings: int`
  - `expiring_certs_30d: int`
  - `pending_hr_tasks: list[{id,name,subject_type,instance_id,due_at}]`  (up to 20; ready+in_progress tasks assigned to role=hr across all instances)
- Create: `app/hr/dashboard/schemas.py` — Pydantic OUT matching above.
- Create: `app/hr/dashboard/router.py` — `GET /hr/overview` authed.
- Modify: `app/hr/router.py` — include.
- Create: `tests/hr/test_hr_overview.py`.

Tests (3-4):
- Empty state → all zeros + empty pending list.
- Counts update as requisitions / applicants / onboarding instances land.
- Expiring certs window respects the 30-day cutoff.

- [ ] Commit: `hr(plan4): HR overview KPI aggregator + /hr/overview endpoint`.

### Task A2: Frontend HR Overview page

**Files (ReactCRM):**
- Create: `src/features/hr/dashboard/api.ts` — `useHrOverview()` hook (Zod schema matching the backend).
- Create: `src/features/hr/shared/KpiCard.tsx` — reusable small card (title, big number, optional trend).
- Create: `src/features/hr/shared/PendingItemsList.tsx` — list with per-row link to the owning instance detail.
- Create: `src/features/hr/dashboard/pages/HrOverviewPage.tsx` — 5 KPI cards + pending items + "New requisition" CTA.
- Modify: `src/routes/app/hr.routes.tsx` — add `/hr` route pointing at the overview.
- Modify: `src/components/layout/navConfig.ts` — promote "HR" label to link to `/hr` (the Overview); keep Requisitions / Applicants / Employees / Onboarding as sub-items.

- [ ] Build + vitest + commit: `hr(plan4): HR overview page`.

---

## Phase B — Global Applicant Inbox

### Task B1: Backend search+filter endpoint

**Files:**
- Modify: `app/hr/recruiting/applicant_services.py` — add `search_applicants(db, *, q, requisition_id, stage, source, since, limit, offset)`. Joins `hr_applications` when any requisition/stage filter is set.
- Modify: `app/hr/recruiting/applicant_router.py` — `GET /hr/applicants` supports `q`, `requisition_id`, `stage`, `source`, `since` query params.
- Create: `tests/hr/test_applicant_inbox.py` — query by name substring, stage, requisition.

- [ ] Commit: `hr(plan4): applicant inbox search + filter endpoint`.

### Task B2: ApplicantInboxPage

**Files (ReactCRM):**
- Create: `src/features/hr/recruiting/pages/ApplicantInboxPage.tsx` — table with filter chips (stage) + requisition dropdown + text search; reuses the Plan 2 applicant row component.
- Modify: `src/routes/app/hr.routes.tsx` — add `/hr/inbox` route.
- Modify: `src/features/hr/index.ts` — re-export.
- Modify: `src/components/layout/navConfig.ts` — add "Inbox" under HR.

- [ ] Build + commit: `hr(plan4): ApplicantInboxPage with filters`.

---

## Phase C — Recruiting message template admin

### Task C1: Backend CRUD

**Files:**
- Create: `app/hr/recruiting/templates_admin_schemas.py` — `MessageTemplateOut`, `MessageTemplatePatch`.
- Create: `app/hr/recruiting/templates_admin_router.py` — `GET /hr/recruiting/message-templates` (list 5 seeded), `PATCH /hr/recruiting/message-templates/{stage}` (body text + active flag; write_audit).
- Modify: `app/hr/router.py` — include.
- Create: `tests/hr/test_message_templates_admin.py`.

Tests (4):
- List returns 5 seeded.
- PATCH updates body + bumps updated_at.
- PATCH audit row written.
- Unknown stage → 404.

- [ ] Commit: `hr(plan4): recruiting message template admin CRUD`.

### Task C2: Frontend admin page

**Files (ReactCRM):**
- Create: `src/features/hr/recruiting/api-templates.ts` — `useMessageTemplates()`, `useUpdateMessageTemplate(stage)`.
- Create: `src/features/hr/recruiting/pages/MessageTemplatesAdminPage.tsx` — table of 5 stages × (body textarea + active toggle + save); inline autosave on blur with optimistic update.
- Modify: `src/routes/app/hr.routes.tsx` — `/hr/settings/message-templates`.
- Modify: `src/components/layout/navConfig.ts` — add "Message Templates" under HR (or nest under a new Settings sub-group if nav starts crowding).

- [ ] Build + commit: `hr(plan4): message template admin page`.

---

## Phase D — Mobile pass

### Task D1: Verify + fix responsive breakpoints

Scope: manual review of every HR page under 375 px width. Fix touched by:
- `RequisitionsListPage` — stack the "New" button below header on xs.
- `RequisitionDetailPage` — pipeline pills wrap; applicant rows stack name+email above buttons on xs.
- `ApplicantDetailPage` — already fine.
- `ApplicantInboxPage` — filters become a drawer on xs.
- `HrOverviewPage` — KPI grid `grid-cols-1 md:grid-cols-3`.
- `MessageTemplatesAdminPage` — table becomes stacked cards on xs.

**Files:** touch the Tailwind classes only on existing pages. No new files.

- [ ] Playwright test at 375 px viewport for the overview + list pages (headless, just asserting no horizontal overflow).

- [ ] Commit: `hr(plan4): mobile responsive pass`.

---

## Phase E — Deploy + verify

### Task E1: Merge, push, verify

1. Merge `feature/hr-polish` → master.
2. Push. Await Railway redeploy.
3. `curl -X POST /health/db/migrate-hr` — expect `version_after: "104"` (no new migrations in Plan 4).
4. Run Playwright (`hr-polish.spec.ts` + existing HR specs) — expect all green.
5. Milestone commit.

---

## Self-Review

- [x] Spec §5.6 message templates admin: list + edit landed.
- [x] Spec §10.9 module dashboard: HR overview with KPIs + mixed pending-items inbox.
- [x] Spec §13.4 v1.1 picks actioned: message template admin UI shipped; template-editor UI and LLM resume parsing remain deferred.
- [x] Mobile responsive per user's frontend rules.
- [x] Zod validation on every new endpoint.
- [x] All frontend routes at `/hr/...` (no `/app/` prefix, per CLAUDE.md).

### Deferred to v1.2+

- DocuSign integration.
- Admin template editor (workflow template authoring UI, beyond seed migrations).
- Admin PDF field-drawing UI for esign templates.
- Structured interview scorecards.
- ADP API auto-provisioning.
- Resume LLM parsing.
- Offer-letter PDF generation.
- Candidate video-interview scheduling.
- Health-insurance enrollment automation.
