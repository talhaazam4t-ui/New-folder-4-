"""Notification Engine Service (In-App, WhatsApp, and Email Alerts).
"""

import uuid
from typing import Any, Dict, List, Optional

from app.core.exceptions import ResourceNotFoundError
from app.database.models.automation import Notification
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class NotificationService:
    """Manages multi-channel tenant notifications and alert states."""

    def _to_dict(self, n: Notification) -> Dict[str, Any]:
        return {
            "id": str(n.id),
            "tenant_id": str(n.tenant_id),
            "user_id": str(n.user_id) if n.user_id else None,
            "channel": n.channel,
            "title": n.title,
            "message": n.message,
            "status": n.status,
            "created_at": n.created_at.isoformat(),
        }

    async def send_notification(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        title: str,
        message: str,
        channel: str = "in_app",
        user_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Create and dispatch a notification to the tenant workspace."""
        notif = Notification(
            tenant_id=tenant_id,
            user_id=user_id,
            channel=channel,
            title=title,
            message=message,
            status="unread",
        )
        session.add(notif)
        await session.commit()
        await session.refresh(notif)
        return self._to_dict(notif)

    async def list_notifications(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        status_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List notifications strictly isolated to the tenant."""
        query = select(Notification).where(Notification.tenant_id == tenant_id)
        if status_filter:
            query = query.where(Notification.status == status_filter)
        query = query.order_by(Notification.created_at.desc()).limit(limit)
        res = await session.execute(query)
        return [self._to_dict(row) for row in res.scalars().all()]

    async def mark_as_read(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        notification_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Mark a single notification as read."""
        res = await session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.tenant_id == tenant_id,
            )
        )
        notif = res.scalar_one_or_none()
        if not notif:
            raise ResourceNotFoundError("Notification", str(notification_id))
        notif.status = "read"
        await session.commit()
        await session.refresh(notif)
        return self._to_dict(notif)


notification_service = NotificationService()
