from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/powerline"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str = ""

    # Deployment environment: "development" | "production".
    # Defaults to production so an unconfigured deploy fails closed.
    ENVIRONMENT: str = "production"

    # IANA timezone name used to resolve "today" and day boundaries in the
    # dashboard and analytics (e.g. "America/New_York").
    TIMEZONE: str = "UTC"

    # Interactive API docs (/docs, /redoc). None = enabled only in development.
    DOCS_ENABLED: bool | None = None

    # Security — no default; startup fails when unset.
    SECRET_KEY: str

    # Secret mixed into every phone-number digest. Empty = plain SHA-256.
    PHONE_HASH_PEPPER: str = ""

    # Lifetime of a password-reset code, in seconds.
    RESET_CODE_TTL_SECONDS: int = 600

    # JWT lifetimes.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Comma-separated IPs/CIDRs of reverse proxies whose X-Forwarded-For
    # header may be trusted. Empty = never trust the header.
    TRUSTED_PROXIES: str = ""

    # Calls per hour per identifier when a campaign has no rate_limit configured.
    DEFAULT_RATE_LIMIT: int = 5

    # Rep lookups per hour per client IP.
    REPS_RATE_LIMIT: int = 20

    # Login / password-reset attempts per hour per identifier.
    AUTH_RATE_LIMIT: int = 10

    # WebRTC access tokens per hour per client IP.
    TOKEN_RATE_LIMIT: int = 5

    # WebRTC access tokens per hour per campaign.
    TOKEN_CAMPAIGN_RATE_LIMIT: int = 500

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

    # CORS policy for the PUBLIC embed endpoints only — comma-separated list of
    # allowed origins, or "*" for all. The embed widget runs on third-party
    # sites, so "*" is the expected value even in production.
    CORS_ORIGINS: str = "*"

    # CORS policy for the admin API — comma-separated origins allowed to call it.
    # Empty = same-origin only.
    ADMIN_CORS_ORIGINS: str = ""

    @property
    def is_development(self) -> bool:
        """True when running in the development environment."""
        return self.ENVIRONMENT == "development"


settings = Settings()
