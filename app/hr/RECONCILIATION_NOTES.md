# HR Module Reconciliation Notes (Task A1)

Read-only audit of existing models and routers before adding the `app/hr/`
module. Purpose: catch naming / FK / route collisions before they happen.

## 1. User model (`app/models/user.py`)

- `__tablename__ = "api_users"`.
- **Primary key is `Integer`, NOT UUID.** Column: `id = Column(Integer, primary_key=True)`.
- Any new FK like `hr_audit_log.actor_user_id -> api_users.id` MUST be declared
  as `INTEGER` (not `UUID`). The plan doc / spec assume UUID — **this is the
  single biggest correction needed before B1**.
- `is_active` column exists (`Boolean, default=True`). Also has `is_admin`,
  `is_superuser`, `default_entity_id (UUID FK company_entities.id)`,
  `microsoft_id`, `microsoft_email`.
- Precedent inconsistency: `workflow_automations.created_by` is declared
  `UUID FK api_users.id` in SQLAlchemy — that FK is already type-mismatched
  against the int PK. Do not copy that pattern.

## 2. Technician model (`app/models/technician.py`)

- Stands alone. **Does NOT extend User.** No FK from `technicians` to
  `api_users`. They are two parallel identity rows today.
- `technicians.id` is native `UUID`. Has `email`, `employee_id`, `hire_date`,
  `department`, `is_active`, pay rates, PTO, home address, `entity_id`,
  `microsoft_user_id/email`.
- Implication for HR: `hr_employee_profile` (or any new employee row) should
  FK to `technicians.id` (UUID) for field staff. Office staff without a
  technicians row will need either (a) a nullable technician_id or (b) a
  separate link to `api_users.id` (int). Decide in A2/B1.

## 3. Certification model (`app/models/certification.py`)

- Table `certifications`. PK UUID. Columns: `name`, `certification_type`
  (free-text: safety/equipment/specialty), `certification_number`,
  `issuing_organization`, `technician_id (String(36), NOT a real FK)`,
  `technician_name`, `issue_date`, `expiry_date`, `status` (free-text),
  `renewal_reminder_sent`, `requires_renewal`, `renewal_interval_months`,
  `training_hours`, `training_date`, `training_provider`, `document_url`,
  `notes`.
- **No enums.** `certification_type` and `status` are untyped strings.
- Does NOT explicitly cover TCEQ OS-0, TCEQ MP, DOT medical, or CDL — it is a
  generic bag. Those would live as arbitrary strings in `certification_type` /
  `name`.
- **Recommendation: introduce `hr_employee_certifications`** (new table).
  Reasons: (1) `technician_id` is a loose String(36), not a real FK; (2) no
  enum discipline; (3) HR needs TCEQ/DOT/CDL-specific fields (endorsements,
  medical card expiry, restriction codes) that don't fit. Leave `certifications`
  in place for the legacy tech-dashboard UI; optionally backfill-link later.

## 4. License model (`app/models/license.py`)

- Table `licenses`. Covers **both** business licenses and technician licenses
  via `holder_type` ("business" | "technician") and `holder_id (String(36))`.
  `license_type` is free text ("business", "septic_installer", "plumber", ...).
  Includes `issuing_state (String(2))`, `expiry_date` (NOT NULL), `status`.
- This is professional / business licensing — not a driver's license table.
  Driver licensing currently lives only as the two fields on `technicians`
  (`license_number`, `license_expiry`).
- **Recommendation: introduce new `hr_employee_documents`** for HR-owned
  artifacts (I-9, W-4, handbook ack, signed offer, background-check release,
  DOT medical card PDF, CDL copy, DL copy). The existing `licenses` table is
  about compliance expiry tracking for the business, not document storage, and
  mixing them would pollute both use cases. Keep `licenses` as-is.

## 5. `workflow_automation.py` (Zapier-style)

- Two tables: `workflow_automations` (id UUID, entity_id, name, trigger_type,
  trigger_config JSON, **nodes JSON, edges JSON**, status, run_count,
  last_run_at, created_by) and `workflow_executions` (workflow_id FK,
  trigger_event JSON, steps_executed JSON, status, error_message).
- Confirmed: this **is** the Zapier-style event→nodes→edges visual-builder
  model. It is user-authored automations driven by the frontend canvas.
- **No collision** with the proposed `hr_workflow_templates`,
  `hr_workflow_instances`, `hr_workflow_tasks`. Different table names,
  different semantics (HR workflows are DAG state machines per-hire/per-fire,
  not user-drawn triggers).

## 6. `app/api/v2/onboarding.py`

- Mounted at `prefix="/onboarding"` in `app/api/v2/router.py` (line 286).
- Full path: `/api/v2/onboarding/...`.
- Purpose: **customer / tenant setup wizard + help center + tutorials + data
  import + release notes.** NOT employee onboarding. Endpoints are `/progress`,
  `/steps/{step_id}`, `/complete`, `/recommendations`, `/tour/{feature_id}`,
  `/import/jobs`, `/tutorials`, `/help/*`, `/releases`.
- **No collision** with planned `/api/v2/hr/onboarding/*` — different prefix
  segment (`hr/onboarding` vs `onboarding`).

## 7. `app/api/v2/workflow_automations.py`

- Mounted at `prefix="/automations"` (router.py line 370). Full path
  `/api/v2/automations/...`. Routes: list/create/`/templates`, `/{id}`,
  `/{id}/test`, `/{id}/toggle`, `/{id}/executions`.
- **No collision** with planned `/api/v2/hr/workflows/*`.

## 8. `app/api/v2/employee_portal.py` — signature capture pattern

- Router mounted at `prefix="/employee"`. For HR e-sign pattern reuse, note:
  - `POST /employee/jobs/{work_order_id}/signature` — handler
    `capture_customer_signature` (line 1190). Accepts base64 `signature_data`
    in a request body, stores as a `WorkOrderPhoto` row with
    `photo_type="signature"`, appends a signer-name note to the work order.
  - `POST /employee/jobs/{job_id}/complete` (line 564) takes
    `customer_signature` and `technician_signature` params (Optional[str]).
- Not a generic e-sign framework — it's a single base64 field persisted as a
  photo. For HR G-series tasks we will build a proper document-bound e-sign
  with audit metadata; this is informational only.

## 9. Fuel card data

- Grep for `fuel_card` / `fuel-card` / `FuelCard` in `app/` and
  `alembic/versions/`: **zero matches** outside the HR spec/plan docs. No
  existing table, no existing model, no migration. HR module is free to define
  `hr_fuel_cards` (or similar) without conflict.

## 10. Trucks / fleet

- **No `trucks` table and no dedicated fleet table exists.** Truck / vehicle
  assets live in the generic `assets` table (`app/models/asset.py`), keyed by
  `asset_type = "vehicle"` with `category` like `"vacuum_truck"`. The Asset
  model has a `samsara_vehicle_id` column for telematics linkage.
- `technicians.assigned_vehicle` is a free-text `String(100)` — not an FK.
- **Recommendation: `hr_truck_assignments.truck_id` should FK to
  `assets.id`** (UUID), with an application-level filter on
  `asset_type='vehicle'`. Alternative: introduce a dedicated `trucks` view or
  table later. Flag for decision in F1/plan update.

## 11. Email transport

- Grep for sendgrid / mailgun / smtplib / send_email: project uses **Brevo**
  (formerly Sendinblue) via `app/services/email_service.py`. No SendGrid
  client is actually wired up despite `sendgrid_service.py` existing (that
  file is vestigial / unused — verify before C-series if it matters).
- Uses plain `httpx` POST to `https://api.brevo.com/v3/smtp/email`, config
  from `settings.BREVO_API_KEY`, `settings.EMAIL_FROM_ADDRESS`,
  `settings.EMAIL_FROM_NAME`.
- **HR should import `EmailService` from `app.services.email_service`** for
  all email notifications. SMS transport needs a separate audit (not in this
  task's scope).

## 12. Auth fixture pattern in `tests/conftest.py`

- Tests use an **in-memory SQLite** (`sqlite+aiosqlite://`, StaticPool) with
  `Base.metadata.create_all` — no Alembic in tests. All HR models must be
  importable and SQLite-compatible (watch PG-specific column types).
- DB override: `fastapi_app.dependency_overrides[get_db] = override_get_db`
  injecting the per-test `AsyncSession`.
- Auth: **Bearer token in `Authorization` header**, NOT cookies. Token minted
  via `create_access_token({"sub": str(user.id), "email": ...})` from
  `app.api.deps`. Fixtures: `client` (unauthenticated), `authenticated_client`
  (regular user), `admin_client` (superuser). `User.id` is int so `sub` is the
  stringified int.
- Note: this contradicts the "cookie auth only" production rule — tests bypass
  cookies entirely via Bearer. HR test fixtures should follow the same
  pattern: depend on `authenticated_client` / `admin_client` and add any
  HR-specific seed data as additional fixtures.
- **Straightforward to match** — just compose on top of `authenticated_client`
  and add an `hr_admin_user` fixture if role-gated endpoints need it (C1
  resolver work).

---

## Summary of risks / corrections to propagate

1. **`api_users.id` is Integer, not UUID.** Spec/plan need correction for
   every FK that targets it (audit log actor, workflow created_by, etc.).
2. `technicians` ↔ `api_users` are **not linked**. Decide canonical employee
   identity row in A2/B1.
3. Use `EmailService` (Brevo), not SendGrid.
4. Trucks live in `assets` table (`asset_type='vehicle'`), no dedicated table.
5. Tests use Bearer, not cookies — HR fixtures follow that.
6. No naming collisions found for `hr_*` tables or `/api/v2/hr/*` routes.
