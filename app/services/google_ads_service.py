"""
Google Ads API Service

Integrates with Google Ads REST API v20 for campaign performance data
and offline conversion uploads (Enhanced Conversions for Leads).
Uses httpx for async HTTP, OAuth2 token refresh, and in-memory caching.

Basic Access: 15,000 operations/day limit.
"""

import hashlib
import re
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
        self.conversion_action_id = getattr(settings, "GOOGLE_ADS_CONVERSION_ACTION_ID", None)

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
                    json={"query": query},
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
                            json={"query": query},
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
        if days == 0:
            return "DURING TODAY"
        elif days == 1:
            return "DURING YESTERDAY"
        elif days <= 7:
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

    async def get_ad_groups(self, days: int = 0) -> Optional[list]:
        """Get ad group level performance data."""
        cache_key = f"ad_groups_{days}"
        cached = self._get_cached(cache_key, CACHE_TTL_CAMPAIGNS)
        if cached is not None:
            return cached

        date_range = self._date_range_clause(days)
        query = f"""
            SELECT
                ad_group.id,
                ad_group.name,
                ad_group.status,
                campaign.id,
                campaign.name,
                metrics.cost_micros,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions,
                metrics.ctr
            FROM ad_group
            WHERE segments.date {date_range}
                AND campaign.status = 'ENABLED'
                AND metrics.impressions > 0
            ORDER BY metrics.conversions DESC, metrics.clicks DESC
            LIMIT 30
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        ad_groups = []
        for row in results:
            ag = row.get("adGroup", {})
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            cost_micros = int(m.get("costMicros", 0))
            cost = cost_micros / 1_000_000
            conversions = float(m.get("conversions", 0))
            ad_groups.append({
                "ad_group_id": str(ag.get("id", "")),
                "ad_group_name": ag.get("name", "Unknown"),
                "ad_group_status": (ag.get("status", "UNKNOWN")).lower(),
                "campaign_id": str(c.get("id", "")),
                "campaign_name": c.get("name", "Unknown"),
                "cost": round(cost, 2),
                "clicks": int(m.get("clicks", 0)),
                "impressions": int(m.get("impressions", 0)),
                "conversions": round(conversions, 1),
                "ctr": round(float(m.get("ctr", 0)), 4),
                "cpa": round(cost / conversions, 2) if conversions > 0 else None,
            })

        self._set_cache(cache_key, ad_groups)
        return ad_groups

    async def get_search_terms(self, days: int = 7) -> Optional[list]:
        """Get search terms that triggered ads."""
        cache_key = f"search_terms_{days}"
        cached = self._get_cached(cache_key, CACHE_TTL_CAMPAIGNS)
        if cached is not None:
            return cached

        date_range = self._date_range_clause(days)
        query = f"""
            SELECT
                search_term_view.search_term,
                campaign.name,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions,
                metrics.cost_micros
            FROM search_term_view
            WHERE segments.date {date_range}
                AND metrics.clicks > 0
            ORDER BY metrics.conversions DESC, metrics.clicks DESC
            LIMIT 50
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        terms = []
        for row in results:
            stv = row.get("searchTermView", {})
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            cost = int(m.get("costMicros", 0)) / 1_000_000
            conversions = float(m.get("conversions", 0))
            terms.append({
                "search_term": stv.get("searchTerm", ""),
                "campaign": c.get("name", "Unknown"),
                "clicks": int(m.get("clicks", 0)),
                "impressions": int(m.get("impressions", 0)),
                "conversions": round(conversions, 1),
                "cost": round(cost, 2),
                "cpa": round(cost / conversions, 2) if conversions > 0 else None,
            })

        self._set_cache(cache_key, terms)
        return terms

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

    async def get_daily_breakdown(self, days: int = 14, campaign_filter: str | None = None) -> Optional[list]:
        """Get daily performance breakdown by campaign. Essential for diagnosing trends."""
        cache_key = f"daily_breakdown_{days}_{campaign_filter}"
        cached = self._get_cached(cache_key, CACHE_TTL_METRICS)
        if cached is not None:
            return cached

        date_range = self._date_range_clause(days)
        where_clauses = [f"segments.date {date_range}", "campaign.status != 'REMOVED'"]
        if campaign_filter:
            where_clauses.append(f"campaign.name LIKE '%{campaign_filter}%'")

        query = f"""
            SELECT
                segments.date,
                campaign.name,
                campaign.advertising_channel_type,
                metrics.cost_micros,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions,
                metrics.phone_calls,
                metrics.phone_impressions
            FROM campaign
            WHERE {' AND '.join(where_clauses)}
            ORDER BY segments.date DESC, metrics.cost_micros DESC
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        rows = []
        for row in results:
            seg = row.get("segments", {})
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            cost_micros = int(m.get("costMicros", 0))
            cost = cost_micros / 1_000_000
            conversions = float(m.get("conversions", 0))
            rows.append({
                "date": seg.get("date", ""),
                "campaign": c.get("name", "Unknown"),
                "channel_type": c.get("advertisingChannelType", "UNKNOWN"),
                "cost": round(cost, 2),
                "clicks": int(m.get("clicks", 0)),
                "impressions": int(m.get("impressions", 0)),
                "conversions": round(conversions, 1),
                "phone_calls": int(m.get("phoneCalls", 0)),
                "phone_impressions": int(m.get("phoneImpressions", 0)),
                "cpa": round(cost / conversions, 2) if conversions > 0 else None,
            })

        self._set_cache(cache_key, rows)
        return rows

    async def get_impression_share(self, days: int = 7) -> Optional[list]:
        """Get Search impression share metrics by campaign. Diagnoses visibility issues."""
        cache_key = f"impression_share_{days}"
        cached = self._get_cached(cache_key, CACHE_TTL_METRICS)
        if cached is not None:
            return cached

        date_range = self._date_range_clause(days)
        query = f"""
            SELECT
                campaign.name,
                campaign.advertising_channel_type,
                metrics.search_impression_share,
                metrics.search_budget_lost_impression_share,
                metrics.search_rank_lost_impression_share,
                metrics.search_exact_match_impression_share,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions,
                metrics.cost_micros,
                metrics.average_cpc
            FROM campaign
            WHERE segments.date {date_range}
                AND campaign.status != 'REMOVED'
                AND metrics.impressions > 0
            ORDER BY metrics.impressions DESC
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        rows = []
        for row in results:
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            cost_micros = int(m.get("costMicros", 0))
            rows.append({
                "campaign": c.get("name", "Unknown"),
                "channel_type": c.get("advertisingChannelType", "UNKNOWN"),
                "search_impression_share": m.get("searchImpressionShare"),
                "search_budget_lost_is": m.get("searchBudgetLostImpressionShare"),
                "search_rank_lost_is": m.get("searchRankLostImpressionShare"),
                "search_exact_match_is": m.get("searchExactMatchImpressionShare"),
                "clicks": int(m.get("clicks", 0)),
                "impressions": int(m.get("impressions", 0)),
                "conversions": round(float(m.get("conversions", 0)), 1),
                "cost": round(cost_micros / 1_000_000, 2),
                "avg_cpc": round(int(m.get("averageCpc", 0)) / 1_000_000, 2),
            })

        self._set_cache(cache_key, rows)
        return rows

    async def get_call_metrics(self, days: int = 14) -> Optional[list]:
        """Get phone call metrics from campaigns and ad groups."""
        cache_key = f"call_metrics_{days}"
        cached = self._get_cached(cache_key, CACHE_TTL_METRICS)
        if cached is not None:
            return cached

        date_range = self._date_range_clause(days)
        query = f"""
            SELECT
                segments.date,
                campaign.name,
                ad_group.name,
                metrics.phone_calls,
                metrics.phone_impressions,
                metrics.phone_through_rate,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions,
                metrics.cost_micros
            FROM ad_group
            WHERE segments.date {date_range}
                AND campaign.status = 'ENABLED'
                AND metrics.impressions > 0
            ORDER BY segments.date DESC, metrics.phone_calls DESC
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        rows = []
        for row in results:
            seg = row.get("segments", {})
            c = row.get("campaign", {})
            ag = row.get("adGroup", {})
            m = row.get("metrics", {})
            rows.append({
                "date": seg.get("date", ""),
                "campaign": c.get("name", "Unknown"),
                "ad_group": ag.get("name", "Unknown"),
                "phone_calls": int(m.get("phoneCalls", 0)),
                "phone_impressions": int(m.get("phoneImpressions", 0)),
                "phone_through_rate": float(m.get("phoneThroughRate", 0)),
                "clicks": int(m.get("clicks", 0)),
                "impressions": int(m.get("impressions", 0)),
                "conversions": round(float(m.get("conversions", 0)), 1),
                "cost": round(int(m.get("costMicros", 0)) / 1_000_000, 2),
            })

        self._set_cache(cache_key, rows)
        return rows

    async def get_ad_position_metrics(self, days: int = 7) -> Optional[list]:
        """Get ad position metrics — absolute top %, top %, and competitive positioning."""
        cache_key = f"ad_position_{days}"
        cached = self._get_cached(cache_key, CACHE_TTL_METRICS)
        if cached is not None:
            return cached

        date_range = self._date_range_clause(days)
        query = f"""
            SELECT
                campaign.name,
                campaign.advertising_channel_type,
                metrics.absolute_top_impression_percentage,
                metrics.top_impression_percentage,
                metrics.search_impression_share,
                metrics.search_budget_lost_impression_share,
                metrics.search_rank_lost_impression_share,
                metrics.average_cpc,
                metrics.average_cost,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions,
                metrics.cost_micros
            FROM campaign
            WHERE segments.date {date_range}
                AND campaign.status = 'ENABLED'
                AND metrics.impressions > 0
            ORDER BY metrics.cost_micros DESC
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        rows = []
        for row in results:
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            rows.append({
                "campaign": c.get("name", "Unknown"),
                "channel_type": c.get("advertisingChannelType", "UNKNOWN"),
                "absolute_top_pct": m.get("absoluteTopImpressionPercentage"),
                "top_pct": m.get("topImpressionPercentage"),
                "search_impression_share": m.get("searchImpressionShare"),
                "budget_lost_is": m.get("searchBudgetLostImpressionShare"),
                "rank_lost_is": m.get("searchRankLostImpressionShare"),
                "avg_cpc": round(int(m.get("averageCpc", 0)) / 1_000_000, 2),
                "avg_cost": round(int(m.get("averageCost", 0)) / 1_000_000, 2),
                "clicks": int(m.get("clicks", 0)),
                "impressions": int(m.get("impressions", 0)),
                "conversions": round(float(m.get("conversions", 0)), 1),
                "cost": round(int(m.get("costMicros", 0)) / 1_000_000, 2),
            })

        self._set_cache(cache_key, rows)
        return rows

    async def get_auction_insights(self, days: int = 7, campaign_id: str | None = None) -> Optional[list]:
        """Get auction insights — competitor overlap, position above, outranking share."""
        cache_key = f"auction_insights_{days}_{campaign_id}"
        cached = self._get_cached(cache_key, CACHE_TTL_METRICS)
        if cached is not None:
            return cached

        date_range = self._date_range_clause(days)
        # Auction insights require campaign-level or ad-group-level filtering
        campaign_filter = ""
        if campaign_id:
            campaign_filter = f"AND campaign.id = {campaign_id}"

        # Try the standard auction_insight resource
        query = f"""
            SELECT
                auction_insight.display_domain
            FROM auction_insight
            WHERE segments.date {date_range}
                {campaign_filter}
        """
        results = await self._execute_query(query)
        if results is None:
            # Auction insights might not be available via GAQL search endpoint
            # Fall back to campaign-level competitive metrics
            return await self._get_competitive_fallback(days)

        rows = []
        for row in results:
            ai = row.get("auctionInsight", {})
            m = row.get("metrics", {})
            rows.append({
                "display_domain": ai.get("displayDomain", ""),
                "impression_share": m.get("auctionInsightSearchImpressionShare"),
                "overlap_rate": m.get("auctionInsightSearchOverlapRate"),
                "position_above_rate": m.get("auctionInsightSearchPositionAboveRate"),
                "top_of_page_rate": m.get("auctionInsightSearchTopImpressionPercentage"),
                "abs_top_of_page_rate": m.get("auctionInsightSearchAbsoluteTopImpressionPercentage"),
                "outranking_share": m.get("auctionInsightSearchOutrankingShare"),
            })

        self._set_cache(cache_key, rows)
        return rows

    async def _get_competitive_fallback(self, days: int = 7) -> list:
        """Fallback competitive analysis using available metrics."""
        return [{"error": "Auction insights not available via GAQL. Check Google Ads UI for competitor data."}]

    async def get_keyword_performance(self, days: int = 7, campaign_filter: str | None = None) -> Optional[list]:
        """Get keyword-level performance with CPC and position data."""
        cache_key = f"keyword_perf_{days}_{campaign_filter}"
        cached = self._get_cached(cache_key, CACHE_TTL_METRICS)
        if cached is not None:
            return cached

        date_range = self._date_range_clause(days)
        where_clauses = [
            f"segments.date {date_range}",
            "campaign.status = 'ENABLED'",
            "ad_group.status = 'ENABLED'",
            "ad_group_criterion.status = 'ENABLED'",
            "metrics.impressions > 0",
        ]
        if campaign_filter:
            where_clauses.append(f"campaign.name LIKE '%{campaign_filter}%'")

        query = f"""
            SELECT
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                campaign.name,
                ad_group.name,
                metrics.average_cpc,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions,
                metrics.cost_micros,
                metrics.absolute_top_impression_percentage,
                metrics.top_impression_percentage,
                metrics.search_impression_share
            FROM keyword_view
            WHERE {' AND '.join(where_clauses)}
            ORDER BY metrics.cost_micros DESC
            LIMIT 50
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        rows = []
        for row in results:
            agc = row.get("adGroupCriterion", {})
            kw = agc.get("keyword", {})
            c = row.get("campaign", {})
            ag = row.get("adGroup", {})
            m = row.get("metrics", {})
            cost_micros = int(m.get("costMicros", 0))
            conversions = float(m.get("conversions", 0))
            rows.append({
                "keyword": kw.get("text", ""),
                "match_type": kw.get("matchType", ""),
                "campaign": c.get("name", "Unknown"),
                "ad_group": ag.get("name", "Unknown"),
                "avg_cpc": round(int(m.get("averageCpc", 0)) / 1_000_000, 2),
                "clicks": int(m.get("clicks", 0)),
                "impressions": int(m.get("impressions", 0)),
                "conversions": round(conversions, 1),
                "cost": round(cost_micros / 1_000_000, 2),
                "abs_top_pct": m.get("absoluteTopImpressionPercentage"),
                "top_pct": m.get("topImpressionPercentage"),
                "search_is": m.get("searchImpressionShare"),
                "cpa": round(cost_micros / 1_000_000 / conversions, 2) if conversions > 0 else None,
            })

        self._set_cache(cache_key, rows)
        return rows

    async def get_change_history(self, days: int = 14) -> Optional[list]:
        """Get account change history — shows all edits to campaigns, ads, assets, etc."""
        cache_key = f"change_history_{days}"
        cached = self._get_cached(cache_key, CACHE_TTL_METRICS)
        if cached is not None:
            return cached

        # change_event uses timestamp comparison, not DURING clause
        start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        query = f"""
            SELECT
                change_event.change_date_time,
                change_event.change_resource_type,
                change_event.change_resource_name,
                change_event.client_type,
                change_event.user_email,
                change_event.resource_change_operation,
                change_event.changed_fields,
                change_event.old_resource,
                change_event.new_resource
            FROM change_event
            WHERE change_event.change_date_time >= '{start_date}'
                AND change_event.change_date_time <= '{end_date}'
            ORDER BY change_event.change_date_time DESC
            LIMIT 200
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        rows = []
        for row in results:
            ce = row.get("changeEvent", {})
            rows.append({
                "change_date_time": ce.get("changeDateTime", ""),
                "resource_type": ce.get("changeResourceType", "UNKNOWN"),
                "resource_name": ce.get("changeResourceName", ""),
                "client_type": ce.get("clientType", "UNKNOWN"),
                "user_email": ce.get("userEmail", ""),
                "operation": ce.get("resourceChangeOperation", "UNKNOWN"),
                "changed_fields": ce.get("changedFields", ""),
                "old_resource": ce.get("oldResource", {}),
                "new_resource": ce.get("newResource", {}),
            })

        self._set_cache(cache_key, rows)
        return rows

    async def get_ad_copy(self, campaign_filter: str | None = None) -> Optional[list]:
        """Get current ad copy (RSA headlines/descriptions) by campaign."""
        cache_key = f"ad_copy_{campaign_filter}"
        cached = self._get_cached(cache_key, CACHE_TTL_CAMPAIGNS)
        if cached is not None:
            return cached

        where_clauses = ["ad_group_ad.status != 'REMOVED'", "campaign.status != 'REMOVED'"]
        if campaign_filter:
            where_clauses.append(f"campaign.name LIKE '%{campaign_filter}%'")

        query = f"""
            SELECT
                ad_group_ad.ad.id,
                ad_group_ad.ad.type,
                ad_group_ad.ad.responsive_search_ad.headlines,
                ad_group_ad.ad.responsive_search_ad.descriptions,
                ad_group_ad.ad.final_urls,
                ad_group_ad.status,
                ad_group_ad.ad.name,
                campaign.name,
                ad_group.name
            FROM ad_group_ad
            WHERE {' AND '.join(where_clauses)}
            ORDER BY campaign.name, ad_group.name
            LIMIT 50
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        rows = []
        for row in results:
            aga = row.get("adGroupAd", {})
            ad = aga.get("ad", {})
            c = row.get("campaign", {})
            ag = row.get("adGroup", {})
            rsa = ad.get("responsiveSearchAd", {})

            headlines = []
            for h in rsa.get("headlines", []):
                headlines.append({"text": h.get("text", ""), "pinned_field": h.get("pinnedField")})

            descriptions = []
            for d in rsa.get("descriptions", []):
                descriptions.append({"text": d.get("text", ""), "pinned_field": d.get("pinnedField")})

            rows.append({
                "ad_id": str(ad.get("id", "")),
                "ad_type": ad.get("type", "UNKNOWN"),
                "status": aga.get("status", "UNKNOWN"),
                "campaign": c.get("name", "Unknown"),
                "ad_group": ag.get("name", "Unknown"),
                "headlines": headlines,
                "descriptions": descriptions,
                "final_urls": ad.get("finalUrls", []),
            })

        self._set_cache(cache_key, rows)
        return rows

    async def get_call_assets(self) -> Optional[list]:
        """Get call extension/asset details across campaigns."""
        cache_key = "call_assets"
        cached = self._get_cached(cache_key, CACHE_TTL_CAMPAIGNS)
        if cached is not None:
            return cached

        query = """
            SELECT
                asset.id,
                asset.name,
                asset.type,
                asset.call_asset.country_code,
                asset.call_asset.phone_number,
                asset.call_asset.call_conversion_reporting_state,
                campaign_asset.campaign,
                campaign_asset.status,
                campaign_asset.field_type
            FROM campaign_asset
            WHERE asset.type = 'CALL'
                AND campaign_asset.status != 'REMOVED'
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        rows = []
        for row in results:
            asset = row.get("asset", {})
            ca = row.get("campaignAsset", {})
            call_asset = asset.get("callAsset", {})
            rows.append({
                "asset_id": str(asset.get("id", "")),
                "asset_name": asset.get("name", ""),
                "phone_number": call_asset.get("phoneNumber", ""),
                "country_code": call_asset.get("countryCode", ""),
                "conversion_reporting": call_asset.get("callConversionReportingState", ""),
                "campaign": ca.get("campaign", ""),
                "status": ca.get("status", "UNKNOWN"),
                "field_type": ca.get("fieldType", ""),
            })

        self._set_cache(cache_key, rows)
        return rows

    # ─── Nashville-Specific Methods ──────────────────────────────────────

    async def get_nashville_today(self) -> Optional[dict]:
        """Get today's real-time metrics for Nashville campaigns only."""
        cache_key = "nashville_today"
        cached = self._get_cached(cache_key, 300)  # 5 min cache for real-time
        if cached is not None:
            return cached

        query = """
            SELECT
                campaign.name,
                campaign.advertising_channel_type,
                metrics.cost_micros,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions,
                metrics.phone_calls,
                metrics.ctr,
                metrics.average_cpc
            FROM campaign
            WHERE segments.date DURING TODAY
                AND campaign.status != 'REMOVED'
                AND campaign.name LIKE '%Nashville%'
            ORDER BY metrics.cost_micros DESC
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        total_cost = 0
        total_clicks = 0
        total_impressions = 0
        total_conversions = 0.0
        total_calls = 0
        campaigns = []

        for row in results:
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            cost_micros = int(m.get("costMicros", 0))
            cost = cost_micros / 1_000_000
            conversions = float(m.get("conversions", 0))
            clicks = int(m.get("clicks", 0))
            impressions = int(m.get("impressions", 0))
            calls = int(m.get("phoneCalls", 0))

            total_cost += cost
            total_clicks += clicks
            total_impressions += impressions
            total_conversions += conversions
            total_calls += calls

            campaigns.append({
                "name": c.get("name", "Unknown"),
                "channel_type": c.get("advertisingChannelType", "UNKNOWN"),
                "cost": round(cost, 2),
                "clicks": clicks,
                "impressions": impressions,
                "conversions": round(conversions, 1),
                "calls": calls,
                "ctr": round(float(m.get("ctr", 0)), 4),
                "avg_cpc": round(int(m.get("averageCpc", 0)) / 1_000_000, 2),
            })

        result = {
            "totals": {
                "cost": round(total_cost, 2),
                "clicks": total_clicks,
                "impressions": total_impressions,
                "conversions": round(total_conversions, 1),
                "calls": total_calls,
                "ctr": round(total_clicks / max(1, total_impressions), 4),
                "cpa": round(total_cost / total_conversions, 2) if total_conversions > 0 else 0,
                "avg_cpc": round(total_cost / max(1, total_clicks), 2),
            },
            "campaigns": campaigns,
        }
        self._set_cache(cache_key, result)
        return result

    async def get_nashville_hourly(self) -> Optional[list]:
        """Get hourly spend/performance breakdown for Nashville campaigns today."""
        cache_key = "nashville_hourly"
        cached = self._get_cached(cache_key, 300)  # 5 min cache
        if cached is not None:
            return cached

        query = """
            SELECT
                segments.hour,
                metrics.cost_micros,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions
            FROM campaign
            WHERE segments.date DURING TODAY
                AND campaign.status != 'REMOVED'
                AND campaign.name LIKE '%Nashville%'
            ORDER BY segments.hour ASC
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        # Aggregate by hour
        hourly = {}
        for row in results:
            hour = int(row.get("segments", {}).get("hour", 0))
            m = row.get("metrics", {})
            if hour not in hourly:
                hourly[hour] = {"hour": hour, "cost": 0, "clicks": 0, "impressions": 0, "conversions": 0}
            hourly[hour]["cost"] += int(m.get("costMicros", 0)) / 1_000_000
            hourly[hour]["clicks"] += int(m.get("clicks", 0))
            hourly[hour]["impressions"] += int(m.get("impressions", 0))
            hourly[hour]["conversions"] += float(m.get("conversions", 0))

        # Fill all 24 hours
        rows = []
        for h in range(24):
            entry = hourly.get(h, {"hour": h, "cost": 0, "clicks": 0, "impressions": 0, "conversions": 0})
            entry["cost"] = round(entry["cost"], 2)
            entry["conversions"] = round(entry["conversions"], 1)
            rows.append(entry)

        self._set_cache(cache_key, rows)
        return rows

    async def get_nashville_budgets(self) -> Optional[list]:
        """Get Nashville campaign budget information."""
        cache_key = "nashville_budgets"
        cached = self._get_cached(cache_key, 600)  # 10 min cache
        if cached is not None:
            return cached

        query = """
            SELECT
                campaign.name,
                campaign.advertising_channel_type,
                campaign_budget.amount_micros,
                campaign.bidding_strategy_type,
                metrics.cost_micros,
                metrics.clicks,
                metrics.conversions
            FROM campaign
            WHERE segments.date DURING TODAY
                AND campaign.status = 'ENABLED'
                AND campaign.name LIKE '%Nashville%'
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        rows = []
        for row in results:
            c = row.get("campaign", {})
            cb = row.get("campaignBudget", {})
            m = row.get("metrics", {})
            budget_micros = int(cb.get("amountMicros", 0))
            cost_micros = int(m.get("costMicros", 0))
            daily_budget = budget_micros / 1_000_000
            today_spend = cost_micros / 1_000_000
            rows.append({
                "campaign": c.get("name", "Unknown"),
                "channel_type": c.get("advertisingChannelType", "UNKNOWN"),
                "daily_budget": round(daily_budget, 2),
                "today_spend": round(today_spend, 2),
                "remaining": round(max(0, daily_budget - today_spend), 2),
                "pacing_pct": round((today_spend / max(0.01, daily_budget)) * 100, 1),
                "bidding_strategy": c.get("biddingStrategyType", "UNKNOWN"),
                "clicks": int(m.get("clicks", 0)),
                "conversions": round(float(m.get("conversions", 0)), 1),
            })

        self._set_cache(cache_key, rows)
        return rows

    async def get_nashville_search_terms(self, days: int = 1) -> Optional[list]:
        """Get search terms for Nashville campaigns only."""
        cache_key = f"nashville_search_terms_{days}"
        cached = self._get_cached(cache_key, 300)
        if cached is not None:
            return cached

        date_range = self._date_range_clause(days)
        query = f"""
            SELECT
                search_term_view.search_term,
                campaign.name,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions,
                metrics.cost_micros
            FROM search_term_view
            WHERE segments.date {date_range}
                AND campaign.name LIKE '%Nashville%'
                AND metrics.clicks > 0
            ORDER BY metrics.cost_micros DESC
            LIMIT 100
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        terms = []
        for row in results:
            stv = row.get("searchTermView", {})
            c = row.get("campaign", {})
            m = row.get("metrics", {})
            cost = int(m.get("costMicros", 0)) / 1_000_000
            conversions = float(m.get("conversions", 0))
            terms.append({
                "search_term": stv.get("searchTerm", ""),
                "campaign": c.get("name", "Unknown"),
                "clicks": int(m.get("clicks", 0)),
                "impressions": int(m.get("impressions", 0)),
                "conversions": round(conversions, 1),
                "cost": round(cost, 2),
                "cpa": round(cost / conversions, 2) if conversions > 0 else None,
            })

        self._set_cache(cache_key, terms)
        return terms

    async def get_nashville_keywords(self, days: int = 7) -> Optional[list]:
        """Get keyword-level performance for Nashville campaigns."""
        cache_key = f"nashville_keywords_{days}"
        cached = self._get_cached(cache_key, CACHE_TTL_METRICS)
        if cached is not None:
            return cached

        date_range = self._date_range_clause(days)
        query = f"""
            SELECT
                ad_group_criterion.keyword.text,
                ad_group_criterion.keyword.match_type,
                campaign.name,
                ad_group.name,
                metrics.average_cpc,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions,
                metrics.cost_micros,
                metrics.search_impression_share
            FROM keyword_view
            WHERE segments.date {date_range}
                AND campaign.name LIKE '%Nashville%'
                AND campaign.status = 'ENABLED'
                AND ad_group.status = 'ENABLED'
                AND ad_group_criterion.status = 'ENABLED'
                AND metrics.impressions > 0
            ORDER BY metrics.cost_micros DESC
            LIMIT 50
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        rows = []
        for row in results:
            agc = row.get("adGroupCriterion", {})
            kw = agc.get("keyword", {})
            c = row.get("campaign", {})
            ag = row.get("adGroup", {})
            m = row.get("metrics", {})
            cost_micros = int(m.get("costMicros", 0))
            conversions = float(m.get("conversions", 0))
            rows.append({
                "keyword": kw.get("text", ""),
                "match_type": kw.get("matchType", ""),
                "campaign": c.get("name", "Unknown"),
                "ad_group": ag.get("name", "Unknown"),
                "avg_cpc": round(int(m.get("averageCpc", 0)) / 1_000_000, 2),
                "clicks": int(m.get("clicks", 0)),
                "impressions": int(m.get("impressions", 0)),
                "conversions": round(conversions, 1),
                "cost": round(cost_micros / 1_000_000, 2),
                "search_is": m.get("searchImpressionShare"),
                "cpa": round(cost_micros / 1_000_000 / conversions, 2) if conversions > 0 else None,
            })

        self._set_cache(cache_key, rows)
        return rows

    async def update_campaign_budget(self, campaign_name: str, new_daily_budget: float) -> dict:
        """Update daily budget for a campaign by name.

        Args:
            campaign_name: Campaign name (exact match or LIKE pattern)
            new_daily_budget: New daily budget in dollars (e.g. 150.00)

        Returns:
            dict with success status and details
        """
        if not self.is_configured():
            return {"success": False, "error": "Google Ads not configured"}

        # First, find the campaign budget resource name
        query = f"""
            SELECT
                campaign.name,
                campaign.resource_name,
                campaign_budget.resource_name,
                campaign_budget.amount_micros
            FROM campaign
            WHERE campaign.status = 'ENABLED'
                AND campaign.name = '{campaign_name}'
        """
        results = await self._execute_query(query)
        if not results:
            return {"success": False, "error": f"Campaign '{campaign_name}' not found"}

        row = results[0]
        budget_rn = row.get("campaignBudget", {}).get("resourceName")
        old_micros = int(row.get("campaignBudget", {}).get("amountMicros", 0))
        old_budget = old_micros / 1_000_000

        if not budget_rn:
            return {"success": False, "error": "Budget resource name not found"}

        new_micros = int(new_daily_budget * 1_000_000)

        access_token = await self._refresh_access_token()
        if not access_token:
            return {"success": False, "error": "Failed to refresh token"}

        customer_id = self._get_clean_customer_id()
        url = f"{GOOGLE_ADS_BASE_URL}/customers/{customer_id}/campaignBudgets/{budget_rn.split('/')[-1]}:mutate"

        # Use the googleAds:mutate endpoint for budget updates
        mutate_url = f"{GOOGLE_ADS_BASE_URL}/customers/{customer_id}/googleAds:mutate"
        payload = {
            "mutateOperations": [
                {
                    "campaignBudgetOperation": {
                        "update": {
                            "resourceName": budget_rn,
                            "amountMicros": str(new_micros),
                        },
                        "updateMask": "amount_micros",
                    }
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    mutate_url,
                    headers=self._get_headers(access_token),
                    json=payload,
                )
                self._increment_ops()

                if response.status_code in (200, 201):
                    # Clear budget cache so next query shows new value
                    if "nashville_budgets" in self._cache:
                        del self._cache["nashville_budgets"]

                    return {
                        "success": True,
                        "campaign": campaign_name,
                        "old_budget": round(old_budget, 2),
                        "new_budget": round(new_daily_budget, 2),
                        "change": round(new_daily_budget - old_budget, 2),
                        "change_pct": round(((new_daily_budget - old_budget) / old_budget) * 100, 1) if old_budget > 0 else 0,
                    }
                else:
                    error_text = response.text[:500]
                    logger.error("Budget update failed: %s %s", response.status_code, error_text)
                    return {"success": False, "error": error_text, "status_code": response.status_code}

        except Exception as e:
            logger.error("Budget update error: %s", str(e))
            return {"success": False, "error": str(e)}

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

    # ─── Offline Conversion Upload (Enhanced Conversions for Leads) ────

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normalize phone to E.164 format for hashing."""
        digits = re.sub(r"[^\d]", "", phone)
        if len(digits) == 10:
            digits = "1" + digits
        return f"+{digits}"

    @staticmethod
    def _normalize_email(email: str) -> str:
        """Normalize email: lowercase, strip whitespace."""
        return email.strip().lower()

    @staticmethod
    def _sha256_hash(value: str) -> str:
        """SHA-256 hash a string (for PII hashing per Google's spec)."""
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _get_conversion_action_resource(self) -> Optional[str]:
        """Build the conversion action resource name."""
        if not self.conversion_action_id:
            return None
        customer_id = self._get_clean_customer_id()
        return f"customers/{customer_id}/conversionActions/{self.conversion_action_id}"

    async def check_enhanced_conversions_setting(self) -> Optional[dict]:
        """Check if enhanced conversions for leads is enabled at the account level."""
        query = """
            SELECT
                customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled,
                customer.conversion_tracking_setting.google_ads_conversion_customer
            FROM customer
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        if results:
            cts = results[0].get("customer", {}).get("conversionTrackingSetting", {})
            return {
                "enhanced_conversions_for_leads_enabled": cts.get("enhancedConversionsForLeadsEnabled", False),
                "conversion_customer": cts.get("googleAdsConversionCustomer"),
            }
        return {"enhanced_conversions_for_leads_enabled": False}

    async def enable_enhanced_conversions_for_leads(self) -> dict:
        """Try to enable enhanced conversions for leads via the API."""
        if not self.is_configured():
            return {"success": False, "error": "Not configured"}

        access_token = await self._refresh_access_token()
        if not access_token:
            return {"success": False, "error": "Failed to refresh token"}

        customer_id = self._get_clean_customer_id()
        url = f"{GOOGLE_ADS_BASE_URL}/customers/{customer_id}:mutate"

        payload = {
            "mutateOperations": [
                {
                    "customerOperation": {
                        "update": {
                            "resourceName": f"customers/{customer_id}",
                        },
                        "updateMask": "conversion_tracking_setting.enhanced_conversions_for_leads_enabled",
                    }
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(access_token),
                    json=payload,
                )
                self._increment_ops()

                if response.status_code not in (200, 201):
                    return {"success": False, "error": response.text[:500], "status_code": response.status_code}

                return {"success": True, "data": response.json()}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def create_offline_conversion_action(self, name: str = "CRM Job Completion") -> Optional[dict]:
        """Create an offline conversion action in Google Ads.

        This only needs to be called once. Save the returned ID as
        GOOGLE_ADS_CONVERSION_ACTION_ID env var.
        """
        if not self.is_configured():
            return None

        if not self._check_daily_limit():
            return None

        access_token = await self._refresh_access_token()
        if not access_token:
            return None

        customer_id = self._get_clean_customer_id()
        url = f"{GOOGLE_ADS_BASE_URL}/customers/{customer_id}/conversionActions:mutate"

        payload = {
            "operations": [
                {
                    "create": {
                        "name": name,
                        "type": "UPLOAD_CLICKS",
                        "category": "PURCHASE",
                        "status": "ENABLED",
                        "valueSettings": {
                            "defaultValue": 700.0,
                            "defaultCurrencyCode": "USD",
                            "alwaysUseDefaultValue": False,
                        },
                    }
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(access_token),
                    json=payload,
                )
                self._increment_ops()

                if response.status_code not in (200, 201):
                    logger.error(
                        "Failed to create conversion action: %s %s",
                        response.status_code,
                        response.text[:1000],
                    )
                    return {"error": response.text[:500], "status_code": response.status_code}

                data = response.json()
                results = data.get("results", [])
                if results:
                    resource_name = results[0].get("resourceName", "")
                    # Extract the ID from the resource name
                    action_id = resource_name.split("/")[-1] if resource_name else None
                    logger.info("Created offline conversion action: %s (ID: %s)", resource_name, action_id)
                    return {
                        "resource_name": resource_name,
                        "conversion_action_id": action_id,
                        "name": name,
                        "message": f"Set GOOGLE_ADS_CONVERSION_ACTION_ID={action_id} in Railway env vars",
                    }
                return {"error": "No results returned", "data": data}

        except Exception as e:
            logger.error("Error creating conversion action: %s", str(e))
            return {"error": str(e)}

    async def list_conversion_actions(self) -> Optional[list]:
        """List all conversion actions in the account."""
        query = """
            SELECT
                conversion_action.id,
                conversion_action.name,
                conversion_action.type,
                conversion_action.status,
                conversion_action.category
            FROM conversion_action
            WHERE conversion_action.status = 'ENABLED'
            ORDER BY conversion_action.name
        """
        results = await self._execute_query(query)
        if results is None:
            return None

        actions = []
        for row in results:
            ca = row.get("conversionAction", {})
            actions.append({
                "id": ca.get("id"),
                "name": ca.get("name"),
                "type": ca.get("type"),
                "status": ca.get("status"),
                "category": ca.get("category"),
            })
        return actions

    async def upload_offline_conversion(
        self,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        conversion_value: float = 700.0,
        conversion_time: Optional[datetime] = None,
        order_id: Optional[str] = None,
    ) -> dict:
        """Upload a single offline conversion using Enhanced Conversions for Leads.

        Google matches the hashed phone/email to the original ad click.
        At least one of phone or email is required.

        Args:
            phone: Customer phone number (will be normalized to E.164 and hashed)
            email: Customer email (will be normalized and hashed)
            conversion_value: Dollar value of the conversion (default $700)
            conversion_time: When the conversion happened (default: now)
            order_id: Unique order ID to prevent duplicates (e.g., work_order_id)
        """
        if not self.is_configured():
            return {"success": False, "error": "Google Ads not configured"}

        conversion_action = self._get_conversion_action_resource()
        if not conversion_action:
            return {"success": False, "error": "GOOGLE_ADS_CONVERSION_ACTION_ID not set. Create a conversion action first via POST /marketing-hub/ads/conversion-action"}

        if not phone and not email:
            return {"success": False, "error": "At least one of phone or email is required"}

        if not self._check_daily_limit():
            return {"success": False, "error": "Daily API operation limit reached"}

        access_token = await self._refresh_access_token()
        if not access_token:
            return {"success": False, "error": "Failed to refresh OAuth token"}

        # Build user identifiers (hashed PII)
        user_identifiers = []
        if phone:
            normalized = self._normalize_phone(phone)
            user_identifiers.append({
                "hashedPhoneNumber": self._sha256_hash(normalized)
            })
        if email:
            normalized = self._normalize_email(email)
            user_identifiers.append({
                "hashedEmail": self._sha256_hash(normalized)
            })

        # Format conversion time
        if not conversion_time:
            conversion_time = datetime.utcnow()
        # Google expects: yyyy-mm-dd hh:mm:ss+|-hh:mm
        # Google expects account timezone; use +00:00 for UTC timestamps
        conv_time_str = conversion_time.strftime("%Y-%m-%d %H:%M:%S+00:00")

        conversion = {
            "conversionAction": conversion_action,
            "conversionDateTime": conv_time_str,
            "conversionValue": conversion_value,
            "currencyCode": "USD",
            "userIdentifiers": user_identifiers,
        }

        if order_id:
            conversion["orderId"] = str(order_id)

        customer_id = self._get_clean_customer_id()
        url = f"{GOOGLE_ADS_BASE_URL}/customers/{customer_id}:uploadClickConversions"

        payload = {
            "conversions": [conversion],
            "partialFailure": True,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(access_token),
                    json=payload,
                )
                self._increment_ops()

                if response.status_code not in (200, 201):
                    error_text = response.text[:1000]
                    logger.error("Offline conversion upload failed: %s %s", response.status_code, error_text)
                    return {"success": False, "error": error_text, "status_code": response.status_code}

                data = response.json()
                partial_errors = data.get("partialFailureError")
                if partial_errors:
                    logger.warning("Partial failure in conversion upload: %s", partial_errors)
                    return {
                        "success": False,
                        "error": "Partial failure",
                        "details": partial_errors,
                        "results": data.get("results", []),
                    }

                results = data.get("results", [])
                logger.info(
                    "Offline conversion uploaded: value=$%.2f, order_id=%s, identifiers=%d",
                    conversion_value,
                    order_id,
                    len(user_identifiers),
                )
                return {
                    "success": True,
                    "results": results,
                    "conversion_value": conversion_value,
                    "order_id": order_id,
                }

        except Exception as e:
            logger.error("Offline conversion upload error: %s", str(e))
            return {"success": False, "error": str(e)}

    async def upload_offline_conversions_batch(
        self,
        conversions: list[dict],
    ) -> dict:
        """Upload multiple offline conversions in a single API call.

        Each dict in conversions should have:
            phone, email, conversion_value, conversion_time, order_id
        """
        if not self.is_configured():
            return {"success": False, "error": "Google Ads not configured"}

        conversion_action = self._get_conversion_action_resource()
        if not conversion_action:
            return {"success": False, "error": "GOOGLE_ADS_CONVERSION_ACTION_ID not set"}

        if not conversions:
            return {"success": False, "error": "No conversions provided"}

        access_token = await self._refresh_access_token()
        if not access_token:
            return {"success": False, "error": "Failed to refresh OAuth token"}

        # Build conversion objects
        conv_objects = []
        skipped = []
        for i, c in enumerate(conversions):
            phone = c.get("phone")
            email = c.get("email")
            if not phone and not email:
                skipped.append({"index": i, "reason": "no phone or email"})
                continue

            user_identifiers = []
            if phone:
                normalized = self._normalize_phone(phone)
                user_identifiers.append({"hashedPhoneNumber": self._sha256_hash(normalized)})
            if email:
                normalized = self._normalize_email(email)
                user_identifiers.append({"hashedEmail": self._sha256_hash(normalized)})

            conv_time = c.get("conversion_time", datetime.utcnow())
            if isinstance(conv_time, str):
                conv_time = datetime.fromisoformat(conv_time)
            conv_time_str = conv_time.strftime("%Y-%m-%d %H:%M:%S+00:00")

            obj = {
                "conversionAction": conversion_action,
                "conversionDateTime": conv_time_str,
                "conversionValue": c.get("conversion_value", 700.0),
                "currencyCode": "USD",
                "userIdentifiers": user_identifiers,
            }
            order_id = c.get("order_id")
            if order_id:
                obj["orderId"] = str(order_id)

            conv_objects.append(obj)

        if not conv_objects:
            return {"success": False, "error": "No valid conversions after filtering", "skipped": skipped}

        customer_id = self._get_clean_customer_id()
        url = f"{GOOGLE_ADS_BASE_URL}/customers/{customer_id}:uploadClickConversions"

        # Google allows up to 2000 per request; batch in chunks of 200
        uploaded = 0
        errors = []
        for chunk_start in range(0, len(conv_objects), 200):
            chunk = conv_objects[chunk_start : chunk_start + 200]
            payload = {"conversions": chunk, "partialFailure": True}

            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        url,
                        headers=self._get_headers(access_token),
                        json=payload,
                    )
                    self._increment_ops()

                    if response.status_code not in (200, 201):
                        errors.append({"chunk": chunk_start, "error": response.text[:500]})
                        continue

                    data = response.json()
                    partial_errors = data.get("partialFailureError")
                    if partial_errors:
                        errors.append({"chunk": chunk_start, "partial_errors": partial_errors})

                    uploaded += len(chunk)

            except Exception as e:
                errors.append({"chunk": chunk_start, "error": str(e)})

        logger.info("Batch offline conversion upload: %d/%d uploaded, %d skipped", uploaded, len(conv_objects), len(skipped))
        return {
            "success": uploaded > 0,
            "uploaded": uploaded,
            "total": len(conv_objects),
            "skipped": skipped,
            "errors": errors if errors else None,
        }


    # ─── GENERIC NEGATIVE KEYWORDS ─────────────────────────────────────

    async def apply_negative_keywords_to_campaigns(
        self, keywords: list[dict], campaign_filter: str
    ) -> dict:
        """Apply negative keywords to campaigns matching a name filter.

        Args:
            keywords: List of {keyword_text, match_type} dicts.
            campaign_filter: Substring to match campaign names (e.g. "South Carolina").

        Returns dict with success, applied_count, campaigns_affected.
        """
        if not self.is_configured():
            return {"success": False, "error": "Google Ads not configured"}

        if not keywords:
            return {"success": False, "error": "No keywords provided"}

        if not campaign_filter or not campaign_filter.strip():
            return {"success": False, "error": "campaign_filter is required"}

        # Query matching campaigns
        query = f"""
            SELECT campaign.resource_name, campaign.name
            FROM campaign
            WHERE campaign.status = 'ENABLED'
                AND campaign.name LIKE '%{campaign_filter.strip()}%'
        """
        results = await self._execute_query(query)
        if not results:
            return {"success": False, "error": f"No campaigns found matching '{campaign_filter}'"}

        campaigns = [
            r.get("campaign", {}).get("resourceName", "")
            for r in results
            if r.get("campaign", {}).get("resourceName")
        ]
        if not campaigns:
            return {"success": False, "error": f"No campaigns found matching '{campaign_filter}'"}

        access_token = await self._refresh_access_token()
        if not access_token:
            return {"success": False, "error": "Failed to refresh token"}

        customer_id = self._get_clean_customer_id()
        url = f"{GOOGLE_ADS_BASE_URL}/customers/{customer_id}/googleAds:mutate"

        operations = []
        for kw in keywords:
            text = kw.get("keyword_text", "").strip()
            match = kw.get("match_type", "EXACT").upper()
            if not text:
                continue

            for campaign_rn in campaigns:
                operations.append({
                    "campaignCriterionOperation": {
                        "create": {
                            "campaign": campaign_rn,
                            "negative": True,
                            "keyword": {
                                "text": text,
                                "matchType": match,
                            },
                        }
                    }
                })

        if not operations:
            return {"success": False, "error": "No valid operations built"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(access_token),
                    json={"mutateOperations": operations},
                )
                self._increment_ops()

                if response.status_code in (200, 201):
                    result = response.json()
                    results_list = result.get("mutateOperationResponses", [])
                    return {
                        "success": True,
                        "applied_count": len(results_list),
                        "keywords": [kw.get("keyword_text") for kw in keywords if kw.get("keyword_text", "").strip()],
                        "campaigns_affected": len(campaigns),
                        "campaign_filter": campaign_filter,
                    }
                else:
                    error_text = response.text[:500]
                    logger.error("Failed to apply negative keywords: %s %s", response.status_code, error_text)
                    return {"success": False, "error": error_text, "status_code": response.status_code}

        except Exception as e:
            logger.error("Negative keyword application error: %s", str(e))
            return {"success": False, "error": str(e)}

    async def remove_negative_keywords_from_campaigns(
        self, keywords: list[dict], campaign_filter: str
    ) -> dict:
        """Remove negative keywords from campaigns matching a name filter.

        Args:
            keywords: List of {keyword_text, match_type} dicts.
            campaign_filter: Substring to match campaign names.

        Returns dict with success, removed_count.
        """
        if not self.is_configured():
            return {"success": False, "error": "Google Ads not configured"}

        if not keywords or not campaign_filter or not campaign_filter.strip():
            return {"success": False, "error": "keywords and campaign_filter required"}

        customer_id = self._get_clean_customer_id()

        # Find existing negative keyword criteria on matching campaigns
        criteria_to_remove = []
        for kw in keywords:
            text = kw.get("keyword_text", "").strip().lower()
            match_type = kw.get("match_type", "PHRASE").upper()
            if not text:
                continue

            query = f"""
                SELECT campaign_criterion.resource_name,
                       campaign_criterion.keyword.text,
                       campaign_criterion.keyword.match_type,
                       campaign.name
                FROM campaign_criterion
                WHERE campaign_criterion.negative = TRUE
                    AND campaign_criterion.type = 'KEYWORD'
                    AND campaign.name LIKE '%{campaign_filter.strip()}%'
                    AND campaign.status != 'REMOVED'
            """
            results = await self._execute_query(query)
            if not results:
                continue

            for r in results:
                criterion = r.get("campaignCriterion", {})
                kw_data = criterion.get("keyword", {})
                if (kw_data.get("text", "").lower() == text
                        and kw_data.get("matchType", "").upper() == match_type):
                    rn = criterion.get("resourceName")
                    if rn:
                        criteria_to_remove.append(rn)

        if not criteria_to_remove:
            return {"success": False, "error": "No matching negative keywords found to remove"}

        access_token = await self._refresh_access_token()
        if not access_token:
            return {"success": False, "error": "Failed to refresh token"}

        url = f"{GOOGLE_ADS_BASE_URL}/customers/{customer_id}/googleAds:mutate"
        operations = [
            {"campaignCriterionOperation": {"remove": rn}}
            for rn in criteria_to_remove
        ]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(access_token),
                    json={"mutateOperations": operations},
                )
                self._increment_ops()

                if response.status_code in (200, 201):
                    result = response.json()
                    removed = len(result.get("mutateOperationResponses", []))
                    return {
                        "success": True,
                        "removed_count": removed,
                        "keywords": [kw.get("keyword_text") for kw in keywords],
                        "campaign_filter": campaign_filter,
                    }
                else:
                    error_text = response.text[:500]
                    logger.error("Failed to remove negative keywords: %s %s", response.status_code, error_text)
                    return {"success": False, "error": error_text}

        except Exception as e:
            logger.error("Remove negative keywords error: %s", str(e))
            return {"success": False, "error": str(e)}

    # ─── CREATE AD GROUP ───────────────────────────────────────────────

    async def create_ad_group(
        self, campaign_id: str, ad_group_name: str, keywords: list[dict]
    ) -> dict:
        """Create an ad group with keywords in a single batch mutation.

        Args:
            campaign_id: The campaign ID (numeric string, no prefix).
            ad_group_name: Name for the new ad group.
            keywords: List of {text, match_type} dicts.

        Returns dict with success, ad_group_resource_name.
        """
        if not self.is_configured():
            return {"success": False, "error": "Google Ads not configured"}

        if not campaign_id or not ad_group_name:
            return {"success": False, "error": "campaign_id and ad_group_name are required"}

        access_token = await self._refresh_access_token()
        if not access_token:
            return {"success": False, "error": "Failed to refresh token"}

        customer_id = self._get_clean_customer_id()
        url = f"{GOOGLE_ADS_BASE_URL}/customers/{customer_id}/googleAds:mutate"

        # Use temporary resource name -1 to link ad group creation with keyword additions
        temp_resource = f"customers/{customer_id}/adGroups/-1"

        operations = [
            {
                "adGroupOperation": {
                    "create": {
                        "resourceName": temp_resource,
                        "name": ad_group_name,
                        "campaign": f"customers/{customer_id}/campaigns/{campaign_id}",
                        "status": "ENABLED",
                        "type": "SEARCH_STANDARD",
                    }
                }
            }
        ]

        # Add keyword criteria
        for kw in (keywords or []):
            text = kw.get("text", "").strip()
            match_type = kw.get("match_type", "BROAD").upper()
            if not text:
                continue
            operations.append({
                "adGroupCriterionOperation": {
                    "create": {
                        "adGroup": temp_resource,
                        "status": "ENABLED",
                        "keyword": {
                            "text": text,
                            "matchType": match_type,
                        },
                    }
                }
            })

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(access_token),
                    json={"mutateOperations": operations},
                )
                self._increment_ops()

                if response.status_code in (200, 201):
                    result = response.json()
                    responses = result.get("mutateOperationResponses", [])
                    # First response is the ad group creation
                    ad_group_rn = None
                    if responses:
                        ag_result = responses[0].get("adGroupResult", {})
                        ad_group_rn = ag_result.get("resourceName")

                    return {
                        "success": True,
                        "ad_group_resource_name": ad_group_rn,
                        "ad_group_name": ad_group_name,
                        "campaign_id": campaign_id,
                        "keywords_added": len(operations) - 1,
                    }
                else:
                    error_text = response.text[:500]
                    logger.error("Failed to create ad group: %s %s", response.status_code, error_text)
                    return {"success": False, "error": error_text, "status_code": response.status_code}

        except Exception as e:
            logger.error("Ad group creation error: %s", str(e))
            return {"success": False, "error": str(e)}

    async def set_ad_schedule_bid_modifiers(
        self, campaign_filter: str, schedule: list[dict]
    ) -> dict:
        """Set ad schedule bid modifiers on campaigns matching a name filter.

        First removes existing ad schedule criteria, then creates new ones.

        Args:
            campaign_filter: Substring to match campaign names (e.g. "Nashville").
            schedule: List of dicts with:
                - day_of_week: MONDAY, TUESDAY, ... SUNDAY
                - start_hour: 0-23
                - end_hour: 1-24 (exclusive)
                - bid_modifier: float (1.0 = no change, 0.7 = -30%, 1.5 = +50%)

        Returns dict with success, applied_count.
        """
        if not self.is_configured():
            return {"success": False, "error": "Google Ads not configured"}

        if not schedule:
            return {"success": False, "error": "No schedule entries provided"}

        # Get matching campaigns
        query = f"""
            SELECT campaign.resource_name, campaign.name
            FROM campaign
            WHERE campaign.status = 'ENABLED'
                AND campaign.name LIKE '%{campaign_filter.strip()}%'
        """
        results = await self._execute_query(query)
        if not results:
            return {"success": False, "error": f"No campaigns found matching '{campaign_filter}'"}

        campaigns = [
            r.get("campaign", {}).get("resourceName", "")
            for r in results
            if r.get("campaign", {}).get("resourceName")
        ]

        # Remove existing ad schedule criteria first
        customer_id = self._get_clean_customer_id()
        remove_query = f"""
            SELECT campaign_criterion.resource_name,
                   campaign_criterion.ad_schedule.day_of_week
            FROM campaign_criterion
            WHERE campaign_criterion.type = 'AD_SCHEDULE'
                AND campaign.name LIKE '%{campaign_filter.strip()}%'
                AND campaign.status != 'REMOVED'
        """
        existing = await self._execute_query(remove_query)
        remove_operations = []
        if existing:
            for r in existing:
                rn = r.get("campaignCriterion", {}).get("resourceName")
                if rn:
                    remove_operations.append(
                        {"campaignCriterionOperation": {"remove": rn}}
                    )

        access_token = await self._refresh_access_token()
        if not access_token:
            return {"success": False, "error": "Failed to refresh token"}

        url = f"{GOOGLE_ADS_BASE_URL}/customers/{customer_id}/googleAds:mutate"
        removed_count = 0

        # Execute removals if any
        if remove_operations:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        url,
                        headers=self._get_headers(access_token),
                        json={"mutateOperations": remove_operations},
                    )
                    self._increment_ops()
                    if response.status_code in (200, 201):
                        removed_count = len(response.json().get("mutateOperationResponses", []))
                        logger.info("Removed %d existing ad schedule criteria", removed_count)
                    else:
                        logger.warning("Remove ad schedule failed: %s", response.text[:300])
            except Exception as e:
                logger.warning("Remove ad schedule error (continuing): %s", str(e))

        # Build create operations for new schedule
        create_operations = []
        for entry in schedule:
            day = entry.get("day_of_week", "").upper()
            start_h = entry.get("start_hour", 0)
            end_h = entry.get("end_hour", 24)
            modifier = entry.get("bid_modifier", 1.0)

            if not day or modifier == 1.0:
                continue  # Skip no-change entries

            for campaign_rn in campaigns:
                create_operations.append({
                    "campaignCriterionOperation": {
                        "create": {
                            "campaign": campaign_rn,
                            "bidModifier": modifier,
                            "adSchedule": {
                                "dayOfWeek": day,
                                "startHour": start_h,
                                "endHour": end_h,
                                "startMinute": "ZERO",
                                "endMinute": "ZERO",
                            },
                        }
                    }
                })

        if not create_operations:
            return {
                "success": True,
                "message": "No bid modifier changes needed (all 1.0x)",
                "removed_count": removed_count,
                "applied_count": 0,
            }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(access_token),
                    json={"mutateOperations": create_operations},
                )
                self._increment_ops()

                if response.status_code in (200, 201):
                    result = response.json()
                    applied = len(result.get("mutateOperationResponses", []))
                    return {
                        "success": True,
                        "removed_count": removed_count,
                        "applied_count": applied,
                        "campaigns_affected": len(campaigns),
                        "schedule_entries": len(schedule),
                    }
                else:
                    error_text = response.text[:500]
                    logger.error("Failed to set ad schedule: %s %s", response.status_code, error_text)
                    return {"success": False, "error": error_text, "status_code": response.status_code}

        except Exception as e:
            logger.error("Ad schedule bid modifier error: %s", str(e))
            return {"success": False, "error": str(e)}


# Singleton instance
google_ads_service = GoogleAdsService()


def get_google_ads_service() -> GoogleAdsService:
    """Get the Google Ads service singleton."""
    return google_ads_service
