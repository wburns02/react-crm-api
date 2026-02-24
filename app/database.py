"""
Database Configuration

SECURITY:
- SQLAlchemy echo disabled in production to prevent credential leakage
- Connection string never logged
"""

import logging
import time

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

logger = logging.getLogger(__name__)

SLOW_QUERY_THRESHOLD_MS = 500


# Create async engine
# SECURITY: Use sqlalchemy_echo property which is disabled in production
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.sqlalchemy_echo,  # Disabled in production
    future=True,
    # Connection pool settings for production stability
    pool_size=20,           # Base pool connections (default is 5)
    max_overflow=10,        # Additional connections for peak load (total max: 30)
    pool_recycle=3600,      # Recycle connections after 1 hour to prevent stale connections
    pool_pre_ping=True,     # Test connection validity before use
)

# Slow query logging
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info["query_start_time"] = time.monotonic()


def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    start = conn.info.get("query_start_time")
    if start is None:
        return
    duration_ms = (time.monotonic() - start) * 1000
    if duration_ms >= SLOW_QUERY_THRESHOLD_MS:
        param_count = len(parameters) if parameters else 0
        truncated = statement[:200] + ("..." if len(statement) > 200 else "")
        logger.warning(
            "Slow query (%.0fms, %d params): %s", duration_ms, param_count, truncated
        )


event.listen(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
event.listen(engine.sync_engine, "after_cursor_execute", _after_cursor_execute)
logger.info("Slow query logging enabled (threshold: %dms)", SLOW_QUERY_THRESHOLD_MS)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


async def get_db() -> AsyncSession:
    """Dependency to get database session.

    Note: Endpoints are responsible for calling commit() when needed.
    This dependency only provides the session and handles cleanup.
    """
    session = async_session_maker()
    try:
        yield session
    finally:
        await session.close()


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
