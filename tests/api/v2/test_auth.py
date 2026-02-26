"""
Tests for the auth API endpoints (/api/v2/auth).
"""
import time
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from jose import jwt

from app.main import app as fastapi_app
from app.database import Base, get_db
from app.api.deps import get_password_hash, create_access_token, verify_password
from app.config import settings
from app.models.user import User
from app.models.company_entity import CompanyEntity
from app.models.technician import Technician


# ---------------------------------------------------------------------------
# Isolated test database (avoids SQLite lock with shared test.db)
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_auth.db"

AUTH_PREFIX = "/api/v2/auth"

# Only the tables needed for auth tests (avoids FK resolution errors
# from unrelated models when using Base.metadata.create_all without filters)
_AUTH_TABLES = [
    CompanyEntity.__table__,
    User.__table__,
    Technician.__table__,
]


@pytest_asyncio.fixture
async def test_db():
    """Create an isolated test database for auth tests."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_AUTH_TABLES)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=_AUTH_TABLES)

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

    fastapi_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    fastapi_app.dependency_overrides.clear()


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_token(token: str) -> dict:
    """Decode a JWT token issued by the application."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


class TestLogin:
    """Tests for POST /auth/login."""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, test_user: User):
        """Successful login returns access token and sets cookies."""
        response = await client.post(
            f"{AUTH_PREFIX}/login",
            json={"email": "test@example.com", "password": "testpassword123"},
        )
        assert response.status_code == 200
        data = response.json()

        # Response must include both access_token and token (React compat)
        assert "access_token" in data
        assert "token" in data
        assert data["token_type"] == "bearer"
        assert data["access_token"] == data["token"]

        # Verify the token decodes correctly
        payload = _decode_token(data["access_token"])
        assert payload["sub"] == str(test_user.id)
        assert payload["email"] == test_user.email

        # Session cookie should be set
        assert "session" in response.cookies

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, test_user: User):
        """Login with wrong password returns 401."""
        response = await client.post(
            f"{AUTH_PREFIX}/login",
            json={"email": "test@example.com", "password": "wrongpassword"},
        )
        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_nonexistent_email(self, client: AsyncClient, test_user: User):
        """Login with non-existent email returns 401."""
        response = await client.post(
            f"{AUTH_PREFIX}/login",
            json={"email": "nobody@example.com", "password": "testpassword123"},
        )
        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, test_db: AsyncSession, client: AsyncClient):
        """Login with a disabled account returns 401."""
        inactive = User(
            email="inactive@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Disabled",
            last_name="Account",
            is_active=False,
        )
        test_db.add(inactive)
        await test_db.commit()

        response = await client.post(
            f"{AUTH_PREFIX}/login",
            json={"email": "inactive@example.com", "password": "password123"},
        )
        assert response.status_code == 401
        assert "disabled" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_sets_refresh_cookie(self, client: AsyncClient, test_user: User):
        """Successful login sets an HTTP-only refresh cookie."""
        response = await client.post(
            f"{AUTH_PREFIX}/login",
            json={"email": "test@example.com", "password": "testpassword123"},
        )
        assert response.status_code == 200
        # Check raw set-cookie headers for refresh cookie
        set_cookie_headers = [
            v for k, v in response.headers.multi_items() if k.lower() == "set-cookie"
        ]
        refresh_cookies = [h for h in set_cookie_headers if h.startswith("refresh=")]
        assert len(refresh_cookies) >= 1, "Expected a refresh cookie to be set"

    @pytest.mark.asyncio
    async def test_login_password_never_returned(self, client: AsyncClient, test_user: User):
        """Login response must never include the password or hash."""
        response = await client.post(
            f"{AUTH_PREFIX}/login",
            json={"email": "test@example.com", "password": "testpassword123"},
        )
        body = response.text
        assert "testpassword123" not in body
        assert "hashed_password" not in body
        assert "$2b$" not in body  # bcrypt hash prefix

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, client: AsyncClient, test_user: User):
        """Login with missing fields returns 422 validation error."""
        response = await client.post(f"{AUTH_PREFIX}/login", json={})
        assert response.status_code == 422

        response = await client.post(
            f"{AUTH_PREFIX}/login", json={"email": "test@example.com"}
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


class TestLogout:
    """Tests for POST /auth/logout."""

    @pytest.mark.asyncio
    async def test_logout_clears_cookies(self, client: AsyncClient, test_user: User):
        """Logout clears session and refresh cookies."""
        # Login first to establish cookies
        login_resp = await client.post(
            f"{AUTH_PREFIX}/login",
            json={"email": "test@example.com", "password": "testpassword123"},
        )
        assert login_resp.status_code == 200

        # Logout
        response = await client.post(f"{AUTH_PREFIX}/logout")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Successfully logged out"

        # Session cookie should be cleared (set to empty / max-age=0)
        set_cookie_headers = [
            v for k, v in response.headers.multi_items() if k.lower() == "set-cookie"
        ]
        session_cookies = [h for h in set_cookie_headers if h.startswith("session=")]
        assert len(session_cookies) >= 1, "Expected session cookie to be deleted"

    @pytest.mark.asyncio
    async def test_logout_without_session(self, client: AsyncClient):
        """Logout without an active session still returns success."""
        response = await client.post(f"{AUTH_PREFIX}/logout")
        assert response.status_code == 200
        assert response.json()["message"] == "Successfully logged out"


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


class TestAuthMe:
    """Tests for GET /auth/me."""

    @pytest.mark.asyncio
    async def test_me_authenticated(self, authenticated_client: AsyncClient, test_user: User):
        """Authenticated user gets their own info."""
        response = await authenticated_client.get(f"{AUTH_PREFIX}/me")
        assert response.status_code == 200
        data = response.json()

        assert "user" in data
        user_data = data["user"]
        assert user_data["email"] == test_user.email
        assert user_data["first_name"] == test_user.first_name
        assert user_data["last_name"] == test_user.last_name
        assert user_data["is_active"] is True
        assert user_data["id"] == str(test_user.id)

    @pytest.mark.asyncio
    async def test_me_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request to /me returns 401."""
        response = await client.get(f"{AUTH_PREFIX}/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_me_admin_user(self, admin_client: AsyncClient, admin_user: User):
        """Admin user has is_superuser=True and role=admin."""
        response = await admin_client.get(f"{AUTH_PREFIX}/me")
        assert response.status_code == 200
        data = response.json()
        user_data = data["user"]
        assert user_data["is_superuser"] is True
        assert user_data["role"] == "admin"

    @pytest.mark.asyncio
    async def test_me_password_not_exposed(self, authenticated_client: AsyncClient):
        """The /me response must not contain password or hash fields."""
        response = await authenticated_client.get(f"{AUTH_PREFIX}/me")
        body = response.text
        assert "hashed_password" not in body
        assert "$2b$" not in body

    @pytest.mark.asyncio
    async def test_me_with_expired_token(self, client: AsyncClient, test_user: User):
        """Expired token returns 401."""
        expired_token = create_access_token(
            data={"sub": str(test_user.id), "email": test_user.email},
            expires_delta=timedelta(minutes=-10),
        )
        client.headers["Authorization"] = f"Bearer {expired_token}"
        response = await client.get(f"{AUTH_PREFIX}/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_invalid_token(self, client: AsyncClient):
        """Garbage token returns 401."""
        client.headers["Authorization"] = "Bearer this.is.not.a.valid.token"
        response = await client.get(f"{AUTH_PREFIX}/me")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------


class TestRefreshToken:
    """Tests for POST /auth/refresh."""

    @pytest.mark.asyncio
    async def test_refresh_valid_token(self, client: AsyncClient, test_user: User):
        """A valid refresh cookie yields a new access token."""
        refresh_token = create_access_token(
            data={"sub": str(test_user.id), "email": test_user.email, "type": "refresh"},
            expires_delta=timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES),
        )
        client.cookies.set("refresh", refresh_token)

        response = await client.post(f"{AUTH_PREFIX}/refresh")
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "token" in data
        assert data["token_type"] == "bearer"

        # New access token should be valid
        payload = _decode_token(data["access_token"])
        assert payload["sub"] == str(test_user.id)
        assert payload["email"] == test_user.email

    @pytest.mark.asyncio
    async def test_refresh_no_cookie(self, client: AsyncClient):
        """Refresh without a cookie returns 401."""
        response = await client.post(f"{AUTH_PREFIX}/refresh")
        assert response.status_code == 401
        assert "No refresh token" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_refresh_expired_token(self, client: AsyncClient, test_user: User):
        """Expired refresh token returns 401."""
        expired_refresh = create_access_token(
            data={"sub": str(test_user.id), "email": test_user.email, "type": "refresh"},
            expires_delta=timedelta(minutes=-10),
        )
        client.cookies.set("refresh", expired_refresh)

        response = await client.post(f"{AUTH_PREFIX}/refresh")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_wrong_token_type(self, client: AsyncClient, test_user: User):
        """A regular access token (no type=refresh) is rejected."""
        access_token = create_access_token(
            data={"sub": str(test_user.id), "email": test_user.email},
            expires_delta=timedelta(minutes=30),
        )
        client.cookies.set("refresh", access_token)

        response = await client.post(f"{AUTH_PREFIX}/refresh")
        assert response.status_code == 401
        assert "Invalid token type" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_refresh_inactive_user(self, test_db: AsyncSession, client: AsyncClient):
        """Refresh fails if user has been deactivated since the refresh token was issued."""
        user = User(
            email="deactivated@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Soon",
            last_name="Gone",
            is_active=True,
        )
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)

        refresh_token = create_access_token(
            data={"sub": str(user.id), "email": user.email, "type": "refresh"},
            expires_delta=timedelta(minutes=60),
        )
        client.cookies.set("refresh", refresh_token)

        # Deactivate the user
        user.is_active = False
        await test_db.commit()

        response = await client.post(f"{AUTH_PREFIX}/refresh")
        assert response.status_code == 401
        assert "not found or inactive" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# JWT token claims
# ---------------------------------------------------------------------------


class TestJWTTokenClaims:
    """Verify the structure and content of JWT tokens."""

    def test_token_contains_sub_and_email(self):
        """Token must contain sub (user id) and email claims."""
        token = create_access_token(data={"sub": "42", "email": "t@test.com"})
        payload = _decode_token(token)
        assert payload["sub"] == "42"
        assert payload["email"] == "t@test.com"

    def test_token_contains_expiry(self):
        """Token must contain an exp claim."""
        token = create_access_token(data={"sub": "1", "email": "t@test.com"})
        payload = _decode_token(token)
        assert "exp" in payload
        # Use time.time() for UTC comparison (datetime.utcnow().timestamp()
        # incorrectly applies local TZ offset on some Python versions)
        assert payload["exp"] > time.time()

    def test_token_custom_expiry(self):
        """Custom expires_delta is honoured."""
        delta = timedelta(minutes=5)
        token = create_access_token(
            data={"sub": "1", "email": "t@test.com"},
            expires_delta=delta,
        )
        payload = _decode_token(token)
        expected_exp = time.time() + delta.total_seconds()
        # Allow 5-second tolerance
        assert abs(payload["exp"] - expected_exp) < 5

    def test_refresh_token_has_type_claim(self):
        """Refresh tokens include type=refresh claim."""
        token = create_access_token(
            data={"sub": "1", "email": "t@test.com", "type": "refresh"},
            expires_delta=timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES),
        )
        payload = _decode_token(token)
        assert payload["type"] == "refresh"


# ---------------------------------------------------------------------------
# Password hashing helpers
# ---------------------------------------------------------------------------


class TestPasswordHelpers:
    """Test password hashing and verification utilities."""

    def test_verify_correct_password(self):
        """verify_password returns True for the correct password."""
        hashed = get_password_hash("my-secret-pass")
        assert verify_password("my-secret-pass", hashed) is True

    def test_verify_wrong_password(self):
        """verify_password returns False for the wrong password."""
        hashed = get_password_hash("my-secret-pass")
        assert verify_password("wrong-pass", hashed) is False

    def test_verify_empty_hash(self):
        """verify_password returns False when hash is None."""
        assert verify_password("anything", None) is False

    def test_hash_is_bcrypt(self):
        """Hashed password uses bcrypt ($2b$ prefix)."""
        hashed = get_password_hash("some-password")
        assert hashed.startswith("$2b$")

    def test_different_hashes_for_same_password(self):
        """Two hashes of the same password should differ (different salts)."""
        h1 = get_password_hash("same")
        h2 = get_password_hash("same")
        assert h1 != h2


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


class TestRegister:
    """Tests for POST /auth/register."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient, test_db: AsyncSession):
        """Registering a new user returns the user object."""
        response = await client.post(
            f"{AUTH_PREFIX}/register",
            json={
                "email": "newuser@example.com",
                "password": "Str0ngP@ssword!",
                "first_name": "New",
                "last_name": "User",
            },
        )
        assert response.status_code in (200, 201), response.text
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["first_name"] == "New"
        assert data["last_name"] == "User"
        # Password should not be in response
        assert "password" not in data
        assert "hashed_password" not in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient, test_user: User):
        """Registering with an existing email returns 400."""
        response = await client.post(
            f"{AUTH_PREFIX}/register",
            json={
                "email": "test@example.com",
                "password": "Str0ngP@ssword!",
                "first_name": "Dup",
                "last_name": "User",
            },
        )
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_weak_password(self, client: AsyncClient):
        """Registering with a weak password returns 422."""
        response = await client.post(
            f"{AUTH_PREFIX}/register",
            json={
                "email": "weak@example.com",
                "password": "short",
                "first_name": "Weak",
                "last_name": "Pass",
            },
        )
        assert response.status_code == 422
