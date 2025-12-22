"""
Rate Limiting Module

Provides per-user and per-destination rate limiting for sensitive endpoints
like SMS sending to prevent abuse.
"""

import time
from collections import defaultdict
from typing import Dict, Optional
from dataclasses import dataclass, field
from fastapi import HTTPException, status, Request
import logging

from app.models.user import User

logger = logging.getLogger(__name__)


@dataclass
class RateLimitWindow:
    """Track requests within a time window."""
    count: int = 0
    window_start: float = field(default_factory=time.time)


class RateLimiter:
    """
    In-memory rate limiter with per-user and per-destination tracking.

    For production at scale, consider Redis-based implementation.
    """

    def __init__(
        self,
        requests_per_minute: int = 10,
        requests_per_hour: int = 100,
        per_destination_per_hour: int = 5,
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.per_destination_per_hour = per_destination_per_hour

        # Track: user_id -> RateLimitWindow
        self._minute_windows: Dict[int, RateLimitWindow] = defaultdict(RateLimitWindow)
        self._hour_windows: Dict[int, RateLimitWindow] = defaultdict(RateLimitWindow)

        # Track: (user_id, destination) -> RateLimitWindow
        self._destination_windows: Dict[tuple, RateLimitWindow] = defaultdict(RateLimitWindow)

    def _check_window(
        self,
        window: RateLimitWindow,
        window_seconds: int,
        max_requests: int,
        limit_name: str,
    ) -> None:
        """Check and update a rate limit window."""
        now = time.time()

        # Reset window if expired
        if now - window.window_start > window_seconds:
            window.count = 0
            window.window_start = now

        # Check limit
        if window.count >= max_requests:
            retry_after = int(window_seconds - (now - window.window_start))
            logger.warning(
                f"Rate limit exceeded: {limit_name}",
                extra={"retry_after": retry_after}
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {limit_name}. Retry after {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)}
            )

        # Increment counter
        window.count += 1

    def check_user_limits(self, user_id: int) -> None:
        """Check per-user rate limits (minute and hour windows)."""
        # Check minute limit
        self._check_window(
            self._minute_windows[user_id],
            window_seconds=60,
            max_requests=self.requests_per_minute,
            limit_name=f"Per-minute limit ({self.requests_per_minute}/min)"
        )

        # Check hour limit
        self._check_window(
            self._hour_windows[user_id],
            window_seconds=3600,
            max_requests=self.requests_per_hour,
            limit_name=f"Per-hour limit ({self.requests_per_hour}/hour)"
        )

    def check_destination_limit(self, user_id: int, destination: str) -> None:
        """Check per-destination rate limit to prevent spam to single number."""
        key = (user_id, destination)
        self._check_window(
            self._destination_windows[key],
            window_seconds=3600,
            max_requests=self.per_destination_per_hour,
            limit_name=f"Per-destination limit ({self.per_destination_per_hour}/hour to same number)"
        )

    def check_sms_limits(self, user_id: int, destination: str) -> None:
        """Combined check for SMS sending."""
        self.check_user_limits(user_id)
        self.check_destination_limit(user_id, destination)

    def reset_user(self, user_id: int) -> None:
        """Reset all limits for a user (for testing or admin override)."""
        self._minute_windows.pop(user_id, None)
        self._hour_windows.pop(user_id, None)
        # Clean up destination windows for this user
        keys_to_remove = [k for k in self._destination_windows if k[0] == user_id]
        for key in keys_to_remove:
            self._destination_windows.pop(key, None)


# Global rate limiter instance
_sms_rate_limiter = RateLimiter(
    requests_per_minute=10,
    requests_per_hour=100,
    per_destination_per_hour=5,
)


def rate_limit_sms(user: User, destination: str) -> None:
    """
    Apply SMS rate limiting for a user and destination.

    Args:
        user: Current authenticated user
        destination: Phone number being messaged

    Raises:
        HTTPException 429 if rate limit exceeded
    """
    _sms_rate_limiter.check_sms_limits(user.id, destination)


def get_sms_rate_limiter() -> RateLimiter:
    """Get the global SMS rate limiter instance."""
    return _sms_rate_limiter
