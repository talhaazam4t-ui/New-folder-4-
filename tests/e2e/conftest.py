"""Isolated E2E test harness and reusable opaque-box API fixtures for TALOXTECH.

Guarantees 100% isolation from `.env` and live Supabase (`pmmduhflikdvddzpgwsi`),
running exclusively against a per-PID temporary SQLite database and mock/sandbox providers.
"""

from __future__ import annotations

import atexit
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

# 1. Prepend <repo_root>/backend, <repo_root>, and tests/e2e BEFORE importing any `app.*` module
_E2E_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _E2E_DIR.parent.parent
_BACKEND_DIR = _REPO_ROOT / "backend"
for _path_str in (str(_E2E_DIR), str(_BACKEND_DIR), str(_REPO_ROOT)):
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

# 2. Force isolated test environment variables BEFORE importing `app.config` / `app.main`
_E2E_DB_PATH = Path(tempfile.gettempdir()) / f"talox_e2e_{os.getpid()}.db"

os.environ["APP_ENV"] = "test"
os.environ["APP_SECRET_KEY"] = "e2e-test-secret-key-at-least-32-chars-long"
os.environ["SUPABASE_DATABASE_URL"] = ""
os.environ["TALOX_ALLOW_SQLITE_FALLBACK"] = "true"
os.environ["TALOX_SQLITE_DB_URL"] = f"sqlite+aiosqlite:///{_E2E_DB_PATH.as_posix()}"
os.environ["AI_PROVIDER"] = "mock"
os.environ["WHATSAPP_PROVIDER"] = "mock"
os.environ["PAYMENT_PROVIDER"] = "manual"
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["GOOGLE_CLIENT_SECRET"] = ""
os.environ["META_APP_ID"] = ""
os.environ["META_APP_SECRET"] = ""
os.environ["WHATSAPP_APP_SECRET"] = ""
os.environ["WHATSAPP_ACCESS_TOKEN"] = ""
os.environ["WHATSAPP_PHONE_NUMBER_ID"] = ""
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["GOOGLE_PLACES_API_KEY"] = ""
os.environ["AI_API_KEY"] = ""
os.environ["PAYMENT_SECRET_KEY"] = ""
os.environ["PAYMENT_WEBHOOK_SECRET"] = ""
os.environ["REDIS_URL"] = ""

import pytest  # noqa: E402
from app.automation.budget_manager import budget_manager  # noqa: E402
from app.automation.retry import dead_letter_queue  # noqa: E402
from app.config import settings  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.database.models.service import Service  # noqa: E402
from app.database.supabase import get_session_factory, reset_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.billing_service import billing_service  # noqa: E402
from e2e_helpers import (  # noqa: E402
    CANONICAL_MODULE_FLAGS,
    CANONICAL_SERVICE_SLUGS,
    approve_tenant_payment,
    create_tenant,
    get_raw_integration_config,
    get_tenant_agent_row,
    invite_member_and_login,
    onboard_paid_tenant,
    register_and_login,
    set_approval_expires_at,
    set_subscription_expires_at,
    set_tenant_status,
    subscribe_service,
)
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _patch_settings_for_e2e() -> None:
    """Ensure Settings singleton never leaks `.env` values into E2E test runs."""
    settings.app_env = "test"
    settings.app_secret_key = "e2e-test-secret-key-at-least-32-chars-long"
    settings.supabase_database_url = ""
    settings.ai_provider = "mock"
    settings.whatsapp_provider = "mock"
    settings.payment_provider = "manual"
    settings.google_client_id = ""
    settings.google_client_secret = ""
    settings.meta_app_id = ""
    settings.meta_app_secret = ""
    settings.whatsapp_app_secret = ""
    settings.whatsapp_access_token = ""
    settings.whatsapp_phone_number_id = ""
    settings.deepseek_api_key = ""
    settings.gemini_api_key = ""
    settings.google_places_api_key = ""
    settings.ai_api_key = ""
    settings.payment_secret_key = ""
    settings.payment_webhook_secret = ""
    settings.redis_url = ""


_patch_settings_for_e2e()


def _cleanup_e2e_db() -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = Path(f"{_E2E_DB_PATH}{suffix}")
        try:
            if candidate.exists():
                candidate.unlink()
        except OSError:
            pass


atexit.register(_cleanup_e2e_db)


@pytest.fixture(autouse=True)
async def clean_database():
    """Reset SQLite tables, rate limiter, budget manager, and DLQ before every test."""
    _patch_settings_for_e2e()
    limiter.reset()
    await reset_db()

    if hasattr(budget_manager, "_tenants"):
        budget_manager._tenants.clear()
    if hasattr(budget_manager, "_records"):
        getattr(budget_manager, "_records").clear()
    if hasattr(dead_letter_queue, "_entries"):
        dead_letter_queue._entries.clear()

    yield

    _patch_settings_for_e2e()


@pytest.fixture
async def async_client():
    """HTTPX AsyncClient bound directly to FastAPI app via ASGITransport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def seed_catalog() -> Dict[str, Dict[str, Any]]:
    """Seed the canonical 6-service catalog and return a slug -> service summary map."""
    session_maker = get_session_factory()
    async with session_maker() as session:
        await billing_service.ensure_default_catalog(session)
        rows = (await session.execute(select(Service).where(Service.active.is_(True)))).scalars().all()
        return {
            srv.slug: {
                "id": str(srv.id),
                "name": srv.name,
                "slug": srv.slug,
                "category": srv.category,
                "configuration_schema": srv.configuration_schema or {},
            }
            for srv in rows
        }


@pytest.fixture
async def super_admin_headers(async_client: AsyncClient) -> Dict[str, str]:
    """Register and authenticate the platform Super Admin for admin approval workflows."""
    admin_email = settings.super_admin_emails[0] if settings.super_admin_emails else "talhazam4@gmail.com"
    auth = await register_and_login(
        async_client,
        email=admin_email,
        password="SuperAdminPass123!",
        full_name="Platform Super Admin",
        phone="+923238300330",
    )
    assert auth["is_super_admin"] is True
    return auth["headers"]


__all__ = [
    "CANONICAL_MODULE_FLAGS",
    "CANONICAL_SERVICE_SLUGS",
    "approve_tenant_payment",
    "async_client",
    "clean_database",
    "create_tenant",
    "get_raw_integration_config",
    "get_tenant_agent_row",
    "invite_member_and_login",
    "onboard_paid_tenant",
    "register_and_login",
    "seed_catalog",
    "set_approval_expires_at",
    "set_subscription_expires_at",
    "set_tenant_status",
    "subscribe_service",
    "super_admin_headers",
]
