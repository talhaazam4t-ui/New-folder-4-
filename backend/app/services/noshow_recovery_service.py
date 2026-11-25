"""No-Show Recovery & Smart Waitlist Rescheduling Service.

Implements:
1. Automated scheduling of WhatsApp Confirm / Reschedule reminders 2 hours before Cal.com appointments.
2. Interactive reply processing (`Confirm` vs `Reschedule`) updating `ReceptionistCallLog.booking_status`.
3. Waitlist auto-fill notifications via WhatsApp when an appointment slot opens up.
"""

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.exceptions import ResourceNotFoundError
from app.core.logging import logger
from app.database.models.automation import AuditLog
from app.database.models.marketing import Lead
from app.database.models.receptionist import ReceptionistCallLog, ReceptionistConfig
from app.integrations.whatsapp.client import whatsapp_client
from app.services.inbox_service import inbox_service
from app.services.job_engine_service import job_engine_service
from app.services.notification_service import notification_service
from app.services.wallet_service import _ensure_utc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _normalize_digits(phone: Optional[str]) -> str:
    return re.sub(r"[^\d]", "", phone or "")[-10:]


class NoShowRecoveryService:
    """Automates pre-appointment confirmations and waitlist slot filling via WhatsApp."""

    async def schedule_appointment_reminder(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        call_log: ReceptionistCallLog,
    ) -> Optional[Dict[str, Any]]:
        """Schedule an interactive WhatsApp reminder 2 hours before the booked appointment."""
        if not call_log.booked_appointment_at:
            return None

        now_utc = datetime.now(timezone.utc)
        appt_dt = _ensure_utc(call_log.booked_appointment_at) or (now_utc + timedelta(hours=3))
        reminder_dt = max(now_utc, appt_dt - timedelta(hours=2))

        job = await job_engine_service.enqueue_job(
            session=session,
            job_type="appointment_reminder",
            tenant_id=tenant_id,
            payload={"call_log_id": str(call_log.id)},
            run_at=reminder_dt,
            idempotency_key=f"appt_reminder:{call_log.id}",
        )
        return job

    async def dispatch_appointment_reminder(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        call_log_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Send an interactive WhatsApp Confirm/Reschedule prompt for an upcoming booking."""
        res = await session.execute(
            select(ReceptionistCallLog).where(
                ReceptionistCallLog.id == call_log_id,
                ReceptionistCallLog.tenant_id == tenant_id,
            )
        )
        call_log = res.scalar_one_or_none()
        if not call_log:
            raise ResourceNotFoundError("ReceptionistCallLog", str(call_log_id))

        if call_log.booking_status in ("confirmed", "cancelled", "completed"):
            return {"sent": False, "reason": f"booking_already_{call_log.booking_status}"}

        if not call_log.caller_phone or call_log.caller_phone == "Unknown":
            return {"sent": False, "reason": "missing_caller_phone"}

        cfg_res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id).limit(1)
        )
        cfg = cfg_res.scalar_one_or_none()
        business_name = cfg.business_name if cfg else "our office"
        appt_str = (
            call_log.booked_appointment_at.strftime("%b %d at %H:%M UTC")
            if call_log.booked_appointment_at
            else "your upcoming slot"
        )
        body_text = (
            f"Hi {call_log.caller_name or 'there'}, reminder from {business_name}: "
            f"you have an appointment scheduled for {appt_str}. Please confirm or reschedule below."
        )
        buttons = [
            {"id": f"appt_confirm:{call_log.id}", "title": "Confirm"},
            {"id": f"appt_reschedule:{call_log.id}", "title": "Reschedule"},
        ]

        from app.services.integration_service import integration_service

        wa_creds = await integration_service.get_tenant_whatsapp_credentials(session, tenant_id)
        send_res = await whatsapp_client.send_interactive_buttons(
            tenant_id=str(tenant_id),
            to_phone=call_log.caller_phone,
            body_text=body_text,
            buttons=buttons,
            phone_number_id=wa_creds.get("phone_number_id"),
            access_token=wa_creds.get("access_token"),
        )

        now_iso = datetime.now(timezone.utc).isoformat()
        meta = dict(call_log.metadata_ or {})
        meta["reminder_sent_at"] = now_iso
        meta["reminder_message_id"] = send_res.get("message_id")
        call_log.metadata_ = meta

        chat_session = await inbox_service.get_or_create_session(
            session=session,
            tenant_id=tenant_id,
            channel="whatsapp",
            external_user_id=call_log.caller_phone,
            contact_name=call_log.caller_name,
        )
        await inbox_service.record_message(
            session=session,
            tenant_id=tenant_id,
            chat_session=chat_session,
            direction="outbound",
            sender_id="ai_noshow_recovery",
            content=body_text,
            message_id=send_res.get("message_id"),
            raw_payload={"buttons": buttons},
        )
        await session.commit()

        return {
            "sent": True,
            "call_log_id": str(call_log.id),
            "message_id": send_res.get("message_id"),
            "to_phone": call_log.caller_phone,
        }

    async def notify_waitlist_for_open_slot(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        freed_call_log: ReceptionistCallLog,
        max_leads: int = 3,
    ) -> Dict[str, Any]:
        """Alert waitlisted leads via WhatsApp when an existing booking requests reschedule/cancel."""
        cfg_res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id).limit(1)
        )
        cfg = cfg_res.scalar_one_or_none()
        business_name = cfg.business_name if cfg else "our office"
        booking_link = (cfg.calcom_booking_url or "").strip() if cfg else ""
        slot_label = (
            freed_call_log.booked_appointment_at.strftime("%b %d at %H:%M UTC")
            if freed_call_log.booked_appointment_at
            else "today's newly opened slot"
        )

        l_res = await session.execute(
            select(Lead)
            .where(Lead.tenant_id == tenant_id, Lead.phone.is_not(None))
            .order_by(Lead.qualification_score.desc(), Lead.created_at.desc())
            .limit(40)
        )
        caller_digits = _normalize_digits(freed_call_log.caller_phone)
        candidates: List[Lead] = []
        for lead in l_res.scalars().all():
            meta = dict(lead.metadata_ or {})
            if meta.get("waitlist") is True and _normalize_digits(lead.phone) != caller_digits:
                candidates.append(lead)
            if len(candidates) >= max_leads:
                break

        from app.services.integration_service import integration_service

        wa_creds = await integration_service.get_tenant_whatsapp_credentials(session, tenant_id)
        notified_ids: List[str] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for lead in candidates:
            link_part = f" Book it right now here: {booking_link}" if booking_link else " Reply YES to claim it."
            msg_body = (
                f"Hi {lead.name}, an appointment slot just opened at {business_name} for {slot_label}.{link_part}"
            )
            try:
                await whatsapp_client.send_text_message(
                    tenant_id=str(tenant_id),
                    to_phone=lead.phone or "",
                    message_body=msg_body,
                    phone_number_id=wa_creds.get("phone_number_id"),
                    access_token=wa_creds.get("access_token"),
                )
                l_meta = dict(lead.metadata_ or {})
                l_meta["waitlist_notified_at"] = now_iso
                l_meta["waitlist_offer_slot"] = slot_label
                lead.metadata_ = l_meta
                notified_ids.append(str(lead.id))
            except Exception as exc:
                logger.warning("Waitlist WhatsApp send failed", lead_id=str(lead.id), error=str(exc))

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_type="system",
                action="appointment.waitlist_notified",
                resource_type="receptionist_call_log",
                resource_id=freed_call_log.id,
                metadata_={"notified_lead_ids": notified_ids, "slot": slot_label},
            )
        )
        await session.commit()

        if notified_ids:
            await notification_service.send_notification(
                session=session,
                tenant_id=tenant_id,
                title=f"Waitlist Activated for {slot_label}",
                message=f"{len(notified_ids)} waitlisted lead(s) were messaged on WhatsApp after a reschedule request.",
                channel="in_app",
            )

        return {"notified_count": len(notified_ids), "notified_lead_ids": notified_ids}

    async def handle_appointment_reply(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        sender_phone: str,
        reply_action: str,
        call_log_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Handle Confirm or Reschedule button/text reply from a booked attendee."""
        call_log: Optional[ReceptionistCallLog] = None
        if call_log_id:
            res = await session.execute(
                select(ReceptionistCallLog).where(
                    ReceptionistCallLog.id == call_log_id,
                    ReceptionistCallLog.tenant_id == tenant_id,
                )
            )
            call_log = res.scalar_one_or_none()

        if not call_log:
            sender_digits = _normalize_digits(sender_phone)
            res = await session.execute(
                select(ReceptionistCallLog)
                .where(
                    ReceptionistCallLog.tenant_id == tenant_id,
                    ReceptionistCallLog.booking_status.in_(["booked", "confirmed", "reschedule_requested"]),
                )
                .order_by(ReceptionistCallLog.created_at.desc())
                .limit(25)
            )
            for row in res.scalars().all():
                if _normalize_digits(row.caller_phone) == sender_digits or len(sender_digits) < 6:
                    call_log = row
                    break

        if not call_log:
            return {"handled": False, "reason": "no_matching_booking"}

        now_iso = datetime.now(timezone.utc).isoformat()
        meta = dict(call_log.metadata_ or {})
        action_lower = reply_action.strip().lower()

        if action_lower == "confirm":
            call_log.booking_status = "confirmed"
            meta["confirmed_at"] = now_iso
            meta["noshow_recovered"] = True
            call_log.metadata_ = meta
            await session.commit()

            await notification_service.send_notification(
                session=session,
                tenant_id=tenant_id,
                title="Appointment Confirmed via WhatsApp",
                message=f"{call_log.caller_name or call_log.caller_phone} confirmed their appointment.",
                channel="in_app",
            )
            return {
                "handled": True,
                "action": "confirm",
                "booking_status": "confirmed",
                "call_log_id": str(call_log.id),
                "reply_text": "Thank you! Your appointment is confirmed. We look forward to seeing you.",
                "waitlist_notified": 0,
            }

        call_log.booking_status = "reschedule_requested"
        meta["reschedule_requested_at"] = now_iso
        meta["noshow_recovered"] = True
        call_log.metadata_ = meta
        await session.commit()

        cfg_res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id).limit(1)
        )
        cfg = cfg_res.scalar_one_or_none()
        booking_url = (cfg.calcom_booking_url or "").strip() if cfg else ""
        waitlist_res = await self.notify_waitlist_for_open_slot(session, tenant_id, call_log)

        link_msg = f" You can pick a new time anytime here: {booking_url}" if booking_url else " Our team will help you pick a new time."
        return {
            "handled": True,
            "action": "reschedule",
            "booking_status": "reschedule_requested",
            "call_log_id": str(call_log.id),
            "reply_text": f"No problem — we freed up your previous slot.{link_msg}",
            "waitlist_notified": waitlist_res["notified_count"],
            "waitlist_lead_ids": waitlist_res["notified_lead_ids"],
        }

    async def set_lead_waitlist(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        lead_id: uuid.UUID,
        waitlisted: bool = True,
    ) -> Dict[str, Any]:
        res = await session.execute(
            select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id)
        )
        lead = res.scalar_one_or_none()
        if not lead:
            raise ResourceNotFoundError("Lead", str(lead_id))
        meta = dict(lead.metadata_ or {})
        meta["waitlist"] = bool(waitlisted)
        meta["waitlist_updated_at"] = datetime.now(timezone.utc).isoformat()
        lead.metadata_ = meta
        await session.commit()
        return {"lead_id": str(lead.id), "waitlist": bool(waitlisted), "name": lead.name}


noshow_recovery_service = NoShowRecoveryService()
