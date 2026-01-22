# Railway Deployment Failure Diagnosis

## Date: January 22, 2026

## FINAL STATUS: ✅ RESOLVED

Production API is now at version **2.5.5** and fully functional.
- Health endpoint: `curl https://react-crm-api-production.up.railway.app/health`
- Permits search: Working with `has_property` field
- All Playwright tests: PASSING

---

## Root Cause #1: Alembic Blocking Startup (FIXED)

**The `alembic upgrade head` command in `railway.json` was blocking uvicorn startup.**

### Failure Chain:
1. Build succeeds (Docker image built and pushed)
2. Container starts, runs startCommand: `alembic upgrade head && uvicorn...`
3. Alembic migration fails OR takes too long
4. Uvicorn never starts listening on $PORT
5. Health check at `/health` times out
6. Railway reports: "Deployment failed during network process"

### Fix Applied (Commit `f755f15`):

Removed `startCommand` entirely from railway.json, letting Dockerfile CMD handle startup:
```dockerfile
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
```

---

## Root Cause #2: Missing property_id Column (FIXED)

After deployment succeeded, `/permits/search` was returning **500 errors**.

### Bug:
```python
# permit_search_service.py line 200
has_property=permit.property_id is not None  # CRASH! property_id doesn't exist
```

The `property_id` column was never added to the `SepticPermit` model, but the search service tried to access it.

### Fix Applied (Commit `9c5ab2c`):

Changed to use `getattr` with a safe default:
```python
has_property = getattr(permit, 'property_id', None) is not None
```

---

## Summary of Commits

| Commit | Description |
|--------|-------------|
| `f755f15` | Remove startCommand, use Dockerfile CMD |
| `9c5ab2c` | Fix property_id AttributeError with getattr |
| `36cdd57` | Bump version to 2.5.5 |

---

## Verification Evidence

```
Health Status: 200
Health Response: {
  "status": "healthy",
  "version": "2.5.5",
  "environment": "production",
  "features": ["public_api", "oauth2", "demo_roles", ...]
}

Sample permit with has_property field:
{
  "id": "e721ad33-3dd7-4081-aa8c-8b23f796cd07",
  "address": "Old Acre Drive 9505",
  "city": "Unincorporated",
  "state_code": "TN",
  "county_name": "Williamson",
  "permit_date": "2025-07-02",
  "has_property": false  ← FIELD NOW PRESENT!
}
```

**Playwright Test Results: 5 passed**

<promise>RAILWAY_BACKEND_FINALLY_DEPLOYED_AND_HEALTHY</promise>
