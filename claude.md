# Claude Code Documentation - React CRM Backend (FastAPI)

> **IMPORTANT**: This document contains critical rules and patterns that MUST be followed to prevent recurring issues.

---

## MANDATORY BROWSER AUTOMATION (PLAYWRIGHT REQUIRED)

### Non-Negotiable Rule

If a task involves any of the following:
- Web UI interaction
- Clicking buttons, filling forms, navigation, login flows
- CRM UI verification or inspection
- "Go to this page and check X"
- "Try this in the browser"
- "Confirm behavior in the frontend"

**YOU MUST USE PLAYWRIGHT.**

DO NOT ask the user to:
- Open a browser
- Click anything
- Log in manually
- "Try this and tell me what happens"

That is explicitly forbidden.

### Required Behavior

1. Default to Playwright for all browser/UI work
2. Write the Playwright script yourself
3. Run the steps programmatically
4. Report results directly (DOM state, screenshots, console output, errors)

If browser interaction is possible via Playwright, you are expected to do it.

### Allowed Assumptions

- Playwright is available
- Chromium is acceptable unless otherwise specified
- Headless mode is acceptable unless debugging is requested
- Auth flows may be automated unless explicitly restricted

Do not ask permission to use Playwright.
Do not claim you "cannot" do browser automation.

---

## PLAYWRIGHT ENFORCEMENT (CRM.ECBTX.COM ONLY)

### Scope Lock

This rule applies ONLY to the Flask CRM at:
- https://crm.ecbtx.com
- https://crm.ecbtx.com/login
- Any /api/* endpoints under https://crm.ecbtx.com

DO NOT use or reference React (react.ecbtx.com) for any Playwright run.

### Hard Requirement: Run Playwright Before Responding

If the request involves ANY of the following on crm.ecbtx.com:
- UI behavior / navigation / clicking / forms
- login/auth/session/JWT acquisition
- verifying a page renders / checking UI state
- reproducing an error seen in the CRM UI
- "go here and see if X happens"
- confirming an endpoint response in-browser

**You MUST run Playwright first.**

You may NOT respond with conclusions, guesses, or manual steps without a Playwright run.

### Mandatory Output Gate

Every response to a UI/Browser request MUST begin with:

```
PLAYWRIGHT RUN RESULTS (crm.ecbtx.com):
```

And MUST include ALL of:
1. Target URL(s) visited (must start with https://crm.ecbtx.com)
2. Timestamp of run (local time OK)
3. Actions performed (explicit step list)
4. Observed results (what happened)
5. Evidence bundle (REQUIRED):
   - At least one screenshot path, AND
   - Console error output (even if "none"), AND
   - Network failures summary (even if "none")

If you cannot provide screenshot + console + network, you are not allowed to answer.

### Absolutely Forbidden Responses

You are explicitly forbidden from replying with:
- "Please try it manually"
- "Open the browser and click..."
- "I can't run Playwright here"
- "I don't have access to your environment"
- "I can only suggest steps"
- Any answer that is not based on a Playwright run

### Failure Protocol (Must Retry Twice)

If the first Playwright run fails, you MUST:
1. Capture screenshot (or attempt; if screenshot fails, say why)
2. Capture console + network logs
3. Retry with improved strategy
4. Only after two failed attempts may you ask the user for additional context

---

## PROJECT ARCHITECTURE

### Tech Stack

| Layer | Technology | Version |
|-------|------------|---------|
| Framework | FastAPI | Latest |
| Language | Python | 3.12 |
| Database | PostgreSQL | 16 |
| ORM | SQLAlchemy (async) | 2.x |
| Migrations | Alembic | Latest |
| Auth | JWT + bcrypt | - |
| Testing | pytest + pytest-asyncio | - |
| Deployment | Railway | - |

### Directory Structure

```
app/
├── main.py              # FastAPI app initialization
├── config.py            # Settings & environment validation
├── database.py          # SQLAlchemy async setup
├── api/
│   ├── deps.py          # Authentication/dependency injection
│   └── v2/              # API v2 routes (all endpoints)
│       ├── router.py    # Main router aggregation
│       ├── auth.py      # Login, logout, register, /me
│       ├── customers.py
│       ├── work_orders.py
│       ├── technicians.py
│       └── [... 15 more routers]
├── models/              # SQLAlchemy ORM models (14 tables)
├── schemas/             # Pydantic request/response schemas
├── security/            # RBAC, rate limiting, validators
│   ├── rbac.py
│   ├── rate_limiter.py
│   └── twilio_validator.py
├── services/            # Business logic services
└── webhooks/            # Webhook handlers
```

### Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                              │
│  React App @ react.ecbtx.com                                │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS API calls
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  THIS BACKEND (FastAPI)                      │
│  @ react-crm-api-production.up.railway.app                  │
│  Base URL: /api/v2                                          │
│  Port: 5001                                                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                       DATABASE                               │
│  PostgreSQL 16 (Railway)                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## CRITICAL KNOWN ISSUES

### ISSUE 1: Technicians Endpoint 500 Error

**Status**: UNRESOLVED
**Endpoint**: `GET /api/v2/technicians/`
**Symptoms**: Returns 500 error in production

**Workaround**:
```python
# Use the raw endpoint instead:
GET /api/v2/technicians/list-raw
```

**Possible Causes**:
1. FastAPI 307 redirect issue (trailing slash)
2. Response model validation failure
3. Route ordering conflict

**Files Affected**: `app/api/v2/technicians.py`

### ISSUE 2: Duplicate Railway Deployments

**Action Required**: Delete `diplomatic-freedom` project, keep `Mac-CRM-React`

### ISSUE 3: Email Marketing API Path

The email marketing endpoints incorrectly include `/api` prefix which conflicts with base URL:
```python
# WRONG - creates /api/v2/api/email-marketing
'/api/email-marketing/...'

# CORRECT
'/email-marketing/...'
```

---

## API ENDPOINT REFERENCE

### Base URL

```
Production: https://react-crm-api-production.up.railway.app/api/v2
Local:      http://localhost:5001/api/v2
```

### All Routers (18 total)

| Prefix | Purpose | Notes |
|--------|---------|-------|
| `/auth` | Authentication | login, logout, register, /me |
| `/customers` | Customer CRUD | Trailing slash required |
| `/prospects` | Prospect management | Sales pipeline |
| `/work-orders` | Jobs/scheduling | NO trailing slash |
| `/communications` | SMS/email | Rate limited |
| `/technicians` | Staff management | **HAS 500 BUG - use /list-raw** |
| `/invoices` | Billing | NO trailing slash |
| `/payments` | Payment tracking | NO trailing slash |
| `/quotes` | Quotations | Convert to WO |
| `/dashboard` | Analytics | Stats, aggregations |
| `/schedule` | Calendar | Availability |
| `/reports` | Reports | Analytics |
| `/ringcentral` | RingCentral | Placeholder |
| `/sms-consent` | SMS opt-in | Consent management |
| `/payroll` | Payroll | Hours tracking |
| `/activities` | Interaction log | Trailing slash required |
| `/tickets` | Support tickets | CRUD |
| `/equipment` | Equipment | CRUD |
| `/inventory` | Parts inventory | With adjustments |

### Trailing Slash Convention

**WITH trailing slash** (FastAPI auto-redirects):
```
/customers/
/technicians/
/activities/
```

**WITHOUT trailing slash**:
```
/work-orders
/invoices
/payments
```

### Standard CRUD Pattern

```
GET    /{resource}/          # List (paginated)
POST   /{resource}/          # Create (201)
GET    /{resource}/{id}      # Get single
PATCH  /{resource}/{id}      # Update
DELETE /{resource}/{id}      # Delete (204)
```

### Pagination Parameters

```python
page: int = Query(1, ge=1)
page_size: int = Query(20, ge=1, le=500)
```

### List Response Format

```json
{
  "items": [...],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

---

## AUTHENTICATION

### Auth Flow

1. `POST /api/v2/auth/login` with `{ email, password }`
2. Returns `{ access_token, token, token_type: "bearer" }`
3. Store token, include in subsequent requests:
   ```
   Authorization: Bearer <token>
   ```
4. Token expires in 30 minutes (configurable)

### Auth Endpoints

```
POST   /auth/login         # Email + password -> JWT token
POST   /auth/logout        # Clear session cookie
GET    /auth/me            # Get current user info
POST   /auth/register      # Create new account
```

### Password Hashing

- Algorithm: bcrypt
- Cost factor: 4 rounds with salt
- Never logged, never returned in responses

### JWT Configuration

```python
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # Default
SECRET_KEY = "..."  # Min 32 chars in production
```

### Dependency Injection

```python
from app.api.deps import CurrentUser, DbSession

@router.get("/")
async def list_items(
    db: DbSession,
    current_user: CurrentUser
):
    ...
```

---

## DATABASE MODELS

### 14 Tables

| Model | Table | Key Fields |
|-------|-------|------------|
| User | `api_users` | id, email, hashed_password, is_active, is_superuser |
| Customer | `customers` | id, name, contact, address, customer_type, tags |
| WorkOrder | `work_orders` | id (UUID), customer_id, status, job_type, priority |
| Technician | `technicians` | id (UUID), name, skills[], license, pay_rates |
| Invoice | `invoices` | id (UUID), customer_id, invoice_number, status, amount |
| Payment | `payments` | id (UUID), invoice_id, amount, stripe_id, status |
| Quote | `quotes` | id (UUID), customer_id, amount, status |
| Message | `messages` | id, customer_id, type, status, content, twilio_sid |
| Activity | `activities` | id (UUID), customer_id, activity_type, description |
| SMSConsent | `sms_consent` | customer_id, is_opted_in, consent_timestamp |
| SMSConsentAudit | `sms_consent_audit` | customer_id, consent_action |
| Ticket | `tickets` | id (UUID), customer_id, title, status, priority |
| Equipment | `equipment` | id (UUID), name, type, specs, condition |
| InventoryItem | `inventory_items` | id (UUID), name, quantity, unit_cost |

### Key Enums

**WorkOrderStatus**:
```python
draft, scheduled, confirmed, enroute, on_site,
in_progress, completed, canceled, requires_followup
```

**JobType**:
```python
pumping, inspection, repair, installation, emergency,
maintenance, grease_trap, camera_inspection
```

**Priority**:
```python
low, normal, high, urgent, emergency
```

**InvoiceStatus**:
```python
draft, sent, paid, overdue, void
```

**ActivityType**:
```python
call, email, sms, note, meeting, task
```

### UUID Handling

Some models use String(36) for UUIDs, others use PostgreSQL UUID type:
```python
id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
# or
id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
```

---

## SECURITY FEATURES

### RBAC (Role-Based Access Control)

**File**: `app/security/rbac.py`

**Roles**: user, admin, superuser

**Permissions**:
```python
send_sms, send_email, view_customers, edit_customers,
delete_customers, manage_users, view_all_communications, admin_panel
```

### Rate Limiting

**File**: `app/security/rate_limiter.py`

- Per-user: 10/minute, 100/hour
- Per-destination: 5/hour to same phone number
- Returns HTTP 429 with Retry-After header

### Webhook Security (Twilio)

**File**: `app/security/twilio_validator.py`

- HMAC-SHA1 signature validation
- Validates X-Twilio-Signature header
- Returns 403 for invalid signatures

### Logging Security

**NEVER log**:
- JWT payloads
- Full phone numbers (only suffix)
- Message content
- Credentials in database URLs

---

## CONFIGURATION

### Environment Variables

**File**: `app/config.py`

```python
# Database
DATABASE_URL              # postgresql+asyncpg:// format

# Auth
SECRET_KEY               # Min 32 chars in production
ALGORITHM                # Default: HS256
ACCESS_TOKEN_EXPIRE_MINUTES  # Default: 30

# CORS
FRONTEND_URL             # Allowed origin

# Twilio
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_PHONE_NUMBER

# Environment
ENVIRONMENT              # development|staging|production
DEBUG                    # Logging level
DOCS_ENABLED             # Enable /docs and /redoc
```

### Production Validation

- Enforces strong SECRET_KEY (min 32 chars)
- Forces DEBUG=False
- Warns if Twilio credentials missing
- Warns if docs enabled

### Database URL Auto-Conversion

```python
# Automatically converts:
postgresql://...
# to:
postgresql+asyncpg://...
```

---

## DEVELOPMENT WORKFLOW

### Local Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db"
export SECRET_KEY="your-secret-key-min-32-chars"
export DEBUG=true

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --port 5001
```

### Docker Compose

```bash
docker-compose up -d
```

Services:
- `api`: FastAPI on port 5001
- `postgres`: PostgreSQL on port 5433

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest tests/test_security.py
```

**Test Database**: SQLite with aiosqlite (in-memory)

---

## ALEMBIC MIGRATIONS

### Location

`alembic/versions/`

### Creating a New Migration

```bash
alembic revision --autogenerate -m "description"
```

### Running Migrations

```bash
# Upgrade to latest
alembic upgrade head

# Downgrade one step
alembic downgrade -1

# Show current revision
alembic current
```

### Migration Conventions

- Use IF NOT EXISTS for idempotency
- Match Flask database schema
- Handle UUID columns with UUID type
- ARRAY columns for skills (PostgreSQL specific)

---

## CODE PATTERNS

### Async Database Operations

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

async def get_customers(db: AsyncSession):
    result = await db.execute(select(Customer))
    return result.scalars().all()
```

### Pagination Helper

```python
async def paginate(db, query, page, page_size):
    # Get total count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # Get paginated items
    items = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )

    return {
        "items": items.scalars().all(),
        "total": total,
        "page": page,
        "page_size": page_size
    }
```

### Error Responses

```python
from fastapi import HTTPException

# 401 - Unauthorized
raise HTTPException(status_code=401, detail="Could not validate credentials")

# 403 - Forbidden
raise HTTPException(status_code=403, detail="Insufficient permissions")

# 404 - Not Found
raise HTTPException(status_code=404, detail="Resource not found")

# 429 - Rate Limited
raise HTTPException(status_code=429, detail="Rate limit exceeded")
```

---

## CRITICAL FILES REFERENCE

### Core Application
- `app/main.py` - FastAPI app initialization, middleware
- `app/config.py` - Settings, env validation
- `app/database.py` - SQLAlchemy async engine setup

### Authentication
- `app/api/v2/auth.py` - Login, logout, register endpoints
- `app/api/deps.py` - CurrentUser, DbSession dependencies

### API Routes
- `app/api/v2/router.py` - Main router (includes all sub-routers)
- `app/api/v2/customers.py`
- `app/api/v2/work_orders.py`
- `app/api/v2/technicians.py` - **HAS 500 BUG**

### Models
- `app/models/__init__.py` - All model imports
- `app/models/customer.py`
- `app/models/work_order.py`
- `app/models/user.py`

### Security
- `app/security/rbac.py` - Role-based access control
- `app/security/rate_limiter.py` - Rate limiting
- `app/security/twilio_validator.py` - Webhook validation

### Schemas
- `app/schemas/customer.py`
- `app/schemas/work_order.py`
- `app/schemas/auth.py`

---

## DEPLOYMENT (Railway)

### Production URL

```
https://react-crm-api-production.up.railway.app/api/v2
```

### Health Check

```
GET /health -> {"status": "healthy"}
```

### Docker Configuration

**File**: `Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
# Install deps
RUN pip install --no-cache-dir -r requirements.txt
# Run as non-root
USER appuser
EXPOSE 5001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5001"]
```

### Auto-Migrations

Railway auto-runs `alembic upgrade head` on deployment.

---

## INCOMPLETE FEATURES / TODOs

1. **Email sending**: Not implemented, placeholder in `communications.py:211`
2. **Inventory adjustments**: Missing audit trail (should log to inventory_transactions)
3. **Quote to WorkOrder**: Create WO from quote not implemented

---

## DEBUGGING TIPS

### Check Logs

```bash
# Railway logs
railway logs

# Local with debug
DEBUG=true uvicorn app.main:app --reload
```

### Test Endpoint Manually

```bash
# Get token
curl -X POST "http://localhost:5001/api/v2/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"password"}'

# Use token
curl "http://localhost:5001/api/v2/customers/" \
  -H "Authorization: Bearer <token>"
```

### Database Inspection

```bash
# Connect to local postgres
psql -h localhost -p 5433 -U crm -d react_crm

# Show tables
\dt

# Show columns
\d customers
```

### Common Issues

1. **500 on technicians**: Use `/list-raw` endpoint instead
2. **401 errors**: Check token format `Bearer <token>` not just `<token>`
3. **CORS errors**: Ensure FRONTEND_URL is set correctly
4. **Async errors**: Use `await` with all db operations

---

## QUICK REFERENCE

### Adding a New Endpoint

1. Create model in `app/models/new_model.py`
2. Create schema in `app/schemas/new_model.py`
3. Create router in `app/api/v2/new_router.py`
4. Register in `app/api/v2/router.py`:
   ```python
   from app.api.v2.new_router import router as new_router
   api_router.include_router(new_router, prefix="/new-resource")
   ```
5. Create migration: `alembic revision --autogenerate -m "Add new_model"`
6. Run migration: `alembic upgrade head`

### Adding a New Migration

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "Add field to customer"

# Empty migration for manual SQL
alembic revision -m "Custom migration"

# Apply
alembic upgrade head
```

### Common Imports

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import CurrentUser, DbSession
from app.models import Customer
from app.schemas.customer import CustomerCreate, CustomerResponse
```
