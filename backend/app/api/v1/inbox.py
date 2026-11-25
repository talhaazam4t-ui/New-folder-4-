"""Unified CRM Live Inbox & Human-in-the-Loop (HITL) Takeover API Endpoints."""

import uuid
from typing import Optional

from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.services.inbox_service import inbox_service
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/inbox", tags=["CRM Live Inbox"])


class TakeoverToggleRequest(BaseModel):
    enabled: bool = True


class InboxReplyRequest(BaseModel):
    message_body: str = Field(min_length=1, max_length=2000)
    enable_takeover: bool = True


@router.get("/conversations")
async def list_inbox_conversations(
    takeover_only: Optional[bool] = Query(default=None),
    limit: int = Query(50, ge=1, le=100),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """List omnichannel conversations (WhatsApp/Social) strictly isolated to the workspace."""
    items = await inbox_service.list_conversations(
        session=session,
        tenant_id=context.tenant_id,
        takeover_only=takeover_only,
        limit=limit,
    )
    return {"success": True, "data": items}


@router.get("/conversations/{session_id}/messages")
async def get_conversation_thread(
    session_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=300),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """Fetch full ordered message thread and takeover status for a single conversation."""
    data = await inbox_service.get_conversation_messages(
        session=session,
        tenant_id=context.tenant_id,
        session_id=session_id,
        limit=limit,
    )
    return {"success": True, "data": data}


@router.post("/conversations/{session_id}/takeover")
async def toggle_human_takeover(
    session_id: uuid.UUID,
    request: TakeoverToggleRequest,
    context: TenantContext = Depends(require_permission("notifications.send")),
    session: AsyncSession = Depends(get_db),
):
    """Enable or disable 1-click HITL takeover (immediately pausing or resuming AI auto-replies)."""
    updated = await inbox_service.set_human_takeover(
        session=session,
        tenant_id=context.tenant_id,
        session_id=session_id,
        user_id=context.user_id,
        enabled=request.enabled,
    )
    return {
        "success": True,
        "data": updated,
        "message": "Human takeover enabled — AI auto-replies paused" if updated["human_takeover"] else "AI auto-replies resumed",
    }


@router.post("/conversations/{session_id}/reply")
async def send_inbox_human_reply(
    session_id: uuid.UUID,
    request: InboxReplyRequest,
    context: TenantContext = Depends(require_permission("notifications.send")),
    session: AsyncSession = Depends(get_db),
):
    """Dispatch a live human reply via WhatsApp and log it into the unified inbox thread."""
    res = await inbox_service.send_human_reply(
        session=session,
        tenant_id=context.tenant_id,
        session_id=session_id,
        user_id=context.user_id,
        message_body=request.message_body,
        enable_takeover=request.enable_takeover,
    )
    return {"success": True, "data": res}
