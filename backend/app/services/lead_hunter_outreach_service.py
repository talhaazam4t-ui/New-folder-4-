"""Hot Lead Call List, Daily-Limited Outreach Senders, 24h/48h/72h Auto Follow-ups,
Instant Human Handover, Opt-Out (DND) Guardrails, and Kanban Pipeline Service.
"""

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.exceptions import ResourceNotFoundError, TaloxException
from app.core.security import decrypt_secret
from app.database.models.automation import AuditLog, Integration
from app.database.models.lead_hunter import (
    HunterConversation,
    HunterDemo,
    HunterFollowup,
    HunterLead,
)
from app.integrations.email.adapter import email_adapter
from app.integrations.whatsapp.client import whatsapp_client
from app.services.job_engine_service import job_engine_service
from app.services.lead_hunter_control_service import lead_hunter_control_service
from app.services.lead_hunter_discovery_service import lead_hunter_discovery_service
from app.services.notification_service import notification_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

KANBAN_STAGES: List[str] = [
    "new_lead",
    "apollo_enriched",
    "demo_generated",
    "demo_sent",
    "followup_1",
    "followup_2",
    "followup_3",
    "replied_hot",
    "call_done",
    "trial_started",
    "paid_client",
    "not_interested",
]

POSITIVE_HANDOVER_RE = re.compile(
    r"\b(yes|interested|price|pricing|demo|call|info|cost|trial|book|schedule|sure|sounds good)\b",
    re.IGNORECASE,
)

OPT_OUT_RE = re.compile(
    r"\b(no|stop|unsubscribe|not interested|remove me|opt out|do not contact|dont contact)\b",
    re.IGNORECASE,
)


def _compute_best_call_window(tz_name: str) -> str:
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
        now_local = datetime.now(tz)
        local_time_str = now_local.strftime("%I:%M %p %Z")
        return f"Now there: {local_time_str} • Best window: 9:30 AM - 11:30 AM & 2:00 PM - 4:30 PM ({tz_name})"
    except Exception:
        return f"Best window: 9:30 AM - 11:30 AM & 2:00 PM - 4:30 PM ({tz_name})"


class LeadHunterOutreachService:
    """Handles Hot Call List, HitL/Daily-Capped Demo Sending, Follow-ups & Handover."""

    @staticmethod
    def serialize_followup(row: HunterFollowup, lead: Optional[HunterLead] = None) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": str(row.id),
            "lead_id": str(row.lead_id),
            "demo_id": str(row.demo_id) if row.demo_id else None,
            "followup_number": int(row.followup_number),
            "subject": row.subject,
            "message": row.message,
            "channel": row.channel,
            "scheduled_at": row.scheduled_at.isoformat() if row.scheduled_at else None,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        if lead:
            out["business_name"] = lead.business_name
            out["owner_name"] = lead.owner_name
            out["human_needed"] = bool(lead.human_needed)
            out["do_not_disturb"] = bool(lead.do_not_disturb)
        return out

    @staticmethod
    def serialize_conversation(row: HunterConversation) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "lead_id": str(row.lead_id),
            "message": row.message,
            "direction": row.direction,
            "channel": row.channel,
            "intent_detected": row.intent_detected,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    # ------------------------------------------------------------------
    # PART 2: Hot Lead Call List + Direct Call Mode Outcomes
    # ------------------------------------------------------------------

    async def get_hot_call_list(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        min_score: int = 80,
    ) -> List[Dict[str, Any]]:
        rows = (
            await session.execute(
                select(HunterLead)
                .where(
                    HunterLead.tenant_id == tenant_id,
                    HunterLead.interest_score >= min_score,
                    HunterLead.do_not_disturb.is_(False),
                )
                .order_by(HunterLead.human_needed.desc(), HunterLead.interest_score.desc(), HunterLead.created_at.desc())
            )
        ).scalars().all()

        cards: List[Dict[str, Any]] = []
        for l in rows:
            serialized = lead_hunter_discovery_service.serialize_lead(l)
            pain_list = list(l.pain_points or [])
            missed_cnt = int((l.ai_evidence or {}).get("missed_call_mentions") or len(pain_list))
            pain_summary = (
                f'{missed_cnt} Google review(s) mention missed calls: "{pain_list[0][:110]}"'
                if pain_list
                else f"No AI Receptionist or chat widget found ({l.rating}★ across {l.total_reviews} reviews)."
            )
            owner_greet = l.owner_name or "there"
            cold_call_script = (
                f'"Hi {owner_greet}, this is Talha with Talox AI. I noticed {l.business_name} in {l.city} does not have an '
                f'automated 24/7 receptionist yet{" and reviews mentioned hard-to-reach calls" if pain_list else ""}. '
                f'I actually built a working AI Receptionist demo trained on {l.business_name}\'s hours & {l.category} services '
                f'that books missed callers onto your calendar automatically. Want me to text or email you the free 60-second demo link?"'
            )
            cold_email_script = (
                f"Subject: Quick question about missed calls at {l.business_name}\n\n"
                f"Hi {owner_greet},\n{pain_summary}\n\n"
                f"We built a 24/7 AI Receptionist demo tailored to {l.business_name} ($299/mo, 7-day free trial). "
                f"Reply YES and I will send the private demo phone line.\n\nBest,\nTalha"
            )
            serialized["best_time_to_call"] = _compute_best_call_window(l.timezone or "America/New_York")
            serialized["pain_summary"] = pain_summary
            serialized["cold_call_script"] = cold_call_script
            serialized["cold_email_script"] = cold_email_script
            cards.append(serialized)
        return cards

    async def promote_to_hot_lead(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        lead_id: uuid.UUID,
    ) -> Dict[str, Any]:
        lead = (
            await session.execute(
                select(HunterLead).where(HunterLead.id == lead_id, HunterLead.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if not lead:
            raise ResourceNotFoundError("HunterLead", str(lead_id))
        if int(lead.interest_score or 0) < 80:
            lead.interest_score = 85
        await session.commit()
        await session.refresh(lead)
        return lead_hunter_discovery_service.serialize_lead(lead)

    async def record_call_outcome(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        lead_id: uuid.UUID,
        outcome: str,
        notes: Optional[str] = None,
        deal_value_usd: Optional[float] = None,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        clean = outcome.strip().lower()
        if clean not in ("interested", "not_interested", "call_later", "demo_sent", "paid"):
            raise TaloxException(
                message="Outcome must be interested, not_interested, call_later, demo_sent, or paid",
                code="INVALID_CALL_OUTCOME",
                status_code=400,
            )

        lead = (
            await session.execute(
                select(HunterLead).where(HunterLead.id == lead_id, HunterLead.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if not lead:
            raise ResourceNotFoundError("HunterLead", str(lead_id))

        now_utc = datetime.now(timezone.utc)
        lead.call_result = clean
        lead.last_contact_at = now_utc

        if clean == "interested":
            lead.pipeline_stage = "replied_hot"
            lead.status = "interested"
        elif clean == "not_interested":
            lead.pipeline_stage = "not_interested"
            lead.do_not_disturb = True
            lead.status = "not_interested"
            await self._cancel_pending_followups(session, tenant_id, lead.id, "cancelled_dnd")
        elif clean == "call_later":
            remind_at = now_utc + timedelta(hours=24)
            lead.pipeline_stage = "call_done"
            lead.status = "call_later"
            lead.next_followup_at = remind_at
            await job_engine_service.enqueue_job(
                session=session,
                job_type="low_balance_alert",
                tenant_id=tenant_id,
                payload={
                    "title": f"24h Call Later Reminder: {lead.business_name}",
                    "message": f"Follow-up call due for {lead.business_name} ({lead.owner_name or lead.phone or lead.city}).",
                },
                run_at=remind_at,
                idempotency_key=f"hunter_call_later:{lead.id}:{remind_at.strftime('%Y%m%d%H')}",
            )
        elif clean == "demo_sent":
            lead.pipeline_stage = "demo_sent"
            lead.status = "demo_sent"
        elif clean == "paid":
            lead.pipeline_stage = "paid_client"
            lead.status = "paid"
            lead.human_needed = False
            lead.deal_value_usd = float(deal_value_usd if deal_value_usd is not None else 299.0)
            await self._cancel_pending_followups(session, tenant_id, lead.id, "cancelled_human_handover")

        session.add(
            HunterConversation(
                tenant_id=tenant_id,
                lead_id=lead.id,
                message=f"[Manual Outreach Outcome: {clean}] {notes or ''}".strip(),
                direction="outbound",
                channel="call",
                intent_detected=clean,
            )
        )
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="lead_hunter.outreach.outcome",
                resource_type="hunter_lead",
                resource_id=lead.id,
                metadata_={"outcome": clean, "deal_value_usd": float(lead.deal_value_usd or 0.0)},
            )
        )
        await session.commit()
        await session.refresh(lead)
        return lead_hunter_discovery_service.serialize_lead(lead)

    # ------------------------------------------------------------------
    # PART 6 & 8: Daily-Limited Senders (Email / LinkedIn / UAE WhatsApp)
    # ------------------------------------------------------------------

    async def _get_tenant_gmail_token(self, session: AsyncSession, tenant_id: uuid.UUID) -> Optional[str]:
        integ = (
            await session.execute(
                select(Integration).where(
                    Integration.tenant_id == tenant_id,
                    Integration.provider == "gmail",
                    Integration.status == "connected",
                ).limit(1)
            )
        ).scalar_one_or_none()
        if not integ or not integ.configuration:
            return None
        tok = integ.configuration.get("access_token")
        return decrypt_secret(str(tok)) if tok else None

    async def _dispatch_channel_message(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        lead: HunterLead,
        channel: str,
        subject: str,
        body: str,
    ) -> Dict[str, Any]:
        ch = channel.strip().lower()
        if ch == "email":
            if not lead.email:
                raise TaloxException(message="Lead has no email address to send to.", code="MISSING_LEAD_EMAIL", status_code=400)
            gmail_tok = await self._get_tenant_gmail_token(session, tenant_id)
            if gmail_tok:
                res = await email_adapter.send_email(
                    tenant_id=str(tenant_id),
                    to_email=lead.email,
                    subject=subject,
                    body=body,
                    access_token=gmail_tok,
                )
            else:
                res = await email_adapter.send_transactional_email(
                    to_email=lead.email,
                    subject=subject,
                    html_body=f"<pre style='font-family:sans-serif;white-space:pre-wrap'>{body}</pre>",
                    text_body=body,
                )
            await lead_hunter_control_service.increment_usage(session, tenant_id, "auto_email_sender", units=1)
            return {"channel": "email", "delivery": res, "manual_copy_only": False}

        if ch == "whatsapp":
            country_l = (lead.country or "").lower()
            city_l = (lead.city or "").lower()
            if "uae" not in country_l and "dubai" not in city_l and "arab emirates" not in country_l:
                raise TaloxException(
                    message="WhatsApp Auto Sender is restricted strictly to UAE / Dubai leads.",
                    code="WHATSAPP_REGION_RESTRICTED",
                    status_code=400,
                )
            if not lead.phone:
                raise TaloxException(message="Lead has no phone number for WhatsApp.", code="MISSING_LEAD_PHONE", status_code=400)
            res = await whatsapp_client.send_text_message(
                tenant_id=str(tenant_id),
                to_phone=lead.phone,
                message_body=body,
            )
            await lead_hunter_control_service.increment_usage(session, tenant_id, "auto_whatsapp_sender", units=1)
            return {"channel": "whatsapp", "delivery": res, "manual_copy_only": False}

        if ch == "linkedin":
            # Safety protection: NEVER auto-send LinkedIn requests — prepare 1-click copy draft cleanly
            await lead_hunter_control_service.increment_usage(session, tenant_id, "auto_linkedin_sender", units=1)
            return {
                "channel": "linkedin",
                "delivery": {
                    "status": "draft_ready_1click_copy",
                    "linkedin_url": lead.linkedin_url,
                    "copy_text": body[:300],
                },
                "manual_copy_only": True,
            }

        raise TaloxException(message=f"Unsupported channel '{channel}'", code="INVALID_CHANNEL", status_code=400)

    async def send_approved_demo(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        demo_id: uuid.UUID,
        channel: str = "email",
        manual_override: bool = False,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        res = await session.execute(
            select(HunterDemo, HunterLead)
            .join(HunterLead, HunterDemo.lead_id == HunterLead.id)
            .where(HunterDemo.id == demo_id, HunterDemo.tenant_id == tenant_id)
        )
        row = res.first()
        if not row:
            raise ResourceNotFoundError("HunterDemo", str(demo_id))
        demo, lead = row

        if demo.status != "approved":
            raise TaloxException(
                message=f"Human Approval Required: demo status is '{demo.status}'. Approve before sending.",
                code="APPROVAL_REQUIRED",
                status_code=403,
            )
        if lead.do_not_disturb:
            raise TaloxException(message="Lead opted out (Do Not Disturb).", code="DO_NOT_DISTURB", status_code=403)
        if lead.human_needed:
            raise TaloxException(
                message="Lead is in Human Handover state. Contact manually from Hot Leads.",
                code="HUMAN_HANDOVER_ACTIVE",
                status_code=403,
            )

        ch = channel.strip().lower()
        module_by_channel = {
            "email": "auto_email_sender",
            "whatsapp": "auto_whatsapp_sender",
            "linkedin": "auto_linkedin_sender",
        }
        mod_name = module_by_channel.get(ch)
        if not mod_name:
            raise TaloxException(message=f"Unsupported send channel '{channel}'", code="INVALID_CHANNEL", status_code=400)

        await lead_hunter_control_service.assert_module_enabled_and_quota(
            session, tenant_id, mod_name, units=1, require_switch_on=not manual_override
        )

        body = (
            demo.whatsapp_copy
            if ch == "whatsapp"
            else (f"Hi {lead.owner_name or 'there'} — built a free 24/7 AI Receptionist demo for {lead.business_name}: {demo.whatsapp_copy}" if ch == "linkedin" else demo.email_copy)
        )
        dispatch_res = await self._dispatch_channel_message(
            session=session,
            tenant_id=tenant_id,
            lead=lead,
            channel=ch,
            subject=demo.email_subject,
            body=body,
        )

        now_utc = datetime.now(timezone.utc)
        demo.status = "sent"
        demo.sent_at = now_utc
        channels_sent = list(demo.sent_channels or [])
        if ch not in channels_sent:
            channels_sent.append(ch)
        demo.sent_channels = channels_sent

        lead.last_contact_at = now_utc
        lead.pipeline_stage = "demo_sent"
        lead.status = "demo_sent"

        session.add(
            HunterConversation(
                tenant_id=tenant_id,
                lead_id=lead.id,
                message=body,
                direction="outbound",
                channel=ch,
                intent_detected="demo_sent",
            )
        )

        # Schedule 24h / 48h / 72h Follow-ups ONLY if Auto Follow-up Engine switch is ON
        fu_setting = await lead_hunter_control_service.get_module_row(session, tenant_id, "auto_followup_engine")
        scheduled_count = 0
        if fu_setting.is_on:
            owner_ref = lead.owner_name or f"{lead.business_name} Team"
            followups_spec = [
                (
                    1,
                    24,
                    f"Re: {demo.email_subject}",
                    f"Hi {owner_ref}, I sent over a free AI Receptionist demo for {lead.business_name} yesterday. Did you get a chance to test it? It handles missed calls and books appointments 24/7.",
                ),
                (
                    2,
                    48,
                    f"8+ weekly bookings for {lead.city} {lead.category}s",
                    f"A {lead.category} in {lead.city} is using our AI Receptionist and capturing 8+ extra bookings every week from missed calls. Want me to set up a 7-Day FREE Trial for {lead.business_name}? No card needed.",
                ),
                (
                    3,
                    72,
                    f"Should I delete {lead.business_name}'s demo?",
                    f"Hi {owner_ref}, this is my final follow-up. Should I delete the custom AI demo I built for {lead.business_name} or keep it active? Reply YES and I'll walk you through it in 2 minutes.",
                ),
            ]
            for num, hrs, subj, msg in followups_spec:
                sched_at = now_utc + timedelta(hours=hrs)
                session.add(
                    HunterFollowup(
                        tenant_id=tenant_id,
                        lead_id=lead.id,
                        demo_id=demo.id,
                        followup_number=num,
                        subject=subj,
                        message=msg,
                        channel=ch if ch in ("email", "whatsapp", "linkedin") else "email",
                        scheduled_at=sched_at,
                        status="scheduled",
                    )
                )
                scheduled_count += 1
            lead.next_followup_at = now_utc + timedelta(hours=24)

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="lead_hunter.demo.sent",
                resource_type="hunter_demo",
                resource_id=demo.id,
                metadata_={"channel": ch, "followups_scheduled": scheduled_count},
            )
        )
        await session.commit()
        return {
            "sent": True,
            "channel": ch,
            "dispatch": dispatch_res,
            "followups_scheduled": scheduled_count,
        }

    # ------------------------------------------------------------------
    # PART 7: Auto Follow-up Engine + Critical Human Handover + Opt-Out
    # ------------------------------------------------------------------

    async def _cancel_pending_followups(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        lead_id: uuid.UUID,
        new_status: str,
    ) -> int:
        rows = (
            await session.execute(
                select(HunterFollowup).where(
                    HunterFollowup.tenant_id == tenant_id,
                    HunterFollowup.lead_id == lead_id,
                    HunterFollowup.status == "scheduled",
                )
            )
        ).scalars().all()
        for r in rows:
            r.status = new_status
        return len(rows)

    async def list_followups(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        rows = (
            await session.execute(
                select(HunterFollowup, HunterLead)
                .join(HunterLead, HunterFollowup.lead_id == HunterLead.id)
                .where(HunterFollowup.tenant_id == tenant_id)
                .order_by(HunterFollowup.scheduled_at.asc())
            )
        ).all()
        return [self.serialize_followup(f, l) for f, l in rows]

    async def process_due_followups(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        force_due_in_test: bool = False,
    ) -> Dict[str, Any]:
        fu_mod = await lead_hunter_control_service.get_module_row(session, tenant_id, "auto_followup_engine")
        if not fu_mod.is_on:
            return {"processed": 0, "skipped_reason": "auto_followup_engine_off"}

        now_utc = datetime.now(timezone.utc)
        q = (
            select(HunterFollowup, HunterLead)
            .join(HunterLead, HunterFollowup.lead_id == HunterLead.id)
            .where(
                HunterFollowup.tenant_id == tenant_id,
                HunterFollowup.status == "scheduled",
            )
            .order_by(HunterFollowup.scheduled_at.asc())
        )
        if not force_due_in_test:
            q = q.where(HunterFollowup.scheduled_at <= now_utc)

        due_rows = (await session.execute(q)).all()
        sent_cnt = 0
        cancelled_cnt = 0
        skipped_cnt = 0

        for fu, lead in due_rows:
            if lead.do_not_disturb:
                fu.status = "cancelled_dnd"
                cancelled_cnt += 1
                continue
            if lead.human_needed:
                fu.status = "cancelled_human_handover"
                cancelled_cnt += 1
                continue

            mod_map = {"email": "auto_email_sender", "whatsapp": "auto_whatsapp_sender", "linkedin": "auto_linkedin_sender"}
            sender_mod = mod_map.get(fu.channel, "auto_email_sender")
            try:
                await lead_hunter_control_service.assert_module_enabled_and_quota(
                    session, tenant_id, "auto_followup_engine", units=1, require_switch_on=True
                )
                await lead_hunter_control_service.assert_module_enabled_and_quota(
                    session, tenant_id, sender_mod, units=1, require_switch_on=True
                )
            except TaloxException:
                fu.status = "skipped_limit"
                skipped_cnt += 1
                continue

            await self._dispatch_channel_message(
                session=session,
                tenant_id=tenant_id,
                lead=lead,
                channel=fu.channel,
                subject=fu.subject or f"Follow-up for {lead.business_name}",
                body=fu.message,
            )
            await lead_hunter_control_service.increment_usage(session, tenant_id, "auto_followup_engine", units=1)

            fu.status = "sent"
            fu.sent_at = now_utc
            lead.last_contact_at = now_utc
            lead.pipeline_stage = f"followup_{fu.followup_number}"
            session.add(
                HunterConversation(
                    tenant_id=tenant_id,
                    lead_id=lead.id,
                    message=fu.message,
                    direction="outbound",
                    channel=fu.channel,
                    intent_detected=f"followup_{fu.followup_number}",
                )
            )
            sent_cnt += 1

        await session.commit()
        return {"processed": len(due_rows), "sent": sent_cnt, "cancelled": cancelled_cnt, "skipped": skipped_cnt}

    async def process_due_followups_global(self, session: AsyncSession) -> Dict[str, Any]:
        """Sweep due follow-ups across tenants that enabled `auto_followup_engine` cleanly."""
        from app.database.models.lead_hunter import HunterModuleSetting

        tenant_ids = (
            await session.execute(
                select(HunterModuleSetting.tenant_id).where(
                    HunterModuleSetting.module_name == "auto_followup_engine",
                    HunterModuleSetting.is_on.is_(True),
                )
            )
        ).scalars().all()
        total_sent = 0
        for tid in tenant_ids:
            res = await self.process_due_followups(session, tid)
            total_sent += int(res.get("sent") or 0)
        return {"tenants_checked": len(tenant_ids), "total_sent": total_sent}

    async def record_inbound_reply(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        lead_id: uuid.UUID,
        message: str,
        channel: str = "email",
    ) -> Dict[str, Any]:
        """Process inbound prospect reply enforcing Instant Human Handover & DND Opt-Out."""
        lead = (
            await session.execute(
                select(HunterLead).where(HunterLead.id == lead_id, HunterLead.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if not lead:
            raise ResourceNotFoundError("HunterLead", str(lead_id))

        clean_msg = (message or "").strip()
        if not clean_msg:
            raise TaloxException(message="Reply message is required", code="EMPTY_MESSAGE", status_code=400)

        now_utc = datetime.now(timezone.utc)
        is_opt_out = bool(OPT_OUT_RE.search(clean_msg)) and not bool(POSITIVE_HANDOVER_RE.search(clean_msg))
        is_positive = bool(POSITIVE_HANDOVER_RE.search(clean_msg))
        intent = "opt_out" if is_opt_out else ("interested_handover" if is_positive else "general_reply")

        session.add(
            HunterConversation(
                tenant_id=tenant_id,
                lead_id=lead.id,
                message=clean_msg,
                direction="inbound",
                channel=channel.strip().lower(),
                intent_detected=intent,
            )
        )

        meta = dict(lead.metadata_ or {})
        meta["last_inbound_message"] = clean_msg[:300]
        meta["last_inbound_at"] = now_utc.isoformat()
        lead.metadata_ = meta
        lead.last_contact_at = now_utc

        cancelled = 0
        if is_opt_out:
            lead.do_not_disturb = True
            lead.human_needed = False
            lead.pipeline_stage = "not_interested"
            lead.status = "not_interested"
            lead.next_followup_at = None
            cancelled = await self._cancel_pending_followups(session, tenant_id, lead.id, "cancelled_dnd")
        else:
            # Critical Human Handover: ANY positive/engaged reply halts auto follow-ups IMMEDIATELY!
            lead.human_needed = True
            lead.pipeline_stage = "replied_hot"
            lead.status = "hot_human_needed"
            lead.next_followup_at = None
            cancelled = await self._cancel_pending_followups(session, tenant_id, lead.id, "cancelled_human_handover")
            await notification_service.send_notification(
                session=session,
                tenant_id=tenant_id,
                title=f"Human Needed - Contact Now: {lead.business_name}",
                message=f'{lead.owner_name or lead.business_name} replied via {channel}: "{clean_msg[:180]}". All auto follow-ups stopped.',
                channel="in_app",
            )

        await session.commit()
        await session.refresh(lead)
        return {
            "lead": lead_hunter_discovery_service.serialize_lead(lead),
            "intent_detected": intent,
            "human_needed": bool(lead.human_needed),
            "do_not_disturb": bool(lead.do_not_disturb),
            "cancelled_followups": cancelled,
            "auto_reply_sent": False,  # Strict Guardrail: never auto-reply once prospect engages
        }

    async def acknowledge_human_handover(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        lead_id: uuid.UUID,
    ) -> Dict[str, Any]:
        lead = (
            await session.execute(
                select(HunterLead).where(HunterLead.id == lead_id, HunterLead.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if not lead:
            raise ResourceNotFoundError("HunterLead", str(lead_id))
        lead.human_needed = False
        if lead.pipeline_stage == "replied_hot":
            lead.pipeline_stage = "call_done"
        await session.commit()
        await session.refresh(lead)
        return lead_hunter_discovery_service.serialize_lead(lead)

    async def update_pipeline_stage(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        lead_id: uuid.UUID,
        pipeline_stage: str,
    ) -> Dict[str, Any]:
        clean = pipeline_stage.strip().lower()
        if clean not in KANBAN_STAGES:
            raise TaloxException(message=f"Invalid pipeline_stage '{pipeline_stage}'", code="INVALID_STAGE", status_code=400)
        lead = (
            await session.execute(
                select(HunterLead).where(HunterLead.id == lead_id, HunterLead.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if not lead:
            raise ResourceNotFoundError("HunterLead", str(lead_id))
        lead.pipeline_stage = clean
        if clean == "not_interested":
            lead.do_not_disturb = True
            await self._cancel_pending_followups(session, tenant_id, lead.id, "cancelled_dnd")
        elif clean == "paid_client" and float(lead.deal_value_usd or 0.0) <= 0:
            lead.deal_value_usd = 299.0
        await session.commit()
        await session.refresh(lead)
        return lead_hunter_discovery_service.serialize_lead(lead)

    async def list_conversations(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        lead_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        lead = (
            await session.execute(
                select(HunterLead.id).where(HunterLead.id == lead_id, HunterLead.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if not lead:
            raise ResourceNotFoundError("HunterLead", str(lead_id))
        rows = (
            await session.execute(
                select(HunterConversation)
                .where(HunterConversation.tenant_id == tenant_id, HunterConversation.lead_id == lead_id)
                .order_by(HunterConversation.created_at.asc())
            )
        ).scalars().all()
        return [self.serialize_conversation(r) for r in rows]


lead_hunter_outreach_service = LeadHunterOutreachService()
