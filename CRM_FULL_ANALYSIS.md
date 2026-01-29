# CRM Full System Analysis

> **Generated:** January 29, 2026
> **Purpose:** Complete deep dive analysis for Email CRM Integration

---

## Executive Summary

The ECBTX CRM is a production-grade field service management system built for septic/plumbing companies. It consists of:

- **Frontend:** React 19 + TypeScript + Vite + TanStack Query
- **Backend:** FastAPI + SQLAlchemy (async) + PostgreSQL
- **Deployment:** Railway (auto-deploy from GitHub)
- **Live URLs:**
  - Frontend: https://react.ecbtx.com
  - API: https://react-crm-api-production.up.railway.app

---

## Architecture Overview

### Frontend (ReactCRM)

**Location:** `/home/will/ReactCRM`

```
src/
├── api/                    # API client & hooks (80+ hooks)
│   ├── client.ts           # Axios instance with correlation IDs
│   ├── hooks/              # TanStack Query hooks
│   └── types/              # Zod schemas & TypeScript types
├── features/               # 56 feature modules
│   ├── customers/          # Customer management
│   ├── work-orders/        # Work order management
│   ├── invoices/           # Billing & invoices
│   ├── communications/     # SMS, Email, Calls
│   ├── phone/              # Twilio voice integration
│   ├── email-marketing/    # Campaigns & templates
│   └── ...
├── components/ui/          # Shared UI components
├── routes/                 # Route definitions
└── mocks/                  # MSW handlers for testing
```

**Key Technologies:**
- React 19 with Concurrent Features
- TanStack Query v5 for data fetching
- React Router v7 for routing
- Axios for HTTP with interceptors
- Zod for runtime validation
- Tailwind CSS for styling

### Backend (react-crm-api)

**Location:** `/home/will/react-crm-api`

```
app/
├── api/v2/                 # 79 endpoint files
│   ├── auth.py             # Authentication
│   ├── customers.py        # Customer CRUD
│   ├── work_orders.py      # Work order management
│   ├── invoices.py         # Billing
│   ├── communications.py   # Messaging hub
│   ├── email.py            # Email-specific endpoints
│   └── ...
├── models/                 # 49 SQLAlchemy models
├── schemas/                # Pydantic schemas
├── services/               # Business logic
│   ├── twilio_service.py   # SMS/voice
│   └── cache_service.py    # Redis caching
├── core/                   # Configuration
│   ├── telemetry.py        # OpenTelemetry APM
│   └── metrics.py          # Prometheus metrics
├── middleware/             # Request middleware
│   └── correlation.py      # X-Correlation-ID tracking
└── security/               # Auth & RBAC
```

**Key Technologies:**
- FastAPI with async/await
- SQLAlchemy 2.0 async
- PostgreSQL (Railway)
- Redis for caching
- OpenTelemetry for tracing
- Prometheus for metrics

---

## Database Models (49 Total)

### Core Entities

| Model | Table | Description |
|-------|-------|-------------|
| User | `users` | System users with roles |
| Customer | `customers` | Customer records |
| WorkOrder | `work_orders` | Service jobs |
| Invoice | `invoices` | Billing records |
| Technician | `technicians` | Field workers |
| Message | `messages` | All communications |

### Message Model (Critical for Email Integration)

**Location:** `app/models/message.py`

```python
class MessageType(str, enum.Enum):
    sms = "sms"
    email = "email"
    call = "call"
    note = "note"

class MessageDirection(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"

class MessageStatus(str, enum.Enum):
    pending = "pending"
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    failed = "failed"
    received = "received"

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    type = Column(Enum(MessageType))           # sms, email, call, note
    direction = Column(Enum(MessageDirection)) # inbound, outbound
    status = Column(Enum(MessageStatus))
    to_address = Column(String(255))           # Phone or email
    from_address = Column(String(255))
    subject = Column(String(255))              # For emails
    content = Column(Text)
    twilio_sid = Column(String(100))           # Twilio tracking
    source = Column(String(20))                # 'react' or 'legacy'
    sent_at = Column(DateTime)
    created_at = Column(DateTime)

    # Relationship
    customer = relationship("Customer", back_populates="messages")
```

---

## Current Communications Implementation

### Frontend Components

**Location:** `src/features/communications/`

| Component | File | Purpose |
|-----------|------|---------|
| EmailInbox | `pages/EmailInbox.tsx` | List email conversations |
| EmailConversation | `pages/EmailConversation.tsx` | View email thread |
| EmailTemplates | `pages/EmailTemplates.tsx` | Manage templates |
| EmailComposeModal | `components/EmailComposeModal.tsx` | Compose new email |
| SMSInbox | `pages/SMSInbox.tsx` | SMS conversations |
| CommunicationsOverview | `pages/CommunicationsOverview.tsx` | Dashboard |

### API Hooks

**Location:** `src/api/hooks/useCommunications.ts`

```typescript
// Query keys
communicationKeys.all: ["communications"]
communicationKeys.history(customerId): ["communications", "history", customerId]

// Hooks
useCommunicationHistory(customerId)  // Get messages for customer
useSendSMS()                          // Send SMS mutation
useSendEmail()                        // Send email mutation
```

### Backend Endpoints

**Communications Router:** `app/api/v2/communications.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/communications/history` | Get message history (filterable) |
| POST | `/communications/sms/send` | Send SMS via Twilio |
| POST | `/communications/email/send` | Send email (placeholder) |
| GET | `/communications/stats` | Unread counts |
| GET | `/communications/activity` | Recent activity |
| GET | `/communications/{id}` | Get single message |

**Email Router:** `app/api/v2/email.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/email/conversations` | List email conversations |
| GET | `/email/conversations/{id}` | Get email thread |
| POST | `/email/reply` | Reply to email thread |

---

## Current Email Flow

### Sending Email (Outbound)

1. User opens `EmailComposeModal`
2. Fills in recipient, subject, body
3. Optional: Uses AI to generate content
4. Clicks "Send Email"
5. Frontend calls `POST /communications/email/send`
6. Backend creates `Message` record with `type=email`
7. Backend marks as `status=sent` (no actual email sent yet)
8. Record saved to database

**Gap:** No actual email delivery - just database record.

### Viewing Email History

1. User navigates to `/communications/email-inbox`
2. Frontend calls `GET /communications/history?type=email`
3. Backend queries `messages` table filtered by `type=email`
4. Returns paginated list

**Gap:** Only shows outbound emails from CRM, no inbound email sync.

### Customer Detail Page

**Location:** `src/features/customers/CustomerDetailPage.tsx`

Currently displays:
- Contact info (email shown as mailto: link)
- Work order history
- Call history (CallLog component)
- Activity timeline
- Attachments

**Gap:** No email history section on customer detail page.

---

## Integration Points

### Existing Integrations

| Service | Status | Purpose |
|---------|--------|---------|
| Twilio SMS | Active | Send/receive SMS |
| Twilio Voice | Active | Click-to-call |
| QuickBooks | Planned | Invoicing sync |
| HubSpot | Planned | CRM sync |

### Email Service Candidates

For actual email delivery, need to integrate:
- **SendGrid** - Popular, reliable
- **AWS SES** - Cost-effective at scale
- **Postmark** - Transactional focus
- **Mailgun** - Developer-friendly

---

## Security & RBAC

### Permissions System

**Location:** `app/security/rbac.py`

```python
class Permission(str, Enum):
    SEND_SMS = "send_sms"
    SEND_EMAIL = "send_email"
    VIEW_CUSTOMERS = "view_customers"
    # ... more permissions
```

### Rate Limiting

- SMS: 10/min per user, 100/hour per user, 5/hour per destination
- Email: Not yet rate limited

---

## API Patterns

### Request Flow

```
Frontend Request
    ↓
Axios Interceptor (adds X-Correlation-ID)
    ↓
FastAPI Router
    ↓
Correlation Middleware (logs trace_id)
    ↓
RBAC Check
    ↓
Business Logic (Service Layer)
    ↓
Database (SQLAlchemy async)
    ↓
Response with RFC 7807 errors
```

### Error Handling

Uses RFC 7807 Problem Details:

```json
{
  "type": "https://api.ecbtx.com/problems/not-found",
  "title": "Resource Not Found",
  "status": 404,
  "detail": "Customer with ID 123 not found",
  "code": "CUST_001",
  "trace_id": "abc-123-def"
}
```

---

## Testing Infrastructure

### Frontend

- **Vitest** for unit tests
- **MSW** for API mocking
- **Playwright** for E2E tests
- **Test factories** in `src/mocks/factories/`

### Backend

- **pytest** + **pytest-asyncio**
- **factory-boy** for test data
- **SQLite in-memory** for tests
- Coverage target: 70%

---

## Current Email Gaps (To Be Addressed)

### 1. No Actual Email Sending
- `POST /communications/email/send` just creates DB record
- No integration with email service (SendGrid, SES, etc.)

### 2. No Inbound Email
- Cannot receive/sync emails into CRM
- No webhook for incoming email

### 3. No Customer Email History
- CustomerDetailPage shows calls but not emails
- Need email history section

### 4. No Email Tracking
- No open tracking
- No click tracking
- No delivery status updates

### 5. Limited Template System
- EmailTemplates page exists
- But not integrated with compose flow

### 6. No Email-to-Entity Linking
- Emails not linked to work orders
- Emails not linked to invoices
- Only linked to customers via customer_id

---

## Files Requiring Modification for Email Integration

### Frontend

| File | Changes Needed |
|------|----------------|
| `src/features/customers/CustomerDetailPage.tsx` | Add email history section |
| `src/features/communications/components/EmailComposeModal.tsx` | Add work order/invoice linking |
| `src/api/hooks/useCommunications.ts` | Add email-specific queries |
| `src/api/types/communication.ts` | Extend types for email metadata |

### Backend

| File | Changes Needed |
|------|----------------|
| `app/api/v2/communications.py` | Integrate email service |
| `app/models/message.py` | Add work_order_id, invoice_id columns |
| `app/services/email_service.py` | CREATE - SendGrid/SES integration |
| `app/api/v2/email_webhooks.py` | CREATE - Inbound email handling |

---

## Deployment Notes

### Railway Configuration

- Frontend: Auto-deploy from `ReactCRM` repo
- Backend: Auto-deploy from `react-crm-api` repo
- Database: Railway PostgreSQL
- Redis: Railway Redis (optional)

### Environment Variables Required

```env
# Email Service (to be added)
SENDGRID_API_KEY=...
SENDGRID_FROM_EMAIL=support@macseptic.com
EMAIL_WEBHOOK_SECRET=...
```

---

## Summary

The CRM has a solid foundation for email integration:

**Already Exists:**
- Message model with email type support
- Email compose UI with AI generation
- Basic email inbox/conversation views
- Communication history API
- Customer relationship to messages

**Needs Implementation:**
- Actual email delivery (SendGrid/SES)
- Inbound email sync
- Email history on customer detail
- Work order/invoice email linking
- Email tracking (opens, clicks)
- Template integration in compose flow

The infrastructure is production-ready and follows modern patterns (async, RFC 7807 errors, RBAC, correlation IDs). Email integration should build on existing patterns rather than creating new ones.

---

*Analysis complete. Ready for Phase 2: Research 2026 email CRM best practices.*
