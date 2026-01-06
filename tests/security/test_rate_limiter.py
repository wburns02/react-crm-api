"""
Tests for the rate limiter module.
"""
import pytest
import time
from unittest.mock import MagicMock
from fastapi import HTTPException

from app.security.rate_limiter import (
    RateLimiter, RateLimitWindow,
    rate_limit_sms, get_sms_rate_limiter
)


class TestRateLimitWindow:
    """Test RateLimitWindow dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        window = RateLimitWindow()
        assert window.count == 0
        assert isinstance(window.window_start, float)
        assert window.window_start <= time.time()


class TestRateLimiter:
    """Test RateLimiter class."""

    def test_init_defaults(self):
        """Test default initialization values."""
        limiter = RateLimiter()
        assert limiter.requests_per_minute == 10
        assert limiter.requests_per_hour == 100
        assert limiter.per_destination_per_hour == 5

    def test_init_custom_values(self):
        """Test custom initialization values."""
        limiter = RateLimiter(
            requests_per_minute=5,
            requests_per_hour=50,
            per_destination_per_hour=3
        )
        assert limiter.requests_per_minute == 5
        assert limiter.requests_per_hour == 50
        assert limiter.per_destination_per_hour == 3

    def test_check_user_limits_under_limit(self):
        """Test user limits pass when under limit."""
        limiter = RateLimiter(requests_per_minute=10, requests_per_hour=100)
        # Should not raise
        for _ in range(5):
            limiter.check_user_limits(user_id=1)

    def test_check_user_limits_exceeds_minute_limit(self):
        """Test user minute limit is enforced."""
        limiter = RateLimiter(requests_per_minute=3, requests_per_hour=100)
        for _ in range(3):
            limiter.check_user_limits(user_id=1)
        with pytest.raises(HTTPException) as exc:
            limiter.check_user_limits(user_id=1)
        assert exc.value.status_code == 429
        assert "Per-minute limit" in exc.value.detail

    def test_check_destination_limit_under_limit(self):
        """Test destination limits pass when under limit."""
        limiter = RateLimiter(per_destination_per_hour=5)
        destination = "+15551234567"
        for _ in range(4):
            limiter.check_destination_limit(user_id=1, destination=destination)

    def test_check_destination_limit_exceeds_limit(self):
        """Test destination limit is enforced."""
        limiter = RateLimiter(per_destination_per_hour=2)
        destination = "+15551234567"
        for _ in range(2):
            limiter.check_destination_limit(user_id=1, destination=destination)
        with pytest.raises(HTTPException) as exc:
            limiter.check_destination_limit(user_id=1, destination=destination)
        assert exc.value.status_code == 429
        assert "Per-destination limit" in exc.value.detail

    def test_different_destinations_separate_limits(self):
        """Test different destinations have separate limits."""
        limiter = RateLimiter(per_destination_per_hour=2)
        dest1 = "+15551111111"
        dest2 = "+15552222222"

        for _ in range(2):
            limiter.check_destination_limit(user_id=1, destination=dest1)

        # Different destination should still work
        limiter.check_destination_limit(user_id=1, destination=dest2)

    def test_different_users_separate_limits(self):
        """Test different users have separate limits."""
        limiter = RateLimiter(requests_per_minute=2)

        for _ in range(2):
            limiter.check_user_limits(user_id=1)

        # Different user should still work
        limiter.check_user_limits(user_id=2)

    def test_check_sms_limits_combined(self):
        """Test combined SMS limits check."""
        limiter = RateLimiter(requests_per_minute=10, per_destination_per_hour=5)
        # Should not raise
        limiter.check_sms_limits(user_id=1, destination="+15551234567")

    def test_reset_user_clears_limits(self):
        """Test reset_user clears all limits for a user."""
        limiter = RateLimiter(requests_per_minute=2)
        destination = "+15551234567"

        # Exhaust limits
        for _ in range(2):
            limiter.check_user_limits(user_id=1)

        # Should be rate limited
        with pytest.raises(HTTPException):
            limiter.check_user_limits(user_id=1)

        # Reset and try again
        limiter.reset_user(user_id=1)
        limiter.check_user_limits(user_id=1)  # Should not raise

    def test_retry_after_header(self):
        """Test Retry-After header is present when rate limited."""
        limiter = RateLimiter(requests_per_minute=1)
        limiter.check_user_limits(user_id=1)
        with pytest.raises(HTTPException) as exc:
            limiter.check_user_limits(user_id=1)
        assert "Retry-After" in exc.value.headers


class TestGlobalRateLimiter:
    """Test global rate limiter functions."""

    def test_get_sms_rate_limiter_returns_instance(self):
        """Test get_sms_rate_limiter returns a RateLimiter."""
        limiter = get_sms_rate_limiter()
        assert isinstance(limiter, RateLimiter)

    def test_rate_limit_sms_function(self):
        """Test rate_limit_sms function with mocked user."""
        limiter = get_sms_rate_limiter()
        # Clear any existing state
        limiter._minute_windows.clear()
        limiter._hour_windows.clear()
        limiter._destination_windows.clear()

        user = MagicMock()
        user.id = 999
        # Should not raise for first request
        rate_limit_sms(user, "+15551234567")
