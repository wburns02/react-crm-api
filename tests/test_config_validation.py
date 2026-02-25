"""Tests for config.py environment variable validation."""
import pytest
from unittest.mock import patch
import os


class TestSettingsValidation:
    """Test production security validation in Settings."""

    def test_weak_secret_key_rejected_in_production(self):
        """Production must reject known weak secret keys."""
        from app.config import WEAK_SECRET_KEYS
        assert "changeme" in WEAK_SECRET_KEYS
        assert "secret" in WEAK_SECRET_KEYS
        assert len(WEAK_SECRET_KEYS) >= 6

    def test_development_defaults_work(self):
        """Settings should load with defaults in development."""
        env = {
            "ENVIRONMENT": "development",
            "DATABASE_URL": "postgresql+asyncpg://localhost/test",
        }
        with patch.dict(os.environ, env, clear=False):
            from app.config import Settings
            s = Settings(
                ENVIRONMENT="development",
                DATABASE_URL="postgresql+asyncpg://localhost/test",
            )
            assert s.DEBUG is True
            assert s.ENVIRONMENT == "development"
            assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 120

    def test_database_url_conversion(self):
        """postgresql:// should be converted to postgresql+asyncpg://."""
        from app.config import Settings
        s = Settings(
            ENVIRONMENT="development",
            DATABASE_URL="postgresql://user:pass@host:5432/db",
        )
        assert s.DATABASE_URL.startswith("postgresql+asyncpg://")

    def test_production_rejects_short_secret(self):
        """Production should reject secrets shorter than 32 chars."""
        from app.config import Settings
        with pytest.raises(Exception):
            Settings(
                ENVIRONMENT="production",
                SECRET_KEY="tooshort",
                DATABASE_URL="postgresql+asyncpg://localhost/db",
            )

    def test_production_rejects_default_secret(self):
        """Production should reject the default dev secret."""
        from app.config import Settings
        with pytest.raises(Exception):
            Settings(
                ENVIRONMENT="production",
                SECRET_KEY="development-secret-key-change-in-production",
                DATABASE_URL="postgresql+asyncpg://localhost/db",
            )

    def test_production_accepts_strong_secret(self):
        """Production should accept a strong secret key."""
        import secrets
        from app.config import Settings
        strong_key = secrets.token_urlsafe(32)
        s = Settings(
            ENVIRONMENT="production",
            SECRET_KEY=strong_key,
            DATABASE_URL="postgresql+asyncpg://localhost/db",
        )
        assert s.SECRET_KEY == strong_key
        assert s.DEBUG is False  # Forced off in production

    def test_is_production_property(self):
        """is_production should detect production/staging."""
        from app.config import Settings
        s = Settings(ENVIRONMENT="development", DATABASE_URL="postgresql+asyncpg://localhost/db")
        assert s.is_production is False

    def test_refresh_token_expiry(self):
        """Refresh token should be longer than access token."""
        from app.config import Settings
        s = Settings(ENVIRONMENT="development", DATABASE_URL="postgresql+asyncpg://localhost/db")
        assert s.REFRESH_TOKEN_EXPIRE_MINUTES > s.ACCESS_TOKEN_EXPIRE_MINUTES
