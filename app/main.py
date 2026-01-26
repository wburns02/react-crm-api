"""
React CRM API - Main Application

SECURITY FEATURES:
- Conditional API docs (disabled in production by default)
- Structured logging without sensitive data
- Production-hardened configuration
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import traceback

from app.api.v2.router import api_router
from app.api.public.router import public_router
from app.webhooks.twilio import twilio_router
from app.config import settings
from app.database import init_db
from app.api.v2.ringcentral import start_auto_sync, stop_auto_sync
# Import all models to register them with SQLAlchemy metadata before init_db()
from app.models import (
    # Core models
    Customer, WorkOrder, Message, User, Technician,
    Invoice, Payment, Quote, SMSConsent, SMSConsentAudit, Activity,
    Ticket, Equipment, InventoryItem,
    # Phase 1: AI
    AIEmbedding, AIConversation, AIMessage,
    # Phase 2: RingCentral
    CallLog,
    # Phase 3: E-Signatures
    SignatureRequest, Signature, SignedDocument,
    # Phase 4: Pricing
    ServiceCatalog, PricingZone, PricingRule, CustomerPricingTier,
    # Phase 5: AI Agents
    AIAgent, AgentConversation, AgentMessage, AgentTask,
    # Phase 6: Predictions
    LeadScore, ChurnPrediction, RevenueForecast, DealHealth, PredictionModel,
    # Phase 7: Marketing
    MarketingCampaign, MarketingWorkflow, WorkflowEnrollment, EmailTemplate, SMSTemplate,
    # Phase 10: Payroll
    PayrollPeriod, TimeEntry, Commission, TechnicianPayRate,
)
# OAuth models for public API
from app.models.oauth import APIClient, APIToken

# Configure secure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to trust X-Forwarded-* headers from reverse proxies like Railway.

    This fixes the issue where FastAPI's trailing slash redirect (307) generates
    HTTP URLs instead of HTTPS when behind a reverse proxy.
    """

    async def dispatch(self, request: Request, call_next):
        # Trust X-Forwarded-Proto header from Railway's edge proxy
        forwarded_proto = request.headers.get("x-forwarded-proto")
        if forwarded_proto:
            # Update the scope to reflect the actual client protocol
            request.scope["scheme"] = forwarded_proto
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting React CRM API...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    # SECURITY: Don't log full database URL, just prefix
    if settings.DATABASE_URL:
        logger.info(f"Database URL prefix: {settings.DATABASE_URL[:30]}...")
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        # SECURITY: Don't log full exception details which may contain credentials
        logger.error(f"Database initialization failed: {type(e).__name__}")
        logger.warning("App starting without database - some features may not work")

    # Start RingCentral auto-sync background task
    try:
        start_auto_sync()
        logger.info("RingCentral auto-sync started")
    except Exception as e:
        logger.warning(f"Failed to start RingCentral auto-sync: {e}")

    yield

    # Shutdown
    logger.info("Shutting down React CRM API...")
    stop_auto_sync()


# SECURITY: Conditionally enable docs based on settings
docs_url = "/docs" if settings.DOCS_ENABLED else None
redoc_url = "/redoc" if settings.DOCS_ENABLED else None

app = FastAPI(
    title="React CRM API",
    description="API for React CRM - Nationwide Septic Service Management. Includes Public API with OAuth2 authentication.",
    version="2.4.0",  # Added demo mode role switching
    docs_url=docs_url,
    redoc_url=redoc_url,
    lifespan=lifespan,
)

# Proxy headers middleware (must be added before CORS)
# This ensures redirects use HTTPS when behind Railway's edge proxy
app.add_middleware(ProxyHeadersMiddleware)

# CORS middleware
# SECURITY: Restrict origins to known frontend URLs
allowed_origins = [
    settings.FRONTEND_URL,
    "https://react.ecbtx.com",  # Production ReactCRM frontend
]

# Allow localhost origins for development/testing
# These are safe to include since they can only be accessed locally
allowed_origins.extend([
    "http://localhost:5173",  # Vite dev server
    "http://localhost:5174",  # Vite dev server (alternate port)
    "http://localhost:5175",  # Vite dev server (alternate port)
    "http://localhost:3000",  # Alternative dev port
])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router, prefix="/api/v2")
app.include_router(public_router, prefix="/api/public/v1", tags=["Public API"])
app.include_router(twilio_router, prefix="/webhooks/twilio", tags=["webhooks"])


@app.get("/")
async def root():
    """Root endpoint - API info."""
    response = {
        "name": "React CRM API",
        "version": "2.1.0",
        "health": "/health",
        "api_v2": "/api/v2",
        "public_api": "/api/public/v1",
    }
    # Only include docs link if enabled
    if settings.DOCS_ENABLED:
        response["docs"] = "/docs"
    return response


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "2.6.1",  # Added database diagnostic endpoint
        "environment": settings.ENVIRONMENT,
        "features": ["public_api", "oauth2", "demo_roles", "cs_platform", "journey_status", "technician_performance", "call_intelligence"],
    }


@app.get("/health/db")
async def database_health_check():
    """Database connectivity and schema check endpoint."""
    from sqlalchemy import text
    from app.database import async_session_maker

    checks = {
        "database_connected": False,
        "api_users_table_exists": False,
        "api_users_columns": [],
        "errors": []
    }

    try:
        async with async_session_maker() as session:
            # Test connection
            result = await session.execute(text("SELECT 1"))
            checks["database_connected"] = True

            # Check if api_users table exists
            result = await session.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_name = 'api_users'
            """))
            if result.scalar_one_or_none():
                checks["api_users_table_exists"] = True

                # Get columns
                result = await session.execute(text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'api_users'
                    ORDER BY ordinal_position
                """))
                checks["api_users_columns"] = [row[0] for row in result.fetchall()]
            else:
                checks["errors"].append("api_users table does not exist")

    except Exception as e:
        checks["errors"].append(f"{type(e).__name__}: {str(e)}")

    return checks


@app.post("/health/db/fix")
async def fix_database_schema():
    """Create missing api_users table and seed initial admin user."""
    from sqlalchemy import text
    from app.database import async_session_maker
    from app.api.deps import get_password_hash

    results = {
        "table_created": False,
        "user_created": False,
        "errors": []
    }

    try:
        async with async_session_maker() as session:
            # Check if table exists
            result = await session.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_name = 'api_users'
            """))
            table_exists = result.scalar_one_or_none()

            if not table_exists:
                # Create api_users table
                await session.execute(text("""
                    CREATE TABLE api_users (
                        id SERIAL PRIMARY KEY,
                        email VARCHAR(255) NOT NULL UNIQUE,
                        hashed_password VARCHAR(255) NOT NULL,
                        first_name VARCHAR(100),
                        last_name VARCHAR(100),
                        is_active BOOLEAN DEFAULT TRUE,
                        is_superuser BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE
                    )
                """))
                await session.execute(text("""
                    CREATE INDEX ix_api_users_email ON api_users(email)
                """))
                await session.commit()
                results["table_created"] = True
            else:
                results["table_created"] = "already_exists"

            # Check for admin user
            result = await session.execute(text("""
                SELECT id FROM api_users WHERE email = 'will@macseptic.com'
            """))
            user_exists = result.scalar_one_or_none()

            if not user_exists:
                # Create admin user with hashed password
                hashed = get_password_hash("#Espn2025")
                await session.execute(text("""
                    INSERT INTO api_users (email, hashed_password, first_name, last_name, is_active, is_superuser)
                    VALUES (:email, :hashed_password, :first_name, :last_name, :is_active, :is_superuser)
                """), {
                    "email": "will@macseptic.com",
                    "hashed_password": hashed,
                    "first_name": "Will",
                    "last_name": "Burns",
                    "is_active": True,
                    "is_superuser": True
                })
                await session.commit()
                results["user_created"] = True
            else:
                results["user_created"] = "already_exists"

    except Exception as e:
        results["errors"].append(f"{type(e).__name__}: {str(e)}")

    return results


# For running with uvicorn directly (development only)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=5001,
        reload=settings.DEBUG,
    )


# Global exception handler to ensure CORS headers on 500 errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions with proper CORS headers."""
    logger.error(f"Unhandled exception: {type(exc).__name__}: {str(exc)}")
    # Always log traceback for debugging production issues
    logger.error(traceback.format_exc())

    origin = request.headers.get("origin", "")

    # Preserve HTTPException details instead of masking them
    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        detail = exc.detail
    else:
        status_code = 500
        detail = "Internal server error"

    response = JSONResponse(
        status_code=status_code,
        content={"detail": detail},
    )

    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"

    return response
