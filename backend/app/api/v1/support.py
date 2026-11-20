"""Tenant Support Request & Setup Assistance API Endpoints.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.core.tenant_context import TenantContext
from app.database.models.automation import AuditLog, Notification
from app.database.supabase import get_db
from app.dependencies import require_permission
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/support", tags=["Support"])


class SupportRequestCreate(BaseModel):
    subject: str = Field(min_length=2, max_length=200)
    message: str = Field(min_length=5, max_length=4000)
    category: str = Field(default="general", max_length=64)
    priority: str = Field(default="normal", max_length=32)
    provider: Optional[str] = Field(default=None, max_length=64)
    service_slug: Optional[str] = Field(default=None, max_length=100)
    contact_preference: str = Field(default="whatsapp", max_length=32)


def _get_support_whatsapp() -> tuple[str, str]:
    raw = (settings.support_whatsapp_number or "03238300330").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("0") and len(digits) == 11:
        intl_digits = f"92{digits[1:]}"
    elif digits.startswith("92"):
        intl_digits = digits
    else:
        intl_digits = "923238300330"
    return raw or "03238300330", f"https://wa.me/{intl_digits}"


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def create_support_request(
    request: SupportRequestCreate,
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Create a persistent tenant-scoped support or onboarding setup request."""
    ticket_uuid = uuid.uuid4()
    ticket_id = f"SUP-{str(ticket_uuid)[:8].upper()}"
    now = datetime.now(timezone.utc)
    whatsapp_number, whatsapp_url = _get_support_whatsapp()

    audit = AuditLog(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        actor_type="user",
        action="support.request.created",
        resource_type="support_request",
        resource_id=ticket_uuid,
        metadata_={
            "ticket_id": ticket_id,
            "subject": request.subject,
            "message": request.message,
            "category": request.category,
            "priority": request.priority,
            "provider": request.provider,
            "service_slug": request.service_slug,
            "contact_preference": request.contact_preference,
            "status": "open",
        },
        created_at=now,
    )
    session.add(audit)

    notification = Notification(
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        channel="in_app",
        title=f"Support Ticket {ticket_id}: {request.subject}",
        message=(
            f"Your support request ({request.category}, priority: {request.priority}) has been logged. "
            f"Need urgent help? WhatsApp {whatsapp_number}."
        ),
        status="unread",
    )
    session.add(notification)

    await session.commit()
    await session.refresh(audit)

    payload: Dict[str, Any] = {
        "id": str(ticket_uuid),
        "ticket_id": ticket_id,
        "tenant_id": str(context.tenant_id),
        "subject": request.subject,
        "category": request.category,
        "priority": request.priority,
        "provider": request.provider,
        "service_slug": request.service_slug,
        "status": "open",
        "message": request.message,
        "whatsapp_number": whatsapp_number,
        "whatsapp_url": whatsapp_url,
        "created_at": audit.created_at.isoformat(),
    }
    return {
        "success": True,
        "data": payload,
        **payload,
    }


@router.get("/requests")
async def list_support_requests(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """List support requests submitted by the authenticated tenant workspace."""
    res = await session.execute(
        select(AuditLog)
        .where(
            AuditLog.tenant_id == context.tenant_id,
            AuditLog.resource_type == "support_request",
            AuditLog.action == "support.request.created",
        )
        .order_by(AuditLog.created_at.desc())
    )
    rows = res.scalars().all()
    whatsapp_number, whatsapp_url = _get_support_whatsapp()

    items: List[Dict[str, Any]] = []
    for row in rows:
        meta = row.metadata_ or {}
        items.append(
            {
                "id": str(row.resource_id or row.id),
                "ticket_id": meta.get("ticket_id") or f"SUP-{str(row.resource_id or row.id)[:8].upper()}",
                "tenant_id": str(row.tenant_id),
                "subject": meta.get("subject", "Support Request"),
                "category": meta.get("category", "general"),
                "priority": meta.get("priority", "normal"),
                "provider": meta.get("provider"),
                "service_slug": meta.get("service_slug"),
                "status": meta.get("status", "open"),
                "message": meta.get("message", ""),
                "whatsapp_number": whatsapp_number,
                "whatsapp_url": whatsapp_url,
                "created_at": row.created_at.isoformat(),
            }
        )

    return {"success": True, "data": items}
