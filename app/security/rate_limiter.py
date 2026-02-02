"""
Rate Limiting Module

Provides per-user and per-destination rate limiting for sensitive endpoints
like SMS sending to prevent abuse.

Supports optional Redis backend for distributed deployments.
"""

import time
import logging
from collections import defaultdict
from typing import Dict, Optional
from dataclasses import dataclass, field
from fastapi import HTTPException, status

from app.models.user import User

logger = logging.getLogger(__name__)


@dataclass
class RateLimitWindow:
    """Track requests within a time window."""

    count: int = 0
    window_start: float = field(default_factory=time.time)


class RateLimiter:
    """
    Rate limiter with per-user and per-destination tracking.

    Supports optional Redis backend for distributed deployments.
    Falls back to in-memory when Redis is unavailable.
    """

    def __init__(
        self,
        requests_per_minute: int = 10,
        requests_per_hour: int = 100,
        per_destination_per_hour: int = 5,
        redis_client=None,
        fail_closed: bool = False,
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.per_destination_per_hour = per_destination_per_hour
        self.redis = redis_client
        self.fail_closed = fail_closed

        # In-memory fallback storage
        self._minute_windows: Dict[int, RateLimitWindow] = defaultdict(RateLimitWindow)
        self._hour_windows: Dict[int, RateLimitWindow] = defaultdict(RateLimitWindow)
        self._destination_windows: Dict[tuple, RateLimitWindow] = defaultdict(RateLimitWindow)

    def _check_redis_limit(
        self,
        key: str,
        window_seconds: int,
        max_requests: int,
        limit_name: str,
    ) -> None:
        """Check rate limit using Redis sliding window."""
        if not self.redis:
            raise RuntimeError("Redis not available")

        now = time.time()
        window_start = now - window_seconds

        try:
            # Use pipeline for atomic operations
            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)  # Remove old entries
            pipe.zadd(key, {f"{now}": now})  # Add current request
            pipe.zcard(key)  # Count requests in window
            pipe.expire(key, window_seconds)  # Set TTL for cleanup

            results = pipe.execute()
            count = results[2]  # zcard result

            if count > max_requests:
                retry_after = int(window_seconds - (now - window_start))
                logger.warning(
                    f"Rate limit exceeded: {limit_name}",
                    extra={"key": key, "count": count, "retry_after": retry_after},
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded: {limit_name}. Retry after {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )
        except HTTPException:
            raise  # Re-raise rate limit exceptions
        except Exception as e:
            logger.error(f"Redis rate limit error: {e}")
            if self.fail_closed:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Rate limiting service unavailable",
                )
            # Fall through to in-memory check
            raise RuntimeError(f"Redis error: {e}")

    def _check_memory_window(
        self,
        window: RateLimitWindow,
        window_seconds: int,
        max_requests: int,
        limit_name: str,
    ) -> None:
        """Check and update a rate limit window in memory."""
        now = time.time()

        # Reset window if expired
        if now - window.window_start > window_seconds:
            window.count = 0
            window.window_start = now

        # Check limit
        if window.count >= max_requests:
            retry_after = int(window_seconds - (now - window.window_start))
            logger.warning(f"Rate limit exceeded: {limit_name}", extra={"retry_after": retry_after})
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {limit_name}. Retry after {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

        # Increment counter
        window.count += 1

    def _check_limit(
        self,
        key: str,
        memory_window: RateLimitWindow,
        window_seconds: int,
        max_requests: int,
        limit_name: str,
    ) -> None:
        """Check rate limit using Redis if available, otherwise memory."""
        if self.redis:
            try:
                self._check_redis_limit(f"sms_limit:{key}", window_seconds, max_requests, limit_name)
                return
            except RuntimeError:
                # Redis error, fall back to memory unless fail_closed
                if self.fail_closed:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Rate limiting service unavailable",
                    )
                logger.warning("Redis unavailable, falling back to in-memory rate limiting")

        # Use in-memory
        self._check_memory_window(memory_window, window_seconds, max_requests, limit_name)

    def check_user_limits(self, user_id: int) -> None:
        """Check per-user rate limits (minute and hour windows)."""
        # Check minute limit
        self._check_limit(
            key=f"user:{user_id}:minute",
            memory_window=self._minute_windows[user_id],
            window_seconds=60,
            max_requests=self.requests_per_minute,
            limit_name=f"Per-minute limit ({self.requests_per_minute}/min)",
        )

        # Check hour limit
        self._check_limit(
            key=f"user:{user_id}:hour",
            memory_window=self._hour_windows[user_id],
            window_seconds=3600,
            max_requests=self.requests_per_hour,
            limit_name=f"Per-hour limit ({self.requests_per_hour}/hour)",
        )

    def check_destination_limit(self, user_id: int, destination: str) -> None:
        """Check per-destination rate limit to prevent spam to single number."""
        key = (user_id, destination)
        self._check_limit(
            key=f"dest:{user_id}:{destination}",
            memory_window=self._destination_windows[key],
            window_seconds=3600,
            max_requests=self.per_destination_per_hour,
            limit_name=f"Per-destination limit ({self.per_destination_per_hour}/hour to same number)",
        )

    def check_sms_limits(self, user_id: int, destination: str) -> None:
        """Combined check for SMS sending."""
        self.check_user_limits(user_id)
        self.check_destination_limit(user_id, destination)

    def reset_user(self, user_id: int) -> None:
        """Reset all limits for a user (for testing or admin override)."""
        # Reset in-memory
        self._minute_windows.pop(user_id, None)
        self._hour_windows.pop(user_id, None)
        keys_to_remove = [k for k in self._destination_windows if k[0] == user_id]
        for key in keys_to_remove:
            self._destination_windows.pop(key, None)

        # Reset Redis if available
        if self.redis:
            try:
                # Use scan to find and delete all keys for this user
                for pattern in [f"sms_limit:user:{user_id}:*", f"sms_limit:dest:{user_id}:*"]:
                    cursor = 0
                    while True:
                        cursor, keys = self.redis.scan(cursor, match=pattern, count=100)
                        if keys:
                            self.redis.delete(*keys)
                        if cursor == 0:
                            break
            except Exception as e:
                logger.warning(f"Failed to reset Redis limits for user {user_id}: {e}")


# Global rate limiter instance
_sms_rate_limiter: Optional[RateLimiter] = None


def _get_redis_client():
    """Get Redis client for rate limiting."""
    from app.config import settings

    if not settings.RATE_LIMIT_REDIS_ENABLED or not settings.REDIS_URL:
        return None

    try:
        import redis

        client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        # Test connection
        client.ping()
        logger.info("SMS rate limiting: Redis enabled")
        return client
    except ImportError:
        logger.warning("SMS rate limiting: Redis package not installed, using in-memory")
        return None
    except Exception as e:
        logger.warning(f"SMS rate limiting: Redis unavailable ({e}), using in-memory")
        return None


def get_sms_rate_limiter() -> RateLimiter:
    """Get or create the global SMS rate limiter instance."""
    global _sms_rate_limiter
    if _sms_rate_limiter is None:
        redis_client = _get_redis_client()
        _sms_rate_limiter = RateLimiter(
            requests_per_minute=10,
            requests_per_hour=100,
            per_destination_per_hour=5,
            redis_client=redis_client,
            fail_closed=False,  # Fail open by default for backwards compatibility
        )
    return _sms_rate_limiter


def rate_limit_sms(user: User, destination: str) -> None:
    """
    Apply SMS rate limiting for a user and destination.

    Args:
        user: Current authenticated user
        destination: Phone number being messaged

    Raises:
        HTTPException 429 if rate limit exceeded
    """
    rate_limiter = get_sms_rate_limiter()
    rate_limiter.check_sms_limits(user.id, destination)
