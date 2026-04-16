# Plan 2 Reconciliation Notes

Read-only audit of infrastructure Plan 2 depends on, captured before we start
touching code.

## 1. Sidebar is data-driven

`src/components/layout/navConfig.ts` is a config array of `NavGroup` (sidebar
sections) and `NavItem` (rows inside a group).  Each `NavGroup` has a name,
label, icon, and an `items` array.  Adding a new HR section is a pure data
change — no JSX edits to `Sidebar.tsx`.

Placement: insert a new group between the existing `marketing` group (line
~122) and `support` (later in the file).

```ts
{
  name: "hr",
  label: "HR",
  icon: Briefcase,   // lucide icon, add to import
  items: [
    { path: "/hr/requisitions", label: "Requisitions", icon: ClipboardList },
  ],
},
```

Import `Briefcase` from `lucide-react` alongside the other icons at the top
of the file.

## 2. SMS helper

`app/services/sms_service.py` exposes two things:
- `class SMSService` with `async def send_sms(self, to: str, body: str)`
- module-level `async def send_sms(to: str, body: str)` (line ~92) — this is
  the one to import.

**Import:** `from app.services.sms_service import send_sms`.  It's async, idempotent
on the client side (Twilio handles message idempotency), and will raise on
network/auth failures.  Our `maybe_send_stage_sms` wraps it in try/except.

`MockSMSService` exists for tests; the module-level `send_sms` in production
calls the real Twilio client.  In our tests we monkeypatch
`app.hr.recruiting.notifications._send_sms` (a local re-export) instead of
the upstream.

## 3. SMS consent model

`app/models/sms_consent.py::SMSConsent` is keyed to `customer_id`
(`ForeignKey("customers.id")`).  Applicants are not customers — they have
no row in `customers` until (and unless) they are hired and explicitly
promoted.

**Decision:** Plan 2 records consent on the `hr_applicants` row itself
(`sms_consent_given`, `sms_consent_ip`, `sms_consent_at`).  We do **not**
write into `sms_consent` for applicants.  If a hired applicant is later
promoted to a customer or user, Plan 3 (or the hire-promotion step) is
responsible for creating the matching `sms_consent` row.

This keeps Plan 2 shippable without a customer-row dependency and preserves
TCPA auditability — consent is captured with IP + timestamp at the point the
form is submitted.

## 4. Rate limiting on the public apply endpoint

A global rate-limit middleware is already in place.  No per-route limit is
added in Plan 2; if abuse surfaces we revisit.  Payload limits are enforced
in the endpoint itself (`_MAX_RESUME_BYTES = 10 * 1024 * 1024`).

## 5. Existing `EmptyState` component

`src/components/ui/EmptyState.tsx` exists and should be reused on the
requisition-detail and applicant-list pages where "no applications yet" /
"no applicants yet" states appear.  (Noted per the user's frontend rules in
`~/.claude/rules/frontend.md`.)
