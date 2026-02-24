"""
Microsoft 365 Integration API

SSO login, account linking, and integration status.
"""

from fastapi import APIRouter, HTTPException, status, Response, Depends
from sqlalchemy import select
from datetime import timedelta
import logging

from app.api.deps import DbSession, CurrentUser, create_access_token
from app.config import settings
from app.models.user import User
from app.services.microsoft365_service import Microsoft365Service
from app.services.ms365_base import MS365BaseService
from app.services.activity_tracker import log_activity

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/auth-url")
async def get_auth_url():
    """Get Microsoft OAuth authorization URL for SSO."""
    if not MS365BaseService.is_configured():
        raise HTTPException(status_code=503, detail="Microsoft 365 not configured")
    url = Microsoft365Service.get_auth_url(state="sso")
    return {"authorization_url": url}


@router.post("/callback")
async def sso_callback(
    response: Response,
    db: DbSession,
    code: str | None = None,
):
    """Handle Microsoft SSO callback — exchange code, find/match user, issue session cookie."""
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    if not MS365BaseService.is_configured():
        raise HTTPException(status_code=503, detail="Microsoft 365 not configured")

    try:
        # Exchange code for tokens
        token_data = await Microsoft365Service.exchange_code(code)
        ms_access_token = token_data["access_token"]

        # Get user profile from Microsoft
        profile = await Microsoft365Service.get_user_profile(ms_access_token)
        ms_id = profile.get("id")
        ms_email = profile.get("mail") or profile.get("userPrincipalName", "").lower()
        ms_name = profile.get("displayName", "")

        logger.info("Microsoft SSO: user=%s email=%s", ms_name, ms_email)

        # Try to find user by microsoft_id first, then by email
        result = await db.execute(
            select(User).where(User.microsoft_id == ms_id)
        )
        user = result.scalar_one_or_none()

        if not user and ms_email:
            result = await db.execute(
                select(User).where(User.email == ms_email.lower())
            )
            user = result.scalar_one_or_none()
            # Link the Microsoft ID on first SSO match
            if user:
                user.microsoft_id = ms_id
                user.microsoft_email = ms_email
                await db.commit()

        if not user:
            raise HTTPException(
                status_code=403,
                detail="No CRM account found for this Microsoft account. Contact your administrator.",
            )

        if not user.is_active:
            raise HTTPException(status_code=403, detail="User account is disabled")

        # Issue CRM session cookie (same as auth.py login)
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email},
            expires_delta=access_token_expires,
        )

        response.set_cookie(
            key="session",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )

        # Log the SSO login
        import asyncio
        asyncio.create_task(log_activity(
            category="auth",
            action="login_sso_microsoft",
            description=f"Microsoft SSO login for {user.email}",
            user_id=user.id,
            user_email=user.email,
            user_name=f"{user.first_name or ''} {user.last_name or ''}".strip(),
        ))

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "microsoft_linked": True,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Microsoft SSO error: %s", e)
        raise HTTPException(status_code=500, detail="Microsoft SSO failed")


@router.post("/link")
async def link_microsoft_account(
    db: DbSession,
    user: CurrentUser,
    code: str | None = None,
):
    """Link current CRM user to a Microsoft account via OAuth code."""
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    if not MS365BaseService.is_configured():
        raise HTTPException(status_code=503, detail="Microsoft 365 not configured")

    try:
        token_data = await Microsoft365Service.exchange_code(code)
        profile = await Microsoft365Service.get_user_profile(token_data["access_token"])

        ms_id = profile.get("id")
        ms_email = profile.get("mail") or profile.get("userPrincipalName", "")

        # Check if this MS account is already linked to another user
        result = await db.execute(
            select(User).where(User.microsoft_id == ms_id)
        )
        existing = result.scalar_one_or_none()
        if existing and existing.id != user.id:
            raise HTTPException(status_code=409, detail="This Microsoft account is linked to another user")

        user.microsoft_id = ms_id
        user.microsoft_email = ms_email
        await db.commit()

        return {"linked": True, "microsoft_email": ms_email}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Microsoft link error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to link Microsoft account")


@router.delete("/link")
async def unlink_microsoft_account(db: DbSession, user: CurrentUser):
    """Unlink Microsoft account from current CRM user."""
    user.microsoft_id = None
    user.microsoft_email = None
    await db.commit()
    return {"linked": False}


@router.get("/status")
async def get_microsoft_status(user: CurrentUser):
    """Get Microsoft 365 integration status for current user."""
    from app.services.teams_webhook_service import TeamsWebhookService
    from app.services.ms365_sharepoint_service import MS365SharePointService
    from app.services.ms365_email_service import MS365EmailService

    return {
        "configured": MS365BaseService.is_configured(),
        "user_linked": bool(user.microsoft_id),
        "microsoft_email": user.microsoft_email,
        "calendar_sync": MS365BaseService.is_configured(),
        "teams_webhook": TeamsWebhookService.is_configured(),
        "sharepoint": MS365SharePointService.is_configured(),
        "email_monitoring": MS365EmailService.is_configured(),
    }


# ── Session 3: Teams Webhooks ──

@router.post("/teams/test")
async def test_teams_webhook(user: CurrentUser):
    """Send a test message to Teams channel."""
    from app.services.teams_webhook_service import TeamsWebhookService

    if not TeamsWebhookService.is_configured():
        raise HTTPException(status_code=503, detail="Teams webhook URL not configured")

    success = await TeamsWebhookService.send_notification(
        title="Test from Mac Service Platform",
        body=f"This is a test notification sent by {user.email}.",
        color="0078d4",
        facts=[{"name": "Sent by", "value": user.email}],
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send Teams notification")

    return {"sent": True}


# ── Session 4: SharePoint ──

@router.get("/sharepoint/status")
async def sharepoint_status(user: CurrentUser):
    """Get SharePoint integration status."""
    from app.services.ms365_sharepoint_service import MS365SharePointService
    return {
        "configured": MS365SharePointService.is_configured(),
        "site_id": settings.MS365_SHAREPOINT_SITE_ID or None,
        "drive_id": settings.MS365_SHAREPOINT_DRIVE_ID or None,
    }


@router.get("/sharepoint/customer/{customer_id}/files")
async def list_customer_files(customer_id: str, db: DbSession, user: CurrentUser):
    """List files in a customer's SharePoint folder."""
    from app.services.ms365_sharepoint_service import MS365SharePointService
    from app.models.customer import Customer

    if not MS365SharePointService.is_configured():
        raise HTTPException(status_code=503, detail="SharePoint not configured")

    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
    folder = MS365SharePointService.build_customer_folder(name, str(customer.id))
    files = await MS365SharePointService.list_folder_contents(folder)
    return {"files": files, "folder": folder}


# ── Session 5: Email Monitoring ──

@router.get("/email/status")
async def email_status(user: CurrentUser):
    """Get email monitoring status."""
    from app.services.ms365_email_service import MS365EmailService
    return {
        "configured": MS365EmailService.is_configured(),
        "monitored_mailbox": settings.MS365_MONITORED_MAILBOX,
    }


@router.get("/email/log")
async def email_log(db: DbSession, user: CurrentUser, limit: int = 50):
    """Get recent inbound emails."""
    from app.models.inbound_email import InboundEmail

    result = await db.execute(
        select(InboundEmail)
        .order_by(InboundEmail.received_at.desc())
        .limit(limit)
    )
    emails = result.scalars().all()
    return {
        "emails": [
            {
                "id": str(e.id),
                "sender_email": e.sender_email,
                "sender_name": e.sender_name,
                "subject": e.subject,
                "body_preview": e.body_preview,
                "received_at": e.received_at.isoformat() if e.received_at else None,
                "customer_id": str(e.customer_id) if e.customer_id else None,
                "action_taken": e.action_taken,
            }
            for e in emails
        ],
        "total": len(emails),
    }


@router.post("/email/poll-now")
async def poll_now(user: CurrentUser):
    """Trigger immediate email poll."""
    from app.tasks.email_poller import poll_inbound_emails
    import asyncio

    asyncio.create_task(poll_inbound_emails())
    return {"triggered": True}
