"""Notifications & Alert Engine API Endpoints.
"""

import uuid
from typing import Optional

from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.services.notification_service import notification_service
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    message: str = Field(min_length=2, max_length=2000)
    channel: str = Field(default="in_app", max_length=50)


@router.get("")
async def list_tenant_notifications(
    status_filter: Optional[str] = Query(None, alias="status"),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """List notifications for the authenticated tenant workspace."""
    items = await notification_service.list_notifications(
        session=session,
        tenant_id=context.tenant_id,
        status_filter=status_filter,
    )
    return {"success": True, "data": items}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_notification(
    request: NotificationCreateRequest,
    context: TenantContext = Depends(require_permission("notifications.send")),
    session: AsyncSession = Depends(get_db),
):
    """Send an in-app, WhatsApp, or email notification."""
    data = await notification_service.send_notification(
        session=session,
        tenant_id=context.tenant_id,
        title=request.title,
        message=request.message,
        channel=request.channel,
        user_id=context.user_id,
    )
    return {"success": True, "data": data}


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """Mark a notification as read."""
    data = await notification_service.mark_as_read(
        session=session,
        tenant_id=context.tenant_id,
        notification_id=notification_id,
    )
    return {"success": True, "data": data}
