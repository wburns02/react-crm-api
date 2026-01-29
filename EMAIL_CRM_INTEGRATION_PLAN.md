# Email CRM Integration Implementation Plan

> **Created:** January 29, 2026
> **Version:** 1.0
> **Status:** Ready for Implementation

---

## Overview

Transform the ECBTX CRM email capabilities from placeholder functionality to a fully integrated, production-ready email system tied to customers, work orders, and invoices.

### Goals
1. Send real emails via SendGrid
2. Display email history on customer detail page
3. Link emails to work orders and invoices
4. Track sent emails in communications inbox
5. Enable templates in compose flow

---

## Implementation Phases

### Phase A: Backend SendGrid Integration (Priority: Critical)

#### A1. Add SendGrid Dependency

**File:** `requirements.txt`
```
sendgrid>=6.11.0
```

#### A2. Add Configuration

**File:** `app/config.py`
```python
# SendGrid Configuration
SENDGRID_API_KEY: str | None = None
SENDGRID_FROM_EMAIL: str = "support@macseptic.com"
SENDGRID_FROM_NAME: str = "MAC Septic Services"
EMAIL_WEBHOOK_SECRET: str | None = None
```

#### A3. Create Email Service

**New File:** `app/services/email_service.py`

```python
"""
SendGrid Email Service

Handles:
- Sending transactional emails
- Template rendering with merge tags
- Event webhook processing
"""

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        self.api_key = settings.SENDGRID_API_KEY
        self.from_email = settings.SENDGRID_FROM_EMAIL
        self.from_name = settings.SENDGRID_FROM_NAME
        self._client = None

    @property
    def client(self):
        if self._client is None and self.api_key:
            self._client = SendGridAPIClient(self.api_key)
        return self._client

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ) -> dict:
        """Send an email via SendGrid."""
        if not self.is_configured:
            logger.warning("SendGrid not configured, email not sent")
            return {"status": "skipped", "reason": "not_configured"}

        message = Mail(
            from_email=Email(self.from_email, self.from_name),
            to_emails=To(to_email),
            subject=subject,
            plain_text_content=body,
            html_content=html_body or f"<p>{body}</p>",
        )

        try:
            response = self.client.send(message)
            return {
                "status": "sent",
                "status_code": response.status_code,
                "message_id": response.headers.get("X-Message-Id"),
            }
        except Exception as e:
            logger.error(f"SendGrid error: {e}")
            return {"status": "error", "error": str(e)}


# Global singleton
email_service = EmailService()
```

#### A4. Update Communications Endpoint

**File:** `app/api/v2/communications.py`

Modify `/email/send` endpoint to actually send via SendGrid:

```python
from app.services.email_service import email_service

@router.post("/email/send", response_model=MessageResponse)
async def send_email(
    request: SendEmailRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    # ... existing RBAC check ...

    # Create message record
    message = Message(
        customer_id=request.customer_id,
        type=MessageType.email,
        direction=MessageDirection.outbound,
        status=MessageStatus.pending,
        to_address=request.to,
        from_address=email_service.from_email,
        subject=request.subject,
        content=request.body,
        source=request.source,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    # Send via SendGrid
    result = await email_service.send_email(
        to_email=request.to,
        subject=request.subject,
        body=request.body,
    )

    # Update message status
    if result["status"] == "sent":
        message.status = MessageStatus.sent
        message.sent_at = datetime.utcnow()
        # Store SendGrid message ID for tracking
        message.twilio_sid = result.get("message_id")  # Reuse field
    elif result["status"] == "skipped":
        message.status = MessageStatus.sent  # Mark sent for dev mode
        message.sent_at = datetime.utcnow()
    else:
        message.status = MessageStatus.failed
        message.error_message = result.get("error")

    await db.commit()
    await db.refresh(message)

    return message
```

---

### Phase B: Database Schema Updates (Priority: High)

#### B1. Add Work Order & Invoice Links to Message Model

**File:** `app/models/message.py`

```python
class Message(Base):
    # ... existing fields ...

    # NEW: Link to work order
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), index=True)
    work_order = relationship("WorkOrder", back_populates="messages")

    # NEW: Link to invoice
    invoice_id = Column(Integer, ForeignKey("invoices.id"), index=True)
    invoice = relationship("Invoice", back_populates="messages")

    # NEW: Email tracking
    email_opened_at = Column(DateTime(timezone=True))
    email_clicked_at = Column(DateTime(timezone=True))
    tracking_enabled = Column(Boolean, default=False)
```

#### B2. Create Alembic Migration

```bash
alembic revision --autogenerate -m "Add work_order_id and invoice_id to messages"
```

#### B3. Update Related Models

**File:** `app/models/work_order.py`
```python
# Add relationship
messages = relationship("Message", back_populates="work_order")
```

**File:** `app/models/invoice.py`
```python
# Add relationship
messages = relationship("Message", back_populates="invoice")
```

#### B4. Update Message Schema

**File:** `app/schemas/message.py`

```python
class SendEmailRequest(BaseModel):
    # ... existing fields ...
    work_order_id: Optional[int] = None
    invoice_id: Optional[int] = None

class MessageResponse(BaseModel):
    # ... existing fields ...
    work_order_id: Optional[int] = None
    invoice_id: Optional[int] = None
```

---

### Phase C: Frontend Email History on Customer Detail (Priority: High)

#### C1. Create Customer Email History Component

**New File:** `src/features/customers/components/CustomerEmailHistory.tsx`

```tsx
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/Card";
import { formatDate } from "@/lib/utils";

interface CustomerEmailHistoryProps {
  customerId: string;
}

export function CustomerEmailHistory({ customerId }: CustomerEmailHistoryProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["customer-emails", customerId],
    queryFn: async () => {
      const response = await apiClient.get("/communications/history", {
        params: {
          customer_id: customerId,
          type: "email",
          page_size: 10,
        },
      });
      return response.data;
    },
  });

  if (isLoading) {
    return <div className="animate-pulse h-48 bg-bg-muted rounded-lg" />;
  }

  const emails = data?.items || [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Email History</CardTitle>
      </CardHeader>
      <CardContent>
        {emails.length === 0 ? (
          <p className="text-text-muted text-center py-4">No emails sent</p>
        ) : (
          <div className="space-y-3">
            {emails.map((email) => (
              <div
                key={email.id}
                className="flex items-start gap-3 p-3 rounded-lg border border-border"
              >
                <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                  email.direction === "outbound"
                    ? "bg-primary/10 text-primary"
                    : "bg-purple-500/10 text-purple-500"
                }`}>
                  {email.direction === "outbound" ? "→" : "←"}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-text-primary truncate">
                    {email.subject || "(No Subject)"}
                  </p>
                  <p className="text-sm text-text-secondary truncate">
                    {email.content?.substring(0, 100)}
                  </p>
                  <p className="text-xs text-text-muted mt-1">
                    {formatDate(email.sent_at || email.created_at)}
                    {email.status === "delivered" && " • Delivered"}
                    {email.status === "failed" && " • Failed"}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

#### C2. Add to Customer Detail Page

**File:** `src/features/customers/CustomerDetailPage.tsx`

```tsx
import { CustomerEmailHistory } from "./components/CustomerEmailHistory";

// In the render, add after CallLog:
<div className="lg:col-span-2">
  <CustomerEmailHistory customerId={id!} />
</div>
```

---

### Phase D: Compose Email from Customer Detail (Priority: Medium)

#### D1. Add Email Button to Customer Contact Section

**File:** `src/features/customers/CustomerDetailPage.tsx`

Add state and button:
```tsx
const [isEmailModalOpen, setIsEmailModalOpen] = useState(false);

// In contact info section, after email display:
{customer.email && (
  <button
    onClick={() => setIsEmailModalOpen(true)}
    className="ml-2 px-2 py-1 text-xs bg-purple-500/10 text-purple-500 rounded hover:bg-purple-500/20"
  >
    Send Email
  </button>
)}

// Add modal at bottom:
<EmailComposeModal
  open={isEmailModalOpen}
  onClose={() => setIsEmailModalOpen(false)}
  defaultEmail={customer.email}
  customerId={id}
  customerName={`${customer.first_name} ${customer.last_name}`}
/>
```

---

### Phase E: Work Order Email Linking (Priority: Medium)

#### E1. Update Email Compose Modal

**File:** `src/features/communications/components/EmailComposeModal.tsx`

Add work order selection:
```tsx
interface EmailComposeModalProps {
  // ... existing props ...
  workOrderId?: number;
  invoiceId?: number;
}

// In handleSend:
await sendEmail.mutateAsync({
  customer_id: customerId ? parseInt(customerId, 10) : undefined,
  work_order_id: workOrderId,
  invoice_id: invoiceId,
  to: email,
  subject,
  body,
});
```

#### E2. Add Send Email Button to Work Order Detail

**File:** `src/features/workorders/WorkOrderDetailPage.tsx`

```tsx
<button onClick={() => setIsEmailModalOpen(true)}>
  Email Customer
</button>

<EmailComposeModal
  open={isEmailModalOpen}
  onClose={() => setIsEmailModalOpen(false)}
  defaultEmail={workOrder.customer?.email}
  customerId={workOrder.customer_id?.toString()}
  customerName={workOrder.customer?.name}
  workOrderId={workOrder.id}
/>
```

---

### Phase F: Email Templates Integration (Priority: Low)

#### F1. Create Email Template Model

**New File:** `app/models/email_template.py`

```python
class EmailTemplate(Base):
    __tablename__ = "email_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50))  # appointment, invoice, followup, etc.
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
```

#### F2. Template CRUD Endpoints

**New File:** `app/api/v2/email_templates.py`

- GET /email-templates - List templates
- GET /email-templates/{id} - Get template
- POST /email-templates - Create template
- PATCH /email-templates/{id} - Update template
- DELETE /email-templates/{id} - Delete template

#### F3. Template Selection in Compose Modal

Add template dropdown to EmailComposeModal that pre-fills subject and body.

---

## File Changes Summary

### Backend (react-crm-api)

| File | Action | Description |
|------|--------|-------------|
| `requirements.txt` | EDIT | Add sendgrid>=6.11.0 |
| `app/config.py` | EDIT | Add SendGrid env vars |
| `app/services/email_service.py` | CREATE | SendGrid integration |
| `app/models/message.py` | EDIT | Add work_order_id, invoice_id |
| `app/api/v2/communications.py` | EDIT | Use email_service for sending |
| `app/schemas/message.py` | EDIT | Add work_order_id, invoice_id |
| `alembic/versions/xxx.py` | CREATE | Migration for new columns |

### Frontend (ReactCRM)

| File | Action | Description |
|------|--------|-------------|
| `src/features/customers/components/CustomerEmailHistory.tsx` | CREATE | Email history component |
| `src/features/customers/CustomerDetailPage.tsx` | EDIT | Add email history & compose |
| `src/features/communications/components/EmailComposeModal.tsx` | EDIT | Add WO/Invoice linking |
| `src/api/types/communication.ts` | EDIT | Add work_order_id, invoice_id |

---

## Environment Variables

```env
# Production (.env)
SENDGRID_API_KEY=SG.xxxxx
SENDGRID_FROM_EMAIL=support@macseptic.com
SENDGRID_FROM_NAME=MAC Septic Services

# Development (keep empty to skip sending)
SENDGRID_API_KEY=
```

---

## Testing Checklist

### Backend Tests
- [ ] Email service sends via SendGrid (mocked)
- [ ] Message created with work_order_id
- [ ] Message created with invoice_id
- [ ] Failed emails update message status
- [ ] RBAC enforced on email send

### Frontend Tests
- [ ] CustomerEmailHistory displays emails
- [ ] EmailComposeModal submits with workOrderId
- [ ] Compose modal opens from customer detail
- [ ] Email history refreshes after send

### Integration Tests (Playwright)
- [ ] Login as will@macseptic.com
- [ ] Navigate to /communications
- [ ] Compose and send email
- [ ] Verify email appears in inbox
- [ ] Navigate to customer detail
- [ ] Verify email appears in history

---

## Deployment Steps

1. **Backend First:**
   ```bash
   cd react-crm-api
   git add .
   git commit -m "feat: SendGrid email integration with entity linking"
   git push origin master
   # Wait for Railway deploy
   ```

2. **Run Migration:**
   ```bash
   alembic upgrade head
   ```

3. **Add Env Vars in Railway:**
   - SENDGRID_API_KEY
   - SENDGRID_FROM_EMAIL

4. **Frontend Second:**
   ```bash
   cd ReactCRM
   git add .
   git commit -m "feat: Email history on customer detail, compose from customer"
   git push origin master
   # Wait for Railway deploy
   ```

5. **Verify:**
   - Login to https://react.ecbtx.com
   - Send test email
   - Check customer detail for history

---

## Success Criteria

1. **Email Sending Works:** Emails actually delivered via SendGrid
2. **Customer Email History:** Visible on customer detail page
3. **Entity Linking:** Emails linked to work orders/invoices
4. **Communications Inbox:** All emails visible with status
5. **Compose Anywhere:** Can compose from customer, work order, or inbox

---

*Implementation plan complete. Ready for Phase 5: Implementation.*
