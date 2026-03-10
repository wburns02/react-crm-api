"""
Nashville Google Ads Automation Service

Handles all Nashville-specific ad automations:
  1. Auto-negative keyword deployment (add negatives to shared list)
  2. Time-of-day bid adjustments (ad schedule modifier recommendations)
  3. Day-of-week bid adjustments
  4. Performance-based keyword pausing
  5. Budget pacing alerts
  6. Daily performance report generation

All mutations use Google Ads REST API v20 via the main GoogleAdsService.
Nashville-only: all queries filter campaign.name LIKE '%Nashville%'.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from app.services.google_ads_service import GoogleAdsService, GOOGLE_ADS_BASE_URL

logger = logging.getLogger(__name__)

# Competitor brands for Nashville market
NASHVILLE_COMPETITOR_BRANDS = [
    "scotts septic", "maxwell septic", "action septic", "tn septic",
    "nashville septic pros", "music city septic", "volunteer septic",
    "cumberland septic", "southern septic", "blue sky septic", "all clear septic",
]

# Irrelevant keyword patterns (no commercial intent)
IRRELEVANT_PATTERNS = [
    "diy", "how to", "youtube", "reddit", "free", "salary", "job",
    "career", "training", "what is", "wiki", "definition", "diagram",
]

# Thresholds
NEGATIVE_KW_COST_THRESHOLD = 5.0  # Flag terms costing > $5 with 0 conversions
KEYWORD_PAUSE_COST_THRESHOLD = 50.0  # Consider pausing after $50 with 0 conversions
KEYWORD_PAUSE_CLICK_MIN = 10  # Need at least 10 clicks before pausing
HOURLY_BID_MIN_IMPRESSIONS = 50  # Need 50+ impressions in an hour to adjust


class NashvilleAutomationService:
    """Nashville-specific Google Ads automation engine."""

    def __init__(self, ads_service: GoogleAdsService):
        self.ads = ads_service

    # ─── 1. AUTO-NEGATIVE KEYWORD DEPLOYMENT ──────────────────────────────

    async def analyze_negative_candidates(self, days: int = 7) -> dict:
        """Analyze search terms and return candidates for negative keywords.

        Returns terms that are:
        - Competitor brand names with spend > threshold
        - Irrelevant patterns with 0 conversions
        - High cost per conversion (>3x average CPA)
        """
        terms = await self.ads.get_nashville_search_terms(days)
        if not terms:
            return {"candidates": [], "summary": {"total_waste": 0, "candidate_count": 0}}

        # Calculate average CPA across all converting terms
        total_cost = sum(t["cost"] for t in terms)
        total_conv = sum(t["conversions"] for t in terms)
        avg_cpa = total_cost / max(1, total_conv)

        candidates = []
        total_waste = 0.0

        for term in terms:
            search_text = (term.get("search_term") or "").lower()
            cost = term.get("cost", 0)
            conversions = term.get("conversions", 0)
            reason = None

            # Check competitor brands
            for brand in NASHVILLE_COMPETITOR_BRANDS:
                if brand in search_text:
                    reason = "competitor"
                    break

            # Check irrelevant patterns
            if not reason:
                for pattern in IRRELEVANT_PATTERNS:
                    if pattern in search_text:
                        reason = "irrelevant"
                        break

            # High cost, zero conversions
            if not reason and cost >= NEGATIVE_KW_COST_THRESHOLD and conversions == 0:
                reason = "high_cost_zero_conv"

            # Extremely high CPA (>3x average)
            if not reason and conversions > 0 and avg_cpa > 0:
                term_cpa = cost / conversions
                if term_cpa > avg_cpa * 3 and cost > 20:
                    reason = "high_cpa"

            if reason:
                total_waste += cost
                candidates.append({
                    "search_term": term["search_term"],
                    "campaign": term.get("campaign", ""),
                    "cost": cost,
                    "clicks": term.get("clicks", 0),
                    "impressions": term.get("impressions", 0),
                    "conversions": conversions,
                    "reason": reason,
                    "recommended_match_type": "PHRASE" if reason == "competitor" else "EXACT",
                })

        candidates.sort(key=lambda c: -c["cost"])

        return {
            "candidates": candidates,
            "summary": {
                "total_waste": round(total_waste, 2),
                "candidate_count": len(candidates),
                "avg_cpa": round(avg_cpa, 2),
                "days_analyzed": days,
            },
        }

    async def apply_negative_keywords(self, keywords: list[dict]) -> dict:
        """Apply negative keywords to Nashville campaigns via Google Ads API.

        Each keyword dict should have:
          - keyword_text: str
          - match_type: "EXACT" | "PHRASE" | "BROAD"
          - campaign_resource: str (optional, applies to all Nashville if not specified)

        Uses campaign-level negative keywords via googleAds:mutate.
        """
        if not self.ads.is_configured():
            return {"success": False, "error": "Google Ads not configured"}

        if not keywords:
            return {"success": False, "error": "No keywords provided"}

        # First, get Nashville campaign resource names
        campaigns = await self._get_nashville_campaign_resources()
        if not campaigns:
            return {"success": False, "error": "No Nashville campaigns found"}

        access_token = await self.ads._refresh_access_token()
        if not access_token:
            return {"success": False, "error": "Failed to refresh token"}

        customer_id = self.ads._get_clean_customer_id()
        url = f"{GOOGLE_ADS_BASE_URL}/customers/{customer_id}/googleAds:mutate"

        operations = []
        for kw in keywords:
            text = kw.get("keyword_text", "").strip()
            match = kw.get("match_type", "EXACT").upper()
            if not text:
                continue

            # Apply to specified campaign or all Nashville campaigns
            target_campaigns = campaigns
            if kw.get("campaign_resource"):
                target_campaigns = [kw["campaign_resource"]]

            for campaign_rn in target_campaigns:
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
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self.ads._get_headers(access_token),
                    json={"mutateOperations": operations},
                )
                self.ads._increment_ops()

                if response.status_code in (200, 201):
                    result = response.json()
                    results_list = result.get("mutateOperationResponses", [])
                    return {
                        "success": True,
                        "applied_count": len(results_list),
                        "keywords": [kw.get("keyword_text") for kw in keywords],
                        "campaigns_affected": len(campaigns),
                    }
                else:
                    error_text = response.text[:500]
                    logger.error("Failed to apply negative keywords: %s %s", response.status_code, error_text)
                    return {"success": False, "error": error_text, "status_code": response.status_code}

        except Exception as e:
            logger.error("Negative keyword application error: %s", str(e))
            return {"success": False, "error": str(e)}

    async def _get_nashville_campaign_resources(self) -> list[str]:
        """Get resource names for all active Nashville campaigns."""
        query = """
            SELECT campaign.resource_name, campaign.name
            FROM campaign
            WHERE campaign.status = 'ENABLED'
                AND campaign.name LIKE '%Nashville%'
        """
        results = await self.ads._execute_query(query)
        if not results:
            return []
        return [r.get("campaign", {}).get("resourceName", "") for r in results if r.get("campaign", {}).get("resourceName")]

    # ─── 2. TIME-OF-DAY BID ADJUSTMENTS ──────────────────────────────────

    async def get_hourly_performance(self, days: int = 30) -> dict:
        """Analyze hourly performance to recommend bid adjustments.

        Looks at conversion rate and cost per conversion by hour of day
        over the last N days to identify peak vs dead hours.
        """
        date_range = self.ads._date_range_clause(days)
        query = f"""
            SELECT
                segments.hour,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions,
                metrics.cost_micros
            FROM campaign
            WHERE segments.date {date_range}
                AND campaign.status = 'ENABLED'
                AND campaign.name LIKE '%Nashville%'
        """
        results = await self.ads._execute_query(query)
        if not results:
            return {"hours": [], "recommendations": []}

        # Aggregate by hour
        hourly = {}
        for row in results:
            hour = int(row.get("segments", {}).get("hour", 0))
            m = row.get("metrics", {})
            if hour not in hourly:
                hourly[hour] = {"hour": hour, "clicks": 0, "impressions": 0, "conversions": 0.0, "cost": 0.0}
            hourly[hour]["clicks"] += int(m.get("clicks", 0))
            hourly[hour]["impressions"] += int(m.get("impressions", 0))
            hourly[hour]["conversions"] += float(m.get("conversions", 0))
            hourly[hour]["cost"] += int(m.get("costMicros", 0)) / 1_000_000

        # Calculate metrics per hour
        hours_data = []
        total_conv = sum(h["conversions"] for h in hourly.values())
        avg_conv_per_hour = total_conv / max(1, len(hourly))

        for h in range(24):
            data = hourly.get(h, {"hour": h, "clicks": 0, "impressions": 0, "conversions": 0.0, "cost": 0.0})
            ctr = data["clicks"] / max(1, data["impressions"])
            conv_rate = data["conversions"] / max(1, data["clicks"]) if data["clicks"] > 0 else 0
            cpa = data["cost"] / data["conversions"] if data["conversions"] > 0 else None

            hours_data.append({
                "hour": h,
                "clicks": data["clicks"],
                "impressions": data["impressions"],
                "conversions": round(data["conversions"], 1),
                "cost": round(data["cost"], 2),
                "ctr": round(ctr, 4),
                "conv_rate": round(conv_rate, 4),
                "cpa": round(cpa, 2) if cpa else None,
            })

        # Generate recommendations
        recommendations = []
        for hd in hours_data:
            if hd["impressions"] < HOURLY_BID_MIN_IMPRESSIONS:
                continue  # Not enough data

            if hd["conversions"] > avg_conv_per_hour * 1.5 and hd["conv_rate"] > 0.05:
                # High-performing hour — increase bids
                modifier = min(round((hd["conversions"] / max(1, avg_conv_per_hour) - 1) * 0.3 + 1, 2), 1.5)
                recommendations.append({
                    "hour": hd["hour"],
                    "action": "increase",
                    "bid_modifier": modifier,
                    "reason": f"{hd['conversions']} conversions at {hd['conv_rate']*100:.1f}% conv rate",
                })
            elif hd["clicks"] > 5 and hd["conversions"] == 0 and hd["cost"] > 20:
                # Wasteful hour — decrease bids
                modifier = max(round(1 - (hd["cost"] / 100), 2), 0.5)
                recommendations.append({
                    "hour": hd["hour"],
                    "action": "decrease",
                    "bid_modifier": modifier,
                    "reason": f"${hd['cost']:.2f} spent, {hd['clicks']} clicks, 0 conversions",
                })

        return {
            "hours": hours_data,
            "recommendations": recommendations,
            "days_analyzed": days,
            "total_conversions": round(total_conv, 1),
        }

    # ─── 3. DAY-OF-WEEK BID ADJUSTMENTS ──────────────────────────────────

    async def get_daily_performance(self, days: int = 90) -> dict:
        """Analyze day-of-week performance to recommend bid adjustments."""
        date_range = self.ads._date_range_clause(days)
        query = f"""
            SELECT
                segments.day_of_week,
                metrics.clicks,
                metrics.impressions,
                metrics.conversions,
                metrics.cost_micros
            FROM campaign
            WHERE segments.date {date_range}
                AND campaign.status = 'ENABLED'
                AND campaign.name LIKE '%Nashville%'
        """
        results = await self.ads._execute_query(query)
        if not results:
            return {"days": [], "recommendations": []}

        # Aggregate by day of week
        daily = {}
        for row in results:
            dow = row.get("segments", {}).get("dayOfWeek", "UNKNOWN")
            m = row.get("metrics", {})
            if dow not in daily:
                daily[dow] = {"day": dow, "clicks": 0, "impressions": 0, "conversions": 0.0, "cost": 0.0}
            daily[dow]["clicks"] += int(m.get("clicks", 0))
            daily[dow]["impressions"] += int(m.get("impressions", 0))
            daily[dow]["conversions"] += float(m.get("conversions", 0))
            daily[dow]["cost"] += int(m.get("costMicros", 0)) / 1_000_000

        # Calculate metrics
        day_order = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
        days_data = []
        total_conv = sum(d["conversions"] for d in daily.values())
        avg_conv_per_day = total_conv / max(1, len(daily))

        for dow in day_order:
            data = daily.get(dow, {"day": dow, "clicks": 0, "impressions": 0, "conversions": 0.0, "cost": 0.0})
            conv_rate = data["conversions"] / max(1, data["clicks"]) if data["clicks"] > 0 else 0
            cpa = data["cost"] / data["conversions"] if data["conversions"] > 0 else None

            days_data.append({
                "day": dow.capitalize(),
                "clicks": data["clicks"],
                "impressions": data["impressions"],
                "conversions": round(data["conversions"], 1),
                "cost": round(data["cost"], 2),
                "conv_rate": round(conv_rate, 4),
                "cpa": round(cpa, 2) if cpa else None,
            })

        # Generate recommendations
        recommendations = []
        for dd in days_data:
            if dd["clicks"] < 5:
                continue

            if dd["conversions"] > avg_conv_per_day * 1.3:
                modifier = min(round((dd["conversions"] / max(1, avg_conv_per_day) - 1) * 0.25 + 1, 2), 1.4)
                recommendations.append({
                    "day": dd["day"],
                    "action": "increase",
                    "bid_modifier": modifier,
                    "reason": f"{dd['conversions']} conversions ({dd['conv_rate']*100:.1f}% rate)",
                })
            elif dd["conversions"] < avg_conv_per_day * 0.5 and dd["cost"] > 20:
                modifier = max(round(0.8 - (0.1 * (1 - dd["conversions"] / max(1, avg_conv_per_day))), 2), 0.5)
                recommendations.append({
                    "day": dd["day"],
                    "action": "decrease",
                    "bid_modifier": modifier,
                    "reason": f"Only {dd['conversions']} conversions, ${dd['cost']:.2f} spent",
                })

        return {
            "days": days_data,
            "recommendations": recommendations,
            "days_analyzed": days,
        }

    # ─── 4. PERFORMANCE-BASED KEYWORD PAUSING ────────────────────────────

    async def get_pause_candidates(self, days: int = 30) -> dict:
        """Identify keywords that should be paused due to poor performance.

        Criteria:
        - $50+ spend with 0 conversions and 10+ clicks
        - CPA > 4x account average with 20+ clicks
        """
        keywords = await self.ads.get_nashville_keywords(days)
        if not keywords:
            return {"candidates": [], "summary": {}}

        total_cost = sum(k["cost"] for k in keywords)
        total_conv = sum(k["conversions"] for k in keywords)
        avg_cpa = total_cost / max(1, total_conv)

        candidates = []
        potential_savings = 0.0

        for kw in keywords:
            cost = kw["cost"]
            clicks = kw["clicks"]
            conversions = kw["conversions"]
            reason = None

            # High spend, zero conversions
            if cost >= KEYWORD_PAUSE_COST_THRESHOLD and clicks >= KEYWORD_PAUSE_CLICK_MIN and conversions == 0:
                reason = "high_cost_zero_conversions"

            # Extremely high CPA
            elif conversions > 0 and avg_cpa > 0:
                kw_cpa = cost / conversions
                if kw_cpa > avg_cpa * 4 and clicks >= 20:
                    reason = "extremely_high_cpa"

            if reason:
                potential_savings += cost
                candidates.append({
                    "keyword": kw["keyword"],
                    "match_type": kw["match_type"],
                    "campaign": kw["campaign"],
                    "ad_group": kw.get("ad_group", ""),
                    "cost": cost,
                    "clicks": clicks,
                    "conversions": conversions,
                    "cpa": round(cost / conversions, 2) if conversions > 0 else None,
                    "reason": reason,
                })

        candidates.sort(key=lambda c: -c["cost"])

        return {
            "candidates": candidates,
            "summary": {
                "candidate_count": len(candidates),
                "potential_savings": round(potential_savings, 2),
                "avg_cpa": round(avg_cpa, 2),
                "days_analyzed": days,
            },
        }

    # ─── 5. BUDGET PACING ─────────────────────────────────────────────────

    async def get_budget_pacing(self) -> dict:
        """Real-time budget pacing analysis for Nashville campaigns."""
        budgets = await self.ads.get_nashville_budgets()
        if not budgets:
            return {"campaigns": [], "summary": {}}

        now = datetime.utcnow() - timedelta(hours=5)  # CST rough offset
        current_hour = now.hour
        hours_remaining = max(1, 24 - current_hour)
        expected_pacing = (current_hour / 24) * 100

        campaigns = []
        total_budget = 0.0
        total_spend = 0.0

        for b in budgets:
            daily = b["daily_budget"]
            spend = b["today_spend"]
            remaining = max(0, daily - spend)
            pacing_pct = b["pacing_pct"]

            # Calculate projected end-of-day spend
            if current_hour > 0:
                hourly_rate = spend / current_hour
                projected_eod = hourly_rate * 24
            else:
                projected_eod = 0

            # Status
            if pacing_pct > 120:
                status = "overspending"
            elif pacing_pct > expected_pacing + 15:
                status = "ahead"
            elif pacing_pct < expected_pacing - 15:
                status = "behind"
            else:
                status = "on_track"

            total_budget += daily
            total_spend += spend

            campaigns.append({
                **b,
                "remaining": round(remaining, 2),
                "projected_eod_spend": round(projected_eod, 2),
                "projected_over_under": round(projected_eod - daily, 2),
                "status": status,
                "hourly_rate": round(hourly_rate, 2) if current_hour > 0 else 0,
                "recommended_hourly": round(remaining / hours_remaining, 2),
            })

        return {
            "campaigns": campaigns,
            "summary": {
                "total_daily_budget": round(total_budget, 2),
                "total_today_spend": round(total_spend, 2),
                "total_remaining": round(max(0, total_budget - total_spend), 2),
                "overall_pacing_pct": round((total_spend / max(0.01, total_budget)) * 100, 1),
                "expected_pacing_pct": round(expected_pacing, 1),
                "current_hour": current_hour,
                "hours_remaining": hours_remaining,
            },
        }

    # ─── 6. DAILY REPORT GENERATION ──────────────────────────────────────

    async def generate_daily_report(self) -> dict:
        """Generate a comprehensive daily performance report for Nashville.

        Combines today's metrics, budget pacing, waste analysis, and
        keyword performance into a single report dict.
        """
        today = await self.ads.get_nashville_today()
        hourly = await self.ads.get_nashville_hourly()
        budgets = await self.ads.get_nashville_budgets()
        search_terms = await self.ads.get_nashville_search_terms(1)
        keywords = await self.ads.get_nashville_keywords(1)

        # Calculate waste from search terms
        waste_terms = []
        total_waste = 0.0
        if search_terms:
            for t in search_terms:
                text = (t.get("search_term") or "").lower()
                is_competitor = any(b in text for b in NASHVILLE_COMPETITOR_BRANDS)
                is_irrelevant = any(p in text for p in IRRELEVANT_PATTERNS)
                if (is_competitor or is_irrelevant) and t.get("cost", 0) > 0:
                    waste_terms.append(t)
                    total_waste += t["cost"]

        # Top performers
        top_keywords = sorted(keywords or [], key=lambda k: -k.get("conversions", 0))[:5]

        # Budget summary
        total_budget = sum(b["daily_budget"] for b in (budgets or []))
        total_spend = sum(b["today_spend"] for b in (budgets or []))

        totals = today.get("totals", {}) if today else {}

        return {
            "report_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "generated_at": datetime.utcnow().isoformat(),
            "performance": {
                "total_spend": totals.get("cost", 0),
                "clicks": totals.get("clicks", 0),
                "impressions": totals.get("impressions", 0),
                "conversions": totals.get("conversions", 0),
                "calls": totals.get("calls", 0),
                "cpa": totals.get("cpa", 0),
                "ctr": totals.get("ctr", 0),
            },
            "budget": {
                "total_daily": round(total_budget, 2),
                "total_spent": round(total_spend, 2),
                "utilization_pct": round((total_spend / max(0.01, total_budget)) * 100, 1),
            },
            "waste_analysis": {
                "total_waste": round(total_waste, 2),
                "waste_terms": waste_terms[:10],
                "waste_pct_of_spend": round((total_waste / max(0.01, total_spend)) * 100, 1),
            },
            "top_keywords": top_keywords,
            "hourly_peak": max(hourly or [{"cost": 0}], key=lambda h: h.get("cost", 0)),
            "campaign_count": len(budgets or []),
            "alerts": self._generate_report_alerts(totals, total_budget, total_spend, total_waste),
        }

    @staticmethod
    def _generate_report_alerts(totals: dict, budget: float, spend: float, waste: float) -> list[str]:
        """Generate alert messages for the daily report."""
        alerts = []
        if budget > 0 and spend > budget * 1.1:
            alerts.append(f"Over budget: ${spend:.2f} spent vs ${budget:.2f} daily budget")
        if budget > 0 and spend < budget * 0.5:
            alerts.append(f"Underspending: Only ${spend:.2f} of ${budget:.2f} budget used")
        if waste > spend * 0.2 and waste > 10:
            alerts.append(f"High waste: ${waste:.2f} ({waste/max(0.01,spend)*100:.0f}% of spend) on flagged terms")
        conv = totals.get("conversions", 0)
        if conv == 0 and spend > 20:
            alerts.append(f"No conversions today despite ${spend:.2f} spend")
        return alerts
