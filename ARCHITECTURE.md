# MAC Septic CRM - Architecture Documentation

## System Overview

The MAC Septic CRM is a modern web application with a clear separation between frontend and backend.

---

## Architecture Diagram

```
                          ┌─────────────────────────────┐
                          │      React Frontend         │
                          │   react.ecbtx.com           │
                          │   (wburns02/ReactCRM)       │
                          └─────────────┬───────────────┘
                                        │
                                        │ HTTPS + JWT
                                        ▼
                          ┌─────────────────────────────┐
                          │      FastAPI Backend        │
                          │   react-crm-api-production  │
                          │   .up.railway.app           │
                          │   (wburns02/react-crm-api)  │
                          └─────────────┬───────────────┘
                                        │
                                        │ asyncpg
                                        ▼
                          ┌─────────────────────────────┐
                          │      PostgreSQL             │
                          │   Railway Managed           │
                          └─────────────────────────────┘
```

---

## Repositories

| Repository | Purpose | Local Path | Production URL |
|------------|---------|------------|----------------|
| `wburns02/ReactCRM` | React Frontend | `C:\ReactCRM-local` | https://react.ecbtx.com |
| `wburns02/react-crm-api` | FastAPI Backend | `C:\Users\Will\crm-work\react-crm-api` | https://react-crm-api-production.up.railway.app |

### Legacy (DEPRECATED)

| Repository | Purpose | Status |
|------------|---------|--------|
| `wburns02/Mac-Septic-CRM` | Flask Backend | DEPRECATED - Do not use for new development |

---

## Technology Stack

### Frontend
- **Framework:** React 19 + TypeScript
- **Build Tool:** Vite
- **State Management:** TanStack Query (server), Zustand (client)
- **HTTP Client:** Axios
- **UI:** Tailwind CSS 4
- **Mapping:** React Leaflet
- **Charts:** Recharts

### Backend
- **Framework:** FastAPI (Python 3.11+)
- **ORM:** SQLAlchemy 2.0+ (async)
- **Database:** PostgreSQL 15+
- **Migrations:** Alembic
- **Authentication:** JWT (python-jose)
- **Validation:** Pydantic v2

---

## API Structure

All API endpoints are versioned under `/api/v2/`:

```
/api/v2/
├── auth/           # Authentication (login, logout, register, me)
├── customers/      # Customer CRUD
├── work-orders/    # Work order CRUD + scheduling
├── technicians/    # Technician CRUD
├── invoices/       # Invoice CRUD + payments
├── communications/ # SMS/email sending
├── dashboard/      # Aggregated statistics
├── schedule/       # Calendar views
└── reports/        # Analytics reports
```

---

## Database Models

### Current Tables
1. `customers` - Customer records with prospect stages
2. `work_orders` - Service jobs and scheduling
3. `technicians` - Employee records with skills
4. `invoices` - Billing with line items
5. `messages` - SMS/email communication log
6. `api_users` - Authentication accounts

### Enums
- `CustomerType`: residential, commercial, hoa, municipal, property_management
- `ProspectStage`: new_lead, contacted, qualified, quoted, negotiation, won, lost
- `LeadSource`: referral, website, google, facebook, repeat_customer, door_to_door, other
- `WorkOrderStatus`: draft, scheduled, confirmed, enroute, on_site, in_progress, completed, canceled, requires_followup
- `JobType`: pumping, inspection, repair, installation, emergency, maintenance, grease_trap, camera_inspection
- `Priority`: low, normal, high, urgent, emergency
- `InvoiceStatus`: draft, sent, paid, overdue, void
- `MessageType`: sms, email, call, note

---

## Authentication

JWT-based authentication with Bearer tokens:

1. User logs in via `POST /api/v2/auth/login`
2. Backend returns JWT token
3. Frontend stores token in localStorage
4. All subsequent requests include `Authorization: Bearer <token>`
5. Token expiry triggers automatic logout

---

## Development Setup

### Backend
```bash
cd C:\Users\Will\crm-work\react-crm-api
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd C:\ReactCRM-local
npm install
npm run dev
# Runs on http://localhost:5173
```

### Environment Variables

**Backend (.env):**
```
DATABASE_URL=postgresql+asyncpg://...
SECRET_KEY=your-secret-key
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
```

**Frontend (.env):**
```
VITE_API_URL=http://localhost:8000/api/v2
```

---

## Deployment

Both services deploy automatically to Railway on push to main/master branch.

### Backend Deployment
- Dockerfile at repo root
- Auto-runs Alembic migrations
- Environment variables configured in Railway

### Frontend Deployment
- Vite build + nginx
- Static site hosting on Railway
- .env.production contains production API URL

---

## Important Notes

1. **NEVER** reference `crm.ecbtx.com` in new code - that's the legacy Flask backend
2. **ALWAYS** use async patterns in backend code (async def, await)
3. **ALWAYS** create Alembic migrations for schema changes
4. **NEVER** use Flask patterns (Blueprint, Flask-SQLAlchemy) in this codebase

---

## Contact

Repository owners: wburns02
