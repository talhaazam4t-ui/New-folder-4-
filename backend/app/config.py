"""Application Configuration Module

Uses Pydantic BaseSettings to parse environment variables with strict type validation,
safe development defaults, and fallback handling for testing and production environments.
"""

import json
from pathlib import Path
from typing import Annotated, Any, List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

_INSECURE_SECRET_KEYS = {
    "talox-dev-secret-key-32-chars-minimum-needed",
    "change-this-to-a-secure-random-32-byte-hex-key-in-production",
}


def _parse_str_list(value: Any, *, strip_trailing_slash: bool = False) -> List[str]:
    """Parse JSON array, comma-separated string, or empty string into a normalized list."""
    if value is None:
        return []
    items: List[str]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    items = [str(item) for item in parsed]
                else:
                    items = [raw]
            except json.JSONDecodeError:
                inner = raw.strip("[]")
                items = [part.strip().strip("\"'") for part in inner.split(",")]
        else:
            items = [part for part in raw.split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = [str(item) for item in value]
    else:
        items = [str(value)]

    normalized: List[str] = []
    seen = set()
    for item in items:
        cleaned = item.strip()
        if strip_trailing_slash:
            cleaned = cleaned.rstrip("/")
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            normalized.append(cleaned)
    return normalized


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

    # Platform Super Admin Emails & Bootstrap Controls
    super_admin_emails: Annotated[List[str], NoDecode] = Field(
        default=[
            "talhazam4@gmail.com",
            "talhaazam4t@gmail.com",
            "talazam40@gmail.com",
        ],
        alias="SUPER_ADMIN_EMAILS",
    )
    super_admin_bootstrap_password: Optional[str] = Field(
        default=None,
        alias="SUPER_ADMIN_BOOTSTRAP_PASSWORD",
    )
    allow_super_admin_bootstrap: bool = Field(
        default=False,
        alias="ALLOW_SUPER_ADMIN_BOOTSTRAP",
    )

    # URLs & CORS
    backend_url: str = Field(default="http://localhost:8000", alias="BACKEND_URL")
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")
    allowed_origins: Annotated[List[str], NoDecode] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        alias="ALLOWED_ORIGINS"
    )
    auto_create_tables: bool = Field(default=False, alias="AUTO_CREATE_TABLES")

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

    # AI Provider & Smart Model Routing (Priority 1: Groq Free API -> Priority 2: DeepSeek -> Priority 3: Local Safety Net)
    ai_provider: str = Field(default="deepseek", alias="AI_PROVIDER")  # groq | deepseek | mock | openrouter
    ai_api_key: Optional[str] = Field(default=None, alias="AI_API_KEY")
    groq_api_key: Optional[str] = Field(default=None, alias="GROQ_API_KEY")
    groq_base_url: str = Field(
        default="https://api.groq.com/openai/v1",
        alias="GROQ_BASE_URL",
    )
    groq_primary_model: str = Field(
        default="llama-3.3-70b-versatile",
        alias="GROQ_PRIMARY_MODEL",
    )
    groq_fast_model: str = Field(
        default="llama-3.1-8b-instant",
        alias="GROQ_FAST_MODEL",
    )
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash-lite", alias="GEMINI_MODEL")
    deepseek_api_key: Optional[str] = Field(default=None, alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        alias="DEEPSEEK_BASE_URL",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        alias="OPENROUTER_BASE_URL",
    )
    ai_default_fast_model: str = Field(
        default="deepseek-chat",
        alias="AI_DEFAULT_FAST_MODEL",
    )
    ai_default_reasoning_model: str = Field(
        default="deepseek-reasoner",
        alias="AI_DEFAULT_REASONING_MODEL",
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

    # Office Receptionist — AI Voice Agent (Retell AI, Telnyx, Cal.com)
    retell_api_key: Optional[str] = Field(default=None, alias="RETELL_API_KEY")
    retell_base_url: str = Field(default="https://api.retellai.com", alias="RETELL_BASE_URL")
    retell_webhook_secret: Optional[str] = Field(default=None, alias="RETELL_WEBHOOK_SECRET")
    telnyx_api_key: Optional[str] = Field(default=None, alias="TELNYX_API_KEY")
    telnyx_connection_id: Optional[str] = Field(default=None, alias="TELNYX_CONNECTION_ID")
    telnyx_default_number: Optional[str] = Field(default=None, alias="TELNYX_DEFAULT_NUMBER")
    telnyx_default_country: str = Field(default="US", alias="TELNYX_DEFAULT_COUNTRY")
    calcom_api_key: Optional[str] = Field(default=None, alias="CALCOM_API_KEY")
    calcom_base_url: str = Field(default="https://api.cal.com/v2", alias="CALCOM_BASE_URL")

    # Redis (Optional)
    redis_url: Optional[str] = Field(default=None, alias="REDIS_URL")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, value: Any) -> List[str]:
        return _parse_str_list(value, strip_trailing_slash=True)

    @field_validator("super_admin_emails", mode="before")
    @classmethod
    def _parse_super_admin_emails(cls, value: Any) -> List[str]:
        return [email.lower() for email in _parse_str_list(value, strip_trailing_slash=False)]

    @field_validator("frontend_url", "backend_url", mode="before")
    @classmethod
    def _strip_url_trailing_slash(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().rstrip("/")

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> "Settings":
        normalized_origins: List[str] = []
        for origin in self.allowed_origins:
            cleaned = origin.strip().rstrip("/")
            if cleaned and cleaned not in normalized_origins:
                normalized_origins.append(cleaned)
        self.allowed_origins = normalized_origins

        if self.app_env in ("production", "staging"):
            secret = (self.app_secret_key or "").strip()
            if not secret or len(secret) < 32 or secret in _INSECURE_SECRET_KEYS:
                raise ValueError(
                    "APP_SECRET_KEY must be configured with a strong secret (>= 32 chars) in production/staging"
                )

            merged = list(self.allowed_origins)
            if self.frontend_url:
                fe = self.frontend_url.strip().rstrip("/")
                if fe and fe not in merged:
                    merged.append(fe)
            if self.backend_url:
                be = self.backend_url.strip().rstrip("/")
                is_local = any(h in be.lower() for h in ("localhost", "127.0.0.1", "0.0.0.0"))
                if be and not is_local and be not in merged:
                    merged.append(be)
            self.allowed_origins = merged

        return self

    model_config = SettingsConfigDict(
        env_file=(str(ROOT_ENV_PATH), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Global singleton instance
settings = Settings()
