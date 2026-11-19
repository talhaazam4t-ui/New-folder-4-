"""Integrations, One-Click OAuth & Credential Vault API Endpoints.

Supports:
1. Dynamic Onboarding Requirements based on selected industry & subscribed services (`GET /api/v1/integrations/onboarding-requirements`).
2. OAuth Authorization URL generation (`GET /api/v1/integrations/oauth/{provider}/authorize`).
3. Multi-provider One-Click OAuth / API-Key connection with encrypted credential storage (`POST /api/v1/integrations/{provider}/connect`).
4. Self-service Meta Embedded Signup OAuth connection (`POST /api/v1/integrations/whatsapp/connect`).
5. Connection testing, reconnection, and credential revocation (`POST /api/v1/integrations/{id}/test`, `DELETE /api/v1/integrations/{id}`).
6. Meta WhatsApp Webhook challenge verification & inbound message processing (`GET/POST /api/v1/integrations/whatsapp/webhook`).
"""

import json
import urllib.parse
import uuid
from typing import Any, Dict, Optional

from app.config import settings
from app.core.logging import logger
from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.integrations.whatsapp.client import whatsapp_client
from app.services.integration_service import (
    SUPPORTED_INTEGRATION_PROVIDERS,
    integration_service,
    verify_oauth_state,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/integrations", tags=["Integrations & WhatsApp"])


class WhatsAppConnectRequest(BaseModel):
    oauth_code: str = Field(min_length=3, max_length=500, description="Meta Embedded Signup OAuth code")


class ProviderConnectRequest(BaseModel):
    oauth_code: Optional[str] = Field(default=None, description="OAuth authorization callback code")
    api_key: Optional[str] = Field(default=None, description="API Key for providers without OAuth")
    account_identifier: Optional[str] = Field(default=None, description="External account email, phone, or ID")
    configuration: Optional[Dict[str, Any]] = None


class OAuthCallbackRequest(BaseModel):
    code: str = Field(min_length=3, max_length=1500, description="OAuth authorization callback code")
    state: str = Field(min_length=3, max_length=2500, description="OAuth state parameter")
    redirect_uri: Optional[str] = Field(default=None, description="Optional custom redirect URI")


class WhatsAppOutboundRequest(BaseModel):
    to_phone: str = Field(min_length=5, max_length=50)
    message_body: str = Field(min_length=1, max_length=2000)


class WhatsAppInboundWebhookRequest(BaseModel):
    sender_phone: str = Field(min_length=5, max_length=50)
    sender_name: str = Field(default="WhatsApp Contact", max_length=100)
    message_text: str = Field(min_length=1, max_length=2000)
    message_id: Optional[str] = None


@router.get("")
async def list_tenant_integrations(
    context: TenantContext = Depends(require_permission("integrations.read")),
    session: AsyncSession = Depends(get_db),
):
    """List all connected integrations for the tenant (sensitive credentials masked)."""
    items = await integration_service.list_integrations(session, context.tenant_id)
    return {
        "success": True,
        "data": items,
        "supported_providers": list(SUPPORTED_INTEGRATION_PROVIDERS.values()),
    }


@router.get("/onboarding-requirements")
async def get_onboarding_integration_requirements(
    context: TenantContext = Depends(require_permission("integrations.read")),
    session: AsyncSession = Depends(get_db),
):
    """Return required integrations dynamically based on the tenant's industry and purchased services."""
    summary = await integration_service.get_onboarding_requirements(session, context.tenant_id)
    return {"success": True, "data": summary}


@router.get("/oauth/{provider}/authorize")
async def get_provider_oauth_url(
    provider: str,
    return_to: str = Query("/onboarding", description="Target route after OAuth completion"),
    redirect_uri: Optional[str] = Query(None, description="Custom redirect URI"),
    context: TenantContext = Depends(require_permission("integrations.manage")),
):
    """Generate OAuth authorization URL, signed state, and scopes for a supported integration provider."""
    info = integration_service.get_oauth_authorization_info(
        provider=provider,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        return_to=return_to,
        custom_redirect_uri=redirect_uri,
    )
    return {"success": True, "data": info}


@router.post("/oauth/callback", status_code=status.HTTP_200_OK)
async def handle_oauth_callback(
    request: OAuthCallbackRequest,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Handle OAuth authorization callback, validate state, securely exchange code for tokens, and vault credentials."""
    data = await integration_service.handle_oauth_callback(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        code=request.code,
        state=request.state,
        redirect_uri=request.redirect_uri,
    )
    return {
        "success": data["status"] == "connected",
        "data": data,
        "message": f"{data.get('display_name', 'Service')} connected and verified via OAuth 2.0.",
    }


@router.post("/oauth/{provider}/callback", status_code=status.HTTP_200_OK)
async def handle_provider_oauth_callback(
    provider: str,
    request: OAuthCallbackRequest,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Provider-specific alias endpoint for OAuth callback token exchange."""
    data = await integration_service.handle_oauth_callback(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        code=request.code,
        state=request.state,
        redirect_uri=request.redirect_uri,
    )
    return {
        "success": data["status"] == "connected",
        "data": data,
        "message": f"{data.get('display_name', 'Service')} connected and verified via OAuth 2.0.",
    }


@router.get("/oauth/{provider}/callback")
async def oauth_browser_redirect_callback(
    provider: str,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
):
    """Direct browser redirect target for third-party OAuth providers (Google / Meta)."""
    frontend_base = settings.frontend_url.rstrip("/")
    return_to = "/onboarding"

    if state:
        try:
            state_data = verify_oauth_state(state)
            candidate_return = str(state_data.get("return_to") or "/onboarding")
            if candidate_return.startswith("/") and not candidate_return.startswith("//"):
                return_to = candidate_return
        except Exception:
            state_data = None
    else:
        state_data = None

    err_sep = "&" if "?" in return_to else "?"

    if error:
        err_param = urllib.parse.quote(error_description or error or "access_denied")
        return RedirectResponse(
            f"{frontend_base}{return_to}{err_sep}error={err_param}&provider={provider}",
            status_code=302,
        )

    if not code or not state or not state_data:
        return RedirectResponse(
            f"{frontend_base}{return_to}{err_sep}error=missing_code_or_state&provider={provider}",
            status_code=302,
        )

    try:
        tenant_id_str = state_data.get("tenant_id")
        user_id_str = state_data.get("user_id")

        if not tenant_id_str:
            return RedirectResponse(
                f"{frontend_base}{return_to}{err_sep}error=invalid_state_tenant&provider={provider}",
                status_code=302,
            )

        tenant_id = uuid.UUID(tenant_id_str)
        user_id = uuid.UUID(user_id_str) if user_id_str else tenant_id

        await integration_service.handle_oauth_callback(
            session=session,
            tenant_id=tenant_id,
            user_id=user_id,
            code=code,
            state=state,
        )

        sep = "&" if "?" in return_to else "?"
        return RedirectResponse(
            f"{frontend_base}{return_to}{sep}connected={provider}&status=success",
            status_code=302,
        )
    except Exception as exc:
        err_msg = urllib.parse.quote(str(exc))
        return RedirectResponse(
            f"{frontend_base}{return_to}{err_sep}error={err_msg}&provider={provider}",
            status_code=302,
        )


@router.post("/whatsapp/connect", status_code=status.HTTP_201_CREATED)
async def connect_whatsapp_embedded_signup(
    request: WhatsAppConnectRequest,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Authorize and connect WhatsApp Business via Meta Embedded Signup OAuth code."""
    data = await integration_service.connect_whatsapp(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        oauth_code=request.oauth_code,
    )
    return {"success": True, "data": data, "message": "WhatsApp Business connected successfully"}


@router.post("/{provider}/connect", status_code=status.HTTP_201_CREATED)
async def connect_integration_provider(
    provider: str,
    request: ProviderConnectRequest,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Connect any supported third-party integration (OAuth or API Key), encrypt credentials, and test connection."""
    data = await integration_service.connect_provider(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        provider=provider,
        oauth_code=request.oauth_code,
        api_key=request.api_key,
        account_identifier=request.account_identifier,
        extra_config=request.configuration,
    )
    return {
        "success": data["status"] == "connected",
        "data": data,
        "message": (
            f"{data['display_name']} connected and verified."
            if data["status"] == "connected"
            else f"{data['display_name']} connection failed verification. Owner notified."
        ),
    }


@router.post("/{integration_id}/test")
async def test_integration_connection(
    integration_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Test an existing integration connection and update its status."""
    data = await integration_service.test_integration_connection(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        integration_id=integration_id,
    )
    return {"success": data["status"] == "connected", "data": data}


@router.get("/whatsapp/webhook", response_class=PlainTextResponse)
async def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """Meta WhatsApp Cloud API GET webhook subscription verification."""
    return whatsapp_client.verify_webhook_challenge(
        hub_mode=hub_mode,
        hub_verify_token=hub_verify_token,
        hub_challenge=hub_challenge,
    )


@router.post("/whatsapp/simulate")
async def simulate_whatsapp_inbound_message(
    request: WhatsAppInboundWebhookRequest,
    context: TenantContext = Depends(require_permission("integrations.read")),
    session: AsyncSession = Depends(get_db),
):
    """Tenant UI simulator for testing inbound WhatsApp message triage and financial guardrails."""
    result = await integration_service.process_inbound_whatsapp_message(
        session=session,
        tenant_id=context.tenant_id,
        sender_phone=request.sender_phone,
        sender_name=request.sender_name,
        message_text=request.message_text,
        message_id=request.message_id,
        user_id=context.user_id,
    )
    return {"success": True, "data": result}


@router.post("/whatsapp/webhook")
async def process_whatsapp_meta_webhook(
    raw_request: Request,
    session: AsyncSession = Depends(get_db),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
):
    """Meta WhatsApp Cloud API public inbound webhook receiver with HMAC-SHA256 signature verification."""
    body_bytes = await raw_request.body()

    # 1. Verify Meta signature if present or in production
    if not whatsapp_client.verify_webhook_signature(body_bytes, x_hub_signature_256):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "INVALID_META_SIGNATURE", "message": "X-Hub-Signature-256 verification failed"},
        )

    try:
        payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MALFORMED_JSON", "message": "Invalid JSON payload in webhook body"},
        )

    # 2. Process Meta Cloud API webhook events
    entries = payload.get("entry", [])
    processed_count = 0
    results = []

    for entry in entries:
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            contacts = {
                c.get("wa_id"): c.get("profile", {}).get("name", "WhatsApp Contact")
                for c in value.get("contacts", [])
            }

            # Find matching tenant by phone_number_id in integrations table
            tenant_id = None
            if phone_number_id:
                from app.database.models.automation import Integration
                stmt = select(Integration).where(
                    Integration.provider == "whatsapp",
                    Integration.status == "connected",
                )
                res = await session.execute(stmt)
                for integ_row in res.scalars().all():
                    cfg = integ_row.configuration or {}
                    if (
                        integ_row.external_account_id == phone_number_id
                        or cfg.get("phone_number_id") == phone_number_id
                    ):
                        tenant_id = integ_row.tenant_id
                        break

            if not tenant_id:
                logger.warning(
                    "WhatsApp webhook event skipped: unmatched phone_number_id",
                    phone_number_id=phone_number_id,
                )
                continue

            for msg in value.get("messages", []):
                msg_id = msg.get("id")
                sender_phone = msg.get("from", "")
                sender_name = contacts.get(sender_phone, "WhatsApp Contact")
                msg_text = msg.get("text", {}).get("body", "")

                if msg_text:
                    res = await integration_service.process_inbound_whatsapp_message(
                        session=session,
                        tenant_id=tenant_id,
                        sender_phone=sender_phone,
                        sender_name=sender_name,
                        message_text=msg_text,
                        message_id=msg_id,
                    )
                    results.append(res)
                    processed_count += 1

    # Support simple JSON fallback strictly in development/test with explicit X-Tenant-ID
    if (
        not entries
        and settings.app_env in ("development", "test")
        and "sender_phone" in payload
        and "message_text" in payload
    ):
        tenant_id = None
        header_tenant = raw_request.headers.get("x-tenant-id")
        if header_tenant:
            try:
                tenant_id = uuid.UUID(header_tenant)
            except ValueError:
                tenant_id = None

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "TENANT_HEADER_REQUIRED",
                    "message": "Valid X-Tenant-ID header is required for webhook fallback",
                },
            )

        from app.database.models.tenant import Tenant
        t_res = await session.execute(select(Tenant.id).where(Tenant.id == tenant_id))
        if not t_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "TENANT_NOT_FOUND", "message": "Tenant workspace not found"},
            )

        res = await integration_service.process_inbound_whatsapp_message(
            session=session,
            tenant_id=tenant_id,
            sender_phone=payload.get("sender_phone"),
            sender_name=payload.get("sender_name", "WhatsApp Contact"),
            message_text=payload.get("message_text"),
            message_id=payload.get("message_id"),
        )
        results.append(res)
        processed_count += 1

    return {
        "success": True,
        "processed": processed_count,
        "results": results,
        "data": results[0] if results else None,
    }


@router.post("/whatsapp/send")
async def send_whatsapp_message(
    request: WhatsAppOutboundRequest,
    context: TenantContext = Depends(require_permission("notifications.send")),
):
    """Send an outbound WhatsApp message to a customer or tenant member."""
    result = await whatsapp_client.send_text_message(
        tenant_id=str(context.tenant_id),
        to_phone=request.to_phone,
        message_body=request.message_body,
    )
    return {"success": True, "data": result}


@router.delete("/{integration_id}")
async def disconnect_integration(
    integration_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Revoke credentials and disconnect a tenant integration."""
    data = await integration_service.disconnect_integration(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        integration_id=integration_id,
    )
    return {"success": True, "data": data, "message": "Integration credentials revoked and disconnected"}
