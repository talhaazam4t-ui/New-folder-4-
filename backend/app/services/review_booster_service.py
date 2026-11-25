"""Smart Google Review Booster Service (1-5 Star Sentiment Routing).

Workflow (zero third-party tools):
1. Schedules an automated review prompt 1 hour after each completed Cal.com appointment (`job_engine_service`).
2. Sends WhatsApp interactive buttons / 1-5 rating prompt.
3. 4-5 Star rating -> thanks customer and routes directly to tenant's Google Business Profile review link.
4. 1-3 Star rating -> intercepts privately, omits public Google link, notifies workspace owner, and captures private feedback.
"""

import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.core.exceptions import ResourceNotFoundError
from app.database.models.automation import AuditLog
from app.database.models.receptionist import ReceptionistCallLog, ReceptionistConfig
from app.database.models.tenant import Tenant
from app.database.models.upsells import ReviewRequest
from app.integrations.whatsapp.client import whatsapp_client
from app.services.inbox_service import inbox_service
from app.services.job_engine_service import job_engine_service
from app.services.notification_service import notification_service
from app.services.wallet_service import _ensure_utc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_STAR_REPLY_RE = re.compile(r"^(?:rating\s*[:=]?\s*)?([1-5])(?:\s*(?:/\s*5|stars?|star))?$", re.IGNORECASE)


def _normalize_digits(phone: Optional[str]) -> str:
    return re.sub(r"[^\d]", "", phone or "")[-10:]


class ReviewBoosterService:
    """Native Smart Google Review Booster & Negative Review Shield."""

    @staticmethod
    def _serialize_request(row: ReviewRequest) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "call_log_id": str(row.call_log_id) if row.call_log_id else None,
            "lead_id": str(row.lead_id) if row.lead_id else None,
            "customer_name": row.customer_name,
            "customer_phone": row.customer_phone,
            "rating": row.rating,
            "status": row.status,
            "routing_target": row.routing_target,
            "google_review_url": row.google_review_url,
            "private_feedback": row.private_feedback,
            "feedback_token": row.feedback_token,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            "responded_at": row.responded_at.isoformat() if row.responded_at else None,
        }

    async def get_config(self, session: AsyncSession, tenant_id: uuid.UUID) -> Dict[str, Any]:
        t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = t_res.scalar_one_or_none()
        if not tenant:
            raise ResourceNotFoundError("Tenant", str(tenant_id))
        rb = dict((tenant.settings or {}).get("review_booster") or {})
        return {
            "enabled": rb.get("enabled", True),
            "google_review_url": rb.get("google_review_url") or "",
            "delay_minutes": int(rb.get("delay_minutes") or 60),
            "business_name": rb.get("business_name") or tenant.name,
        }

    async def update_config(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        enabled: bool = True,
        google_review_url: Optional[str] = None,
        delay_minutes: int = 60,
        business_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = t_res.scalar_one_or_none()
        if not tenant:
            raise ResourceNotFoundError("Tenant", str(tenant_id))
        settings_copy = dict(tenant.settings or {})
        prev = dict(settings_copy.get("review_booster") or {})
        prev["enabled"] = bool(enabled)
        if google_review_url is not None:
            prev["google_review_url"] = google_review_url.strip()
        prev["delay_minutes"] = max(5, min(int(delay_minutes), 1440))
        if business_name is not None:
            prev["business_name"] = business_name.strip() or tenant.name
        settings_copy["review_booster"] = prev
        tenant.settings = settings_copy
        await session.commit()
        return await self.get_config(session, tenant_id)

    async def schedule_post_appointment_review(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        call_log: ReceptionistCallLog,
    ) -> Optional[Dict[str, Any]]:
        """Schedule a WhatsApp 1-5 rating prompt 1 hour (or tenant delay_minutes) after booking time."""
        if not call_log.booked_appointment_at:
            return None
        cfg = await self.get_config(session, tenant_id)
        if not cfg["enabled"]:
            return None

        now_utc = datetime.now(timezone.utc)
        appt_dt = _ensure_utc(call_log.booked_appointment_at) or now_utc
        run_at = max(now_utc, appt_dt + timedelta(minutes=int(cfg["delay_minutes"])))
        return await job_engine_service.enqueue_job(
            session=session,
            job_type="review_booster_prompt",
            tenant_id=tenant_id,
            payload={
                "call_log_id": str(call_log.id),
                "customer_phone": call_log.caller_phone,
                "customer_name": call_log.caller_name,
            },
            run_at=run_at,
            idempotency_key=f"review_booster:{call_log.id}",
        )

    async def dispatch_review_prompt(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        customer_phone: str,
        customer_name: Optional[str] = None,
        call_log_id: Optional[uuid.UUID] = None,
        lead_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Send interactive 1-5 star WhatsApp rating prompt & persist ReviewRequest."""
        clean_phone = (customer_phone or "").strip()
        if not clean_phone or clean_phone == "Unknown":
            return {"sent": False, "reason": "missing_customer_phone"}

        if call_log_id:
            existing_res = await session.execute(
                select(ReviewRequest).where(
                    ReviewRequest.tenant_id == tenant_id,
                    ReviewRequest.call_log_id == call_log_id,
                ).limit(1)
            )
            existing = existing_res.scalar_one_or_none()
            if existing:
                return {"sent": True, "idempotent": True, "request": self._serialize_request(existing)}

        cfg = await self.get_config(session, tenant_id)
        rec_res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id).limit(1)
        )
        rec_cfg = rec_res.scalar_one_or_none()
        biz_name = cfg.get("business_name") or (rec_cfg.business_name if rec_cfg else "our team")
        g_url = cfg.get("google_review_url") or f"{settings.frontend_url.rstrip('/')}/reviews"

        req_row = ReviewRequest(
            tenant_id=tenant_id,
            call_log_id=call_log_id,
            lead_id=lead_id,
            customer_name=customer_name or "Valued Customer",
            customer_phone=clean_phone,
            status="sent",
            google_review_url=g_url,
            feedback_token=secrets.token_urlsafe(18),
        )
        session.add(req_row)
        await session.flush()

        body_text = (
            f"Hi {req_row.customer_name}! Thank you for visiting {biz_name}. "
            f"How would you rate your experience from 1 to 5 stars? Tap a button or reply with 1-5."
        )
        buttons = [
            {"id": f"review_rate:{req_row.id}:5", "title": "5 Stars - Great"},
            {"id": f"review_rate:{req_row.id}:4", "title": "4 Stars - Good"},
            {"id": f"review_rate:{req_row.id}:2", "title": "1-3 Needs Help"},
        ]

        from app.services.integration_service import integration_service

        wa_creds = await integration_service.get_tenant_whatsapp_credentials(session, tenant_id)
        send_res = await whatsapp_client.send_interactive_buttons(
            tenant_id=str(tenant_id),
            to_phone=clean_phone,
            body_text=body_text,
            buttons=buttons,
            phone_number_id=wa_creds.get("phone_number_id"),
            access_token=wa_creds.get("access_token"),
        )

        chat_sess = await inbox_service.get_or_create_session(
            session=session,
            tenant_id=tenant_id,
            channel="whatsapp",
            external_user_id=clean_phone,
            contact_name=req_row.customer_name,
            lead_id=lead_id,
        )
        await inbox_service.record_message(
            session=session,
            tenant_id=tenant_id,
            chat_session=chat_sess,
            direction="outbound",
            sender_id="ai_review_booster",
            content=body_text,
            message_id=send_res.get("message_id"),
        )
        await session.commit()
        await session.refresh(req_row)
        return {"sent": True, "idempotent": False, "request": self._serialize_request(req_row)}

    async def handle_whatsapp_rating_reply(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        sender_phone: str,
        message_text: str,
        interactive_reply_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Route 4-5 star replies to Google Business URL and 1-3 star replies privately to owner."""
        target_req: Optional[ReviewRequest] = None
        rating_val: Optional[int] = None

        reply_id = (interactive_reply_id or "").strip()
        if reply_id.startswith("review_rate:"):
            parts = reply_id.split(":")
            if len(parts) == 3:
                try:
                    req_uuid = uuid.UUID(parts[1])
                    rating_val = max(1, min(5, int(parts[2])))
                    res = await session.execute(
                        select(ReviewRequest).where(
                            ReviewRequest.id == req_uuid,
                            ReviewRequest.tenant_id == tenant_id,
                        )
                    )
                    target_req = res.scalar_one_or_none()
                except Exception:
                    target_req = None

        if not target_req:
            phone_tail = _normalize_digits(sender_phone)
            all_res = await session.execute(
                select(ReviewRequest)
                .where(ReviewRequest.tenant_id == tenant_id)
                .order_by(ReviewRequest.created_at.desc())
                .limit(30)
            )
            for row in all_res.scalars().all():
                if _normalize_digits(row.customer_phone) == phone_tail or row.customer_phone == sender_phone:
                    target_req = row
                    break

        if not target_req:
            return {"handled": False}

        # Case A: awaiting initial 1-5 rating
        if target_req.status == "sent":
            if rating_val is None:
                m = _STAR_REPLY_RE.match((message_text or "").strip())
                if not m:
                    return {"handled": False}
                rating_val = int(m.group(1))

            now_utc = datetime.now(timezone.utc)
            target_req.rating = rating_val
            target_req.responded_at = now_utc

            if rating_val >= 4:
                cfg = await self.get_config(session, tenant_id)
                review_url = cfg.get("google_review_url") or target_req.google_review_url or ""
                target_req.google_review_url = review_url
                target_req.status = "rated_positive"
                target_req.routing_target = "google_business"
                reply_text = (
                    f"Thank you for your {rating_val}-star rating! It means a lot to us. "
                    f"Could you tap below to leave a quick Google review? {review_url}"
                ).strip()
                session.add(
                    AuditLog(
                        tenant_id=tenant_id,
                        actor_type="system",
                        action="growth.review.routed_google",
                        resource_type="review_request",
                        resource_id=target_req.id,
                        metadata_={"rating": rating_val, "google_review_url": review_url},
                    )
                )
                await session.commit()
                return {
                    "handled": True,
                    "outcome": "google_review",
                    "rating": rating_val,
                    "google_review_url": review_url,
                    "reply_text": reply_text,
                    "request": self._serialize_request(target_req),
                }

            # Negative (1-3 stars): NEVER emit Google Business Review URL! Route privately.
            target_req.status = "rated_negative"
            target_req.routing_target = "internal_feedback"
            feedback_link = f"{settings.frontend_url.rstrip('/')}/feedback?token={target_req.feedback_token}"
            reply_text = (
                f"We're sorry your experience rated {rating_val}/5. Your feedback goes straight to our manager — "
                f"please reply right here with what happened or fill out this private form: {feedback_link}"
            )
            await notification_service.send_notification(
                session=session,
                tenant_id=tenant_id,
                title=f"Low Rating Alert ({rating_val}/5) Intercepted Privately",
                message=f"{target_req.customer_name or sender_phone} rated {rating_val} stars. Routed away from Google to private feedback.",
                channel="in_app",
            )
            session.add(
                AuditLog(
                    tenant_id=tenant_id,
                    actor_type="system",
                    action="growth.review.intercepted_private",
                    resource_type="review_request",
                    resource_id=target_req.id,
                    metadata_={"rating": rating_val},
                )
            )
            await session.commit()
            return {
                "handled": True,
                "outcome": "private_feedback",
                "rating": rating_val,
                "feedback_link": feedback_link,
                "reply_text": reply_text,
                "request": self._serialize_request(target_req),
            }

        # Case B: already rated 1-3 and waiting on WhatsApp follow-up text
        if target_req.status == "rated_negative" and not target_req.private_feedback and (message_text or "").strip():
            target_req.private_feedback = message_text.strip()
            target_req.status = "feedback_submitted"
            await notification_service.send_notification(
                session=session,
                tenant_id=tenant_id,
                title=f"Private Feedback Received from {target_req.customer_name or sender_phone}",
                message=message_text.strip()[:280],
                channel="in_app",
            )
            await session.commit()
            return {
                "handled": True,
                "outcome": "private_feedback_captured",
                "reply_text": "Thank you for sharing this privately. Our management team is reviewing it now and will make things right.",
                "request": self._serialize_request(target_req),
            }

        return {"handled": False}

    async def submit_public_private_feedback(
        self,
        session: AsyncSession,
        feedback_token: str,
        feedback_text: str,
        customer_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        res = await session.execute(
            select(ReviewRequest).where(ReviewRequest.feedback_token == feedback_token.strip()).limit(1)
        )
        row = res.scalar_one_or_none()
        if not row:
            raise ResourceNotFoundError("ReviewRequest", "invalid_token")
        row.private_feedback = feedback_text.strip()
        if customer_name and customer_name.strip():
            row.customer_name = customer_name.strip()
        row.status = "feedback_submitted"
        row.responded_at = row.responded_at or datetime.now(timezone.utc)
        await notification_service.send_notification(
            session=session,
            tenant_id=row.tenant_id,
            title=f"Private Feedback Form Submitted ({row.rating or '?'}/5)",
            message=f"{row.customer_name or row.customer_phone}: {row.private_feedback[:240]}",
            channel="in_app",
        )
        await session.commit()
        await session.refresh(row)
        return self._serialize_request(row)

    async def list_requests_and_stats(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        limit: int = 50,
    ) -> Dict[str, Any]:
        res = await session.execute(
            select(ReviewRequest)
            .where(ReviewRequest.tenant_id == tenant_id)
            .order_by(ReviewRequest.created_at.desc())
            .limit(limit)
        )
        rows = res.scalars().all()
        rated = [int(r.rating) for r in rows if r.rating is not None]
        avg_rating = round(sum(rated) / len(rated), 2) if rated else 0.0
        google_cnt = sum(1 for r in rows if r.routing_target == "google_business")
        priv_cnt = sum(1 for r in rows if r.routing_target == "internal_feedback")
        return {
            "stats": {
                "total_sent": len(rows),
                "responded_count": len(rated),
                "average_rating": avg_rating,
                "google_routed_count": google_cnt,
                "private_intercepted_count": priv_cnt,
            },
            "requests": [self._serialize_request(r) for r in rows],
        }


review_booster_service = ReviewBoosterService()
