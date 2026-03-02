from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/powerline"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production"

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

    # CORS — comma-separated list of allowed origins, or "*" for all.
    # Use "*" for development and the embed widget (runs on third-party sites).
    # In production, restrict to your frontend domain: "https://app.example.com"
    CORS_ORIGINS: str = "*"


settings = Settings()
