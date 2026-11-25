"""Unified CRM Live Inbox & Human-in-the-Loop (HITL) Takeover Service.

Uses `public.omnichannel_sessions` and `public.whatsapp_messages` so every inbound/outbound
WhatsApp message is threaded and a human staff member can pause AI auto-replies with 1 click.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.exceptions import ResourceNotFoundError
from app.database.models.automation import AuditLog
from app.database.models.knowledge import OmnichannelSession, WhatsAppMessage
from app.integrations.whatsapp.client import whatsapp_client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class InboxService:
    """Manages omnichannel conversation threads, message history, and live human takeover."""

    def _serialize_session(self, s: OmnichannelSession) -> Dict[str, Any]:
        history = list(s.conversation_history or [])
        last_preview = history[-1].get("content", "") if history and isinstance(history[-1], dict) else ""
        return {
            "id": str(s.id),
            "tenant_id": str(s.tenant_id),
            "lead_id": str(s.lead_id) if s.lead_id else None,
            "channel": s.channel,
            "external_user_id": s.external_user_id,
            "contact_name": s.contact_name or s.external_user_id,
            "status": s.status,
            "human_takeover": bool(s.human_takeover),
            "takeover_by": str(s.takeover_by) if s.takeover_by else None,
            "takeover_at": s.takeover_at.isoformat() if s.takeover_at else None,
            "last_message_at": s.last_message_at.isoformat() if s.last_message_at else None,
            "last_message_preview": str(last_preview)[:180],
            "message_count": len(history),
        }

    def _serialize_message(self, m: WhatsAppMessage) -> Dict[str, Any]:
        return {
            "id": str(m.id),
            "session_id": str(m.session_id),
            "message_id": m.message_id,
            "direction": m.direction,
            "sender_id": m.sender_id,
            "content": m.content,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
        }

    async def get_or_create_session(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        channel: str,
        external_user_id: str,
        contact_name: Optional[str] = None,
        lead_id: Optional[uuid.UUID] = None,
    ) -> OmnichannelSession:
        clean_ext = str(external_user_id or "unknown").strip()[:120]
        res = await session.execute(
            select(OmnichannelSession).where(
                OmnichannelSession.tenant_id == tenant_id,
                OmnichannelSession.channel == channel,
                OmnichannelSession.external_user_id == clean_ext,
            )
        )
        row = res.scalar_one_or_none()
        now_utc = datetime.now(timezone.utc)
        if row:
            if contact_name and not row.contact_name:
                row.contact_name = contact_name[:200]
            if lead_id and not row.lead_id:
                row.lead_id = lead_id
            row.last_message_at = now_utc
            await session.flush()
            return row

        row = OmnichannelSession(
            tenant_id=tenant_id,
            lead_id=lead_id,
            channel=channel,
            external_user_id=clean_ext,
            contact_name=(contact_name or clean_ext)[:200],
            status="active",
            last_message_at=now_utc,
            conversation_history=[],
            metadata_={},
            human_takeover=False,
        )
        session.add(row)
        await session.flush()
        return row

    async def record_message(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        chat_session: OmnichannelSession,
        direction: str,
        sender_id: Optional[str],
        content: str,
        message_id: Optional[str] = None,
        raw_payload: Optional[Dict[str, Any]] = None,
    ) -> WhatsAppMessage:
        now_utc = datetime.now(timezone.utc)
        msg = WhatsAppMessage(
            tenant_id=tenant_id,
            session_id=chat_session.id,
            message_id=message_id,
            direction=direction,
            sender_id=sender_id,
            content=content,
            raw_payload=dict(raw_payload or {}),
            timestamp=now_utc,
        )
        session.add(msg)

        history = list(chat_session.conversation_history or [])
        history.append(
            {
                "direction": direction,
                "sender_id": sender_id,
                "content": content[:500],
                "timestamp": now_utc.isoformat(),
            }
        )
        chat_session.conversation_history = history[-40:]
        chat_session.last_message_at = now_utc
        await session.flush()
        return msg

    async def list_conversations(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        takeover_only: Optional[bool] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query = select(OmnichannelSession).where(OmnichannelSession.tenant_id == tenant_id)
        if takeover_only is True:
            query = query.where(OmnichannelSession.human_takeover == True)  # noqa: E712
        elif takeover_only is False:
            query = query.where(OmnichannelSession.human_takeover == False)  # noqa: E712
        query = query.order_by(OmnichannelSession.last_message_at.desc()).limit(limit)
        res = await session.execute(query)
        return [self._serialize_session(r) for r in res.scalars().all()]

    async def get_conversation_messages(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        limit: int = 100,
    ) -> Dict[str, Any]:
        s_res = await session.execute(
            select(OmnichannelSession).where(
                OmnichannelSession.id == session_id,
                OmnichannelSession.tenant_id == tenant_id,
            )
        )
        chat_session = s_res.scalar_one_or_none()
        if not chat_session:
            raise ResourceNotFoundError("OmnichannelSession", str(session_id))

        m_res = await session.execute(
            select(WhatsAppMessage)
            .where(
                WhatsAppMessage.session_id == session_id,
                WhatsAppMessage.tenant_id == tenant_id,
            )
            .order_by(WhatsAppMessage.timestamp.asc())
            .limit(limit)
        )
        messages = [self._serialize_message(m) for m in m_res.scalars().all()]
        return {
            "session": self._serialize_session(chat_session),
            "messages": messages,
        }

    async def set_human_takeover(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        enabled: bool,
    ) -> Dict[str, Any]:
        res = await session.execute(
            select(OmnichannelSession).where(
                OmnichannelSession.id == session_id,
                OmnichannelSession.tenant_id == tenant_id,
            )
        )
        chat_session = res.scalar_one_or_none()
        if not chat_session:
            raise ResourceNotFoundError("OmnichannelSession", str(session_id))

        now_utc = datetime.now(timezone.utc)
        chat_session.human_takeover = bool(enabled)
        chat_session.takeover_by = user_id if enabled else None
        chat_session.takeover_at = now_utc if enabled else None

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=user_id,
                actor_type="user",
                action="inbox.human_takeover_toggled",
                resource_type="omnichannel_session",
                resource_id=chat_session.id,
                metadata_={"human_takeover": bool(enabled), "contact": chat_session.external_user_id},
            )
        )
        await session.commit()
        await session.refresh(chat_session)
        return self._serialize_session(chat_session)

    async def send_human_reply(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        message_body: str,
        enable_takeover: bool = True,
    ) -> Dict[str, Any]:
        s_res = await session.execute(
            select(OmnichannelSession).where(
                OmnichannelSession.id == session_id,
                OmnichannelSession.tenant_id == tenant_id,
            )
        )
        chat_session = s_res.scalar_one_or_none()
        if not chat_session:
            raise ResourceNotFoundError("OmnichannelSession", str(session_id))

        from app.services.integration_service import integration_service
        from app.services.wallet_service import wallet_service

        await wallet_service.assert_wallet_active(session, tenant_id, estimated_credits=1.0)
        wa_creds = await integration_service.get_tenant_whatsapp_credentials(session, tenant_id)
        send_res = await whatsapp_client.send_text_message(
            tenant_id=str(tenant_id),
            to_phone=chat_session.external_user_id,
            message_body=message_body,
            phone_number_id=wa_creds.get("phone_number_id"),
            access_token=wa_creds.get("access_token"),
        )

        if enable_takeover:
            chat_session.human_takeover = True
            chat_session.takeover_by = user_id
            chat_session.takeover_at = datetime.now(timezone.utc)

        msg = await self.record_message(
            session=session,
            tenant_id=tenant_id,
            chat_session=chat_session,
            direction="outbound",
            sender_id=f"human:{user_id}",
            content=message_body,
            message_id=send_res.get("message_id"),
            raw_payload={"human_reply": True, "dispatch": send_res},
        )
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=user_id,
                actor_type="user",
                action="inbox.human_reply_sent",
                resource_type="omnichannel_session",
                resource_id=chat_session.id,
                metadata_={"to": chat_session.external_user_id},
            )
        )
        await session.commit()
        await session.refresh(chat_session)
        await session.refresh(msg)

        await wallet_service.debit_credits(
            session=session,
            tenant_id=tenant_id,
            category="whatsapp_message",
            unit_count=1.0,
            description=f"Inbox human reply to {chat_session.external_user_id}",
            metadata={"session_id": str(chat_session.id)},
            enforce_pause=False,
        )

        return {
            "session": self._serialize_session(chat_session),
            "message": self._serialize_message(msg),
            "dispatch": send_res,
        }


inbox_service = InboxService()
