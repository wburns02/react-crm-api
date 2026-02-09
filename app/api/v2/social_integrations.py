"""
Social Platform Integrations API

Endpoints for managing Yelp and Facebook integrations,
fetching reviews, and responding to reviews.
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import select
import secrets
import logging

from app.api.deps import CurrentUser, DbSession
from app.services.yelp_service import get_yelp_service, YelpService
from app.services.facebook_service import get_facebook_service, FacebookService
from app.models.social_integrations import SocialIntegration, SocialReview
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Response Models
# ============================================================================

class IntegrationStatus(BaseModel):
    """Integration status response."""
    platform: str
    connected: bool
    configured: bool
    business_id: Optional[str] = None
    business_name: Optional[str] = None
    page_id: Optional[str] = None
    page_name: Optional[str] = None
    last_sync: Optional[datetime] = None
    message: str


class ReviewItem(BaseModel):
    """Single review item."""
    id: str
    platform: str
    author: str
    rating: Optional[float] = None
    text: str
    date: datetime
    has_response: bool
    response_text: Optional[str] = None
    sentiment: Optional[str] = None
    review_url: Optional[str] = None


class ReviewsResponse(BaseModel):
    """Reviews list response."""
    success: bool
    reviews: List[ReviewItem]
    total: int
    platform: Optional[str] = None


class ReplyRequest(BaseModel):
    """Request to reply to a review."""
    review_id: str
    reply: str


class YelpSearchResult(BaseModel):
    """Yelp business search result."""
    id: str
    name: str
    rating: Optional[float] = None
    review_count: Optional[int] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None


class YelpSearchResponse(BaseModel):
    """Yelp search response."""
    success: bool
    businesses: List[YelpSearchResult]


# In-memory OAuth state storage (in production, use Redis or database)
_oauth_states: dict = {}


# ============================================================================
# Integration Status Endpoints
# ============================================================================

@router.get("/status")
async def get_integrations_status(
    current_user: CurrentUser,
    db: DbSession,
    yelp: YelpService = Depends(get_yelp_service),
    facebook: FacebookService = Depends(get_facebook_service),
) -> dict:
    """Get status of all social integrations."""
    try:
        # Get stored integrations
        result = await db.execute(
            select(SocialIntegration).where(SocialIntegration.is_active == True)
        )
        integrations = result.scalars().all()

        yelp_integration = next((i for i in integrations if i.platform == "yelp"), None)
        fb_integration = next((i for i in integrations if i.platform == "facebook"), None)

        # Get Yelp status safely
        yelp_status = {"connected": False, "configured": False, "message": "Yelp not configured"}
        try:
            yelp_status = await yelp.get_status()
        except Exception as e:
            logger.warning(f"Error getting Yelp status: {e}")

        # Get Facebook status safely
        fb_status = {"connected": False, "configured": False, "message": "Facebook not configured"}
        try:
            fb_status = await facebook.get_status(
                fb_integration.access_token if fb_integration else None
            )
        except Exception as e:
            logger.warning(f"Error getting Facebook status: {e}")

        return {
            "yelp": {
                **yelp_status,
                "business_id": yelp_integration.business_id if yelp_integration else None,
                "business_name": yelp_integration.business_name if yelp_integration else None,
                "last_sync": yelp_integration.last_sync_at if yelp_integration else None,
            },
            "facebook": {
                **fb_status,
                "page_id": fb_integration.business_id if fb_integration else None,
                "page_name": fb_integration.business_name if fb_integration else None,
                "last_sync": fb_integration.last_sync_at if fb_integration else None,
            },
        }
    except Exception as e:
        logger.warning(f"Error getting integrations status: {e}")
        return {
            "yelp": {"connected": False, "configured": False, "message": "Not configured"},
            "facebook": {"connected": False, "configured": False, "message": "Not configured"},
        }


# ============================================================================
# Yelp Endpoints
# ============================================================================

@router.get("/yelp/status")
async def get_yelp_status(
    current_user: CurrentUser,
    db: DbSession,
    yelp: YelpService = Depends(get_yelp_service),
) -> IntegrationStatus:
    """Get Yelp integration status."""
    status_data = await yelp.get_status()

    # Get stored integration
    result = await db.execute(
        select(SocialIntegration).where(
            SocialIntegration.platform == "yelp",
            SocialIntegration.is_active == True
        )
    )
    integration = result.scalar_one_or_none()

    return IntegrationStatus(
        platform="yelp",
        business_id=integration.business_id if integration else None,
        business_name=integration.business_name if integration else None,
        last_sync=integration.last_sync_at if integration else None,
        **status_data
    )


@router.get("/yelp/search")
async def search_yelp_business(
    current_user: CurrentUser,
    name: str = Query(..., description="Business name"),
    location: str = Query(..., description="City, state or address"),
    yelp: YelpService = Depends(get_yelp_service),
) -> YelpSearchResponse:
    """Search for a business on Yelp."""
    result = await yelp.search_business(name, location)

    if "error" in result:
        return YelpSearchResponse(success=False, businesses=[])

    businesses = []
    for b in result.get("businesses", []):
        loc = b.get("location", {})
        businesses.append(YelpSearchResult(
            id=b.get("id", ""),
            name=b.get("name", ""),
            rating=b.get("rating"),
            review_count=b.get("review_count"),
            address=loc.get("address1"),
            city=loc.get("city"),
            state=loc.get("state"),
        ))

    return YelpSearchResponse(success=True, businesses=businesses)


@router.post("/yelp/connect")
async def connect_yelp_business(
    current_user: CurrentUser,
    db: DbSession,
    business_id: str = Query(..., description="Yelp business ID"),
    yelp: YelpService = Depends(get_yelp_service),
) -> dict:
    """Connect a Yelp business by ID."""

    # Verify business exists
    business = await yelp.get_business(business_id)
    if "error" in business:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not find Yelp business: {business.get('error')}"
        )

    # Create or update integration
    result = await db.execute(
        select(SocialIntegration).where(
            SocialIntegration.platform == "yelp",
            SocialIntegration.is_active == True
        )
    )
    integration = result.scalar_one_or_none()

    if integration:
        integration.business_id = business_id
        integration.business_name = business.get("name")
        integration.updated_at = datetime.utcnow()
    else:
        integration = SocialIntegration(
            platform="yelp",
            business_id=business_id,
            business_name=business.get("name"),
            is_active=True,
        )
        db.add(integration)

    await db.commit()

    logger.info(f"Connected Yelp business: {business.get('name')} ({business_id})")

    return {
        "success": True,
        "business_id": business_id,
        "business_name": business.get("name"),
        "message": f"Connected to {business.get('name')}",
    }


@router.delete("/yelp/disconnect")
async def disconnect_yelp(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Disconnect Yelp integration."""
    result = await db.execute(
        select(SocialIntegration).where(
            SocialIntegration.platform == "yelp",
            SocialIntegration.is_active == True
        )
    )
    integration = result.scalar_one_or_none()

    if integration:
        integration.is_active = False
        await db.commit()

    return {"success": True, "message": "Yelp disconnected"}


@router.get("/yelp/reviews")
async def get_yelp_reviews(
    current_user: CurrentUser,
    db: DbSession,
    yelp: YelpService = Depends(get_yelp_service),
) -> ReviewsResponse:
    """Get reviews from Yelp for connected business."""

    # Get integration
    result = await db.execute(
        select(SocialIntegration).where(
            SocialIntegration.platform == "yelp",
            SocialIntegration.is_active == True
        )
    )
    integration = result.scalar_one_or_none()

    if not integration or not integration.business_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Yelp business connected"
        )

    # Fetch reviews from Yelp
    reviews_data = await yelp.get_reviews(integration.business_id)

    if "error" in reviews_data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=reviews_data["error"]
        )

    # Transform to our format
    reviews = []
    for r in reviews_data.get("reviews", []):
        user_info = r.get("user", {})
        time_created = r.get("time_created", "")

        # Parse date
        try:
            review_date = datetime.fromisoformat(time_created.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            review_date = datetime.utcnow()

        reviews.append(ReviewItem(
            id=r.get("id", ""),
            platform="yelp",
            author=user_info.get("name", "Anonymous"),
            rating=float(r.get("rating", 0)),
            text=r.get("text", ""),
            date=review_date,
            has_response=False,  # Yelp doesn't support responses via API
            review_url=r.get("url"),
        ))

    # Update sync timestamp
    integration.last_sync_at = datetime.utcnow()
    await db.commit()

    return ReviewsResponse(
        success=True,
        reviews=reviews,
        total=len(reviews),
        platform="yelp",
    )


# ============================================================================
# Facebook Endpoints
# ============================================================================

@router.get("/facebook/status")
async def get_facebook_status(
    current_user: CurrentUser,
    db: DbSession,
    facebook: FacebookService = Depends(get_facebook_service),
) -> IntegrationStatus:
    """Get Facebook integration status."""

    # Get stored integration
    result = await db.execute(
        select(SocialIntegration).where(
            SocialIntegration.platform == "facebook",
            SocialIntegration.is_active == True
        )
    )
    integration = result.scalar_one_or_none()

    status_data = await facebook.get_status(
        integration.access_token if integration else None
    )

    return IntegrationStatus(
        platform="facebook",
        page_id=integration.business_id if integration else None,
        page_name=integration.business_name if integration else None,
        last_sync=integration.last_sync_at if integration else None,
        **status_data
    )


@router.get("/facebook/auth-url")
async def get_facebook_auth_url(
    current_user: CurrentUser,
    facebook: FacebookService = Depends(get_facebook_service),
) -> dict:
    """Get Facebook OAuth authorization URL."""

    if not facebook.is_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Facebook App not configured. Set FACEBOOK_APP_ID and FACEBOOK_APP_SECRET."
        )

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)

    # Store state temporarily (in production, use Redis with expiry)
    _oauth_states[state] = {
        "user_id": current_user.id,
        "created_at": datetime.utcnow(),
    }

    auth_url = facebook.get_authorization_url(state)

    return {
        "auth_url": auth_url,
        "state": state,
    }


@router.get("/facebook/callback")
async def facebook_oauth_callback(
    code: str,
    state: str,
    db: DbSession,
    facebook: FacebookService = Depends(get_facebook_service),
) -> RedirectResponse:
    """Handle Facebook OAuth callback."""

    # Validate state
    state_data = _oauth_states.pop(state, None)
    if not state_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter"
        )

    # Check state expiry (15 minutes)
    if datetime.utcnow() - state_data["created_at"] > timedelta(minutes=15):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="State parameter expired"
        )

    # Exchange code for token
    token_response = await facebook.exchange_code_for_token(code)

    if "error" in token_response:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=token_response["error"]
        )

    short_token = token_response.get("access_token")

    # Get long-lived token
    long_token_response = await facebook.get_long_lived_token(short_token)

    if "error" in long_token_response:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=long_token_response["error"]
        )

    long_token = long_token_response.get("access_token")
    expires_in = long_token_response.get("expires_in", 5184000)  # Default 60 days

    # Get user's pages
    pages_response = await facebook.get_user_pages(long_token)

    if "error" in pages_response:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=pages_response["error"]
        )

    pages = pages_response.get("data", [])

    if not pages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Facebook pages found for this account"
        )

    # Use the first page (could add page selection UI later)
    page = pages[0]
    page_token = page.get("access_token")

    # Store integration
    result = await db.execute(
        select(SocialIntegration).where(
            SocialIntegration.platform == "facebook",
            SocialIntegration.is_active == True
        )
    )
    integration = result.scalar_one_or_none()

    if integration:
        integration.business_id = page.get("id")
        integration.business_name = page.get("name")
        integration.access_token = page_token
        integration.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        integration.updated_at = datetime.utcnow()
    else:
        integration = SocialIntegration(
            platform="facebook",
            business_id=page.get("id"),
            business_name=page.get("name"),
            access_token=page_token,
            token_expires_at=datetime.utcnow() + timedelta(seconds=expires_in),
            is_active=True,
        )
        db.add(integration)

    await db.commit()

    logger.info(f"Connected Facebook page: {page.get('name')} ({page.get('id')})")

    # Redirect to integrations page with success
    frontend_url = settings.FRONTEND_URL.rstrip("/")
    return RedirectResponse(
        url=f"{frontend_url}/integrations?facebook=connected",
        status_code=status.HTTP_302_FOUND
    )


@router.delete("/facebook/disconnect")
async def disconnect_facebook(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Disconnect Facebook integration."""
    result = await db.execute(
        select(SocialIntegration).where(
            SocialIntegration.platform == "facebook",
            SocialIntegration.is_active == True
        )
    )
    integration = result.scalar_one_or_none()

    if integration:
        integration.is_active = False
        integration.access_token = None
        await db.commit()

    return {"success": True, "message": "Facebook disconnected"}


@router.get("/facebook/reviews")
async def get_facebook_reviews(
    current_user: CurrentUser,
    db: DbSession,
    facebook: FacebookService = Depends(get_facebook_service),
) -> ReviewsResponse:
    """Get reviews from Facebook for connected page."""

    # Get integration
    result = await db.execute(
        select(SocialIntegration).where(
            SocialIntegration.platform == "facebook",
            SocialIntegration.is_active == True
        )
    )
    integration = result.scalar_one_or_none()

    if not integration or not integration.access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Facebook page connected"
        )

    # Check token expiry
    if integration.is_token_expired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Facebook token expired. Please reconnect."
        )

    # Fetch reviews
    reviews_data = await facebook.get_page_reviews(
        integration.business_id,
        integration.access_token
    )

    if "error" in reviews_data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=reviews_data["error"]
        )

    # Transform to our format
    reviews = []
    for r in reviews_data.get("data", []):
        reviewer = r.get("reviewer", {})
        created_time = r.get("created_time", "")

        # Parse date
        try:
            review_date = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            review_date = datetime.utcnow()

        # Facebook recommendations don't always have ratings
        rating = r.get("rating")
        if rating is None and r.get("recommendation_type") == "positive":
            rating = 5.0
        elif rating is None:
            rating = 1.0

        text = r.get("review_text", "")
        if not text and r.get("recommendation_type"):
            text = f"{'Recommends' if r.get('recommendation_type') == 'positive' else 'Does not recommend'} {integration.business_name}"

        reviews.append(ReviewItem(
            id=r.get("id", ""),
            platform="facebook",
            author=reviewer.get("name", "Anonymous"),
            rating=float(rating),
            text=text,
            date=review_date,
            has_response=False,  # Would need to check comments
            sentiment="positive" if r.get("recommendation_type") == "positive" else "negative",
        ))

    # Update sync timestamp
    integration.last_sync_at = datetime.utcnow()
    await db.commit()

    return ReviewsResponse(
        success=True,
        reviews=reviews,
        total=len(reviews),
        platform="facebook",
    )


@router.post("/facebook/reviews/reply")
async def reply_to_facebook_review(
    current_user: CurrentUser,
    request: ReplyRequest,
    db: DbSession,
    facebook: FacebookService = Depends(get_facebook_service),
) -> dict:
    """Reply to a Facebook review."""

    # Get integration
    result = await db.execute(
        select(SocialIntegration).where(
            SocialIntegration.platform == "facebook",
            SocialIntegration.is_active == True
        )
    )
    integration = result.scalar_one_or_none()

    if not integration or not integration.access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Facebook page connected"
        )

    if integration.is_token_expired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Facebook token expired. Please reconnect."
        )

    # Send reply
    reply_result = await facebook.reply_to_review(
        request.review_id,
        integration.access_token,
        request.reply
    )

    if not reply_result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=reply_result.get("error", "Failed to post reply")
        )

    logger.info(f"Replied to Facebook review {request.review_id}")

    return {
        "success": True,
        "message": "Reply posted successfully",
    }


@router.get("/facebook/insights")
async def get_facebook_insights(
    current_user: CurrentUser,
    db: DbSession,
    facebook: FacebookService = Depends(get_facebook_service),
) -> dict:
    """Get Facebook page insights for marketing dashboard."""

    # Get integration
    result = await db.execute(
        select(SocialIntegration).where(
            SocialIntegration.platform == "facebook",
            SocialIntegration.is_active == True
        )
    )
    integration = result.scalar_one_or_none()

    if not integration or not integration.access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Facebook page connected"
        )

    if integration.is_token_expired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Facebook token expired. Please reconnect."
        )

    insights = await facebook.get_page_insights(
        integration.business_id,
        integration.access_token
    )

    if "error" in insights:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=insights["error"]
        )

    return {
        "success": True,
        "insights": insights.get("data", []),
    }


# ============================================================================
# Combined Reviews Endpoint
# ============================================================================

@router.get("/reviews")
async def get_all_reviews(
    current_user: CurrentUser,
    db: DbSession,
    platform: Optional[str] = Query(None, description="Filter by platform: yelp, facebook"),
    yelp: YelpService = Depends(get_yelp_service),
    facebook: FacebookService = Depends(get_facebook_service),
) -> dict:
    """Get reviews from all connected platforms."""
    try:
        all_reviews = []

        # Get Yelp reviews if connected and requested
        if platform in (None, "yelp"):
            try:
                yelp_response = await get_yelp_reviews(current_user, db, yelp)
                all_reviews.extend(yelp_response.reviews)
            except (HTTPException, Exception) as e:
                logger.warning(f"Could not fetch Yelp reviews: {e}")

        # Get Facebook reviews if connected and requested
        if platform in (None, "facebook"):
            try:
                fb_response = await get_facebook_reviews(current_user, db, facebook)
                all_reviews.extend(fb_response.reviews)
            except (HTTPException, Exception) as e:
                logger.warning(f"Could not fetch Facebook reviews: {e}")

        # Sort by date descending
        all_reviews.sort(key=lambda r: r.date, reverse=True)

        return {
            "success": True,
            "reviews": [r.model_dump() for r in all_reviews],
            "total": len(all_reviews),
        }
    except Exception as e:
        logger.warning(f"Error getting all reviews: {e}")
        return {
            "success": True,
            "reviews": [],
            "total": 0,
        }
