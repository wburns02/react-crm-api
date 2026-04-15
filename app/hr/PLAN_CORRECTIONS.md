# Plan Corrections (from Task A1 reconciliation)

Applied to Plan 1 after A1 surfaced real deltas between spec and codebase. These override the plan text where they conflict.

## 1. `api_users.id` is Integer, not UUID

**Decision:** All FKs to `api_users.id` are `Integer`, not `UUID`.

Affected columns across the plan (find-and-replace):
- `hr_audit_log.actor_user_id` → `Integer FK api_users.id`
- `hr_role_assignments.user_id` → `Integer`
- `hr_workflow_templates.created_by` → `Integer`
- `hr_workflow_instances.started_by` → `Integer`
- `hr_workflow_tasks.assignee_user_id` → `Integer`
- `hr_workflow_tasks.completed_by` → `Integer`
- `hr_workflow_task_comments.user_id` → `Integer`
- `hr_workflow_task_attachments.uploaded_by` → `Integer`
- `hr_requisitions.hiring_manager_id` → `Integer`
- `hr_requisitions.created_by` → `Integer`
- `hr_signature_requests.signer_user_id` → `Integer`

Pydantic schemas: the user-id fields that used `UUIDStr` need to be `int`. Keep `UUIDStr` for non-user UUID columns (template_id, instance_id, subject_id, etc.).

Rationale: the existing `workflow_automations.created_by` is declared UUID FK api_users.id in SQLAlchemy but this is a pre-existing bug. Don't propagate it.

## 2. Polymorphic `subject_id` semantics

`hr_workflow_instances.subject_type` values and what `subject_id` references:
- `employee` → `technicians.id` (UUID). Field staff only in v1; office staff without a technician row cannot be subjects.
- `applicant` → `hr_applicants.id` (UUID; defined in Plan 2).
- `truck` → `assets.id` where `asset_type = 'vehicle'` (UUID).
- `customer` → `customers.id` (UUID; already exists).

No DB-level FK; application-level validation only.

## 3. Fleet / trucks table

`hr_truck_assignments.truck_id` FKs to `assets.id` (UUID) with application-level filter on `asset_type = 'vehicle'`. No dedicated trucks table exists today.

(Note: Plan 1 only creates the workflow `assignment` task kind; `hr_truck_assignments` itself is deferred to Plan 3. No migration impact in Plan 1 from this decision.)

## 4. Email transport = Brevo

All HR email notifications go through `EmailService` imported from `app.services.email_service`. Do not introduce SendGrid or create new transports. The stale `app/services/sendgrid_service.py` is not the production path.

## 5. Tests use Bearer + SQLite, not cookies + Postgres

- HR test fixtures compose on the existing `authenticated_client` / `admin_client` fixtures from `tests/conftest.py`. No cookie flow needed in tests.
- Tests run against in-memory SQLite (StaticPool). HR models must be SQLite-compatible:
  - `INET` column type must fall back to `String(45)` on SQLite. Use a TypeDecorator or the `sqlalchemy.dialects.postgresql.INET().with_variant(String(45), "sqlite")` pattern.
  - `JSONB` avoided entirely — use `JSON` (generic) which works on both backends.
  - `UUID(as_uuid=True)` works on SQLite via pypdf; no change needed.
- Production/Railway runs Postgres; Alembic migrations only target Postgres.
- No test-time Alembic; `Base.metadata.create_all` is used. All new HR models must be registered in `app/models/__init__.py` so they land on test DB.

## 6. Auth fixture in plan Task E4

The plan's `authed_client` placeholder (`NotImplementedError`) is replaced by: import existing `authenticated_client` / `admin_client` from `tests/conftest.py` and use them directly. No new fixture needed for HR admin endpoints unless a role gate requires it (C1 resolver may need an `hr_admin_user`).

## 7. Downstream plan edits

These corrections affect Tasks B1, B2, C1, D1, E1, E4, F1, F2, G1, G3. When each task is dispatched, the implementer subagent receives this file as context.
