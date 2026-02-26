"""
Daily Marketing Report Generator

Runs at 7 AM daily via APScheduler.
Pulls Google Ads + GA4 data, computes deltas, flags anomalies.
Saves to marketing_daily_reports table.
"""

import asyncio
import logging
from datetime import datetime, date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database import async_session_maker
from app.models.marketing import MarketingDailyReport
from app.services.google_ads_service import get_google_ads_service
from app.services.ga4_service import get_ga4_service

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

# Anomaly thresholds
CPA_SPIKE_THRESHOLD = 0.50  # 50% increase
SPEND_OVER_BUDGET_THRESHOLD = 0.20  # 20% over daily budget


async def generate_daily_report():
    """Generate and save the daily marketing report."""
    logger.info("Starting daily marketing report generation...")
    today = date.today()

    try:
        ads_service = get_google_ads_service()
        ga4_service = get_ga4_service()

        # Get today (yesterday's full data) and previous day
        ads_today = None
        ads_prev = None
        ga4_today = None

        if ads_service.is_configured():
            try:
                ads_today = await ads_service.get_performance_metrics(1)  # yesterday
                ads_prev = await ads_service.get_performance_metrics(2)  # 2 days
            except Exception as e:
                logger.warning("Failed to fetch ads data for report: %s", e)

        if ga4_service.is_configured():
            try:
                ga4_today = await ga4_service.get_traffic_summary(1)
            except Exception as e:
                logger.warning("Failed to fetch GA4 data for report: %s", e)

        # Calculate deltas
        deltas = {}
        if ads_today and ads_prev:
            # Previous-only = 2-day total minus today
            for key in ["cost", "clicks", "impressions", "conversions", "ctr", "cpa"]:
                curr = ads_today.get(key, 0) or 0
                prev_total = ads_prev.get(key, 0) or 0
                prev = max(0, prev_total - curr)
                if prev > 0:
                    pct = round(((curr - prev) / prev) * 100, 1)
                else:
                    pct = 0
                deltas[key] = {"current": curr, "previous": round(prev, 2), "change_percent": pct}

        # Flag anomalies
        alerts = []
        if ads_today:
            cpa = ads_today.get("cpa", 0) or 0
            cost = ads_today.get("cost", 0) or 0

            # CPA spike detection
            if deltas.get("cpa") and deltas["cpa"]["previous"] > 0:
                cpa_change = deltas["cpa"]["change_percent"]
                if cpa_change > CPA_SPIKE_THRESHOLD * 100:
                    alerts.append({
                        "type": "cpa_spike",
                        "severity": "high",
                        "message": f"CPA spiked {cpa_change}% — ${cpa:.2f} vs ${deltas['cpa']['previous']:.2f} yesterday",
                        "metric": "cpa",
                        "value": cpa,
                    })

            # Daily spend over budget (assume $100/day budget as default)
            daily_budget = 100
            if cost > daily_budget * (1 + SPEND_OVER_BUDGET_THRESHOLD):
                alerts.append({
                    "type": "overspend",
                    "severity": "medium",
                    "message": f"Daily spend ${cost:.2f} exceeds budget target ${daily_budget:.2f} by {((cost / daily_budget - 1) * 100):.0f}%",
                    "metric": "cost",
                    "value": cost,
                })

            # Zero conversions warning
            conversions = ads_today.get("conversions", 0) or 0
            clicks = ads_today.get("clicks", 0) or 0
            if clicks > 20 and conversions == 0:
                alerts.append({
                    "type": "zero_conversions",
                    "severity": "high",
                    "message": f"{clicks} clicks but 0 conversions yesterday — check landing pages",
                    "metric": "conversions",
                    "value": 0,
                })

        # Build summary
        summary_parts = []
        if ads_today:
            summary_parts.append(
                f"Ads: ${ads_today.get('cost', 0):.2f} spent, "
                f"{ads_today.get('clicks', 0)} clicks, "
                f"{ads_today.get('conversions', 0):.0f} conversions"
            )
        if ga4_today and ga4_today.get("totals"):
            t = ga4_today["totals"]
            summary_parts.append(
                f"Traffic: {t.get('sessions', 0)} sessions, "
                f"{t.get('users', 0)} users"
            )
        if alerts:
            summary_parts.append(f"{len(alerts)} alert(s) flagged")

        summary = " | ".join(summary_parts) if summary_parts else "No data available"

        # Save to database
        async with async_session_maker() as db:
            # Upsert (delete existing for today, then insert)
            from sqlalchemy import select, delete
            await db.execute(
                delete(MarketingDailyReport).where(MarketingDailyReport.report_date == today)
            )

            import uuid
            report = MarketingDailyReport(
                id=uuid.uuid4(),
                report_date=today,
                ads_data=ads_today,
                ga4_data=ga4_today,
                deltas=deltas,
                alerts=alerts,
                summary=summary,
                email_sent=False,
            )
            db.add(report)
            await db.commit()

        logger.info("Daily marketing report saved for %s — %d alerts", today, len(alerts))

        # Optional: send email via SendGrid
        if alerts:
            try:
                await _send_alert_email(summary, alerts)
            except Exception as e:
                logger.warning("Failed to send marketing alert email: %s", e)

    except Exception as e:
        logger.error("Daily marketing report generation failed: %s", e)


async def _send_alert_email(summary: str, alerts: list):
    """Send alert email via SendGrid if configured."""
    from app.config import settings as app_settings
    sendgrid_key = getattr(app_settings, "SENDGRID_API_KEY", None)
    if not sendgrid_key:
        return

    try:
        from app.services.sendgrid_service import get_sendgrid_service
        sg = get_sendgrid_service()
        if not sg:
            return

        alert_html = "<ul>"
        for a in alerts:
            severity_color = {"high": "#dc2626", "medium": "#f59e0b", "low": "#3b82f6"}.get(a["severity"], "#6b7280")
            alert_html += f'<li><span style="color:{severity_color};font-weight:bold">[{a["severity"].upper()}]</span> {a["message"]}</li>'
        alert_html += "</ul>"

        await sg.send_email(
            to_email=getattr(app_settings, "ADMIN_EMAIL", "will@macseptic.com"),
            subject=f"Marketing Alert: {len(alerts)} issue(s) detected",
            html_content=f"<h2>Daily Marketing Report</h2><p>{summary}</p><h3>Alerts</h3>{alert_html}",
        )
    except Exception as e:
        logger.warning("SendGrid marketing email failed: %s", e)


def start_marketing_report_scheduler():
    """Start the daily marketing report scheduler (7 AM)."""
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        generate_daily_report,
        "cron",
        hour=7,
        minute=0,
        id="marketing_daily_report",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Marketing report scheduler started (daily at 7:00 AM)")


def stop_marketing_report_scheduler():
    """Stop the marketing report scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Marketing report scheduler stopped")
