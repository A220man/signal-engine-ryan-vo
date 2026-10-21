"""Application configuration."""
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_NAME: str = "signal-engine"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Server
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./signal_engine.db"

    # Auth - Keycloak OIDC
    KEYCLOAK_URL: str = "http://localhost:8080"
    KEYCLOAK_REALM: str = "signal-engine"
    KEYCLOAK_CLIENT_ID: str = "signal-engine-client"
    KEYCLOAK_CLIENT_SECRET: str = ""
    OIDC_ISSUER_URL: str = ""
    OIDC_AUDIENCE: str = "signal-engine-api"

    # Demo mode (local only)
    DEMO_MODE: bool = True
    DEMO_USER_EMAIL: str = "demo@local"
    DEMO_USER_ROLE: str = "operator"

    # LLM (optional)
    LLM_API_KEY: Optional[str] = None
    LLM_PROVIDER: str = "openai-compatible"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_BASE_URL: Optional[str] = None

    # File upload
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50 MB
    UPLOAD_DIR: str = "./uploads"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()