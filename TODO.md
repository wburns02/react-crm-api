# react-crm-api Autonomous Task Queue

FastAPI backend for ReactCRM. Tasks are processed sequentially.

## Format
- `[ ]` Pending task
- `[~]` In-progress task
- `[x]` Completed task
- `PRIORITY:HIGH` - Urgent (processed first)
- `BLOCKED: reason` - Skipped until unblocked

---

## Current Sprint Tasks

### Critical Bugs
- [ ] PRIORITY:HIGH - Fix technicians endpoint 500 error (use /list-raw workaround pattern)
- [ ] Fix email marketing API path that incorrectly includes /api prefix

### Testing
- [ ] Run pytest and fix any failing tests
- [ ] Add integration tests for authentication flow
- [ ] Add tests for work_orders CRUD operations

### API Improvements
- [ ] Review and optimize slow database queries
- [ ] Add pagination to list endpoints that don't have it
- [ ] Implement rate limiting on public endpoints

### Code Quality
- [ ] Review SQLAlchemy models for missing indexes
- [ ] Add type hints to functions missing them
- [ ] Remove deprecated endpoints and clean up unused code

### Documentation
- [ ] Update OpenAPI schema descriptions
- [ ] Document webhook payload formats
- [ ] Add examples to Pydantic schemas

---

## Completed Tasks

<!-- Move completed tasks here -->

---

## Notes

- Run tests with: `pytest tests/ -v`
- Check API docs at: /docs (Swagger UI)
- Use Alembic for database migrations: `alembic upgrade head`
- NEVER modify production database directly

---

*Processed by: autonomous-claude*
