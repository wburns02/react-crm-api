# Incident Report: December 30, 2024

## Summary
Chaotic debugging session with multiple issues discovered and created.

---

## Issues Discovered

### 1. Duplicate Railway Deployments
**Severity: HIGH**

The GitHub repo `wburns02/react-crm-api` was connected to TWO Railway projects:
- **Mac-CRM-React** → `react-crm-api` service (CORRECT)
- **diplomatic-freedom** → `web` service (INCORRECT - should be deleted)

Every push triggered deployments to BOTH projects, wasting resources and causing confusion.

**Resolution Required:**
1. Go to Railway → diplomatic-freedom project
2. Settings → Danger Zone → Delete Project
   OR
   Go to the `web` service → Settings → Disconnect GitHub repo

### 2. Technicians Endpoint 500 Error
**Severity: MEDIUM**

The `/api/v2/technicians/` endpoint returns 500 Internal Server Error while `/api/v2/technicians/list-raw` works perfectly with identical code.

**Root Cause:** Still under investigation. Possibly related to:
- FastAPI trailing slash redirect (307) going to HTTP instead of HTTPS
- Response model validation issues
- Route ordering conflicts

**Workaround:** Frontend can use `/api/v2/technicians/list-raw` until fixed.

### 3. Rapid Commit Churn
**Severity: LOW**

Too many rapid commits were made trying to debug the technicians issue:
- fix: Fix status shadowing bug in payments.py
- fix: Improve technicians endpoint datetime handling
- debug: Add technicians debug endpoints
- fix: Change email field to str
- fix: Remove response_model from technicians
- fix: Remove try-except from technicians
- fix: Use empty string route
- debug: Return error details from technicians

This caused deployment instability with multiple restarts.

---

## What Went Wrong

1. **Debugging without logs** - Made code changes without checking Railway logs for actual errors
2. **Rapid-fire commits** - Pushed too many small changes instead of testing locally first
3. **Didn't notice duplicate deployments** - Wasn't aware of diplomatic-freedom project
4. **Wrong initial diagnosis** - Spent time on response model validation when issue might be routing

---

## Fixes Made (that are correct)

### payments.py
- Renamed `status` import to `http_status` to avoid parameter shadowing
- Changed `status` parameter to `payment_status`

### technicians.py
- Changed `technician_id` parameter type from `int` to `str` (UUIDs)
- Added `/debug` and `/list-raw` endpoints for diagnostics

### schemas/technician.py
- Changed `email` from `EmailStr` to `str` (database has empty strings)
- Made `first_name` and `last_name` have defaults
- Changed `created_at`/`updated_at` from `datetime` to `str`

### schemas/payment.py
- Updated to match Flask database schema (work_order_id instead of invoice_id)

### models/
- Invoice model updated to use UUID types
- Payment model updated to match Flask schema with Stripe fields

---

## Action Items

### Immediate
- [ ] Delete or disconnect diplomatic-freedom Railway project
- [ ] Wait for react-crm-api deployment to stabilize
- [ ] Check Railway logs for actual technicians error

### Short-term
- [ ] Fix technicians "/" endpoint properly
- [ ] Clean up debug endpoints once fixed
- [ ] Run Playwright tests to verify frontend

### Prevention
- [ ] Always check Railway dashboard before mass debugging
- [ ] Test locally before pushing when possible
- [ ] Check deployment logs instead of guessing at fixes
- [ ] Document Railway project architecture

---

## Railway Architecture (Correct)

```
Project: Mac-CRM-React
├── Mac-Septic-CRM (react.ecbtx.com) - React Frontend
├── react-crm-api (react-crm-api-production.up.railway.app) - FastAPI Backend
└── Postgres - Database

Project: diplomatic-freedom (TO BE DELETED)
└── web - Incorrectly connected to same GitHub repo
```

---

## Lesson Learned

Before debugging production issues:
1. Check Railway dashboard for deployment status
2. Check Railway logs for actual errors
3. Verify which projects are connected to the repo
4. Make changes methodically, not rapidly
5. Test locally if possible
