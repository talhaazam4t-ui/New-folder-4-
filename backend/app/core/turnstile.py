"""Cloudflare Turnstile Anti-Bot Verification Helper."""

from typing import Optional

import httpx
from app.config import settings
from app.core.exceptions import TaloxException
from app.core.logging import logger

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def is_turnstile_enabled() -> bool:
    """Return True when both Turnstile Site Key and Secret Key are configured."""
    site = (settings.turnstile_site_key or "").strip()
    secret = (settings.turnstile_secret_key or "").strip()
    return bool(site and secret and site != "mock" and secret != "mock")


async def verify_turnstile_token(
    token: Optional[str],
    remote_ip: Optional[str] = None,
) -> None:
    """Validate Cloudflare Turnstile response token when protection is enabled."""
    if not is_turnstile_enabled():
        return

    cleaned = (token or "").strip()
    if not cleaned:
        raise TaloxException(
            message="Please complete the Cloudflare Turnstile security check.",
            code="TURNSTILE_REQUIRED",
            status_code=400,
        )

    payload = {
        "secret": (settings.turnstile_secret_key or "").strip(),
        "response": cleaned,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(TURNSTILE_VERIFY_URL, data=payload)
        data = resp.json() if resp.text else {}
    except Exception as exc:
        logger.warning("Cloudflare Turnstile verification request failed", error=str(exc))
        raise TaloxException(
            message="Security verification service temporarily unavailable. Please try again.",
            code="TURNSTILE_UNAVAILABLE",
            status_code=503,
        )

    if not data.get("success"):
        error_codes = data.get("error-codes") or []
        logger.warning("Turnstile bot verification failed", error_codes=error_codes)
        raise TaloxException(
            message="Security challenge failed or expired. Please try again.",
            code="BOT_VERIFICATION_FAILED",
            status_code=400,
        )
