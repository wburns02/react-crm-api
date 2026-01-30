"""
Database Configuration

SECURITY:
- SQLAlchemy echo disabled in production to prevent credential leakage
- Connection string never logged
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


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
    """Dependency to get database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
