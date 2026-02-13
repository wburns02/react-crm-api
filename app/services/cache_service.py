"""
Redis cache service with circuit breaker pattern.

Provides distributed caching for API responses with:
- Automatic fallback when Redis is unavailable
- TTL presets for different data types
- Key namespacing by domain
- Circuit breaker to prevent cascade failures

Usage:
    from app.services.cache_service import cache_service

    # Get/set with automatic serialization
    await cache_service.set("customers:123", customer_data, ttl=TTL_MEDIUM)
    customer = await cache_service.get("customers:123")

    # Decorator for endpoint caching
    @cached(ttl=TTL_SHORT, key_prefix="customers")
    async def get_customers(page: int):
        ...
"""

import json
import logging
import time
from typing import Any, Optional, Callable, TypeVar
from functools import wraps
from enum import IntEnum

logger = logging.getLogger(__name__)

# Type variable for generic return types
T = TypeVar("T")


class TTL(IntEnum):
    """Cache TTL presets in seconds."""

    SHORT = 60  # 1 minute - frequently changing data
    MEDIUM = 300  # 5 minutes - standard API responses
    LONG = 3600  # 1 hour - rarely changing data
    DAY = 86400  # 24 hours - static reference data


class CircuitState(IntEnum):
    """Circuit breaker states."""

    CLOSED = 0  # Normal operation
    OPEN = 1  # Failing, reject requests
    HALF_OPEN = 2  # Testing recovery


class CacheService:
    """
    Redis cache service with circuit breaker pattern.

    Handles cache operations with automatic fallback when Redis is unavailable.
    Uses circuit breaker to prevent cascade failures.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
    ):
        """
        Initialize cache service.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379)
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before testing recovery
        """
        self._redis_url = redis_url
        self._client = None
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout

        # Circuit breaker state
        self._circuit_state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0

        # Track metrics
        self._hits = 0
        self._misses = 0

    async def _get_client(self):
        """Get or create Redis client."""
        if not self._redis_url:
            return None

        if self._client is None:
            try:
                import redis.asyncio as redis

                self._client = redis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
            except ImportError:
                logger.warning("redis package not installed, caching disabled")
                return None
            except Exception as e:
                logger.warning(f"Failed to create Redis client: {e}")
                return None

        return self._client

    def _check_circuit(self) -> bool:
        """Check if circuit allows requests."""
        if self._circuit_state == CircuitState.CLOSED:
            return True

        if self._circuit_state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if time.time() - self._last_failure_time >= self._recovery_timeout:
                self._circuit_state = CircuitState.HALF_OPEN
                logger.info("Cache circuit breaker entering half-open state")
                return True
            return False

        # HALF_OPEN - allow single request to test
        return True

    def _record_success(self):
        """Record successful operation."""
        if self._circuit_state == CircuitState.HALF_OPEN:
            self._circuit_state = CircuitState.CLOSED
            self._failure_count = 0
            logger.info("Cache circuit breaker closed (recovered)")

    def _record_failure(self):
        """Record failed operation."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._circuit_state == CircuitState.HALF_OPEN:
            self._circuit_state = CircuitState.OPEN
            logger.warning("Cache circuit breaker opened (failed recovery)")
        elif self._failure_count >= self._failure_threshold:
            self._circuit_state = CircuitState.OPEN
            logger.warning(f"Cache circuit breaker opened after {self._failure_count} failures")

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/error
        """
        if not self._check_circuit():
            return None

        client = await self._get_client()
        if not client:
            return None

        try:
            value = await client.get(key)
            # A successful Redis operation (hit or miss) resets the circuit breaker
            self._record_success()
            if value is not None:
                self._hits += 1
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            self._misses += 1
            return None
        except Exception as e:
            logger.debug(f"Cache get error for {key}: {e}")
            self._record_failure()
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = TTL.MEDIUM,
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self._check_circuit():
            return False

        client = await self._get_client()
        if not client:
            return False

        try:
            serialized = json.dumps(value, default=str)
            await client.setex(key, ttl, serialized)
            self._record_success()
            return True
        except Exception as e:
            logger.debug(f"Cache set error for {key}: {e}")
            self._record_failure()
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if successful, False otherwise
        """
        if not self._check_circuit():
            return False

        client = await self._get_client()
        if not client:
            return False

        try:
            await client.delete(key)
            self._record_success()
            return True
        except Exception as e:
            logger.debug(f"Cache delete error for {key}: {e}")
            self._record_failure()
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern.

        Args:
            pattern: Key pattern with wildcards (e.g., "customers:*")

        Returns:
            Number of keys deleted
        """
        if not self._check_circuit():
            return 0

        client = await self._get_client()
        if not client:
            return 0

        try:
            keys = await client.keys(pattern)
            if keys:
                await client.delete(*keys)
            self._record_success()
            return len(keys) if keys else 0
        except Exception as e:
            logger.debug(f"Cache delete_pattern error for {pattern}: {e}")
            self._record_failure()
            return 0

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 2),
            "circuit_state": self._circuit_state.name,
            "failure_count": self._failure_count,
        }

    @property
    def is_available(self) -> bool:
        """Check if cache is available."""
        return self._redis_url is not None and self._check_circuit()


# Global cache service instance
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get or create the global cache service."""
    global _cache_service
    if _cache_service is None:
        from app.config import settings

        redis_url = getattr(settings, "REDIS_URL", None)
        _cache_service = CacheService(redis_url=redis_url)
    return _cache_service


# Convenience reference
cache_service = get_cache_service()


def cached(
    ttl: int = TTL.MEDIUM,
    key_prefix: str = "",
    key_builder: Optional[Callable[..., str]] = None,
):
    """
    Decorator for caching function results.

    Args:
        ttl: Cache TTL in seconds
        key_prefix: Prefix for cache keys
        key_builder: Custom function to build cache key from args

    Example:
        @cached(ttl=TTL.SHORT, key_prefix="customers")
        async def get_customer(customer_id: int):
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            service = get_cache_service()

            # Build cache key
            if key_builder:
                key = key_builder(*args, **kwargs)
            else:
                # Default key from function name and arguments
                arg_str = ":".join(str(a) for a in args)
                kwarg_str = ":".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
                parts = [key_prefix, func.__name__, arg_str, kwarg_str]
                key = ":".join(p for p in parts if p)

            # Try to get from cache
            cached_value = await service.get(key)
            if cached_value is not None:
                return cached_value

            # Call function and cache result
            result = await func(*args, **kwargs)
            await service.set(key, result, ttl=ttl)
            return result

        return wrapper

    return decorator
