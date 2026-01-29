"""
Public API Rate Limiting Module

Provides sliding window rate limiting for public API endpoints.
Supports in-memory storage with optional Redis backend for distributed deployments.
"""

import time
import hashlib
import logging
from collections import defaultdict
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from fastapi import HTTPException, status, Request
from datetime import datetime

logger = logging.getLogger(__name__)


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
    ):
        self.default_requests_per_minute = default_requests_per_minute
        self.default_requests_per_hour = default_requests_per_hour
        self.redis_client = redis_client

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


def get_public_api_rate_limiter() -> PublicAPIRateLimiter:
    """Get or create the global public API rate limiter instance."""
    global _public_api_rate_limiter
    if _public_api_rate_limiter is None:
        _public_api_rate_limiter = PublicAPIRateLimiter()
    return _public_api_rate_limiter


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
