"""AI Call Sentiment, Lead Scoring & Weekly ROI Summary Service.

Implements:
1. Post-call sentiment (`positive`/`neutral`/`negative`) & lead qualification (`hot`/`warm`/`cold`, 0-100 score).
2. Automatic CRM `Lead` synchronization from call logs.
3. Weekly ROI summary aggregation (`calls_handled`, `appointments_booked`, `noshows_recovered`, `estimated_revenue_saved`).
4. Automated Monday morning (and on-demand) delivery via Email (Resend) & WhatsApp.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.integrations.ai_providers.router import route_and_execute_ai_task
from app.core.logging import logger
from app.database.models.automation import AuditLog
from app.database.models.knowledge import WhatsAppMessage
from app.database.models.marketing import Lead
from app.database.models.receptionist import ReceptionistCallLog, ReceptionistConfig
from app.database.models.tenant import Profile, Tenant, TenantMember
from app.integrations.email.adapter import email_adapter
from app.integrations.whatsapp.client import whatsapp_client
from app.services.notification_service import notification_service
from app.services.wallet_service import _ensure_utc
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def _heuristic_call_intelligence(call_log: ReceptionistCallLog) -> Dict[str, Any]:
    text_blob = f"{call_log.summary or ''} {call_log.transcript or ''}".lower()
    if call_log.booking_status in ("booked", "confirmed"):
        return {
            "sentiment": "positive",
            "lead_tier": "hot",
            "lead_score": 92,
            "ai_summary": call_log.summary or "Caller booked an appointment via AI Receptionist.",
        }
    if any(w in text_blob for w in ("angry", "complaint", "refund", "cancel", "stop calling", "terrible", "frustrated")):
        return {
            "sentiment": "negative",
            "lead_tier": "cold",
            "lead_score": 25,
            "ai_summary": call_log.summary or "Caller expressed dissatisfaction or cancellation intent.",
        }
    if any(w in text_blob for w in ("urgent", "emergency", "book", "schedule", "appointment", "price", "quote", "start")):
        return {
            "sentiment": "positive",
            "lead_tier": "hot",
            "lead_score": 84,
            "ai_summary": call_log.summary or "High-intent inquiry ready for booking/follow-up.",
        }
    if any(w in text_blob for w in ("hours", "services", "location", "question", "info", "details")):
        return {
            "sentiment": "neutral",
            "lead_tier": "warm",
            "lead_score": 65,
            "ai_summary": call_log.summary or "General business/FAQ inquiry handled by AI.",
        }
    return {
        "sentiment": "neutral",
        "lead_tier": "warm",
        "lead_score": 55,
        "ai_summary": call_log.summary or "Completed inbound voice call.",
    }


def _parse_intelligence_json(raw: str) -> Optional[Dict[str, Any]]:
    text_val = (raw or "").strip()
    if not text_val or "[mock" in text_val.lower():
        return None
    start = text_val.find("{")
    end = text_val.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text_val[start : end + 1])
    except Exception:
        return None
    sentiment = str(obj.get("sentiment") or "").strip().lower()
    tier = str(obj.get("lead_tier") or "").strip().lower()
    if sentiment not in ("positive", "neutral", "negative") or tier not in ("hot", "warm", "cold"):
        return None
    try:
        score = min(max(int(obj.get("lead_score") or 60), 0), 100)
    except Exception:
        score = 60
    summary = str(obj.get("ai_summary") or "").strip()[:400]
    return {
        "sentiment": sentiment,
        "lead_tier": tier,
        "lead_score": score,
        "ai_summary": summary,
    }


class CallIntelligenceService:
    """Computes call sentiment/lead scores and generates/delivers Weekly ROI Reports."""

    async def analyze_call_and_score_lead(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        call_log: ReceptionistCallLog,
    ) -> Dict[str, Any]:
        """Classify sentiment + Hot/Warm/Cold score and synchronize into CRM Leads."""
        baseline = _heuristic_call_intelligence(call_log)
        parsed_ai: Optional[Dict[str, Any]] = None

        prompt = (
            "Classify this business phone call and return strict JSON with keys: "
            '"sentiment" (positive|neutral|negative), "lead_tier" (hot|warm|cold), '
            '"lead_score" (0-100 int), "ai_summary" (max 160 chars).\n'
            f"Booking Status: {call_log.booking_status}\n"
            f"Transferred to Human: {call_log.transferred_to_human}\n"
            f"Summary: {call_log.summary or ''}\n"
            f"Transcript: {(call_log.transcript or '')[:1200]}\n"
            "Return ONLY valid JSON."
        )
        try:
            ai_res = await route_and_execute_ai_task(
                task_type="lead_scoring",
                prompt=prompt,
                tenant_id=str(tenant_id),
            )
            if ai_res.success and ai_res.content:
                parsed_ai = _parse_intelligence_json(ai_res.content)
        except Exception as exc:
            logger.debug("AI call scoring fell back to deterministic heuristic", error=str(exc))

        result = parsed_ai or baseline
        if not result.get("ai_summary"):
            result["ai_summary"] = baseline["ai_summary"]

        new_meta = dict(call_log.metadata_ or {})
        new_meta["call_intelligence"] = result
        call_log.metadata_ = new_meta

        # Sync or upsert CRM Lead if phone is known
        caller_phone = (call_log.caller_phone or "").strip()
        if caller_phone and caller_phone != "Unknown":
            l_res = await session.execute(
                select(Lead).where(Lead.tenant_id == tenant_id, Lead.phone == caller_phone).limit(1)
            )
            lead = l_res.scalar_one_or_none()
            lead_status = (
                "qualified"
                if result["lead_tier"] == "hot"
                else ("contacted" if result["lead_tier"] == "warm" else "new")
            )
            if lead:
                lead.qualification_score = max(int(lead.qualification_score or 0), int(result["lead_score"]))
                if result["lead_tier"] == "hot":
                    lead.status = "qualified"
                l_meta = dict(lead.metadata_ or {})
                l_meta["lead_tier"] = result["lead_tier"]
                l_meta["call_sentiment"] = result["sentiment"]
                l_meta["last_call_log_id"] = str(call_log.id)
                lead.metadata_ = l_meta
            else:
                session.add(
                    Lead(
                        tenant_id=tenant_id,
                        name=call_log.caller_name or f"Voice Caller ({caller_phone[-4:]})",
                        phone=caller_phone,
                        source="voice_receptionist",
                        status=lead_status,
                        qualification_score=int(result["lead_score"]),
                        metadata_={
                            "lead_tier": result["lead_tier"],
                            "call_sentiment": result["sentiment"],
                            "last_call_log_id": str(call_log.id),
                            "notes": result["ai_summary"],
                        },
                    )
                )

        await session.commit()
        return result

    async def build_weekly_roi_report(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        days: int = 7,
    ) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(days=days)

        t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = t_res.scalar_one_or_none()
        t_settings = dict(tenant.settings or {}) if tenant else {}
        avg_booking_value = float(t_settings.get("avg_booking_value_usd") or 150.0)

        c_res = await session.execute(
            select(ReceptionistCallLog).where(ReceptionistCallLog.tenant_id == tenant_id)
        )
        calls = [
            c
            for c in c_res.scalars().all()
            if (_ensure_utc(c.created_at) or now_utc) >= cutoff
        ]

        hot_leads = 0
        warm_leads = 0
        cold_leads = 0
        appointments_booked = 0
        appointments_confirmed = 0
        noshows_recovered = 0
        positive_calls = 0

        for c in calls:
            meta = dict(c.metadata_ or {})
            intel = meta.get("call_intelligence") or {}
            tier = str(intel.get("lead_tier") or "").lower()
            sent = str(intel.get("sentiment") or "").lower()
            if tier == "hot":
                hot_leads += 1
            elif tier == "warm":
                warm_leads += 1
            elif tier == "cold":
                cold_leads += 1
            if sent == "positive":
                positive_calls += 1

            if c.booking_status in ("booked", "confirmed", "reschedule_requested"):
                appointments_booked += 1
            if c.booking_status == "confirmed":
                appointments_confirmed += 1
            if meta.get("noshow_recovered") is True or c.booking_status == "confirmed":
                noshows_recovered += 1

        wa_count_res = await session.execute(
            select(func.count(WhatsAppMessage.id)).where(
                WhatsAppMessage.tenant_id == tenant_id,
                WhatsAppMessage.timestamp >= cutoff,
            )
        )
        whatsapp_messages = int(wa_count_res.scalar() or 0)

        estimated_revenue = round(appointments_booked * avg_booking_value, 2)
        hours_saved = round((len(calls) * 0.12) + (whatsapp_messages * 0.05), 1)

        return {
            "tenant_id": str(tenant_id),
            "tenant_name": tenant.name if tenant else "Workspace",
            "period_days": days,
            "generated_at": now_utc.isoformat(),
            "calls_handled": len(calls),
            "appointments_booked": appointments_booked,
            "appointments_confirmed": appointments_confirmed,
            "noshows_recovered": noshows_recovered,
            "whatsapp_messages_handled": whatsapp_messages,
            "hot_leads": hot_leads,
            "warm_leads": warm_leads,
            "cold_leads": cold_leads,
            "positive_calls": positive_calls,
            "avg_booking_value_usd": avg_booking_value,
            "estimated_revenue_saved": estimated_revenue,
            "estimated_hours_saved": hours_saved,
        }

    async def send_weekly_roi_report(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Deliver Weekly ROI Summary via Resend Email + WhatsApp + In-App Notification."""
        report = await self.build_weekly_roi_report(session, tenant_id, days=7)

        # Find workspace owner email
        owner_q = (
            select(Profile.email)
            .join(TenantMember, TenantMember.user_id == Profile.id)
            .where(TenantMember.tenant_id == tenant_id, TenantMember.role.in_(["owner", "client_owner", "admin"]))
            .limit(1)
        )
        owner_email = (await session.execute(owner_q)).scalar_one_or_none()

        cfg_q = select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id).limit(1)
        cfg = (await session.execute(cfg_q)).scalar_one_or_none()
        target_phone = cfg.fallback_phone_number if cfg and cfg.fallback_phone_number else None

        subject = f"Weekly AI ROI Report — {report['tenant_name']}: ${report['estimated_revenue_saved']:,.0f} Value"
        text_summary = (
            f"Weekly AI Performance Summary for {report['tenant_name']} (Last 7 Days):\n"
            f"- Calls Handled: {report['calls_handled']} ({report['positive_calls']} positive)\n"
            f"- Hot / Warm / Cold Leads: {report['hot_leads']} / {report['warm_leads']} / {report['cold_leads']}\n"
            f"- Appointments Booked: {report['appointments_booked']} ({report['noshows_recovered']} confirmed/recovered)\n"
            f"- WhatsApp Messages Automated: {report['whatsapp_messages_handled']}\n"
            f"- Estimated Revenue Protected: ${report['estimated_revenue_saved']:,.2f}\n"
            f"- Staff Time Saved: ~{report['estimated_hours_saved']} hrs"
        )
        html_summary = (
            f"<h2>{subject}</h2>"
            f"<p>Here is your automated 7-day ROI breakdown for <strong>{report['tenant_name']}</strong>:</p>"
            f"<ul>"
            f"<li><strong>Calls Handled:</strong> {report['calls_handled']} ({report['positive_calls']} positive sentiment)</li>"
            f"<li><strong>Lead Scoring:</strong> {report['hot_leads']} Hot / {report['warm_leads']} Warm / {report['cold_leads']} Cold</li>"
            f"<li><strong>Appointments Booked:</strong> {report['appointments_booked']} ({report['noshows_recovered']} confirmed/recovered)</li>"
            f"<li><strong>WhatsApp Conversations:</strong> {report['whatsapp_messages_handled']} messages</li>"
            f"<li><strong>Estimated Revenue Protected:</strong> ${report['estimated_revenue_saved']:,.2f}</li>"
            f"</ul>"
        )

        email_result: Dict[str, Any] = {"skipped": "no_owner_email"}
        if owner_email:
            email_result = await email_adapter.send_transactional_email(
                to_email=owner_email,
                subject=subject,
                html_body=html_summary,
                text_body=text_summary,
            )

        wa_result: Dict[str, Any] = {"skipped": "no_phone_configured"}
        if target_phone and target_phone != "+10000000000":
            from app.services.integration_service import integration_service

            wa_creds = await integration_service.get_tenant_whatsapp_credentials(session, tenant_id)
            wa_result = await whatsapp_client.send_text_message(
                tenant_id=str(tenant_id),
                to_phone=target_phone,
                message_body=text_summary,
                phone_number_id=wa_creds.get("phone_number_id"),
                access_token=wa_creds.get("access_token"),
            )

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="analytics.weekly_roi_sent",
                resource_type="tenant",
                resource_id=tenant_id,
                metadata_={
                    "owner_email": owner_email,
                    "estimated_revenue_saved": report["estimated_revenue_saved"],
                },
            )
        )
        await session.commit()

        await notification_service.send_notification(
            session=session,
            tenant_id=tenant_id,
            title="Weekly AI ROI Report Ready",
            message=(
                f"{report['calls_handled']} calls, {report['appointments_booked']} bookings, "
                f"${report['estimated_revenue_saved']:,.0f} estimated value delivered."
            ),
            channel="in_app",
        )

        return {
            "report": report,
            "email_delivery": email_result,
            "whatsapp_delivery": wa_result,
        }

    async def run_monday_weekly_roi_tick(self, session: AsyncSession) -> Dict[str, Any]:
        """Monday morning UTC sweep: sends once per ISO week per active paid/trial workspace."""
        now_utc = datetime.now(timezone.utc)
        if now_utc.weekday() != 0 or now_utc.hour < 7:
            return {"skipped": True, "reason": "not_monday_morning_utc", "sent": 0}

        iso_year, iso_week, _ = now_utc.isocalendar()
        week_tag = f"{iso_year}-W{iso_week:02d}"

        res = await session.execute(select(Tenant).where(Tenant.status == "active"))
        tenants = res.scalars().all()
        sent = 0
        for tenant in tenants:
            settings_map = dict(tenant.settings or {})
            if settings_map.get("last_weekly_roi_iso_week") == week_tag:
                continue
            try:
                await self.send_weekly_roi_report(session, tenant.id)
                settings_map["last_weekly_roi_iso_week"] = week_tag
                tenant.settings = settings_map
                await session.commit()
                sent += 1
            except Exception as exc:
                logger.warning("Weekly ROI sweep failed for tenant", tenant_id=str(tenant.id), error=str(exc))
                await session.rollback()

        return {"skipped": False, "iso_week": week_tag, "sent": sent}


call_intelligence_service = CallIntelligenceService()
