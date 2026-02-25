---
active: true
iteration: 1
max_iterations: 30
completion_promise: "APPLICATION COMPLETE AND VERIFIED"
started_at: "2026-02-25T00:42:00Z"
loop_uuid: "4ebede5d-f76a-4d09-a8ad-f87f9c8ec9bd"
---

Sequential quality/security push — 7 items:

1. CASCADE DELETE on Customer model relationships
2. Reduce JWT expiry to 2hr + implement refresh token endpoint
3. Login rate limiting per email address
4. WebSocket rate limiting per connection
5. Background task watchdog (restart crashed tasks)
6. ESLint no-explicit-any → error + fix 56 violations
7. Split AppLayout.tsx (519 LOC) into smaller components

Test and verify each. Do not move forward until resolved.
