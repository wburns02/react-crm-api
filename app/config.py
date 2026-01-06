"""
Application Configuration

Security-hardened settings with production validation.
"""

from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from functools import lru_cache
import secrets
import logging

logger = logging.getLogger(__name__)

# List of known weak/default secret keys that must be rejected in production
WEAK_SECRET_KEYS = {
    "development-secret-key-change-in-production",
    "secret",
    "changeme",
    "your-secret-key",
    "supersecret",
    "dev-secret",
    "test-secret",
}


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://localhost:5432/react_crm"

    @field_validator('DATABASE_URL', mode='before')
    @classmethod
    def convert_database_url(cls, v: str) -> str:
        """Convert postgresql:// to postgresql+asyncpg:// for async support."""
        if v and v.startswith('postgresql://'):
            return v.replace('postgresql://', 'postgresql+asyncpg://', 1)
        return v

    LEGACY_DATABASE_URL: str | None = None

    # Auth - SECURITY: Must be set via environment in production
    SECRET_KEY: str = "development-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS
    FRONTEND_URL: str = "http://localhost:5173"

    # Twilio
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_PHONE_NUMBER: str | None = None
    TWILIO_SMS_FROM_NUMBER: str | None = None
    TWILIO_API_KEY_SID: str | None = None
    TWILIO_API_KEY_SECRET: str | None = None
    TWILIO_TWIML_APP_SID: str | None = None

    # RingCentral
    RINGCENTRAL_CLIENT_ID: str | None = None
    RINGCENTRAL_CLIENT_SECRET: str | None = None
    RINGCENTRAL_SERVER_URL: str = "https://platform.ringcentral.com"
    RINGCENTRAL_JWT_TOKEN: str | None = None

    # Samsara Fleet Tracking
    SAMSARA_API_TOKEN: str | None = None

    # AI Services
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None

    # Local AI Server (for vLLM on RTX 5090)
    AI_SERVER_URL: str = "http://localhost:8000"
    AI_SERVER_API_KEY: str | None = None
    AI_SERVER_ENABLED: bool = False

    # Legacy backend (for webhook routing)
    LEGACY_BACKEND_URL: str = "http://localhost:5000"

    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Security settings
    DOCS_ENABLED: bool = True  # Disable in production
    RATE_LIMIT_SMS_PER_MINUTE: int = 10
    RATE_LIMIT_SMS_PER_HOUR: int = 100
    RATE_LIMIT_SMS_PER_DESTINATION_HOUR: int = 5

    @model_validator(mode='after')
    def validate_production_settings(self) -> 'Settings':
        """
        Validate security settings for production environment.

        SECURITY: Fails startup if production environment has weak secrets.
        """
        is_production = self.ENVIRONMENT.lower() in ('production', 'prod', 'staging')

        if is_production:
            # Check SECRET_KEY strength
            if self.SECRET_KEY in WEAK_SECRET_KEYS:
                raise ValueError(
                    "SECURITY ERROR: SECRET_KEY is set to a known weak/default value. "
                    "Set a strong SECRET_KEY environment variable for production. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )

            if len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "SECURITY ERROR: SECRET_KEY must be at least 32 characters in production. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )

            # Force DEBUG off in production
            if self.DEBUG:
                logger.warning(
                    "SECURITY WARNING: DEBUG=True in production environment. "
                    "This will be overridden to False."
                )
                object.__setattr__(self, 'DEBUG', False)

            # Disable docs in production by default
            if self.DOCS_ENABLED:
                logger.warning(
                    "SECURITY WARNING: API docs enabled in production. "
                    "Consider setting DOCS_ENABLED=false for security."
                )

            # Warn if Twilio auth token is missing (webhooks won't be secure)
            if not self.TWILIO_AUTH_TOKEN:
                logger.warning(
                    "SECURITY WARNING: TWILIO_AUTH_TOKEN not set. "
                    "Twilio webhooks will reject all requests."
                )

        return self

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT.lower() in ('production', 'prod', 'staging')

    @property
    def sqlalchemy_echo(self) -> bool:
        """SQLAlchemy echo setting - disabled in production for security."""
        return self.DEBUG and not self.is_production

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
