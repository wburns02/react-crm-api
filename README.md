# Mac Service Platform — Backend API

FastAPI backend for MAC Septic CRM. Python 3.12 + SQLAlchemy 2.0 async + PostgreSQL 16.

**Live:** https://react-crm-api-production.up.railway.app/api/v2
**Docs:** https://react-crm-api-production.up.railway.app/docs
**Health:** https://react-crm-api-production.up.railway.app/health

## Quick Start

```bash
git clone https://github.com/wburns02/react-crm-api.git
cd react-crm-api
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Set DATABASE_URL, SECRET_KEY
uvicorn app.main:app --reload --port 8000
```

## Tech Stack

- **FastAPI** with fully async endpoints
- **SQLAlchemy 2.0** async ORM — 40+ models, UUID primary keys
- **PostgreSQL 16** via asyncpg
- **Alembic** — 57 migration versions
- **Redis** — optional caching with circuit breaker fallback
- **Pydantic v2** — request/response validation

## Project Structure

```
app/
  api/
    v2/            # 70+ route modules (200+ endpoints)
      router.py    # Central router registration
      auth.py      # Login, register, MFA
      customers.py, work_orders.py, technicians.py, ...
      payroll.py, invoices.py, payments.py, ...
      ai_coaching.py, ai_jobs.py, ai.py
      samsara.py, ringcentral.py, twilio.py
    deps.py        # Dependency injection (DbSession, CurrentUser)
  models/          # SQLAlchemy models (UUID PKs)
  schemas/         # Pydantic schemas
  services/        # Business logic (Clover, Google Ads, Samsara, etc.)
  core/
    config.py      # Settings from environment
    security.py    # JWT, password hashing, MFA
    database.py    # Async engine + session factory
migrations/        # Alembic versions (001-057)
```

## Key Architecture

- **Auth**: Cookie-based JWT (`session` cookie). No Bearer token.
- **IDs**: All business entities use native PostgreSQL UUID.
- **Async**: All DB operations use `await db.execute()`. Never use sync `.query()`.
- **Caching**: Redis with circuit breaker. Falls back gracefully when unavailable.
- **Background jobs**: APScheduler for RingCentral sync, reminders.
- **Real-time**: WebSocket at `/api/v2/ws`.
- **Route ordering**: Static routes MUST come before `/{id}` catch-all routes.

## Integrations

| Service | Status | Config |
|---------|--------|--------|
| Clover POS | Active | `CLOVER_MERCHANT_ID`, `CLOVER_API_KEY` |
| Samsara GPS | Active | `SAMSARA_API_TOKEN` |
| RingCentral | Active | `RINGCENTRAL_*` env vars |
| Google Ads | Ready | Needs OAuth2 credentials |
| Twilio | Ready | `TWILIO_*` env vars |
| Stripe | Ready | `STRIPE_SECRET_KEY` |
| SendGrid | Ready | `SENDGRID_API_KEY` |

## Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply locally
alembic upgrade head

# Apply on Railway (admin auth required)
POST /api/v2/admin/migrations/run
```

## Environment Variables

**Required:**
```env
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
SECRET_KEY=your-secret-key
ENVIRONMENT=development
```

**Optional:**
```env
REDIS_URL=redis://localhost:6379
SENTRY_DSN=
CLOVER_MERCHANT_ID=
CLOVER_API_KEY=
SAMSARA_API_TOKEN=
RINGCENTRAL_CLIENT_ID=
RINGCENTRAL_CLIENT_SECRET=
RINGCENTRAL_JWT_TOKEN=
```

## Deployment

Railway auto-deploys on push to `master`. Never use `railway up`.

```bash
git push origin master
curl -s https://react-crm-api-production.up.railway.app/health  # Verify version
```

## Testing

```bash
pytest                    # Run all tests
pytest --cov=app          # With coverage
```

E2E tests live in the frontend repo (`ReactCRM/e2e/tests/`).
