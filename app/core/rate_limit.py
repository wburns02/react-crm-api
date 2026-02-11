"""
Public API Rate Limiting Module

Provides sliding window rate limiting for public API endpoints.
Supports in-memory storage with optional Redis backend for distributed deployments.
"""

import time
import hashlib
import logging
from collections import defaultdict
from typing import Dict, Optional, Tuple, Protocol
from dataclasses import dataclass, field
from fastapi import HTTPException, status, Request
from datetime import datetime
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class RateLimiterBackend(ABC):
    """Abstract base class for rate limiter backends."""

    @abstractmethod
    def check_and_increment(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> Tuple[bool, int, int]:
        """
        Check rate limit and increment counter atomically.

        Returns:
            Tuple of (allowed, remaining, reset_time)
        """
        pass


class RedisRateLimiterBackend(RateLimiterBackend):
    """
    Redis-backed rate limiter using sorted sets for sliding window.

    Provides distributed rate limiting for horizontal scaling.
    Uses Redis sorted sets with timestamps as scores for sliding window.
    """

    def __init__(self, redis_client, fail_closed: bool = False):
        """
        Initialize Redis rate limiter.

        Args:
            redis_client: Async Redis client instance
            fail_closed: If True, raise exception when Redis unavailable
        """
        self.redis = redis_client
        self.fail_closed = fail_closed

    def check_and_increment(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> Tuple[bool, int, int]:
        """
        Check rate limit using Redis sliding window.

        Uses MULTI/EXEC for atomic operations:
        1. Remove old entries outside window
        2. Add current request with timestamp
        3. Count entries in window
        4. Set TTL on key

        Returns:
            Tuple of (allowed, remaining, reset_time)
        """
        import redis as sync_redis

        now = time.time()
        window_start = now - window_seconds

        # Use pipeline for atomic operations
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)  # Remove old entries
        pipe.zadd(key, {f"{now}:{id(now)}": now})  # Add current request
        pipe.zcard(key)  # Count requests in window
        pipe.expire(key, window_seconds)  # Set TTL for cleanup

        try:
            results = pipe.execute()
            count = results[2]  # zcard result

            allowed = count <= limit
            remaining = max(0, limit - count)
            reset_time = int(now + window_seconds)

            return allowed, remaining, reset_time
        except Exception as e:
            logger.error(f"Redis rate limit error: {e}")
            if self.fail_closed:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": "rate_limit_unavailable",
                        "message": "Rate limiting service temporarily unavailable",
                    },
                )
            # Fail open - allow request if Redis is unavailable
            return True, limit, int(now + window_seconds)

    async def check_and_increment_async(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> Tuple[bool, int, int]:
        """
        Async version of check_and_increment for async Redis clients.

        Uses MULTI/EXEC for atomic operations.
        """
        now = time.time()
        window_start = now - window_seconds

        try:
            # Use pipeline for atomic operations
            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {f"{now}:{id(now)}": now})
            pipe.zcard(key)
            pipe.expire(key, window_seconds)

            results = await pipe.execute()
            count = results[2]

            allowed = count <= limit
            remaining = max(0, limit - count)
            reset_time = int(now + window_seconds)

            return allowed, remaining, reset_time
        except Exception as e:
            logger.error(f"Redis rate limit error: {e}")
            if self.fail_closed:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": "rate_limit_unavailable",
                        "message": "Rate limiting service temporarily unavailable",
                    },
                )
            return True, limit, int(now + window_seconds)


@dataclass
class SlidingWindow:
    """Sliding window counter for rate limiting."""

    current_count: int = 0
    previous_count: int = 0
    current_window_start: float = field(default_factory=time.time)
    window_size_seconds: int = 60


class PublicAPIRateLimiter:
    """
    Sliding window rate limiter for public API.

    Uses a sliding window algorithm that provides smoother rate limiting
    compared to fixed window counters.

    For production deployments, consider implementing Redis backend
    for distributed rate limiting across multiple instances.
    """

    def __init__(
        self,
        default_requests_per_minute: int = 100,
        default_requests_per_hour: int = 1000,
        redis_client=None,  # Optional Redis client for distributed limiting
        fail_closed: bool = False,  # If True, reject requests when rate limiting unavailable
    ):
        self.default_requests_per_minute = default_requests_per_minute
        self.default_requests_per_hour = default_requests_per_hour
        self.redis_client = redis_client
        self.fail_closed = fail_closed

        # In-memory storage: client_id -> (minute_window, hour_window)
        self._minute_windows: Dict[str, SlidingWindow] = defaultdict(lambda: SlidingWindow(window_size_seconds=60))
        self._hour_windows: Dict[str, SlidingWindow] = defaultdict(lambda: SlidingWindow(window_size_seconds=3600))

    def _get_sliding_window_count(self, window: SlidingWindow) -> float:
        """
        Calculate the sliding window count.

        Uses weighted average between current and previous window
        to provide smooth rate limiting.
        """
        now = time.time()
        window_size = window.window_size_seconds

        # Check if we need to rotate windows
        elapsed = now - window.current_window_start
        if elapsed >= window_size:
            # Move to new window
            windows_passed = int(elapsed / window_size)
            if windows_passed == 1:
                window.previous_count = window.current_count
            else:
                window.previous_count = 0
            window.current_count = 0
            window.current_window_start = now - (elapsed % window_size)
            elapsed = elapsed % window_size

        # Calculate weighted count using sliding window
        weight = elapsed / window_size
        return window.previous_count * (1 - weight) + window.current_count

    def _increment_window(self, window: SlidingWindow) -> None:
        """Increment the current window counter."""
        now = time.time()
        elapsed = now - window.current_window_start

        # Rotate window if needed
        if elapsed >= window.window_size_seconds:
            windows_passed = int(elapsed / window.window_size_seconds)
            if windows_passed == 1:
                window.previous_count = window.current_count
            else:
                window.previous_count = 0
            window.current_count = 0
            window.current_window_start = now - (elapsed % window.window_size_seconds)

        window.current_count += 1

    def check_rate_limit(
        self,
        client_id: str,
        rate_limit_per_minute: Optional[int] = None,
        rate_limit_per_hour: Optional[int] = None,
    ) -> Tuple[int, int]:
        """
        Check and apply rate limits for a client.

        Args:
            client_id: The API client ID
            rate_limit_per_minute: Custom per-minute limit (uses default if None)
            rate_limit_per_hour: Custom per-hour limit (uses default if None)

        Returns:
            Tuple of (remaining_minute, remaining_hour)

        Raises:
            HTTPException 429 if rate limit exceeded
        """
        minute_limit = rate_limit_per_minute or self.default_requests_per_minute
        hour_limit = rate_limit_per_hour or self.default_requests_per_hour

        # Use Redis backend if available
        if self.redis_client is not None:
            return self._check_rate_limit_redis(client_id, minute_limit, hour_limit)

        # Fall back to in-memory rate limiting
        return self._check_rate_limit_memory(client_id, minute_limit, hour_limit)

    def _check_rate_limit_redis(
        self,
        client_id: str,
        minute_limit: int,
        hour_limit: int,
    ) -> Tuple[int, int]:
        """Check rate limit using Redis backend."""
        redis_backend = RedisRateLimiterBackend(self.redis_client, fail_closed=self.fail_closed)

        # Check minute limit
        minute_key = f"ratelimit:{client_id}:minute"
        minute_allowed, minute_remaining, minute_reset = redis_backend.check_and_increment(
            minute_key, minute_limit, 60
        )

        if not minute_allowed:
            retry_after = minute_reset - int(time.time())
            logger.warning(f"Rate limit exceeded for client {client_id}: minute limit {minute_limit}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded: {minute_limit} requests per minute",
                    "retry_after": max(1, retry_after),
                },
                headers={
                    "Retry-After": str(max(1, retry_after)),
                    "X-RateLimit-Limit": str(minute_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(minute_reset),
                },
            )

        # Check hour limit
        hour_key = f"ratelimit:{client_id}:hour"
        hour_allowed, hour_remaining, hour_reset = redis_backend.check_and_increment(
            hour_key, hour_limit, 3600
        )

        if not hour_allowed:
            retry_after = hour_reset - int(time.time())
            logger.warning(f"Rate limit exceeded for client {client_id}: hour limit {hour_limit}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded: {hour_limit} requests per hour",
                    "retry_after": max(1, retry_after),
                },
                headers={
                    "Retry-After": str(max(1, retry_after)),
                    "X-RateLimit-Limit": str(hour_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(hour_reset),
                },
            )

        return minute_remaining, hour_remaining

    def _check_rate_limit_memory(
        self,
        client_id: str,
        minute_limit: int,
        hour_limit: int,
    ) -> Tuple[int, int]:
        """Check rate limit using in-memory backend."""
        minute_window = self._minute_windows[client_id]
        hour_window = self._hour_windows[client_id]

        # Get current counts using sliding window
        minute_count = self._get_sliding_window_count(minute_window)
        hour_count = self._get_sliding_window_count(hour_window)

        # Check minute limit
        if minute_count >= minute_limit:
            retry_after = 60 - (time.time() - minute_window.current_window_start)
            logger.warning(f"Rate limit exceeded for client {client_id}: {minute_count:.0f}/{minute_limit} per minute")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded: {minute_limit} requests per minute",
                    "retry_after": int(retry_after),
                },
                headers={
                    "Retry-After": str(int(retry_after)),
                    "X-RateLimit-Limit": str(minute_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + retry_after)),
                },
            )

        # Check hour limit
        if hour_count >= hour_limit:
            retry_after = 3600 - (time.time() - hour_window.current_window_start)
            logger.warning(f"Rate limit exceeded for client {client_id}: {hour_count:.0f}/{hour_limit} per hour")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded: {hour_limit} requests per hour",
                    "retry_after": int(retry_after),
                },
                headers={
                    "Retry-After": str(int(retry_after)),
                    "X-RateLimit-Limit": str(hour_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + retry_after)),
                },
            )

        # Increment counters
        self._increment_window(minute_window)
        self._increment_window(hour_window)

        # Calculate remaining
        remaining_minute = max(0, int(minute_limit - minute_count - 1))
        remaining_hour = max(0, int(hour_limit - hour_count - 1))

        return remaining_minute, remaining_hour

    def get_rate_limit_headers(
        self,
        client_id: str,
        rate_limit_per_minute: Optional[int] = None,
    ) -> Dict[str, str]:
        """
        Get rate limit headers for response.

        Args:
            client_id: The API client ID
            rate_limit_per_minute: Custom per-minute limit

        Returns:
            Dict of rate limit headers
        """
        minute_limit = rate_limit_per_minute or self.default_requests_per_minute
        minute_window = self._minute_windows.get(client_id)

        if not minute_window:
            return {
                "X-RateLimit-Limit": str(minute_limit),
                "X-RateLimit-Remaining": str(minute_limit),
            }

        current_count = self._get_sliding_window_count(minute_window)
        remaining = max(0, int(minute_limit - current_count))
        reset_time = int(minute_window.current_window_start + 60)

        return {
            "X-RateLimit-Limit": str(minute_limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_time),
        }

    def reset_client(self, client_id: str) -> None:
        """Reset rate limits for a client (admin function)."""
        self._minute_windows.pop(client_id, None)
        self._hour_windows.pop(client_id, None)
        logger.info(f"Rate limits reset for client {client_id}")


# Global rate limiter instance
_public_api_rate_limiter: Optional[PublicAPIRateLimiter] = None
_redis_client = None


def _get_redis_client():
    """Get or create Redis client for rate limiting."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    from app.config import settings

    if not settings.RATE_LIMIT_REDIS_ENABLED or not settings.REDIS_URL:
        return None

    try:
        import redis

        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        # Test connection
        _redis_client.ping()
        logger.info("Redis rate limiting enabled")
        return _redis_client
    except ImportError:
        logger.warning("Redis package not installed, falling back to in-memory rate limiting")
        return None
    except Exception as e:
        logger.warning(f"Failed to connect to Redis for rate limiting: {e}. Falling back to in-memory.")
        return None


def get_public_api_rate_limiter() -> PublicAPIRateLimiter:
    """Get or create the global public API rate limiter instance.

    Uses Redis backend if RATE_LIMIT_REDIS_ENABLED=true and REDIS_URL is set.
    Falls back to in-memory rate limiting otherwise.
    """
    global _public_api_rate_limiter
    if _public_api_rate_limiter is None:
        redis_client = _get_redis_client()
        _public_api_rate_limiter = PublicAPIRateLimiter(redis_client=redis_client)
    return _public_api_rate_limiter


def reset_rate_limits() -> dict:
    """Reset all in-memory rate limit state. Used by admin endpoint."""
    global _public_api_rate_limiter
    if _public_api_rate_limiter is not None:
        _public_api_rate_limiter._minute_windows.clear()
        _public_api_rate_limiter._hour_windows.clear()
        return {"status": "reset", "message": "All rate limit windows cleared"}
    return {"status": "no_limiter", "message": "No rate limiter instance to reset"}


def rate_limit_by_ip(request: Request, requests_per_minute: int = 60) -> None:
    """
    Rate limit by IP address for unauthenticated endpoints.

    Used for OAuth token endpoint to prevent brute force attacks.
    """
    # Get client IP (handle proxy headers)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    # Hash IP for privacy
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]

    rate_limiter = get_public_api_rate_limiter()
    rate_limiter.check_rate_limit(
        client_id=f"ip:{ip_hash}",
        rate_limit_per_minute=requests_per_minute,
        rate_limit_per_hour=requests_per_minute * 10,
    )
