# Security Configuration Guide

This document describes the security features implemented in the React CRM API and how to configure them properly for production.

## Table of Contents

1. [Environment Variables](#environment-variables)
2. [Authentication](#authentication)
3. [Twilio Webhook Security](#twilio-webhook-security)
4. [Rate Limiting](#rate-limiting)
5. [Role-Based Access Control](#role-based-access-control)
6. [Production Checklist](#production-checklist)

---

## Environment Variables

### Required for Production

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing key (min 32 chars) | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:5432/db` |
| `ENVIRONMENT` | Environment name | `production` |
| `TWILIO_AUTH_TOKEN` | Twilio auth token for webhook verification | `your_twilio_auth_token` |

### Optional Security Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCS_ENABLED` | `true` | Set to `false` to disable `/docs` and `/redoc` in production |
| `DEBUG` | `true` | Automatically set to `false` in production |
| `RATE_LIMIT_SMS_PER_MINUTE` | `10` | Max SMS per user per minute |
| `RATE_LIMIT_SMS_PER_HOUR` | `100` | Max SMS per user per hour |
| `RATE_LIMIT_SMS_PER_DESTINATION_HOUR` | `5` | Max SMS to same number per hour |

### Railway/Render/Heroku Setup

```bash
# Generate a secure SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Set environment variables (Railway example)
railway variables set SECRET_KEY="your-generated-key-here"
railway variables set ENVIRONMENT="production"
railway variables set DOCS_ENABLED="false"
railway variables set TWILIO_AUTH_TOKEN="your-twilio-token"
```

---

## Authentication

### Bearer Token (Recommended for SPAs)

The API supports Bearer token authentication, which is **recommended for single-page applications** because:

1. **No CSRF vulnerability** - Tokens in Authorization header aren't automatically sent by browsers
2. **Stateless** - No server-side session storage needed
3. **Cross-domain friendly** - Works easily across different origins

**React Client Example:**

```typescript
// src/api/client.ts
import axios from 'axios';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
});

// Store token in memory (not localStorage for security)
let accessToken: string | null = null;

export const setAccessToken = (token: string) => {
  accessToken = token;
};

// Add token to every request
apiClient.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

export default apiClient;
```

**Login Flow:**

```typescript
// src/hooks/useAuth.ts
const login = async (email: string, password: string) => {
  const response = await apiClient.post('/api/v2/auth/login', { email, password });
  const { access_token } = response.data;

  // Store in memory (more secure than localStorage)
  setAccessToken(access_token);

  // Optionally store in httpOnly cookie via backend response
  return response.data;
};
```

### Session Cookie (Alternative)

Session cookies are also supported for browser convenience. The backend sets an `httpOnly` cookie on login.

**Security Notes:**
- Cookies are set with `httpOnly=True` (not accessible via JavaScript)
- `secure=True` in production (HTTPS only)
- `samesite=lax` for CSRF protection

---

## Twilio Webhook Security

All Twilio webhook endpoints validate the `X-Twilio-Signature` header to ensure requests actually come from Twilio.

### How It Works

1. Twilio signs every webhook request using your Auth Token
2. The signature is sent in the `X-Twilio-Signature` header
3. Our API validates this signature before processing

### Configuration

1. Set `TWILIO_AUTH_TOKEN` environment variable
2. Configure Twilio webhook URLs to point to your API:
   - Incoming SMS: `https://your-api.com/webhooks/twilio/incoming`
   - Status Callbacks: `https://your-api.com/webhooks/twilio/status`

### Reverse Proxy Considerations

If your API is behind a reverse proxy (Railway, Heroku, etc.), ensure these headers are forwarded:
- `X-Forwarded-Proto`
- `X-Forwarded-Host`

The API uses these to reconstruct the original URL for signature validation.

---

## Rate Limiting

SMS sending is rate-limited to prevent abuse:

| Limit | Default | Description |
|-------|---------|-------------|
| Per-minute | 10 | Max SMS any user can send per minute |
| Per-hour | 100 | Max SMS any user can send per hour |
| Per-destination | 5/hour | Max SMS to the same phone number per hour |

### Response When Limited

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 45
Content-Type: application/json

{
  "detail": "Rate limit exceeded: Per-minute limit (10/min). Retry after 45 seconds."
}
```

### Customizing Limits

Set environment variables:
```bash
RATE_LIMIT_SMS_PER_MINUTE=20
RATE_LIMIT_SMS_PER_HOUR=200
RATE_LIMIT_SMS_PER_DESTINATION_HOUR=10
```

---

## Role-Based Access Control

### Roles

| Role | Description |
|------|-------------|
| `user` | Standard user - can send SMS/email, view/edit customers |
| `admin` | Administrator - all user permissions + delete customers, admin panel |
| `superuser` | Full access - all permissions including user management |

### Permissions

| Permission | user | admin | superuser |
|------------|------|-------|-----------|
| `send_sms` | ✓ | ✓ | ✓ |
| `send_email` | ✓ | ✓ | ✓ |
| `view_customers` | ✓ | ✓ | ✓ |
| `edit_customers` | ✓ | ✓ | ✓ |
| `delete_customers` | | ✓ | ✓ |
| `view_all_communications` | | ✓ | ✓ |
| `admin_panel` | | ✓ | ✓ |
| `manage_users` | | | ✓ |

### Setting User Roles

```sql
-- Make user an admin (via is_superuser flag for now)
UPDATE api_users SET is_superuser = true WHERE email = 'admin@example.com';
```

---

## Production Checklist

### Before Deployment

- [ ] Generate strong `SECRET_KEY` (32+ characters)
- [ ] Set `ENVIRONMENT=production`
- [ ] Set `DOCS_ENABLED=false` (or protect docs endpoint)
- [ ] Configure `TWILIO_AUTH_TOKEN` for webhook security
- [ ] Set proper `FRONTEND_URL` for CORS
- [ ] Ensure HTTPS is enforced at load balancer level

### Security Verification

Run the security tests:

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run security tests
pytest tests/test_security.py -v

# Run all tests
pytest -v
```

### Monitoring

- Monitor for 429 responses (rate limiting triggers)
- Monitor for 403 responses (potential unauthorized access attempts)
- Check logs for "signature" warnings (potential Twilio spoofing)

---

## Reporting Security Issues

If you discover a security vulnerability, please report it privately to the development team. Do not create public issues for security vulnerabilities.
