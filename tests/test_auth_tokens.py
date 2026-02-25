"""Tests for JWT token creation, validation, and refresh token logic."""
import pytest
import time
from datetime import timedelta
from jose import jwt, JWTError


class TestJWTTokens:
    """Test JWT access and refresh token behavior."""

    def test_create_access_token(self):
        """Access token should contain sub and email claims."""
        from app.api.deps import create_access_token
        token = create_access_token(data={"sub": "1", "email": "test@example.com"})
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 50

    def test_access_token_decode(self):
        """Access token should be decodable with correct secret."""
        from app.api.deps import create_access_token
        from app.config import settings
        token = create_access_token(data={"sub": "42", "email": "user@test.com"})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["sub"] == "42"
        assert payload["email"] == "user@test.com"
        assert "exp" in payload

    def test_access_token_expiry(self):
        """Access token should have correct expiration time."""
        from app.api.deps import create_access_token
        from app.config import settings
        token = create_access_token(data={"sub": "1", "email": "test@test.com"})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        exp = payload["exp"]
        now = time.time()
        # Should expire within ACCESS_TOKEN_EXPIRE_MINUTES (120 min = 7200 sec)
        assert 7000 < (exp - now) < 7300

    def test_access_token_custom_expiry(self):
        """Should support custom expiration delta."""
        from app.api.deps import create_access_token
        from app.config import settings
        token = create_access_token(
            data={"sub": "1", "email": "test@test.com"},
            expires_delta=timedelta(minutes=30),
        )
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        exp = payload["exp"]
        now = time.time()
        assert 1700 < (exp - now) < 1900

    def test_wrong_secret_fails(self):
        """Token decoded with wrong secret should fail."""
        from app.api.deps import create_access_token
        token = create_access_token(data={"sub": "1", "email": "test@test.com"})
        with pytest.raises(JWTError):
            jwt.decode(token, "wrong-secret-key", algorithms=["HS256"])

    def test_token_algorithm_is_hs256(self):
        """Tokens should use HS256 algorithm."""
        from app.config import settings
        assert settings.ALGORITHM == "HS256"

    def test_refresh_token_longer_than_access(self):
        """Refresh token expiry should be longer than access token."""
        from app.config import settings
        assert settings.REFRESH_TOKEN_EXPIRE_MINUTES > settings.ACCESS_TOKEN_EXPIRE_MINUTES
        assert settings.REFRESH_TOKEN_EXPIRE_MINUTES == 1440  # 24 hours
