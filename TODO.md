# react-crm-api - Backend Feature Migration

Backend API tasks for ReactCRM feature parity with Legacy CRM.

## Format
- `[ ]` Pending | `[~]` In-progress | `[x]` Completed
- `PRIORITY:HIGH` - Process first

---

## PHASE 1: CALL CENTER

- [ ] PRIORITY:HIGH - Create app/models/call_log.py with CallLog model
- [ ] Create app/models/call_disposition.py with CallDisposition model
- [ ] Create app/schemas/calls.py with Pydantic schemas
- [ ] Create app/api/v2/calls.py router with CRUD endpoints
- [ ] Add calls router to app/api/v2/router.py
- [ ] Create Alembic migration for call_logs and call_dispositions tables
- [ ] Run alembic upgrade head and verify tables created

---

## PHASE 2: COMPLIANCE

- [ ] Create app/models/license.py with License model
- [ ] Create app/models/certification.py with Certification model
- [ ] Create app/models/inspection.py with Inspection model
- [ ] Create app/schemas/compliance.py with Pydantic schemas
- [ ] Create app/api/v2/compliance.py router
- [ ] Add compliance router to app/api/v2/router.py
- [ ] Create Alembic migration for compliance tables
- [ ] Run alembic upgrade head

---

## PHASE 3: CONTRACTS

- [ ] Create app/models/contract.py with Contract model
- [ ] Create app/models/contract_template.py with ContractTemplate model
- [ ] Create app/schemas/contracts.py with Pydantic schemas
- [ ] Create app/api/v2/contracts.py router
- [ ] Add contracts router to app/api/v2/router.py
- [ ] Create Alembic migration for contracts tables
- [ ] Run alembic upgrade head

---

## PHASE 4: TIME TRACKING

- [ ] Create app/models/time_entry.py with TimeEntry model
- [ ] Create app/schemas/time_tracking.py with Pydantic schemas
- [ ] Create app/api/v2/time_tracking.py router (clock-in, clock-out, timesheets)
- [ ] Add time_tracking router to app/api/v2/router.py
- [ ] Create Alembic migration for time_entries table
- [ ] Run alembic upgrade head

---

## PHASE 5: JOB COSTING

- [ ] Create app/models/job_cost.py with JobCost model
- [ ] Create app/schemas/job_costing.py with Pydantic schemas
- [ ] Add costs endpoints to app/api/v2/work_orders.py
- [ ] Create app/api/v2/job_costing.py for summary/profitability reports
- [ ] Create Alembic migration for job_costs table
- [ ] Run alembic upgrade head

---

## PHASE 6: DATA IMPORT

- [ ] Create app/services/csv_importer.py with validation logic
- [ ] Create app/api/v2/import_data.py router
- [ ] Add CSV template generation endpoints
- [ ] Add import_data router to app/api/v2/router.py

---

## PHASE 7: ENHANCED REPORTS

- [ ] Add revenue-by-service endpoint to app/api/v2/reports.py
- [ ] Add revenue-by-technician endpoint
- [ ] Add revenue-by-location endpoint
- [ ] Add customer-lifetime-value endpoint
- [ ] Add technician-performance endpoint

---

## TESTING

- [ ] Run pytest and fix any failures
- [ ] Add tests for new call endpoints
- [ ] Add tests for compliance endpoints
- [ ] Add tests for contracts endpoints
- [ ] Add tests for time tracking endpoints

---

## Notes

- Reference legacy models at C:/Users/Will/crm-work/Mac-Septic-CRM/crm_customer_module_fixed/backend/application/models/
- Follow existing patterns (async SQLAlchemy, Pydantic v2)
- Run migrations on Railway after local verification

---

*Processed by: autonomous-claude*
