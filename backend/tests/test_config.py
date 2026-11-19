import app.database.supabase as supabase_mod
import pytest
from app.config import Settings, settings
from pydantic import ValidationError


def test_settings_defaults():
    s = Settings()
    assert s.app_name == "Talox Tech Stream"
    assert s.app_env in ["development", "staging", "production"]
    assert s.rate_limit_agent_rpm == 20
    assert s.circuit_breaker_max_failures == 3
    assert s.ai_default_fast_model == "deepseek-chat"
    assert s.ai_default_reasoning_model == "deepseek-reasoner"


def test_settings_comma_separated_and_empty_env_parsing(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", " https://teloxtech.stream/ , https://www.teloxtech.stream ")
    monkeypatch.setenv("SUPER_ADMIN_EMAILS", "admin1@teloxtech.stream, Admin2@teloxtech.stream ")
    monkeypatch.setenv("FRONTEND_URL", "https://teloxtech.stream/")
    monkeypatch.setenv("BACKEND_URL", "https://api.teloxtech.stream/")

    s = Settings()
    assert s.allowed_origins == ["https://teloxtech.stream", "https://www.teloxtech.stream"]
    assert s.super_admin_emails == ["admin1@teloxtech.stream", "admin2@teloxtech.stream"]
    assert s.frontend_url == "https://teloxtech.stream"
    assert s.backend_url == "https://api.teloxtech.stream"

    monkeypatch.setenv("ALLOWED_ORIGINS", "")
    monkeypatch.setenv("SUPER_ADMIN_EMAILS", "")
    s_empty = Settings()
    assert s_empty.allowed_origins == []
    assert s_empty.super_admin_emails == []


def test_settings_production_secret_and_cors_merge(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_SECRET_KEY", "talox-dev-secret-key-32-chars-minimum-needed")
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("APP_SECRET_KEY", "short-key")
    with pytest.raises(ValidationError):
        Settings()

    monkeypatch.setenv("APP_SECRET_KEY", "a-very-strong-production-secret-key-at-least-32-chars")
    monkeypatch.setenv("FRONTEND_URL", "https://teloxtech.stream/")
    monkeypatch.setenv("BACKEND_URL", "http://localhost:8000")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://www.teloxtech.stream/")
    prod_settings = Settings()
    assert "https://www.teloxtech.stream" in prod_settings.allowed_origins
    assert "https://teloxtech.stream" in prod_settings.allowed_origins
    assert "http://localhost:8000" not in prod_settings.allowed_origins


def test_supabase_engine_connect_args_for_pgbouncer_vs_sqlite(monkeypatch):
    captured = {}

    def fake_create_async_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(supabase_mod, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(supabase_mod, "_engine", None)
    monkeypatch.setattr(settings, "supabase_database_url", "postgresql://user:pass@pooler.supabase.com:6543/postgres")
    supabase_mod.get_engine()
    assert captured["url"].startswith("postgresql+asyncpg://")
    assert captured["kwargs"]["connect_args"] == {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }

    captured.clear()
    monkeypatch.setattr(supabase_mod, "_engine", None)
    monkeypatch.setattr(settings, "supabase_database_url", "")
    monkeypatch.setattr(settings, "app_env", "development")
    supabase_mod.get_engine()
    assert captured["url"].startswith("sqlite+aiosqlite://")
    assert captured["kwargs"]["connect_args"] == {"check_same_thread": False}
