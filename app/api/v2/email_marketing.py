"""
Email Marketing API - Stub endpoints for frontend compatibility.

Provides email marketing status and basic campaign endpoints.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime

from app.api.deps import CurrentUser

router = APIRouter()


class EmailMarketingStatus(BaseModel):
    connected: bool
    provider: str | None
    email_quota: int
    emails_sent_today: int
    contacts_count: int
    lists_count: int


@router.get("/status")
async def get_email_marketing_status(current_user: CurrentUser) -> EmailMarketingStatus:
    """
    Get email marketing integration status.
    Returns disconnected status if not configured.
    """
    return EmailMarketingStatus(
        connected=False,
        provider=None,
        email_quota=0,
        emails_sent_today=0,
        contacts_count=0,
        lists_count=0,
    )
