from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/powerline"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Deployment environment: "development" | "production".
    # Defaults to production so an unconfigured deploy fails closed.
    ENVIRONMENT: str = "production"

    # Security — no default; startup fails when unset.
    SECRET_KEY: str

    # Comma-separated IPs/CIDRs of reverse proxies whose X-Forwarded-For
    # header may be trusted. Empty = never trust the header.
    TRUSTED_PROXIES: str = ""

    # Calls per hour per identifier when a campaign has no rate_limit configured.
    DEFAULT_RATE_LIMIT: int = 5

    # Rep lookups per hour per client IP.
    REPS_RATE_LIMIT: int = 20

    # Login / password-reset attempts per hour per identifier.
    AUTH_RATE_LIMIT: int = 10

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_TWIML_APP_SID: str = ""
    TWILIO_FROM_NUMBER: str = ""
    # API Key credentials for WebRTC AccessToken generation (distinct from auth token).
    # Create at console.twilio.com → Account → API Keys. SID starts with SK.
    TWILIO_API_KEY_SID: str = ""
    TWILIO_API_KEY_SECRET: str = ""

    # Public base URL for Twilio callback URLs (e.g. https://abc.ngrok.io in dev,
    # production domain in prod). Leave empty to skip placing the Twilio call.
    PUBLIC_BASE_URL: str = ""

    # Cloudinary (audio file hosting)
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # Civic API (ZIP → representative lookup)
    GOOGLE_CIVIC_API_KEY: str = ""
    OPENSTATES_API_KEY: str = ""

    # CORS — comma-separated list of allowed origins, or "*" for all.
    # Use "*" for development and the embed widget (runs on third-party sites).
    # In production, restrict to your frontend domain: "https://app.example.com"
    CORS_ORIGINS: str = "*"

    @property
    def is_development(self) -> bool:
        """True when running in the development environment."""
        return self.ENVIRONMENT == "development"


settings = Settings()
