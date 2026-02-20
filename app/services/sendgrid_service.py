"""SendGrid email service for transactional and marketing emails.

Wraps the SendGrid REST API v3 without any external SDK.
Falls back gracefully when SENDGRID_API_KEY is not configured.
"""

import os
import logging
from typing import Optional
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "noreply@macseptic.com")
SENDGRID_FROM_NAME = os.getenv("SENDGRID_FROM_NAME", "MAC Septic")
BASE_URL = "https://api.sendgrid.com/v3"


def is_configured() -> bool:
    """Return True if SENDGRID_API_KEY is set."""
    return bool(SENDGRID_API_KEY)


async def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    html_content: str,
) -> dict:
    """Send a single transactional email via SendGrid.

    Returns {"success": bool, "message_id": str|None, "error": str|None}
    """
    if not is_configured():
        logger.warning("SendGrid not configured — SENDGRID_API_KEY missing")
        return {"success": False, "error": "SendGrid not configured"}

    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "personalizations": [{"to": [{"email": to_email, "name": to_name}]}],
        "from": {"email": SENDGRID_FROM_EMAIL, "name": SENDGRID_FROM_NAME},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_content}],
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/mail/send",
                json=payload,
                headers=headers,
            )
            if resp.status_code == 202:
                return {
                    "success": True,
                    "message_id": resp.headers.get("X-Message-Id"),
                    "error": None,
                }
            logger.warning(f"SendGrid error {resp.status_code}: {resp.text[:200]}")
            return {
                "success": False,
                "message_id": None,
                "error": f"SendGrid HTTP {resp.status_code}",
            }
        except Exception as e:
            logger.warning(f"SendGrid send_email failed: {e}")
            return {"success": False, "message_id": None, "error": str(e)}


async def get_stats(days: int = 7) -> dict:
    """Fetch aggregate email stats from the SendGrid Stats API.

    Returns a dict with 'configured' plus totals (requests, delivered, opens,
    clicks, bounces) or an 'error' key on failure.
    """
    if not is_configured():
        return {"configured": False}

    start_date = (date.today() - timedelta(days=days)).isoformat()
    headers = {"Authorization": f"Bearer {SENDGRID_API_KEY}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{BASE_URL}/stats",
                params={"start_date": start_date, "aggregated_by": "day"},
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                totals: dict[str, int] = {
                    "requests": 0,
                    "delivered": 0,
                    "opens": 0,
                    "clicks": 0,
                    "bounces": 0,
                }
                for day in data:
                    for stat in day.get("stats", []):
                        m = stat.get("metrics", {})
                        for k in totals:
                            totals[k] += m.get(k, 0)
                return {"configured": True, "days": days, **totals}

            return {
                "configured": True,
                "error": f"SendGrid Stats API returned {resp.status_code}",
            }
        except Exception as e:
            logger.warning(f"SendGrid get_stats failed: {e}")
            return {"configured": True, "error": str(e)}
