"""Production Readiness & Health Verification Script for Talox Tech Stream.

Checks database connectivity, DeepSeek AI routing configuration, WhatsApp adapter health,
deployment environment readiness, and security guardrails.
Usage:
    python scripts/health_check.py
"""

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.config import settings  # noqa: E402
from app.core.security import sanitize_ai_prompt  # noqa: E402
from app.database.supabase import get_session_factory  # noqa: E402
from app.integrations.ai_providers.router import select_model_for_task  # noqa: E402
from app.integrations.whatsapp.client import whatsapp_client  # noqa: E402


async def _check_database() -> Dict[str, Any]:
    db_url = (settings.supabase_database_url or "").strip()
    configured = bool(db_url and (db_url.startswith("postgresql") or db_url.startswith("postgres")))
    status: Dict[str, Any] = {
        "configured": configured,
        "dialect": "unknown",
        "connected": False,
        "error": None,
    }
    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
            bind = session.get_bind()
            status["dialect"] = bind.dialect.name if bind is not None else "unknown"
            status["connected"] = True
    except Exception as exc:
        sanitized_err = re.sub(r"://[^\s/]+@", "://***@", str(exc))
        status["error"] = f"{type(exc).__name__}: {sanitized_err}"
    return status


async def run_health_check() -> Dict[str, Any]:
    db_status = await _check_database()
    wa_health = await whatsapp_client.health_check()
    fast_model = select_model_for_task("whatsapp_reply")
    reasoning_model = select_model_for_task("complex_planning")
    sanitized_sample = sanitize_ai_prompt("Card 4532-1111-2222-3333 password=secret123")

    resolved_deepseek_key = (
        settings.deepseek_api_key
        or os.environ.get("DEEPSEEK_API_KEY")
        or settings.ai_api_key
        or ""
    ).strip()
    deepseek_key_configured = bool(
        resolved_deepseek_key
        and resolved_deepseek_key != "mock"
        and not resolved_deepseek_key.startswith("your-")
    )

    url_candidates = [
        settings.frontend_url,
        settings.backend_url,
        *settings.allowed_origins,
    ]
    localhost_in_urls = any(
        "localhost" in url.lower() or "127.0.0.1" in url for url in url_candidates if url
    )
    deployment_warnings: List[str] = []
    if settings.app_env in ("production", "staging"):
        if localhost_in_urls:
            deployment_warnings.append(
                "localhost/127.0.0.1 detected in FRONTEND_URL, BACKEND_URL, or ALLOWED_ORIGINS"
            )
        if settings.debug:
            deployment_warnings.append("DEBUG=true in production/staging environment")
        if not db_status["configured"]:
            deployment_warnings.append("SUPABASE_DATABASE_URL is not configured")
    elif localhost_in_urls:
        deployment_warnings.append("Using localhost URLs (expected in development/test mode)")

    pii_redaction_active = "4532" not in sanitized_sample and "secret123" not in sanitized_sample
    is_prod_like = settings.app_env in ("production", "staging")
    is_healthy = pii_redaction_active and (
        not is_prod_like or (db_status["connected"] and not localhost_in_urls)
    )

    report = {
        "app_name": settings.app_name,
        "environment": settings.app_env,
        "database": db_status,
        "ai_routing": {
            "provider": settings.ai_provider,
            "deepseek_key_configured": deepseek_key_configured,
            "fast_tier_model": fast_model,
            "reasoning_tier_model": reasoning_model,
        },
        "whatsapp_adapter": wa_health,
        "deployment_config": {
            "frontend_url": settings.frontend_url,
            "backend_url": settings.backend_url,
            "debug": settings.debug,
            "localhost_in_urls": localhost_in_urls,
            "warnings": deployment_warnings,
        },
        "security_guardrails": {
            "pii_redaction_active": pii_redaction_active,
            "rate_limit_rpm": settings.rate_limit_agent_rpm,
            "circuit_breaker_max_failures": settings.circuit_breaker_max_failures,
        },
        "status": "healthy" if is_healthy else "degraded",
    }
    return report


if __name__ == "__main__":
    result = asyncio.run(run_health_check())
    print(result)
