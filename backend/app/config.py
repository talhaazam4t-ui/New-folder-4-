"""Application Configuration Module

Uses Pydantic BaseSettings to parse environment variables with strict type validation,
safe development defaults, and fallback handling for testing and production environments.
"""

from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    # Application Info
    app_name: str = Field(default="Talox Tech Stream", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_secret_key: str = Field(
        default="talox-dev-secret-key-32-chars-minimum-needed",
        alias="APP_SECRET_KEY"
    )
    debug: bool = Field(default=True, alias="DEBUG")
    port: int = Field(default=8000, alias="PORT")
    host: str = Field(default="0.0.0.0", alias="HOST")

    # Platform Super Admin Emails (Sole Exclusive Administrator)
    super_admin_emails: List[str] = Field(
        default=[
            "talazam40@gmail.com",
            "talhazam4@gmail.com",
            "talhaazam4t@gmail.com",
        ],
        alias="SUPER_ADMIN_EMAILS",
    )

    # URLs & CORS
    backend_url: str = Field(default="http://localhost:8000", alias="BACKEND_URL")
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        alias="ALLOWED_ORIGINS"
    )

    # Supabase PostgreSQL & Auth
    supabase_url: str = Field(default="https://mock-project.supabase.co", alias="SUPABASE_URL")
    supabase_anon_key: str = Field(default="mock-anon-key", alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(
        default="mock-service-role-key",
        alias="SUPABASE_SERVICE_ROLE_KEY"
    )
    supabase_jwt_secret: Optional[str] = Field(
        default=None,
        alias="SUPABASE_JWT_SECRET"
    )
    supabase_database_url: Optional[str] = Field(
        default=None,
        alias="SUPABASE_DATABASE_URL"
    )
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")

    # AI Provider & Smart Model Routing (DeepSeek API Only)
    ai_provider: str = Field(default="deepseek", alias="AI_PROVIDER")  # deepseek | mock
    deepseek_api_key: Optional[str] = Field(default=None, alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        alias="DEEPSEEK_BASE_URL"
    )
    ai_api_key: Optional[str] = Field(default=None, alias="AI_API_KEY")  # backward-compatible alias
    ai_default_fast_model: str = Field(
        default="deepseek-chat",
        alias="AI_DEFAULT_FAST_MODEL"
    )
    ai_default_reasoning_model: str = Field(
        default="deepseek-reasoner",
        alias="AI_DEFAULT_REASONING_MODEL"
    )

    # Cost Protection, Rate Limiting & Circuit Breaker
    rate_limit_agent_rpm: int = Field(default=20, alias="RATE_LIMIT_AGENT_RPM")
    rate_limit_default_rpm: int = Field(default=60, alias="RATE_LIMIT_DEFAULT_RPM")
    circuit_breaker_max_failures: int = Field(default=3, alias="CIRCUIT_BREAKER_MAX_FAILURES")
    circuit_breaker_cooldown_seconds: int = Field(
        default=300,
        alias="CIRCUIT_BREAKER_COOLDOWN_SECONDS"
    )
    default_tenant_daily_token_budget: int = Field(
        default=100000,
        alias="DEFAULT_TENANT_DAILY_TOKEN_BUDGET"
    )

    # Session Persistence & Support Contact
    session_expire_days: int = Field(default=30, alias="SESSION_EXPIRE_DAYS")
    support_whatsapp_number: str = Field(default="03238300330", alias="SUPPORT_WHATSAPP_NUMBER")

    # WhatsApp Business & Meta Embedded Signup
    whatsapp_provider: str = Field(default="mock", alias="WHATSAPP_PROVIDER")  # meta | mock
    whatsapp_access_token: Optional[str] = Field(default=None, alias="WHATSAPP_ACCESS_TOKEN")
    whatsapp_phone_number_id: Optional[str] = Field(default=None, alias="WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_business_account_id: Optional[str] = Field(
        default=None,
        alias="WHATSAPP_BUSINESS_ACCOUNT_ID"
    )
    whatsapp_verify_token: str = Field(default="talox_verify_token", alias="WHATSAPP_VERIFY_TOKEN")
    whatsapp_app_secret: Optional[str] = Field(default=None, alias="WHATSAPP_APP_SECRET")
    meta_app_id: Optional[str] = Field(default=None, alias="META_APP_ID")
    meta_app_secret: Optional[str] = Field(default=None, alias="META_APP_SECRET")
    meta_config_id: Optional[str] = Field(default=None, alias="META_CONFIG_ID")

    # Payment Rails
    payment_provider: str = Field(default="manual", alias="PAYMENT_PROVIDER")  # manual | mock
    payment_secret_key: Optional[str] = Field(default=None, alias="PAYMENT_SECRET_KEY")
    payment_webhook_secret: Optional[str] = Field(default=None, alias="PAYMENT_WEBHOOK_SECRET")

    # Google Services (Maps/Places, Gmail, Calendar OAuth)
    google_client_id: Optional[str] = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: Optional[str] = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: Optional[str] = Field(default=None, alias="GOOGLE_REDIRECT_URI")
    google_places_api_key: Optional[str] = Field(default=None, alias="GOOGLE_PLACES_API_KEY")

    # Redis (Optional)
    redis_url: Optional[str] = Field(default=None, alias="REDIS_URL")

    model_config = SettingsConfigDict(
        env_file=(str(ROOT_ENV_PATH), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Global singleton instance
settings = Settings()
