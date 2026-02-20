"""
Integration Status Endpoint
Returns which third-party integrations are configured via environment variables.
Used by the frontend to show "Not configured" badges and disable broken features.
"""

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.config import get_settings
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


class IntegrationStatus(BaseModel):
    configured: bool
    detail: Optional[str] = None


class IntegrationStatusResponse(BaseModel):
    clover: IntegrationStatus
    quickbooks: IntegrationStatus
    google_ads: IntegrationStatus
    twilio: IntegrationStatus
    samsara: IntegrationStatus
    sendgrid: IntegrationStatus
    stripe: IntegrationStatus


@router.get("/status", response_model=IntegrationStatusResponse)
async def get_integration_status(current_user=Depends(get_current_user)):
    """
    Returns which integrations are configured (env vars present).
    Does not test live connectivity — only checks that required credentials exist.
    """
    settings = get_settings()

    # Clover: needs MERCHANT_ID + API_KEY (REST) OR OAuth credentials
    clover_configured = bool(
        (settings.CLOVER_MERCHANT_ID and settings.CLOVER_API_KEY)
        or (settings.CLOVER_CLIENT_ID and settings.CLOVER_CLIENT_SECRET)
    )

    # QuickBooks: needs CLIENT_ID + CLIENT_SECRET (OAuth flow)
    qbo_client_id = getattr(settings, "QBO_CLIENT_ID", None)
    qbo_client_secret = getattr(settings, "QBO_CLIENT_SECRET", None)
    qbo_configured = bool(qbo_client_id and qbo_client_secret)

    # Google Ads: needs DEVELOPER_TOKEN + CLIENT_ID + REFRESH_TOKEN
    google_ads_configured = bool(
        settings.GOOGLE_ADS_DEVELOPER_TOKEN
        and settings.GOOGLE_ADS_CLIENT_ID
        and settings.GOOGLE_ADS_REFRESH_TOKEN
        and settings.GOOGLE_ADS_CUSTOMER_ID
    )

    # Twilio: needs ACCOUNT_SID + AUTH_TOKEN + phone number
    twilio_configured = bool(
        settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_AUTH_TOKEN
        and (settings.TWILIO_PHONE_NUMBER or settings.TWILIO_SMS_FROM_NUMBER)
    )

    # Samsara: needs API token
    samsara_configured = bool(settings.SAMSARA_API_TOKEN)

    # SendGrid: needs API key
    sendgrid_configured = bool(settings.SENDGRID_API_KEY)

    # Stripe: needs secret key
    stripe_configured = bool(settings.STRIPE_SECRET_KEY)

    return IntegrationStatusResponse(
        clover=IntegrationStatus(
            configured=clover_configured,
            detail=None if clover_configured else "Set CLOVER_MERCHANT_ID + CLOVER_API_KEY on Railway",
        ),
        quickbooks=IntegrationStatus(
            configured=qbo_configured,
            detail=None if qbo_configured else "Set QBO_CLIENT_ID + QBO_CLIENT_SECRET on Railway",
        ),
        google_ads=IntegrationStatus(
            configured=google_ads_configured,
            detail=None if google_ads_configured else "Set GOOGLE_ADS_DEVELOPER_TOKEN + CLIENT_ID + REFRESH_TOKEN + CUSTOMER_ID on Railway",
        ),
        twilio=IntegrationStatus(
            configured=twilio_configured,
            detail=None if twilio_configured else "Set TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN + TWILIO_PHONE_NUMBER on Railway",
        ),
        samsara=IntegrationStatus(
            configured=samsara_configured,
            detail=None if samsara_configured else "Set SAMSARA_API_TOKEN on Railway",
        ),
        sendgrid=IntegrationStatus(
            configured=sendgrid_configured,
            detail=None if sendgrid_configured else "Set SENDGRID_API_KEY on Railway",
        ),
        stripe=IntegrationStatus(
            configured=stripe_configured,
            detail=None if stripe_configured else "Set STRIPE_SECRET_KEY on Railway",
        ),
    )
