"""Integrations, One-Click OAuth & Credential Vault API Endpoints.

Supports:
1. Dynamic Onboarding Requirements based on selected industry & subscribed services (`GET /api/v1/integrations/onboarding-requirements`).
2. OAuth Authorization URL generation (`GET /api/v1/integrations/oauth/{provider}/authorize`).
3. Multi-provider One-Click OAuth / API-Key connection with encrypted credential storage (`POST /api/v1/integrations/{provider}/connect`).
4. Self-service Meta Embedded Signup OAuth connection (`POST /api/v1/integrations/whatsapp/connect`).
5. Connection testing, reconnection, and credential revocation (`POST /api/v1/integrations/{id}/test`, `DELETE /api/v1/integrations/{id}`).
6. Meta WhatsApp Webhook challenge verification & inbound message processing (`GET/POST /api/v1/integrations/whatsapp/webhook`).
"""

import uuid
from typing import Any, Dict, Optional

from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.integrations.whatsapp.client import whatsapp_client
from app.services.integration_service import (
    SUPPORTED_INTEGRATION_PROVIDERS,
    integration_service,
)
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/integrations", tags=["Integrations & WhatsApp"])


class WhatsAppConnectRequest(BaseModel):
    oauth_code: str = Field(min_length=3, max_length=500, description="Meta Embedded Signup OAuth code")


class ProviderConnectRequest(BaseModel):
    oauth_code: Optional[str] = Field(default=None, description="OAuth authorization callback code")
    api_key: Optional[str] = Field(default=None, description="API Key for providers without OAuth")
    account_identifier: Optional[str] = Field(default=None, description="External account email, phone, or ID")
    configuration: Optional[Dict[str, Any]] = None


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
    context: TenantContext = Depends(require_permission("integrations.manage")),
):
    """Generate OAuth authorization URL and scopes for a supported integration provider."""
    info = integration_service.get_oauth_authorization_info(provider, context.tenant_id)
    return {"success": True, "data": info}


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


@router.post("/whatsapp/webhook")
async def process_whatsapp_inbound_message(
    request: WhatsAppInboundWebhookRequest,
    context: TenantContext = Depends(require_permission("integrations.read")),
    session: AsyncSession = Depends(get_db),
):
    """Process an inbound WhatsApp message with financial ambiguity and lead routing."""
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
