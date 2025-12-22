from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.api.v2.router import api_router
from app.webhooks.twilio import twilio_router
from app.config import settings
from app.database import init_db

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting React CRM API...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Database URL prefix: {settings.DATABASE_URL[:30]}...")
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        logger.warning("App starting without database - some features may not work")
    yield
    # Shutdown
    logger.info("Shutting down React CRM API...")


app = FastAPI(
    title="React CRM API",
    description="API for React CRM - Nationwide Septic Service Management",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative dev port
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router, prefix="/api/v2")
app.include_router(twilio_router, prefix="/webhooks/twilio", tags=["webhooks"])


@app.get("/")
async def root():
    """Root endpoint - API info."""
    return {
        "name": "React CRM API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "environment": settings.ENVIRONMENT,
    }


# For running with uvicorn directly
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=5001,
        reload=settings.DEBUG,
    )
