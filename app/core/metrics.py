"""
Prometheus metrics collection for CRM API.

Provides metrics for monitoring:
- HTTP request counts and latency
- Database connection pool status
- Business metrics (AI requests, etc.)

Usage:
    from app.core.metrics import (
        track_request_start, track_request_end,
        track_db_pool, track_ai_request
    )
"""

import time
from typing import Optional
from dataclasses import dataclass, field
from collections import defaultdict
import threading


@dataclass
class MetricBucket:
    """A single histogram bucket."""
    le: float  # Less than or equal
    count: int = 0


@dataclass
class Histogram:
    """Prometheus-style histogram."""
    name: str
    help_text: str
    buckets: list = field(default_factory=list)
    sum_value: float = 0.0
    count: int = 0
    labels: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.buckets:
            # Default buckets for HTTP request latency (in seconds)
            bucket_bounds = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
            self.buckets = [MetricBucket(le=b) for b in bucket_bounds]
            self.buckets.append(MetricBucket(le=float('inf')))  # +Inf bucket

    def observe(self, value: float):
        """Record an observation."""
        self.sum_value += value
        self.count += 1
        for bucket in self.buckets:
            if value <= bucket.le:
                bucket.count += 1


@dataclass
class Counter:
    """Prometheus-style counter."""
    name: str
    help_text: str
    value: float = 0.0
    labels: dict = field(default_factory=dict)

    def inc(self, amount: float = 1.0):
        """Increment the counter."""
        self.value += amount


@dataclass
class Gauge:
    """Prometheus-style gauge."""
    name: str
    help_text: str
    value: float = 0.0
    labels: dict = field(default_factory=dict)

    def set(self, value: float):
        """Set the gauge value."""
        self.value = value

    def inc(self, amount: float = 1.0):
        """Increment the gauge."""
        self.value += amount

    def dec(self, amount: float = 1.0):
        """Decrement the gauge."""
        self.value -= amount


class MetricsRegistry:
    """
    Central registry for all metrics.

    Thread-safe singleton pattern for collecting metrics across the application.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize all metrics."""
        self._metrics_lock = threading.Lock()

        # HTTP metrics
        self.http_requests_total = defaultdict(
            lambda: Counter(
                name="http_requests_total",
                help_text="Total number of HTTP requests"
            )
        )
        self.http_request_duration = defaultdict(
            lambda: Histogram(
                name="http_request_duration_seconds",
                help_text="HTTP request duration in seconds"
            )
        )
        self.http_requests_in_flight = Gauge(
            name="http_requests_in_flight",
            help_text="Number of HTTP requests currently being processed"
        )

        # Database metrics
        self.db_pool_size = Gauge(
            name="db_pool_connections_total",
            help_text="Total database pool connections"
        )
        self.db_pool_available = Gauge(
            name="db_pool_connections_available",
            help_text="Available database pool connections"
        )

        # Business metrics
        self.ai_requests_total = defaultdict(
            lambda: Counter(
                name="crm_ai_requests_total",
                help_text="Total AI/ML API requests"
            )
        )
        self.cache_hits = Counter(
            name="crm_cache_hits_total",
            help_text="Total cache hits"
        )
        self.cache_misses = Counter(
            name="crm_cache_misses_total",
            help_text="Total cache misses"
        )

        # Error metrics
        self.errors_total = defaultdict(
            lambda: Counter(
                name="crm_errors_total",
                help_text="Total errors by type"
            )
        )

    def format_prometheus(self) -> str:
        """Format all metrics in Prometheus text format."""
        lines = []

        with self._metrics_lock:
            # HTTP requests total
            lines.append("# HELP http_requests_total Total number of HTTP requests")
            lines.append("# TYPE http_requests_total counter")
            for labels, counter in self.http_requests_total.items():
                method, status, path = labels
                lines.append(
                    f'http_requests_total{{method="{method}",status="{status}",path="{path}"}} {counter.value}'
                )

            # HTTP request duration
            lines.append("")
            lines.append("# HELP http_request_duration_seconds HTTP request duration in seconds")
            lines.append("# TYPE http_request_duration_seconds histogram")
            for labels, histogram in self.http_request_duration.items():
                method, path = labels
                for bucket in histogram.buckets:
                    le_str = "+Inf" if bucket.le == float('inf') else str(bucket.le)
                    lines.append(
                        f'http_request_duration_seconds_bucket{{method="{method}",path="{path}",le="{le_str}"}} {bucket.count}'
                    )
                lines.append(
                    f'http_request_duration_seconds_sum{{method="{method}",path="{path}"}} {histogram.sum_value}'
                )
                lines.append(
                    f'http_request_duration_seconds_count{{method="{method}",path="{path}"}} {histogram.count}'
                )

            # HTTP in flight
            lines.append("")
            lines.append("# HELP http_requests_in_flight Number of HTTP requests currently being processed")
            lines.append("# TYPE http_requests_in_flight gauge")
            lines.append(f"http_requests_in_flight {self.http_requests_in_flight.value}")

            # Database pool
            lines.append("")
            lines.append("# HELP db_pool_connections_total Total database pool connections")
            lines.append("# TYPE db_pool_connections_total gauge")
            lines.append(f"db_pool_connections_total {self.db_pool_size.value}")
            lines.append("")
            lines.append("# HELP db_pool_connections_available Available database pool connections")
            lines.append("# TYPE db_pool_connections_available gauge")
            lines.append(f"db_pool_connections_available {self.db_pool_available.value}")

            # AI requests
            lines.append("")
            lines.append("# HELP crm_ai_requests_total Total AI/ML API requests")
            lines.append("# TYPE crm_ai_requests_total counter")
            for labels, counter in self.ai_requests_total.items():
                ai_type, status = labels
                lines.append(
                    f'crm_ai_requests_total{{type="{ai_type}",status="{status}"}} {counter.value}'
                )

            # Cache metrics
            lines.append("")
            lines.append("# HELP crm_cache_hits_total Total cache hits")
            lines.append("# TYPE crm_cache_hits_total counter")
            lines.append(f"crm_cache_hits_total {self.cache_hits.value}")
            lines.append("")
            lines.append("# HELP crm_cache_misses_total Total cache misses")
            lines.append("# TYPE crm_cache_misses_total counter")
            lines.append(f"crm_cache_misses_total {self.cache_misses.value}")

            # Error metrics
            lines.append("")
            lines.append("# HELP crm_errors_total Total errors by type")
            lines.append("# TYPE crm_errors_total counter")
            for labels, counter in self.errors_total.items():
                error_type, = labels
                lines.append(f'crm_errors_total{{type="{error_type}"}} {counter.value}')

        return "\n".join(lines)


# Global registry instance
_registry = MetricsRegistry()


def get_registry() -> MetricsRegistry:
    """Get the global metrics registry."""
    return _registry


def track_request_start():
    """Track start of HTTP request."""
    _registry.http_requests_in_flight.inc()
    return time.time()


def track_request_end(
    start_time: float,
    method: str,
    path: str,
    status_code: int
):
    """Track end of HTTP request."""
    duration = time.time() - start_time

    # Normalize path to avoid cardinality explosion
    # Remove IDs and keep only the route pattern
    normalized_path = _normalize_path(path)

    with _registry._metrics_lock:
        _registry.http_requests_in_flight.dec()
        _registry.http_requests_total[(method, str(status_code), normalized_path)].inc()
        _registry.http_request_duration[(method, normalized_path)].observe(duration)


def track_ai_request(ai_type: str, success: bool = True):
    """Track AI/ML API request."""
    status = "success" if success else "error"
    with _registry._metrics_lock:
        _registry.ai_requests_total[(ai_type, status)].inc()


def track_cache_hit():
    """Track cache hit."""
    with _registry._metrics_lock:
        _registry.cache_hits.inc()


def track_cache_miss():
    """Track cache miss."""
    with _registry._metrics_lock:
        _registry.cache_misses.inc()


def track_error(error_type: str):
    """Track error by type."""
    with _registry._metrics_lock:
        _registry.errors_total[(error_type,)].inc()


def track_db_pool(total: int, available: int):
    """Update database pool metrics."""
    with _registry._metrics_lock:
        _registry.db_pool_size.set(total)
        _registry.db_pool_available.set(available)


def _normalize_path(path: str) -> str:
    """
    Normalize path to prevent high cardinality.

    Replaces numeric IDs with :id placeholder.
    Examples:
        /api/v2/customers/123 -> /api/v2/customers/:id
        /api/v2/work-orders/456/photos -> /api/v2/work-orders/:id/photos
    """
    parts = path.split("/")
    normalized = []
    for part in parts:
        # Check if part looks like an ID (numeric or UUID-like)
        if part.isdigit() or (len(part) >= 8 and "-" in part):
            normalized.append(":id")
        else:
            normalized.append(part)
    return "/".join(normalized)
