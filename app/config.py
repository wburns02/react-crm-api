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

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def convert_database_url(cls, v: str) -> str:
        """Convert postgresql:// to postgresql+asyncpg:// for async support."""
        if v and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    LEGACY_DATABASE_URL: str | None = None

    # Auth - SECURITY: Must be set via environment in production
    SECRET_KEY: str = "development-secret-key-change-in-production"  # nosec B105 - Default for dev, overridden in production via env var
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours

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

    # Email (Brevo - formerly Sendinblue)
    BREVO_API_KEY: str | None = None
    SENDGRID_API_KEY: str | None = None  # Legacy - use BREVO_API_KEY instead
    EMAIL_FROM_ADDRESS: str = "noreply@macseptic.com"
    EMAIL_FROM_NAME: str = "Mac Septic Services"

    # RingCentral
    RINGCENTRAL_CLIENT_ID: str | None = None
    RINGCENTRAL_CLIENT_SECRET: str | None = None
    RINGCENTRAL_SERVER_URL: str = "https://platform.ringcentral.com"
    RINGCENTRAL_JWT_TOKEN: str | None = None

    # Samsara Fleet Tracking
    SAMSARA_API_TOKEN: str | None = None

    # Yelp Fusion API
    YELP_API_KEY: str | None = None

    # Facebook Graph API
    FACEBOOK_APP_ID: str | None = None
    FACEBOOK_APP_SECRET: str | None = None
    FACEBOOK_REDIRECT_URI: str = ""

    # Stripe Payment Processing (deprecated - use Clover)
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_PUBLISHABLE_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None

    # Clover Payment Processing
    CLOVER_MERCHANT_ID: str | None = None
    CLOVER_API_KEY: str | None = None
    CLOVER_ENVIRONMENT: str = "sandbox"  # "sandbox" or "production"

    # Google Ads API (Basic Access - 15,000 ops/day)
    GOOGLE_ADS_DEVELOPER_TOKEN: str | None = None
    GOOGLE_ADS_CLIENT_ID: str | None = None
    GOOGLE_ADS_CLIENT_SECRET: str | None = None
    GOOGLE_ADS_REFRESH_TOKEN: str | None = None
    GOOGLE_ADS_CUSTOMER_ID: str | None = None
    GOOGLE_ADS_LOGIN_CUSTOMER_ID: str | None = None  # Manager account ID

    # AI Services
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None

    # Local AI Server (for vLLM on RTX 5090)
    AI_SERVER_URL: str = "http://localhost:8000"
    AI_SERVER_API_KEY: str | None = None
    AI_SERVER_ENABLED: bool = False

    # R730 ML Workstation (Local AI via Tailscale Funnel)
    USE_LOCAL_AI: bool = True
    OLLAMA_BASE_URL: str = "https://localhost-0.tailad2d5f.ts.net/ollama"
    OLLAMA_MODEL: str = "llama3.2:3b"
    WHISPER_BASE_URL: str = "https://localhost-0.tailad2d5f.ts.net/whisper"
    LOCAL_WHISPER_MODEL: str = "medium"
    LLAVA_MODEL: str = "llava:13b"
    HCTG_AI_URL: str = "https://hctg-ai.tailad2d5f.ts.net"
    HCTG_AI_MODEL: str = "qwen2.5:32b"

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

    # Error Tracking
    SENTRY_DSN: str | None = None
    VERSION: str = "2.8.0"

    # Redis Cache (optional)
    REDIS_URL: str | None = None
    RATE_LIMIT_REDIS_ENABLED: bool = False  # Use Redis for distributed rate limiting

    # OpenTelemetry (optional)
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_SERVICE_NAME: str = "react-crm-api"

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """
        Validate security settings for production environment.

        SECURITY: Fails startup if production environment has weak secrets.
        """
        is_production = self.ENVIRONMENT.lower() in ("production", "prod", "staging")

        if is_production:
            # Check SECRET_KEY strength
            if self.SECRET_KEY in WEAK_SECRET_KEYS:
                raise ValueError(
                    "SECURITY ERROR: SECRET_KEY is set to a known weak/default value. "
                    "Set a strong SECRET_KEY environment variable for production. "
                    'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
                )

            if len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "SECURITY ERROR: SECRET_KEY must be at least 32 characters in production. "
                    'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
                )

            # Force DEBUG off in production
            if self.DEBUG:
                logger.warning(
                    "SECURITY WARNING: DEBUG=True in production environment. This will be overridden to False."
                )
                object.__setattr__(self, "DEBUG", False)

            # Disable docs in production by default
            if self.DOCS_ENABLED:
                logger.warning(
                    "SECURITY WARNING: API docs enabled in production. "
                    "Consider setting DOCS_ENABLED=false for security."
                )

            # Warn if Twilio auth token is missing (webhooks won't be secure)
            if not self.TWILIO_AUTH_TOKEN:
                logger.warning("SECURITY WARNING: TWILIO_AUTH_TOKEN not set. Twilio webhooks will reject all requests.")

        return self

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT.lower() in ("production", "prod", "staging")

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
