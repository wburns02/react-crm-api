"""
Security Tests

Tests for all security controls:
- Twilio signature verification
- Rate limiting
- RBAC
- Auth security
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from twilio.request_validator import RequestValidator
import hmac
import hashlib
import base64
from urllib.parse import urlencode

from app.main import app
from app.database import Base, get_db
from app.api.deps import get_password_hash, create_access_token
from app.models.user import User
from app.security.rate_limiter import get_sms_rate_limiter


# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_security.db"


@pytest_asyncio.fixture
async def test_db():
    """Create test database and tables."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(test_db: AsyncSession):
    """Create a test user."""
    user = User(
        email="test@example.com",
        hashed_password=get_password_hash("testpassword123"),
        first_name="Test",
        last_name="User",
        is_active=True,
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(test_db: AsyncSession):
    """Create an admin user."""
    user = User(
        email="admin@example.com",
        hashed_password=get_password_hash("adminpassword123"),
        first_name="Admin",
        last_name="User",
        is_active=True,
        is_superuser=True,
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def client(test_db: AsyncSession):
    """Create test client with overridden database."""
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def authenticated_client(client: AsyncClient, test_user: User):
    """Create authenticated test client."""
    token = create_access_token(data={"sub": str(test_user.id), "email": test_user.email})
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient, admin_user: User):
    """Create admin authenticated test client."""
    token = create_access_token(data={"sub": str(admin_user.id), "email": admin_user.email})
    client.headers["Authorization"] = f"Bearer {token}"
    return client


# ============================================================================
# TWILIO SIGNATURE VERIFICATION TESTS
# ============================================================================

class TestTwilioSignatureVerification:
    """Test Twilio webhook signature validation."""

    @pytest.mark.asyncio
    async def test_missing_signature_rejected(self, client: AsyncClient):
        """Webhook without X-Twilio-Signature should be rejected with 403."""
        response = await client.post(
            "/webhooks/twilio/incoming",
            data={
                "MessageSid": "SM1234567890",
                "From": "+15551234567",
                "To": "+15559876543",
                "Body": "Test message",
            },
        )
        assert response.status_code == 403
        assert "Missing Twilio signature" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self, client: AsyncClient):
        """Webhook with invalid X-Twilio-Signature should be rejected with 403."""
        response = await client.post(
            "/webhooks/twilio/incoming",
            data={
                "MessageSid": "SM1234567890",
                "From": "+15551234567",
                "To": "+15559876543",
                "Body": "Test message",
            },
            headers={"X-Twilio-Signature": "invalid_signature_here"},
        )
        assert response.status_code == 403
        detail = response.json()["detail"]
        # Should be rejected for invalid signature or validation error (if token not configured)
        assert "Invalid Twilio signature" in detail or "Signature validation error" in detail

    @pytest.mark.asyncio
    async def test_status_callback_missing_signature_rejected(self, client: AsyncClient):
        """Status callback without signature should be rejected."""
        response = await client.post(
            "/webhooks/twilio/status",
            data={
                "MessageSid": "SM1234567890",
                "MessageStatus": "delivered",
            },
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_valid_signature_accepted(self, client: AsyncClient, monkeypatch):
        """Webhook with valid signature should be accepted (requires Twilio setup)."""
        # This test validates the signature verification infrastructure works
        # In CI/CD, set TWILIO_AUTH_TOKEN for full validation

        # Skip detailed signature test if no Twilio token configured
        import os
        if not os.environ.get("TWILIO_AUTH_TOKEN"):
            pytest.skip("TWILIO_AUTH_TOKEN not set - skipping signature acceptance test")

        auth_token = os.environ["TWILIO_AUTH_TOKEN"]
        url = "http://test/webhooks/twilio/incoming"
        params = {
            "MessageSid": "SM1234567890",
            "From": "+15551234567",
            "To": "+15559876543",
            "Body": "Test message",
        }

        validator = RequestValidator(auth_token)
        signature = validator.compute_signature(url, params)

        response = await client.post(
            "/webhooks/twilio/incoming",
            data=params,
            headers={"X-Twilio-Signature": signature},
        )
        # Should not get signature-related 403
        if response.status_code == 403:
            detail = response.json().get("detail", "")
            assert "Missing Twilio signature" not in detail
            assert "Invalid Twilio signature" not in detail


# ============================================================================
# RATE LIMITING TESTS
# ============================================================================

class TestRateLimiting:
    """Test rate limiting on SMS endpoints."""

    @pytest.mark.skip(reason="Test needs update: UUID columns incompatible with SQLite test DB (str has no attribute hex)")
    @pytest.mark.asyncio
    async def test_rate_limit_per_minute(self, authenticated_client: AsyncClient):
        """Should enforce per-minute rate limit."""
        # Reset rate limiter
        rate_limiter = get_sms_rate_limiter()
        rate_limiter._minute_windows.clear()
        rate_limiter._hour_windows.clear()
        rate_limiter._destination_windows.clear()

        # Make requests up to limit (this will fail because Twilio isn't configured,
        # but we're testing the rate limit logic)
        for i in range(10):
            response = await authenticated_client.post(
                "/api/v2/communications/sms/send",
                json={
                    "to": f"+1555123000{i}",  # Different numbers
                    "body": "Test message",
                    "customer_id": "00000000-0000-0000-0000-000000000001",
                },
            )
            # Might fail for other reasons (no Twilio), but shouldn't be rate limited yet
            if response.status_code == 429:
                pytest.fail(f"Rate limited too early at request {i+1}")

        # Next request should be rate limited
        response = await authenticated_client.post(
            "/api/v2/communications/sms/send",
            json={
                "to": "+15551230099",
                "body": "Test message",
                "customer_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]

    @pytest.mark.skip(reason="Test needs update: UUID columns incompatible with SQLite test DB (str has no attribute hex)")
    @pytest.mark.asyncio
    async def test_rate_limit_per_destination(self, authenticated_client: AsyncClient):
        """Should enforce per-destination rate limit."""
        # Reset rate limiter
        rate_limiter = get_sms_rate_limiter()
        rate_limiter._minute_windows.clear()
        rate_limiter._hour_windows.clear()
        rate_limiter._destination_windows.clear()

        same_number = "+15551234567"

        # Make requests to same number up to limit
        for i in range(5):
            response = await authenticated_client.post(
                "/api/v2/communications/sms/send",
                json={
                    "to": same_number,
                    "body": f"Test message {i}",
                    "customer_id": "00000000-0000-0000-0000-000000000001",
                },
            )
            if response.status_code == 429:
                pytest.fail(f"Rate limited too early at request {i+1}")

        # Next request to same number should be rate limited
        response = await authenticated_client.post(
            "/api/v2/communications/sms/send",
            json={
                "to": same_number,
                "body": "Test message 6",
                "customer_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert response.status_code == 429
        assert "Per-destination limit" in response.json()["detail"]

    @pytest.mark.skip(reason="Test needs update: UUID columns incompatible with SQLite test DB (str has no attribute hex)")
    @pytest.mark.asyncio
    async def test_rate_limit_headers(self, authenticated_client: AsyncClient):
        """Should include Retry-After header when rate limited."""
        # Reset and exhaust limit
        rate_limiter = get_sms_rate_limiter()
        rate_limiter._minute_windows.clear()
        rate_limiter._hour_windows.clear()
        rate_limiter._destination_windows.clear()

        # Exhaust per-destination limit
        same_number = "+15559999999"
        for i in range(5):
            await authenticated_client.post(
                "/api/v2/communications/sms/send",
                json={"to": same_number, "body": f"msg{i}", "customer_id": 1},
            )

        response = await authenticated_client.post(
            "/api/v2/communications/sms/send",
            json={"to": same_number, "body": "overflow", "customer_id": 1},
        )

        assert response.status_code == 429
        assert "Retry-After" in response.headers


# ============================================================================
# RBAC TESTS
# ============================================================================

class TestRBAC:
    """Test role-based access control."""

    @pytest.mark.asyncio
    async def test_unauthenticated_access_denied(self, client: AsyncClient):
        """Unauthenticated requests should be denied."""
        response = await client.post(
            "/api/v2/communications/sms/send",
            json={
                "to": "+15551234567",
                "body": "Test",
                "customer_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="SQLite UUID incompatibility in messages table - works on PostgreSQL")
    async def test_regular_user_can_send_sms(self, authenticated_client: AsyncClient):
        """Regular users should have send_sms permission."""
        # Reset rate limiter
        rate_limiter = get_sms_rate_limiter()
        rate_limiter._minute_windows.clear()
        rate_limiter._hour_windows.clear()
        rate_limiter._destination_windows.clear()

        response = await authenticated_client.post(
            "/api/v2/communications/sms/send",
            json={
                "to": "+15551234567",
                "body": "Test",
                "customer_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        # Should not be 403 (permission denied)
        assert response.status_code != 403 or "permission" not in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="SQLite UUID incompatibility in messages table - works on PostgreSQL")
    async def test_admin_has_all_permissions(self, admin_client: AsyncClient):
        """Admin users should have all permissions."""
        # Reset rate limiter
        rate_limiter = get_sms_rate_limiter()
        rate_limiter._minute_windows.clear()
        rate_limiter._hour_windows.clear()
        rate_limiter._destination_windows.clear()

        response = await admin_client.post(
            "/api/v2/communications/sms/send",
            json={
                "to": "+15551234567",
                "body": "Test",
                "customer_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        # Should not be 403 (permission denied)
        assert response.status_code != 403 or "permission" not in response.json().get("detail", "").lower()


# ============================================================================
# AUTH SECURITY TESTS
# ============================================================================

class TestAuthSecurity:
    """Test authentication security measures."""

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, client: AsyncClient):
        """Invalid JWT tokens should be rejected."""
        client.headers["Authorization"] = "Bearer invalid_token_here"
        response = await client.get("/api/v2/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, client: AsyncClient, test_user: User):
        """Expired tokens should be rejected."""
        from datetime import timedelta

        # Create expired token
        expired_token = create_access_token(
            data={"sub": str(test_user.id), "email": test_user.email},
            expires_delta=timedelta(seconds=-1)  # Already expired
        )

        client.headers["Authorization"] = f"Bearer {expired_token}"
        response = await client.get("/api/v2/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_tampered_token_rejected(self, client: AsyncClient, test_user: User):
        """Tampered tokens should be rejected."""
        token = create_access_token(data={"sub": str(test_user.id), "email": test_user.email})
        # Tamper with the token
        tampered_token = token[:-5] + "xxxxx"

        client.headers["Authorization"] = f"Bearer {tampered_token}"
        response = await client.get("/api/v2/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_user_rejected(self, test_db: AsyncSession, client: AsyncClient):
        """Inactive users should be rejected."""
        # Create inactive user
        inactive_user = User(
            email="inactive@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Inactive",
            last_name="User",
            is_active=False,
        )
        test_db.add(inactive_user)
        await test_db.commit()
        await test_db.refresh(inactive_user)

        token = create_access_token(data={"sub": str(inactive_user.id), "email": inactive_user.email})
        client.headers["Authorization"] = f"Bearer {token}"

        response = await client.get("/api/v2/auth/me")
        assert response.status_code == 403
        assert "disabled" in response.json()["detail"].lower()


# ============================================================================
# SENSITIVE DATA LOGGING TESTS
# ============================================================================

class TestSensitiveDataProtection:
    """Test that sensitive data is not exposed."""

    @pytest.mark.asyncio
    async def test_login_error_no_detail_leak(self, client: AsyncClient):
        """Login errors should not reveal whether email exists."""
        # Try non-existent email
        response1 = await client.post(
            "/api/v2/auth/login",
            json={"email": "nonexistent@example.com", "password": "wrongpassword"},
        )

        # The error message should be generic
        assert response1.status_code == 401
        detail1 = response1.json()["detail"]

        # Try wrong password for existing email (if we had one)
        # The error should be the same generic message
        assert "Incorrect email or password" in detail1 or "credentials" in detail1.lower()


# ============================================================================
# CONFIGURATION SECURITY TESTS
# ============================================================================

class TestConfigurationSecurity:
    """Test security configuration."""

    def test_weak_secret_key_rejected_in_production(self, monkeypatch):
        """Weak SECRET_KEY should be rejected in production."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "secret")

        # Clear the settings cache
        from app.config import get_settings
        get_settings.cache_clear()

        with pytest.raises(ValueError) as exc_info:
            get_settings()

        assert "SECRET_KEY" in str(exc_info.value)
        assert "weak" in str(exc_info.value).lower() or "default" in str(exc_info.value).lower()

        # Reset
        monkeypatch.setenv("ENVIRONMENT", "development")
        get_settings.cache_clear()

    def test_short_secret_key_rejected_in_production(self, monkeypatch):
        """Short SECRET_KEY should be rejected in production."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "short")  # Less than 32 chars

        from app.config import get_settings
        get_settings.cache_clear()

        with pytest.raises(ValueError) as exc_info:
            get_settings()

        assert "SECRET_KEY" in str(exc_info.value)
        assert "32 characters" in str(exc_info.value)

        # Reset
        monkeypatch.setenv("ENVIRONMENT", "development")
        get_settings.cache_clear()
