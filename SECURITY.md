# Security Policy

**Document Version:** 2.0
**Last Updated:** 2025-12-22
**Classification:** Internal / Customer-Facing
**Owner:** Security Engineering

---

## Table of Contents

1. [Threat Model](#threat-model)
2. [Security Invariants](#security-invariants)
3. [Authentication & Authorization](#authentication--authorization)
4. [CSRF Protection Protocol](#csrf-protection-protocol)
5. [Webhook Security](#webhook-security)
6. [Rate Limiting](#rate-limiting)
7. [Secrets Management](#secrets-management)
8. [Logging & Data Handling](#logging--data-handling)
9. [Incident Response](#incident-response)
10. [Enforcement & Verification](#enforcement--verification)
11. [Environment Configuration](#environment-configuration)
12. [Compliance & Audit](#compliance--audit)

---

## Threat Model

### Threat Actors

| Actor | Description | Capabilities |
|-------|-------------|--------------|
| **Unauthenticated External** | Anonymous internet user | Can access public endpoints, attempt auth bypass, enumerate APIs |
| **Authenticated User** | Valid user with session/token | Can access authorized resources, attempt privilege escalation, abuse rate limits |
| **Malicious Insider** | Employee or contractor with system access | Can access logs, environment variables, database connections |
| **Webhook Spoofer** | Attacker impersonating Twilio | Can send forged webhook requests to trigger unauthorized actions |
| **Network Attacker** | Man-in-the-middle position | Can intercept unencrypted traffic, replay requests |

### High-Risk Assets

| Asset | Classification | Protection Requirements |
|-------|----------------|------------------------|
| User credentials (passwords) | Critical | Hashed with bcrypt, never logged, never transmitted in plaintext |
| JWT tokens | Critical | Short-lived, signed with strong secret, never logged |
| Session cookies | Critical | HttpOnly, Secure, SameSite attributes enforced |
| PII (names, emails, phones) | Sensitive | Encrypted at rest (database), masked in logs |
| SMS message content | Sensitive | Not logged, not cached unnecessarily |
| API secrets (Twilio, DB credentials) | Critical | Environment variables only, never committed to source |
| Customer financial data | Critical | Not stored in this system (out of scope) |

### Trust Boundaries

```
┌─────────────────────────────────────────────────────────────────────┐
│                         UNTRUSTED ZONE                              │
│  • Public Internet                                                  │
│  • Client Applications (React SPA)                                  │
│  • Twilio Webhook Requests                                          │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ HTTPS + Auth
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      TRUST BOUNDARY: API GATEWAY                    │
│  • TLS Termination                                                  │
│  • Authentication Verification                                      │
│  • Webhook Signature Validation                                     │
│  • Rate Limiting                                                    │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ Validated Requests
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         TRUSTED ZONE                                │
│  • Application Server                                               │
│  • PostgreSQL Database                                              │
│  • Internal Service Communication                                   │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ Authenticated API Calls
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      EXTERNAL SERVICES                              │
│  • Twilio API (outbound SMS)                                        │
│  • Legacy Backend (webhook forwarding)                              │
└─────────────────────────────────────────────────────────────────────┘
```

### Attack Vectors Considered

1. **Authentication Bypass:** Mitigated by JWT validation, session verification
2. **Webhook Spoofing:** Mitigated by Twilio signature verification (HMAC-SHA1)
3. **CSRF Attacks:** Mitigated by Bearer token preference, SameSite cookies
4. **Rate Limit Abuse:** Mitigated by per-user and per-destination limits
5. **Privilege Escalation:** Mitigated by RBAC enforcement on all protected endpoints
6. **Secret Exposure:** Mitigated by environment-only secrets, production validation
7. **Information Disclosure:** Mitigated by secure logging practices, no sensitive data in logs

---

## Security Invariants

The following rules are **non-negotiable** and enforced through code, tests, and CI/CD:

### Authentication & Sessions

- JWT tokens MUST NOT be logged at any verbosity level
- JWT payloads MUST NOT be logged at any verbosity level
- Passwords MUST be hashed using bcrypt with cost factor ≥ 10
- Plaintext passwords MUST NOT be stored, logged, or transmitted (except over HTTPS to auth endpoint)
- Session cookies MUST have `HttpOnly`, `Secure` (in production), and `SameSite=Lax` attributes
- Expired or invalid tokens MUST return HTTP 401 without detailed error information
- Disabled user accounts MUST return HTTP 403

### Secrets Management

- Default/weak SECRET_KEY values MUST NOT be accepted in production
- SECRET_KEY MUST be at least 32 characters in production
- Application MUST fail to start if production secrets validation fails
- Database credentials MUST NOT be logged, even partially
- Twilio auth tokens MUST NOT be logged

### Webhook Security

- All Twilio webhook endpoints MUST validate `X-Twilio-Signature` header
- Requests with missing signatures MUST be rejected with HTTP 403
- Requests with invalid signatures MUST be rejected with HTTP 403
- Webhook endpoints MUST NOT process requests before signature validation completes

### Rate Limiting

- SMS sending MUST be rate-limited per user (default: 10/minute, 100/hour)
- SMS sending MUST be rate-limited per destination (default: 5/hour per phone number)
- Rate limit responses MUST include `Retry-After` header
- Rate limiting MUST NOT be bypassable by authenticated users

### Access Control

- All state-changing endpoints MUST require authentication
- RBAC checks MUST occur before any business logic execution
- Permission denied MUST return HTTP 403 with generic message
- User enumeration MUST NOT be possible through error message differences

### Production Hardening

- API documentation (`/docs`, `/redoc`) SHOULD be disabled in production
- `DEBUG` mode MUST be disabled in production
- SQLAlchemy query echo MUST be disabled in production
- CORS origins MUST be explicitly allowlisted (no wildcards in production)

---

## Authentication & Authorization

### Authentication Methods

| Method | Header/Location | Use Case | CSRF Risk |
|--------|-----------------|----------|-----------|
| Bearer Token | `Authorization: Bearer <token>` | API clients, SPAs | None |
| Session Cookie | `Cookie: session=<token>` | Browser convenience | Mitigated by SameSite |

### Token Lifecycle

1. **Issuance:** POST `/api/v2/auth/login` with valid credentials
2. **Validity:** 30 minutes (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`)
3. **Refresh:** Not implemented; client must re-authenticate
4. **Revocation:** Logout clears cookie; token remains valid until expiry

### Role Hierarchy

| Role | Permissions |
|------|-------------|
| `user` | send_sms, send_email, view_customers, edit_customers |
| `admin` | All user permissions + delete_customers, view_all_communications, admin_panel |
| `superuser` | All permissions including manage_users |

### Authorization Flow

```
Request → Authentication Check → Role Resolution → Permission Check → Business Logic
              ↓ fail                                    ↓ fail
           HTTP 401                                  HTTP 403
```

---

## CSRF Protection Protocol

### Applicability

CSRF protection is relevant when:
- Authentication is provided via cookies (session cookie)
- The request is state-changing (POST, PUT, PATCH, DELETE)

### Protection Mechanism

This API implements a **Bearer-Token-First** authentication strategy:

1. **Primary:** Bearer tokens in `Authorization` header (immune to CSRF)
2. **Secondary:** Session cookies with `SameSite=Lax` attribute

### Protocol Rules

| Rule | Specification |
|------|---------------|
| SPA clients | MUST use Bearer token authentication |
| Session cookies | MUST have `SameSite=Lax` attribute |
| Cross-origin requests | MUST NOT succeed with cookie-only auth |
| Token transmission | MUST occur only over HTTPS in production |

### Client Implementation Requirements

**Recommended (Bearer Token):**
```typescript
// Store token in memory (not localStorage)
const headers = { Authorization: `Bearer ${accessToken}` };
await fetch('/api/v2/endpoint', { method: 'POST', headers });
```

**If Using Cookies:**
- Ensure SPA is served from same origin as API
- Do not disable SameSite protections
- Consider implementing explicit CSRF tokens for defense-in-depth

### Failure Behavior

| Scenario | Response |
|----------|----------|
| No authentication provided | HTTP 401 |
| Invalid/expired token | HTTP 401 |
| Cookie-only auth from cross-origin | Blocked by SameSite |

---

## Webhook Security

### Twilio Signature Verification

All endpoints under `/webhooks/twilio/*` enforce signature verification.

#### Verification Process

1. Extract `X-Twilio-Signature` header
2. Reconstruct request URL (respecting `X-Forwarded-*` headers for reverse proxies)
3. Compute expected signature using Twilio auth token and request parameters
4. Compare signatures using constant-time comparison
5. Reject with HTTP 403 if validation fails

#### Configuration Requirements

| Variable | Requirement |
|----------|-------------|
| `TWILIO_AUTH_TOKEN` | MUST be set for webhook endpoints to function |
| Reverse proxy headers | MUST forward `X-Forwarded-Proto` and `X-Forwarded-Host` |

#### Failure Modes

| Condition | Response |
|-----------|----------|
| Missing `X-Twilio-Signature` | HTTP 403: "Missing Twilio signature" |
| Invalid signature | HTTP 403: "Invalid Twilio signature" |
| Missing `TWILIO_AUTH_TOKEN` | HTTP 403: "Signature validation error" |

---

## Rate Limiting

### SMS Rate Limits

| Limit Type | Default | Configurable Via |
|------------|---------|------------------|
| Per-user per-minute | 10 requests | `RATE_LIMIT_SMS_PER_MINUTE` |
| Per-user per-hour | 100 requests | `RATE_LIMIT_SMS_PER_HOUR` |
| Per-destination per-hour | 5 requests | `RATE_LIMIT_SMS_PER_DESTINATION_HOUR` |

### Response Format

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 45
Content-Type: application/json

{"detail": "Rate limit exceeded: Per-minute limit (10/min). Retry after 45 seconds."}
```

### Implementation Notes

- Rate limits are enforced in-memory (resets on application restart)
- For production scale, consider Redis-backed rate limiting
- Rate limits apply per authenticated user ID

---

## Secrets Management

### Secret Classification

| Secret | Storage | Rotation |
|--------|---------|----------|
| `SECRET_KEY` | Environment variable | Annually or on compromise |
| `DATABASE_URL` | Environment variable | On compromise |
| `TWILIO_AUTH_TOKEN` | Environment variable | Per Twilio policy |
| `TWILIO_ACCOUNT_SID` | Environment variable | Static |

### Production Validation

The application performs startup validation in production:

1. **SECRET_KEY Strength:** Rejects known weak values and keys < 32 characters
2. **Environment Detection:** Validates when `ENVIRONMENT` is `production`, `prod`, or `staging`
3. **Failure Behavior:** Application refuses to start with clear error message

### Generating Secrets

```bash
# Generate a secure SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Logging & Data Handling

### Data Classification for Logging

| Data Type | Logging Policy |
|-----------|----------------|
| JWT tokens | MUST NOT log |
| JWT payloads | MUST NOT log |
| Passwords | MUST NOT log |
| Full phone numbers | MUST NOT log (last 4 digits only) |
| SMS content | MUST NOT log |
| Email content | MUST NOT log |
| User IDs | MAY log |
| Request paths | MAY log |
| HTTP status codes | MAY log |
| Error types (not messages) | MAY log |

### Log Format

```
%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

### Audit Events

The following events SHOULD be logged for audit purposes:

- Authentication success/failure (without credentials)
- Authorization denial (user ID, requested resource)
- Rate limit triggers (user ID, limit type)
- Webhook signature failures (source IP, path)

---

## Incident Response

### Definition of Security Incident

A security incident includes but is not limited to:

- Unauthorized access to user data or system resources
- Suspected credential compromise
- Detection of vulnerability exploitation attempts
- Webhook signature validation bypasses
- Unexpected privilege escalation
- Data exfiltration indicators

### Immediate Response Procedure

#### 1. Containment (0-15 minutes)

| Action | Command/Process |
|--------|-----------------|
| Rotate SECRET_KEY | Update environment variable, redeploy |
| Invalidate all sessions | Change SECRET_KEY (invalidates all JWTs) |
| Block suspicious IPs | Configure at load balancer/WAF level |
| Disable compromised accounts | Set `is_active = false` in database |

#### 2. Investigation (15-60 minutes)

- Review application logs for anomalous patterns
- Check for 403/401 spikes indicating attack attempts
- Audit database for unauthorized modifications
- Review webhook logs for signature bypass attempts

#### 3. Remediation

- Patch identified vulnerabilities
- Reset affected user credentials
- Update security controls as needed
- Document timeline and actions taken

#### 4. Post-Incident

- Conduct post-mortem within 72 hours
- Update threat model if new vectors identified
- Implement additional monitoring if gaps found
- Notify affected users per legal requirements

### Emergency Contacts

| Role | Responsibility |
|------|----------------|
| Security Lead | Incident coordination, external communication |
| Engineering Lead | Technical remediation, deployment |
| Legal/Compliance | Regulatory notification requirements |

---

## Enforcement & Verification

### Automated Testing

| Test Category | Location | Coverage |
|---------------|----------|----------|
| Twilio signature verification | `tests/test_security.py` | Missing/invalid signatures rejected |
| Rate limiting | `tests/test_security.py` | Per-minute, per-hour, per-destination |
| Authentication | `tests/test_security.py` | Invalid/expired/tampered tokens |
| Authorization | `tests/test_security.py` | Unauthenticated access, role checks |
| Secret validation | `tests/test_security.py` | Weak keys rejected in production |

### CI/CD Security Checks

| Tool | Purpose | Enforcement |
|------|---------|-------------|
| `bandit` | Python SAST | Blocks on high-severity findings |
| `pip-audit` | Dependency vulnerabilities | Blocks on known CVEs |
| `pytest` | Security test suite | Blocks on test failure |

### Runtime Monitoring

| Signal | Indicates | Response |
|--------|-----------|----------|
| Spike in HTTP 401 | Credential stuffing attempt | Review logs, consider IP blocking |
| Spike in HTTP 403 | Authorization bypass attempts | Review logs, audit RBAC rules |
| Spike in HTTP 429 | Rate limit abuse | Review user activity |
| Webhook 403s | Twilio spoofing attempts | Verify Twilio configuration |

### Verification Commands

```bash
# Run security test suite
pytest tests/test_security.py -v

# Run SAST scan
bandit -r app/ -f txt

# Check dependency vulnerabilities
pip-audit -r requirements.txt

# Verify production config rejection
ENVIRONMENT=production SECRET_KEY=weak python -c "from app.config import settings"
# Should raise ValueError
```

---

## Environment Configuration

### Required Variables (Production)

| Variable | Description | Validation |
|----------|-------------|------------|
| `SECRET_KEY` | JWT signing key | ≥32 chars, not in weak list |
| `DATABASE_URL` | PostgreSQL connection | Valid connection string |
| `ENVIRONMENT` | Environment name | `production` for prod settings |
| `TWILIO_AUTH_TOKEN` | Webhook verification | Required for webhook endpoints |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCS_ENABLED` | `true` | Set `false` to disable `/docs` |
| `DEBUG` | `true` | Forced `false` in production |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT lifetime |
| `FRONTEND_URL` | `http://localhost:5173` | CORS allowed origin |

### Platform-Specific Setup

**Railway:**
```bash
railway variables set SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
railway variables set ENVIRONMENT="production"
railway variables set DOCS_ENABLED="false"
```

**Heroku:**
```bash
heroku config:set SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
heroku config:set ENVIRONMENT="production"
heroku config:set DOCS_ENABLED="false"
```

---

## Compliance & Audit

### Standards Alignment

| Standard | Relevant Controls |
|----------|-------------------|
| OWASP ASVS | V2 (Auth), V3 (Session), V4 (Access Control), V8 (Data Protection) |
| SOC 2 | CC6.1 (Logical Access), CC6.6 (System Boundaries), CC7.2 (Monitoring) |
| GDPR | Article 32 (Security of Processing) |

### Audit Checklist

- [ ] SECRET_KEY is unique and ≥32 characters
- [ ] ENVIRONMENT is set to `production`
- [ ] DOCS_ENABLED is `false` or docs are access-controlled
- [ ] TWILIO_AUTH_TOKEN is configured
- [ ] CORS origins are explicitly allowlisted
- [ ] Database connections use TLS
- [ ] Application logs do not contain sensitive data
- [ ] Security tests pass in CI/CD
- [ ] Dependency vulnerabilities are remediated

### Security Contact

For security concerns or vulnerability reports, contact the security team through established internal channels. Do not create public issues for security vulnerabilities.

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2025-12-22 | Added threat model, security invariants, incident response |
| 1.0 | 2025-12-22 | Initial security documentation |
