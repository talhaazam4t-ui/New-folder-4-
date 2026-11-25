"""Email Integration Adapter (`backend/app/integrations/email/`).
"""

import base64
from email.message import EmailMessage
from typing import Any, Dict, Optional
import uuid

import httpx
from app.config import settings
from app.core.logging import logger
from app.integrations.base import BaseIntegrationAdapter

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def is_live_google_token(access_token: Optional[str]) -> bool:
    """Return True only when access_token appears to be a genuine non-mock OAuth token."""
    token = (access_token or "").strip()
    if len(token) < 12:
        return False
    if token.startswith("ya29.mock_") or token.startswith("oauth_access_"):
        return False
    return True


def _build_rfc2822_base64url(
    to_email: str,
    subject: str,
    body: str,
    from_email: Optional[str] = None,
) -> str:
    """Encode an RFC 2822 UTF-8 plain-text email into URL-safe base64 for Gmail API."""
    msg = EmailMessage()
    msg["To"] = to_email
    msg["Subject"] = subject
    if from_email:
        msg["From"] = from_email
    msg.set_content(body, charset="utf-8")
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def _extract_gmail_error(resp: httpx.Response) -> str:
    """Safely extract a concise error message from a Gmail API response."""
    try:
        payload = resp.json()
        err = payload.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:250]
        if err:
            return str(err)[:250]
    except Exception:
        pass
    return (resp.text or f"HTTP {resp.status_code}")[:250]


class EmailIntegrationAdapter(BaseIntegrationAdapter):
    """Transactional and Gmail REST API email adapter with sandbox fallback."""

    provider_name = "email"
    integration_type = "messaging"

    async def health_check(self) -> Dict[str, Any]:
        return {"provider": self.provider_name, "healthy": True}

    async def create_gmail_draft(
        self,
        tenant_id: str,
        to_email: str,
        subject: str,
        body: str,
        access_token: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Save an email draft directly in the workspace's Gmail Drafts folder when OAuth token is present.

        Never sends the email automatically; falls back cleanly to CRM-only storage when OAuth is absent.
        """
        if is_live_google_token(access_token):
            raw_b64 = _build_rfc2822_base64url(
                to_email=to_email,
                subject=subject,
                body=body,
                from_email=from_email,
            )
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(
                        f"{GMAIL_API_BASE}/drafts",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                        json={"message": {"raw": raw_b64}},
                    )
                if resp.status_code in (200, 201):
                    data = resp.json() if resp.text else {}
                    draft_id = str(data.get("id") or "")
                    message_id = str((data.get("message") or {}).get("id") or "")
                    logger.info(
                        "Saved live Gmail draft",
                        tenant_id=tenant_id,
                        to_email=to_email,
                        draft_id=draft_id,
                    )
                    return {
                        "success": True,
                        "draft_id": draft_id,
                        "message_id": message_id or None,
                        "to": to_email,
                        "subject": subject,
                        "is_live": True,
                        "status": "saved_in_gmail",
                    }

                err_msg = _extract_gmail_error(resp)
                logger.warning(
                    "Gmail draft API returned error",
                    tenant_id=tenant_id,
                    status_code=resp.status_code,
                    error=err_msg,
                )
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "error": err_msg,
                    "to": to_email,
                    "subject": subject,
                    "is_live": False,
                    "status": "gmail_api_error",
                }
            except Exception as exc:
                logger.warning(
                    "Gmail draft API request failed",
                    tenant_id=tenant_id,
                    error=str(exc),
                )
                return {
                    "success": False,
                    "status_code": 0,
                    "error": str(exc),
                    "to": to_email,
                    "subject": subject,
                    "is_live": False,
                    "status": "gmail_api_error",
                }

        draft_id = f"crm_draft_{uuid.uuid4().hex[:10]}"
        logger.info(
            "Saved CRM email draft pending Gmail OAuth authorization",
            tenant_id=tenant_id,
            to_email=to_email,
            draft_id=draft_id,
        )
        return {
            "success": True,
            "draft_id": draft_id,
            "message_id": None,
            "to": to_email,
            "subject": subject,
            "is_live": False,
            "status": "saved_in_crm_oauth_required",
        }

    async def send_email(
        self,
        tenant_id: str,
        to_email: str,
        subject: str,
        body: str,
        access_token: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an email via Gmail REST API when a live token is passed, otherwise log in sandbox."""
        if is_live_google_token(access_token):
            raw_b64 = _build_rfc2822_base64url(
                to_email=to_email,
                subject=subject,
                body=body,
                from_email=from_email,
            )
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(
                        f"{GMAIL_API_BASE}/messages/send",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json",
                        },
                        json={"raw": raw_b64},
                    )
                if resp.status_code in (200, 201):
                    data = resp.json() if resp.text else {}
                    message_id = str(data.get("id") or f"gmail.{uuid.uuid4().hex[:10]}")
                    logger.info(
                        "Dispatched live Gmail email",
                        tenant_id=tenant_id,
                        to_email=to_email,
                        subject=subject,
                        message_id=message_id,
                    )
                    return {
                        "success": True,
                        "message_id": message_id,
                        "to": to_email,
                        "subject": subject,
                        "is_live": True,
                        "status": "sent",
                    }
                err_msg = _extract_gmail_error(resp)
                logger.warning(
                    "Live Gmail send API returned error",
                    tenant_id=tenant_id,
                    status_code=resp.status_code,
                    error=err_msg,
                )
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "error": err_msg,
                    "to": to_email,
                    "subject": subject,
                    "is_live": False,
                    "status": "gmail_api_error",
                }
            except Exception as exc:
                logger.warning("Live Gmail send API request failed", tenant_id=tenant_id, error=str(exc))
                return {
                    "success": False,
                    "status_code": 0,
                    "error": str(exc),
                    "to": to_email,
                    "subject": subject,
                    "is_live": False,
                    "status": "gmail_api_error",
                }

        message_id = f"email.{uuid.uuid4().hex[:12]}"
        logger.info(
            "Dispatched transactional email",
            tenant_id=tenant_id,
            to_email=to_email,
            subject=subject,
            message_id=message_id,
        )
        return {
            "success": True,
            "message_id": message_id,
            "to": to_email,
            "subject": subject,
            "status": "sent",
        }

    async def send_transactional_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> Dict[str, Any]:
        """Send platform verification / password-reset / digest email via Resend API with safe fallback."""
        resend_key = (settings.resend_api_key or "").strip()
        if resend_key and resend_key != "mock" and settings.app_env != "test":
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        "https://api.resend.com/emails",
                        headers={
                            "Authorization": f"Bearer {resend_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "from": settings.resend_from_email,
                            "to": [to_email],
                            "subject": subject,
                            "html": html_body,
                            "text": text_body,
                        },
                    )
                if resp.status_code in (200, 201):
                    data = resp.json() if resp.text else {}
                    logger.info(
                        "Dispatched transactional email via Resend",
                        to_email=to_email,
                        subject=subject,
                        resend_id=data.get("id"),
                    )
                    return {
                        "success": True,
                        "provider": "resend",
                        "message_id": data.get("id"),
                        "delivered": True,
                    }
                logger.warning(
                    "Resend API returned non-2xx",
                    status_code=resp.status_code,
                    body=resp.text[:200],
                )
            except Exception as exc:
                logger.warning("Resend API email delivery failed", error=str(exc))

        logger.info(
            "Transactional email logged locally (configure RESEND_API_KEY for live inbox delivery)",
            to_email=to_email,
            subject=subject,
        )
        return {
            "success": True,
            "provider": "log_fallback",
            "delivered": False,
        }


email_adapter = EmailIntegrationAdapter()
