"""Shared SlowAPI Rate Limiter Instance for Cost & Abuse Protection.
"""

from app.config import settings
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_tenant_or_ip_key(request: Request) -> str:
    """Rate limit by X-Tenant-ID header when present, falling back to client IP."""
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        return f"tenant:{tenant_id}"
    return get_remote_address(request)


limiter = Limiter(
    key_func=get_tenant_or_ip_key,
    default_limits=[f"{settings.rate_limit_default_rpm}/minute"],
)
