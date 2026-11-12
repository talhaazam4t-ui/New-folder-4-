"""Integrations & WhatsApp Business Cloud API Endpoints (Section 11 & 13.9).

Supports:
1. Self-service Meta Embedded Signup OAuth connection (`POST /api/v1/integrations/whatsapp/connect`).
2. Meta WhatsApp Webhook challenge verification (`GET /api/v1/integrations/whatsapp/webhook`).
3. Inbound WhatsApp message processing with financial ambiguity protection (`POST /api/v1/integrations/whatsapp/webhook`).
4. Outbound WhatsApp messaging (`POST /api/v1/integrations/whatsapp/send`).
5. Listing and disconnecting tenant integrations (`GET /api/v1/integrations`, `DELETE /api/v1/integrations/{id}`).
"""

import uuid
from typing import Optional

from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.integrations.whatsapp.client import whatsapp_client
from app.services.integration_service import integration_service
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/integrations", tags=["Integrations & WhatsApp"])


class WhatsAppConnectRequest(BaseModel):
    oauth_code: str = Field(min_length=3, max_length=500, description="Meta Embedded Signup OAuth code")


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
    """List all connected integrations for the tenant."""
    items = await integration_service.list_integrations(session, context.tenant_id)
    return {"success": True, "data": items}


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
    """Disconnect a tenant integration."""
    data = await integration_service.disconnect_integration(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        integration_id=integration_id,
    )
    return {"success": True, "data": data, "message": "Integration disconnected"}
