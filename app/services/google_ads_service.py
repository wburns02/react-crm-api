"""
Google Ads API Service

Integrates with Google Ads REST API v20 for campaign performance data.
Uses httpx for async HTTP, OAuth2 token refresh, and in-memory caching.

Basic Access: 15,000 operations/day limit.
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Google Ads REST API
GOOGLE_ADS_API_VERSION = "v20"
GOOGLE_ADS_BASE_URL = f"https://googleads.googleapis.com/{GOOGLE_ADS_API_VERSION}"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Cache TTLs (seconds)
CACHE_TTL_METRICS = 900  # 15 minutes
CACHE_TTL_CAMPAIGNS = 900  # 15 minutes
CACHE_TTL_RECOMMENDATIONS = 3600  # 1 hour
CACHE_TTL_STATUS = 300  # 5 minutes

# Daily operation tracking
MAX_DAILY_OPERATIONS = 14000  # Leave 1000 buffer from 15k limit


class GoogleAdsService:
    """Google Ads API client using REST API + httpx."""

    def __init__(self):
        self.developer_token = getattr(settings, "GOOGLE_ADS_DEVELOPER_TOKEN", None)
        self.client_id = getattr(settings, "GOOGLE_ADS_CLIENT_ID", None)
        self.client_secret = getattr(settings, "GOOGLE_ADS_CLIENT_SECRET", None)
        self.refresh_token = getattr(settings, "GOOGLE_ADS_REFRESH_TOKEN", None)
        self.customer_id = getattr(settings, "GOOGLE_ADS_CUSTOMER_ID", None)
        self.login_customer_id = getattr(settings, "GOOGLE_ADS_LOGIN_CUSTOMER_ID", None)

        # OAuth2 access token
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

        # In-memory cache
        self._cache: dict[str, tuple[float, object]] = {}

        # Daily operation counter
        self._daily_ops: int = 0
        self._daily_ops_date: str = ""

    def is_configured(self) -> bool:
        """Check if all required credentials are present."""
        return bool(
            self.developer_token
            and self.client_id
            and self.client_secret
            and self.refresh_token
            and self.customer_id
        )

    def _get_clean_customer_id(self) -> str:
        """Return customer ID without dashes."""
        return (self.customer_id or "").replace("-", "")

    def _get_clean_login_customer_id(self) -> str:
        """Return login customer ID without dashes."""
        return (self.login_customer_id or "").replace("-", "")

    def _check_daily_limit(self) -> bool:
        """Check if we're within the daily operation limit."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if self._daily_ops_date != today:
            self._daily_ops = 0
            self._daily_ops_date = today
        return self._daily_ops < MAX_DAILY_OPERATIONS

    def _increment_ops(self):
        """Track daily API operations."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if self._daily_ops_date != today:
            self._daily_ops = 0
            self._daily_ops_date = today
        self._daily_ops += 1

    def _get_cached(self, key: str, ttl: int) -> Optional[object]:
        """Get value from cache if not expired."""
        if key in self._cache:
            cached_time, value = self._cache[key]
            if time.time() - cached_time < ttl:
                return value
        return None

    def _set_cache(self, key: str, value: object):
        """Store value in cache."""
        self._cache[key] = (time.time(), value)

    async def _refresh_access_token(self) -> Optional[str]:
        """Refresh OAuth2 access token using refresh token."""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    GOOGLE_OAUTH_TOKEN_URL,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "refresh_token": self.refresh_token,
                        "grant_type": "refresh_token",
                    },
                )

                if response.status_code != 200:
                    logger.error(
                        "Google Ads OAuth token refresh failed: %s %s",
                        response.status_code,
                        response.text[:200],
                    )
                    return None

                data = response.json()
                self._access_token = data["access_token"]
                # Refresh 60 seconds before actual expiry
                self._token_expires_at = time.time() + data.get("expires_in", 3600) - 60
                logger.info("Google Ads OAuth token refreshed successfully")
                return self._access_token

        except Exception as e:
            logger.error("Google Ads OAuth token refresh error: %s", str(e))
            return None

    def _get_headers(self, access_token: str) -> dict:
        """Build request headers for Google Ads API."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": self.developer_token,
            "Content-Type": "application/json",
        }
        if self.login_customer_id:
            headers["login-customer-id"] = self._get_clean_login_customer_id()
        return headers

    async def _execute_query(self, query: str) -> Optional[list]:
        """Execute a GAQL query against the Google Ads REST API."""
        if not self.is_configured():
            return None

        if not self._check_daily_limit():
            logger.warning("Google Ads daily operation limit reached (%d)", self._daily_ops)
            return None

        access_token = await self._refresh_access_token()
        if not access_token:
            return None

        customer_id = self._get_clean_customer_id()
        url = f"{GOOGLE_ADS_BASE_URL}/customers/{customer_id}/googleAds:search"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(access_token),
                    json={"query": query, "pageSize": 1000},
                )

                self._increment_ops()

                if response.status_code == 401:
                    # Token might have expired, clear and retry once
                    self._access_token = None
                    self._token_expires_at = 0
                    access_token = await self._refresh_access_token()
                    if access_token:
                        response = await client.post(
                            url,
                            headers=self._get_headers(access_token),
                            json={"query": query, "pageSize": 1000},
                        )
                        self._increment_ops()

                if response.status_code != 200:
                    logger.error(
                        "Google Ads API query failed: %s %s",
                        response.status_code,
                        response.text[:1000],
                    )
                    return None

                data = response.json()
                return data.get("results", [])

        except httpx.TimeoutException:
            logger.error("Google Ads API query timed out")
            return None
        except Exception as e:
            logger.error("Google Ads API query error: %s", str(e))
            return None

    async def get_account_info(self) -> Optional[dict]:
        """Get Google Ads account information."""
        cache_key = "account_info"
        cached = self._get_cached(cache_key, CACHE_TTL_STATUS)
        if cached is not None:
            return cached

        query = """
            SELECT
                customer.descriptive_name,
                customer.id,
                customer.currency_code,
                customer.time_zone
            FROM customer
            LIMIT 1
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        if not results:
            return {"id": self.customer_id, "name": "Unknown", "currency": "USD"}

        row = results[0]
        customer = row.get("customer", {})
        info = {
            "id": customer.get("id", self.customer_id),
            "name": customer.get("descriptiveName", "Google Ads Account"),
            "currency": customer.get("currencyCode", "USD"),
            "timezone": customer.get("timeZone", "America/Chicago"),
        }
        self._set_cache(cache_key, info)
        return info

    def _date_range_clause(self, days: int) -> str:
        """Build a GAQL date range clause."""
        if days <= 7:
            return "DURING LAST_7_DAYS"
        elif days <= 14:
            return "DURING LAST_14_DAYS"
        elif days <= 30:
            return "DURING LAST_30_DAYS"
        else:
            # Custom date range for >30 days
            end_date = datetime.utcnow().strftime("%Y-%m-%d")
            start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
            return f"BETWEEN '{start_date}' AND '{end_date}'"

    async def get_performance_metrics(self, days: int = 30) -> Optional[dict]:
        """Get account-level performance metrics."""
        cache_key = f"metrics_{days}"
        cached = self._get_cached(cache_key, CACHE_TTL_METRICS)
        if cached is not None:
            return cached

        date_range = self._date_range_clause(days)
        query = f"""
            SELECT
                metrics.cost_micros,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions,
                metrics.ctr
            FROM customer
            WHERE segments.date {date_range}
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        # Aggregate metrics across all rows
        total_cost_micros = 0
        total_clicks = 0
        total_impressions = 0
        total_conversions = 0.0

        for row in results:
            m = row.get("metrics", {})
            total_cost_micros += int(m.get("costMicros", 0))
            total_clicks += int(m.get("clicks", 0))
            total_impressions += int(m.get("impressions", 0))
            total_conversions += float(m.get("conversions", 0))

        cost = total_cost_micros / 1_000_000  # micros to dollars
        ctr = total_clicks / max(1, total_impressions)
        cpa = cost / max(1, total_conversions) if total_conversions > 0 else 0

        metrics = {
            "cost": round(cost, 2),
            "clicks": total_clicks,
            "impressions": total_impressions,
            "conversions": round(total_conversions, 1),
            "ctr": round(ctr, 4),
            "cpa": round(cpa, 2),
        }
        self._set_cache(cache_key, metrics)
        return metrics

    async def get_campaigns(self, days: int = 30) -> Optional[list]:
        """Get campaign-level performance data."""
        cache_key = f"campaigns_{days}"
        cached = self._get_cached(cache_key, CACHE_TTL_CAMPAIGNS)
        if cached is not None:
            return cached

        date_range = self._date_range_clause(days)
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                metrics.cost_micros,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions
            FROM campaign
            WHERE segments.date {date_range}
                AND campaign.status != 'REMOVED'
            ORDER BY metrics.cost_micros DESC
            LIMIT 20
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        campaigns = []
        for row in results:
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            cost_micros = int(m.get("costMicros", 0))
            campaigns.append({
                "id": str(c.get("id", "")),
                "name": c.get("name", "Unknown Campaign"),
                "status": (c.get("status", "UNKNOWN")).lower(),
                "cost": round(cost_micros / 1_000_000, 2),
                "clicks": int(m.get("clicks", 0)),
                "impressions": int(m.get("impressions", 0)),
                "conversions": round(float(m.get("conversions", 0)), 1),
            })

        self._set_cache(cache_key, campaigns)
        return campaigns

    async def get_recommendations(self) -> Optional[list]:
        """Get optimization recommendations from Google Ads."""
        cache_key = "recommendations"
        cached = self._get_cached(cache_key, CACHE_TTL_RECOMMENDATIONS)
        if cached is not None:
            return cached

        query = """
            SELECT
                recommendation.type,
                recommendation.impact.base_metrics.impressions.value,
                recommendation.impact.base_metrics.clicks.value,
                recommendation.impact.base_metrics.cost_micros.value,
                recommendation.campaign
            FROM recommendation
            LIMIT 10
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        # Map recommendation types to human-readable descriptions
        type_descriptions = {
            "KEYWORD": ("Add Keywords", "New keyword opportunities found for your campaigns"),
            "TEXT_AD": ("Improve Ad Copy", "Update ad text to improve click-through rates"),
            "CAMPAIGN_BUDGET": ("Adjust Budget", "Campaign budget changes could improve performance"),
            "MAXIMIZE_CONVERSIONS_OPT_IN": ("Smart Bidding", "Switch to maximize conversions bidding"),
            "ENHANCED_CPC_OPT_IN": ("Enhanced CPC", "Enable Enhanced CPC for better conversion rates"),
            "SEARCH_PARTNERS_OPT_IN": ("Search Partners", "Expand reach with search partner network"),
            "TARGET_CPA_OPT_IN": ("Target CPA", "Set target CPA for automated bidding"),
            "KEYWORD_MATCH_TYPE": ("Match Types", "Adjust keyword match types for better targeting"),
            "MOVE_UNUSED_BUDGET": ("Reallocate Budget", "Move unused budget to higher-performing campaigns"),
            "RESPONSIVE_SEARCH_AD": ("Responsive Ads", "Create responsive search ads for better performance"),
        }

        recommendations = []
        for row in results:
            rec = row.get("recommendation", {})
            rec_type = rec.get("type", "UNKNOWN")
            impact = rec.get("impact", {}).get("baseMetrics", {})

            type_info = type_descriptions.get(rec_type, (rec_type.replace("_", " ").title(), "Optimization opportunity"))

            # Estimate impact
            impact_clicks = float(impact.get("clicks", {}).get("value", 0))
            impact_impressions = float(impact.get("impressions", {}).get("value", 0))

            impact_text = ""
            if impact_clicks > 0:
                impact_text = f"+{impact_clicks:.0f} clicks/week"
            elif impact_impressions > 0:
                impact_text = f"+{impact_impressions:.0f} impressions/week"

            # Determine priority based on type
            high_priority_types = {"CAMPAIGN_BUDGET", "MAXIMIZE_CONVERSIONS_OPT_IN", "MOVE_UNUSED_BUDGET"}
            low_priority_types = {"SEARCH_PARTNERS_OPT_IN", "KEYWORD_MATCH_TYPE"}

            if rec_type in high_priority_types:
                priority = "high"
            elif rec_type in low_priority_types:
                priority = "low"
            else:
                priority = "medium"

            recommendations.append({
                "type": type_info[0],
                "message": type_info[1],
                "priority": priority,
                "impact": impact_text or None,
            })

        self._set_cache(cache_key, recommendations)
        return recommendations

    async def get_full_performance(self, days: int = 30) -> dict:
        """Get complete performance data (metrics + campaigns + recommendations).

        This is the main method called by the marketing hub endpoint.
        """
        if not self.is_configured():
            return {
                "configured": False,
                "metrics": {"cost": 0, "clicks": 0, "impressions": 0, "conversions": 0, "ctr": 0, "cpa": 0},
                "campaigns": [],
                "recommendations": [],
            }

        metrics = await self.get_performance_metrics(days)
        campaigns = await self.get_campaigns(days)
        recommendations = await self.get_recommendations()

        return {
            "configured": True,
            "metrics": metrics or {"cost": 0, "clicks": 0, "impressions": 0, "conversions": 0, "ctr": 0, "cpa": 0},
            "campaigns": campaigns or [],
            "recommendations": recommendations or [],
        }

    async def get_connection_status(self) -> dict:
        """Check if Google Ads is connected and return account info."""
        if not self.is_configured():
            return {
                "connected": False,
                "customer_id": None,
                "account_name": None,
                "daily_operations": self._daily_ops,
                "daily_limit": MAX_DAILY_OPERATIONS,
            }

        account_info = await self.get_account_info()
        connected = account_info is not None

        return {
            "connected": connected,
            "customer_id": self.customer_id if connected else None,
            "account_name": account_info.get("name") if account_info else None,
            "daily_operations": self._daily_ops,
            "daily_limit": MAX_DAILY_OPERATIONS,
        }


# Singleton instance
google_ads_service = GoogleAdsService()


def get_google_ads_service() -> GoogleAdsService:
    """Get the Google Ads service singleton."""
    return google_ads_service
