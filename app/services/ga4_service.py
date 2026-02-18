"""
Google Analytics 4 Data API Service

Fetches real traffic data from GA4 using the Data API v1beta (REST).
Uses OAuth2 refresh tokens for authentication, with in-memory caching.

Required env vars:
  GA4_PROPERTY_ID - The numeric GA4 property ID (e.g., 437747839)
  GA4_OAUTH_CLIENT_ID - OAuth2 client ID
  GA4_OAUTH_CLIENT_SECRET - OAuth2 client secret
  GA4_OAUTH_REFRESH_TOKEN - OAuth2 refresh token
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# GA4 Data API
GA4_DATA_API_URL = "https://analyticsdata.googleapis.com/v1beta"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Cache TTLs (seconds)
CACHE_TTL_TRAFFIC = 900       # 15 minutes
CACHE_TTL_SOURCES = 900       # 15 minutes
CACHE_TTL_PAGES = 900         # 15 minutes
CACHE_TTL_REALTIME = 60       # 1 minute
CACHE_TTL_DEVICES = 1800      # 30 minutes
CACHE_TTL_GEO = 1800          # 30 minutes


class GA4Service:
    """Google Analytics 4 Data API client using REST + httpx."""

    def __init__(self):
        self.property_id = getattr(settings, "GA4_PROPERTY_ID", None)
        self.client_id = getattr(settings, "GA4_OAUTH_CLIENT_ID", None)
        self.client_secret = getattr(settings, "GA4_OAUTH_CLIENT_SECRET", None)
        self.refresh_token = getattr(settings, "GA4_OAUTH_REFRESH_TOKEN", None)

        # OAuth2 access token
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

        # In-memory cache
        self._cache: dict[str, tuple[float, object]] = {}

    def is_configured(self) -> bool:
        """Check if GA4 credentials are present."""
        return bool(
            self.property_id
            and self.client_id
            and self.client_secret
            and self.refresh_token
        )

    async def _refresh_access_token(self) -> str:
        """Refresh OAuth2 access token."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_OAUTH_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expires_at = time.time() + data.get("expires_in", 3600)
            return self._access_token

    def _get_cache(self, key: str, ttl: int) -> Optional[object]:
        """Get cached value if still valid."""
        if key in self._cache:
            cached_at, value = self._cache[key]
            if time.time() - cached_at < ttl:
                return value
        return None

    def _set_cache(self, key: str, value: object):
        """Set cache value."""
        self._cache[key] = (time.time(), value)

    async def _run_report(self, body: dict) -> dict:
        """Execute a GA4 Data API runReport request."""
        token = await self._refresh_access_token()
        url = f"{GA4_DATA_API_URL}/properties/{self.property_id}:runReport"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def _run_realtime_report(self, body: dict) -> dict:
        """Execute a GA4 Data API runRealtimeReport request."""
        token = await self._refresh_access_token()
        url = f"{GA4_DATA_API_URL}/properties/{self.property_id}:runRealtimeReport"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    # ──────────────────────────────────────
    # Public API methods
    # ──────────────────────────────────────

    async def get_traffic_summary(self, days: int = 7) -> dict:
        """
        Get traffic summary: sessions, users, pageviews, bounce rate, avg session duration.
        Also returns day-by-day breakdown.
        """
        cache_key = f"traffic_{days}"
        cached = self._get_cache(cache_key, CACHE_TTL_TRAFFIC)
        if cached:
            return cached

        end_date = "today"
        start_date = f"{days}daysAgo"

        # Main metrics
        body = {
            "dateRanges": [
                {"startDate": start_date, "endDate": end_date},
            ],
            "metrics": [
                {"name": "sessions"},
                {"name": "totalUsers"},
                {"name": "screenPageViews"},
                {"name": "bounceRate"},
                {"name": "averageSessionDuration"},
                {"name": "newUsers"},
                {"name": "engagedSessions"},
            ],
            "dimensions": [{"name": "date"}],
            "orderBys": [{"dimension": {"dimensionName": "date"}}],
        }

        try:
            data = await self._run_report(body)
            rows = data.get("rows", [])

            # Parse totals from the totals row
            totals = data.get("totals", [{}])
            total_metrics = totals[0].get("metricValues", []) if totals else []

            # Build daily breakdown
            daily = []
            total_sessions = 0
            total_users = 0
            total_pageviews = 0
            total_new_users = 0
            total_engaged = 0
            sum_bounce = 0.0
            sum_duration = 0.0

            for row in rows:
                date_val = row["dimensionValues"][0]["value"]
                metrics = row["metricValues"]
                sessions = int(metrics[0]["value"])
                users = int(metrics[1]["value"])
                pageviews = int(metrics[2]["value"])
                bounce = float(metrics[3]["value"])
                duration = float(metrics[4]["value"])
                new_users = int(metrics[5]["value"])
                engaged = int(metrics[6]["value"])

                total_sessions += sessions
                total_users += users
                total_pageviews += pageviews
                total_new_users += new_users
                total_engaged += engaged
                sum_bounce += bounce * sessions  # weighted
                sum_duration += duration * sessions  # weighted

                daily.append({
                    "date": f"{date_val[:4]}-{date_val[4:6]}-{date_val[6:8]}",
                    "sessions": sessions,
                    "users": users,
                    "pageviews": pageviews,
                    "bounce_rate": round(bounce * 100, 1),
                    "avg_duration": round(duration, 1),
                    "new_users": new_users,
                })

            avg_bounce = round((sum_bounce / max(1, total_sessions)) * 100, 1)
            avg_duration = round(sum_duration / max(1, total_sessions), 1)

            result = {
                "period_days": days,
                "totals": {
                    "sessions": total_sessions,
                    "users": total_users,
                    "pageviews": total_pageviews,
                    "new_users": total_new_users,
                    "engaged_sessions": total_engaged,
                    "bounce_rate": avg_bounce,
                    "avg_session_duration": avg_duration,
                },
                "daily": daily,
            }

            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error("GA4 get_traffic_summary failed: %s", str(e))
            raise

    async def get_traffic_sources(self, days: int = 7) -> dict:
        """Get traffic by source/medium."""
        cache_key = f"sources_{days}"
        cached = self._get_cache(cache_key, CACHE_TTL_SOURCES)
        if cached:
            return cached

        body = {
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "today"}],
            "metrics": [
                {"name": "sessions"},
                {"name": "totalUsers"},
                {"name": "engagedSessions"},
                {"name": "conversions"},
            ],
            "dimensions": [
                {"name": "sessionDefaultChannelGroup"},
            ],
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
            "limit": 20,
        }

        try:
            data = await self._run_report(body)
            rows = data.get("rows", [])

            sources = []
            for row in rows:
                channel = row["dimensionValues"][0]["value"]
                metrics = row["metricValues"]
                sessions = int(metrics[0]["value"])
                users = int(metrics[1]["value"])
                engaged = int(metrics[2]["value"])
                conversions = int(metrics[3]["value"])

                sources.append({
                    "channel": channel,
                    "sessions": sessions,
                    "users": users,
                    "engaged_sessions": engaged,
                    "conversions": conversions,
                    "engagement_rate": round((engaged / max(1, sessions)) * 100, 1),
                })

            result = {"period_days": days, "sources": sources}
            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error("GA4 get_traffic_sources failed: %s", str(e))
            raise

    async def get_top_pages(self, days: int = 7, limit: int = 20) -> dict:
        """Get top pages by pageviews."""
        cache_key = f"pages_{days}_{limit}"
        cached = self._get_cache(cache_key, CACHE_TTL_PAGES)
        if cached:
            return cached

        body = {
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "today"}],
            "metrics": [
                {"name": "screenPageViews"},
                {"name": "totalUsers"},
                {"name": "averageSessionDuration"},
                {"name": "bounceRate"},
            ],
            "dimensions": [{"name": "pagePath"}],
            "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
            "limit": limit,
        }

        try:
            data = await self._run_report(body)
            rows = data.get("rows", [])

            pages = []
            for row in rows:
                path = row["dimensionValues"][0]["value"]
                metrics = row["metricValues"]
                pages.append({
                    "path": path,
                    "pageviews": int(metrics[0]["value"]),
                    "users": int(metrics[1]["value"]),
                    "avg_duration": round(float(metrics[2]["value"]), 1),
                    "bounce_rate": round(float(metrics[3]["value"]) * 100, 1),
                })

            result = {"period_days": days, "pages": pages}
            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error("GA4 get_top_pages failed: %s", str(e))
            raise

    async def get_device_breakdown(self, days: int = 7) -> dict:
        """Get traffic by device category."""
        cache_key = f"devices_{days}"
        cached = self._get_cache(cache_key, CACHE_TTL_DEVICES)
        if cached:
            return cached

        body = {
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "today"}],
            "metrics": [
                {"name": "sessions"},
                {"name": "totalUsers"},
            ],
            "dimensions": [{"name": "deviceCategory"}],
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
        }

        try:
            data = await self._run_report(body)
            rows = data.get("rows", [])

            devices = []
            total_sessions = sum(int(r["metricValues"][0]["value"]) for r in rows)

            for row in rows:
                device = row["dimensionValues"][0]["value"]
                sessions = int(row["metricValues"][0]["value"])
                users = int(row["metricValues"][1]["value"])
                devices.append({
                    "device": device,
                    "sessions": sessions,
                    "users": users,
                    "percentage": round((sessions / max(1, total_sessions)) * 100, 1),
                })

            result = {"period_days": days, "devices": devices}
            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error("GA4 get_device_breakdown failed: %s", str(e))
            raise

    async def get_geo_breakdown(self, days: int = 7) -> dict:
        """Get traffic by region/city (focus on Texas)."""
        cache_key = f"geo_{days}"
        cached = self._get_cache(cache_key, CACHE_TTL_GEO)
        if cached:
            return cached

        body = {
            "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "today"}],
            "metrics": [
                {"name": "sessions"},
                {"name": "totalUsers"},
            ],
            "dimensions": [
                {"name": "region"},
                {"name": "city"},
            ],
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
            "limit": 30,
        }

        try:
            data = await self._run_report(body)
            rows = data.get("rows", [])

            locations = []
            for row in rows:
                region = row["dimensionValues"][0]["value"]
                city = row["dimensionValues"][1]["value"]
                sessions = int(row["metricValues"][0]["value"])
                users = int(row["metricValues"][1]["value"])
                locations.append({
                    "region": region,
                    "city": city,
                    "sessions": sessions,
                    "users": users,
                })

            result = {"period_days": days, "locations": locations}
            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error("GA4 get_geo_breakdown failed: %s", str(e))
            raise

    async def get_realtime(self) -> dict:
        """Get real-time active users."""
        cached = self._get_cache("realtime", CACHE_TTL_REALTIME)
        if cached:
            return cached

        body = {
            "metrics": [{"name": "activeUsers"}],
            "dimensions": [{"name": "deviceCategory"}],
        }

        try:
            data = await self._run_realtime_report(body)
            rows = data.get("rows", [])

            total_active = 0
            by_device = {}
            for row in rows:
                device = row["dimensionValues"][0]["value"]
                count = int(row["metricValues"][0]["value"])
                by_device[device] = count
                total_active += count

            result = {
                "active_users": total_active,
                "by_device": by_device,
                "timestamp": datetime.utcnow().isoformat(),
            }
            self._set_cache("realtime", result)
            return result
        except Exception as e:
            logger.error("GA4 get_realtime failed: %s", str(e))
            raise

    async def get_comparison(self, days: int = 7) -> dict:
        """
        Get this period vs previous period comparison.
        E.g., last 7 days vs the 7 days before that.
        """
        cache_key = f"comparison_{days}"
        cached = self._get_cache(cache_key, CACHE_TTL_TRAFFIC)
        if cached:
            return cached

        body = {
            "dateRanges": [
                {"startDate": f"{days}daysAgo", "endDate": "today"},
                {"startDate": f"{days * 2}daysAgo", "endDate": f"{days + 1}daysAgo"},
            ],
            "metrics": [
                {"name": "sessions"},
                {"name": "totalUsers"},
                {"name": "screenPageViews"},
                {"name": "bounceRate"},
                {"name": "averageSessionDuration"},
                {"name": "conversions"},
            ],
        }

        try:
            data = await self._run_report(body)
            rows = data.get("rows", [])

            current = {"sessions": 0, "users": 0, "pageviews": 0, "bounce_rate": 0, "avg_duration": 0, "conversions": 0}
            previous = {"sessions": 0, "users": 0, "pageviews": 0, "bounce_rate": 0, "avg_duration": 0, "conversions": 0}

            # GA4 returns rows with dateRange index
            for row in rows:
                metrics = row.get("metricValues", [])
                if len(metrics) >= 6:
                    bucket = {
                        "sessions": int(metrics[0]["value"]),
                        "users": int(metrics[1]["value"]),
                        "pageviews": int(metrics[2]["value"]),
                        "bounce_rate": round(float(metrics[3]["value"]) * 100, 1),
                        "avg_duration": round(float(metrics[4]["value"]), 1),
                        "conversions": int(metrics[5]["value"]),
                    }
                    # First row = current period, second = previous (when no dimensions)
                    if not current["sessions"]:
                        current = bucket
                    else:
                        previous = bucket

            # Calculate changes
            changes = {}
            for key in current:
                curr = current[key]
                prev = previous[key]
                if prev > 0:
                    pct = round(((curr - prev) / prev) * 100, 1)
                elif curr > 0:
                    pct = 100.0
                else:
                    pct = 0.0
                changes[key] = {
                    "current": curr,
                    "previous": prev,
                    "change_percent": pct,
                    "direction": "up" if pct > 0 else ("down" if pct < 0 else "flat"),
                }

            result = {
                "period_days": days,
                "current_period": current,
                "previous_period": previous,
                "changes": changes,
            }
            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            logger.error("GA4 get_comparison failed: %s", str(e))
            raise


# Singleton
_ga4_service: Optional[GA4Service] = None


def get_ga4_service() -> GA4Service:
    """Get or create the GA4 service singleton."""
    global _ga4_service
    if _ga4_service is None:
        _ga4_service = GA4Service()
    return _ga4_service
