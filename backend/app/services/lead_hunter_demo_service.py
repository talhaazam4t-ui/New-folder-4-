"""Personalized English Demo Generator, HITL Draft/Approved/Sent Approval & Interactive Chat Demo Service.

All generated demo assets strictly use Native Business English and USD pricing ($299/month, $499 setup).
Never auto-sends after generation — demos always enter `draft` first.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.core.exceptions import ResourceNotFoundError, TaloxException
from app.database.models.automation import AuditLog
from app.database.models.lead_hunter import HunterDemo, HunterLead
from app.integrations.ai_providers.router import route_and_execute_ai_task
from app.services.lead_hunter_control_service import lead_hunter_control_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class LeadHunterDemoService:
    """Builds tailored English AI Receptionist demos & enforces Draft -> Approved -> Sent workflow."""

    @staticmethod
    def serialize_demo(row: HunterDemo, lead: Optional[HunterLead] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "lead_id": str(row.lead_id),
            "email_subject": row.email_subject,
            "email_copy": row.email_copy,
            "whatsapp_copy": row.whatsapp_copy,
            "voice_script": row.voice_script,
            "chat_prompt": row.chat_prompt,
            "business_snapshot": row.business_snapshot or {},
            "status": row.status,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            "sent_channels": row.sent_channels or [],
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        if lead:
            payload["lead"] = {
                "business_name": lead.business_name,
                "owner_name": lead.owner_name,
                "owner_title": lead.owner_title,
                "linkedin_url": lead.linkedin_url,
                "country": lead.country,
                "city": lead.city,
                "category": lead.category,
                "phone": lead.phone,
                "email": lead.email,
                "website": lead.website,
                "favicon_url": lead.favicon_url,
                "pipeline_stage": lead.pipeline_stage,
                "do_not_disturb": bool(lead.do_not_disturb),
                "human_needed": bool(lead.human_needed),
            }
        return payload

    async def generate_demo_for_lead(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        lead_id: uuid.UUID,
        require_auto_switch: bool = False,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        if require_auto_switch:
            await lead_hunter_control_service.assert_module_enabled_and_quota(
                session, tenant_id, "auto_demo_generator", units=1, require_switch_on=True
            )
        else:
            # Manual click on "Generate Demo" checks quota cleanly without blocking manual founder review
            await lead_hunter_control_service.assert_module_enabled_and_quota(
                session, tenant_id, "auto_demo_generator", units=1, require_switch_on=False
            )

        lead = (
            await session.execute(
                select(HunterLead).where(HunterLead.id == lead_id, HunterLead.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if not lead:
            raise ResourceNotFoundError("HunterLead", str(lead_id))

        recipient = lead.owner_name or f"{lead.business_name} Team"
        services = lead.services or f"{lead.category} appointments and consultations"
        hours = lead.working_hours or "Mon-Fri 9:00 AM - 6:00 PM"
        pain_list = list(lead.pain_points or [])
        pain_ref = (
            f'Recent Google reviews specifically mentioned missed calls ("{pain_list[0][:100]}")'
            if pain_list
            else f"Many {lead.category} practices in {lead.city} miss 25%+ of inbound calls after hours"
        )
        demo_link = f"{settings.frontend_url.rstrip('/')}/lead-hunter?demo_lead={lead.id}"

        prompt = (
            f"Write concise, high-converting B2B cold email copy in native American/British Business English "
            f"pitching a custom 24/7 AI Receptionist for {lead.business_name} ({lead.category} in {lead.city}, {lead.country}).\n"
            f"Owner/Recipient: {recipient}\nServices: {services}\nHours: {hours}\nPain point: {pain_ref}\n"
            f"USD Pricing: $299/month (or $499 setup + $299/month), 7-Day Free Trial available.\n"
            f"Include link: {demo_link}"
        )
        ai_res = await route_and_execute_ai_task(
            task_type="lead_hunter_demo_email",
            prompt=prompt,
            tenant_id=str(tenant_id),
        )
        await lead_hunter_control_service.increment_usage(session, tenant_id, "auto_demo_generator", units=1)

        email_subject = f"I made a FREE AI Receptionist Demo for {lead.business_name}"
        if (
            ai_res.success
            and ai_res.content
            and not getattr(ai_res, "is_mock", False)
            and "mock ai completion" not in ai_res.content.lower()
        ):
            email_copy = ai_res.content.strip()
        else:
            email_copy = (
                f"Hi {recipient},\n\n"
                f"While researching top {lead.category} businesses in {lead.city}, I noticed {lead.business_name} "
                f"has strong customer demand — and {pain_ref.lower()}.\n\n"
                f"I went ahead and built a FREE working 24/7 AI Receptionist demo pre-trained on {lead.business_name}'s "
                f"hours ({hours}) and {services}. It answers every call on the first ring, qualifies leads, and books "
                f"appointments directly onto your calendar.\n\n"
                f"Preview your live interactive demo here: {demo_link}\n\n"
                f"Plans start at $299/month ($499 white-glove setup, waived with an annual plan) with a 7-Day FREE Trial.\n"
                f"Want me to send your private sandbox phone number so you can call and test it yourself?\n\n"
                f"Best regards,\nTalox AI Automation Team"
            )

        whatsapp_copy = (
            f"Hi {recipient}, I built a free 24/7 AI Receptionist demo tailored for {lead.business_name} "
            f"so you never lose a booking from missed calls ({hours}).\n"
            f"Plans start at $299/month ($499 setup, 7-day free trial available). "
            f"Test your custom demo here: {demo_link} — shall I send the test line?"
        )

        voice_script = (
            f"Hello, thank you for calling {lead.business_name}. I am your 24/7 AI Receptionist. "
            f"I can help book your appointment, share our current hours ({hours}), or connect you directly with our team "
            f"for {services}. What brings you in today?"
        )

        chat_prompt = (
            f"You are the friendly 24/7 AI Receptionist for {lead.business_name} ({lead.category}) located in {lead.city}, {lead.country}. "
            f"Operating hours: {hours}. Address: {lead.address or lead.city}. Services: {services}. "
            f"Pricing info: $299/month Talox AI Receptionist demo ($499 setup) showcases instant FAQ answers & appointment booking."
        )

        snapshot = {
            "business_name": lead.business_name,
            "favicon_url": lead.favicon_url,
            "website": lead.website,
            "services": services,
            "working_hours": hours,
            "address": lead.address,
            "category": lead.category,
            "city": lead.city,
            "country": lead.country,
            "pain_points": pain_list,
            "usd_pricing": "$299/month | $499 setup (7-Day Free Trial)",
        }

        demo = HunterDemo(
            tenant_id=tenant_id,
            lead_id=lead.id,
            email_subject=email_subject,
            email_copy=email_copy,
            whatsapp_copy=whatsapp_copy,
            voice_script=voice_script,
            chat_prompt=chat_prompt,
            business_snapshot=snapshot,
            status="draft",
        )
        session.add(demo)
        if lead.pipeline_stage in ("new_lead", "apollo_enriched"):
            lead.pipeline_stage = "demo_generated"
        lead.status = "demo_ready"
        await session.flush()

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="lead_hunter.demo.generated",
                resource_type="hunter_demo",
                resource_id=demo.id,
                metadata_={"lead_id": str(lead.id), "business_name": lead.business_name},
            )
        )
        await session.commit()
        await session.refresh(demo)
        return self.serialize_demo(demo, lead)

    async def list_demos(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        status_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        q = (
            select(HunterDemo, HunterLead)
            .join(HunterLead, HunterDemo.lead_id == HunterLead.id)
            .where(HunterDemo.tenant_id == tenant_id)
            .order_by(HunterDemo.created_at.desc())
        )
        if status_filter and status_filter in ("draft", "approved", "sent", "rejected"):
            q = q.where(HunterDemo.status == status_filter)
        rows = (await session.execute(q)).all()
        return [self.serialize_demo(d, l) for d, l in rows]

    async def update_demo_draft(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        demo_id: uuid.UUID,
        updates: Dict[str, Any],
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
        for field in ("email_subject", "email_copy", "whatsapp_copy", "voice_script", "chat_prompt"):
            if field in updates and updates[field] is not None:
                setattr(demo, field, str(updates[field]).strip())
        await session.commit()
        await session.refresh(demo)
        return self.serialize_demo(demo, lead)

    async def approve_demo(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        demo_id: uuid.UUID,
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
        demo.status = "approved"
        demo.approved_at = datetime.now(timezone.utc)
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="lead_hunter.demo.approved",
                resource_type="hunter_demo",
                resource_id=demo.id,
            )
        )
        await session.commit()
        await session.refresh(demo)
        return self.serialize_demo(demo, lead)

    async def reject_demo(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        demo_id: uuid.UUID,
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
        demo.status = "rejected"
        await session.commit()
        await session.refresh(demo)
        return self.serialize_demo(demo, lead)

    async def interactive_chat_preview(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        demo_id: uuid.UUID,
        visitor_message: str,
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
        msg = (visitor_message or "").strip()
        if not msg:
            raise TaloxException(message="Visitor message is required", code="EMPTY_MESSAGE", status_code=400)

        ai_res = await route_and_execute_ai_task(
            task_type="demo_chat_widget",
            prompt=f"{demo.chat_prompt}\n\nCustomer asks: '{msg}'\nReply warmly in 2 sentences in native English:",
            tenant_id=str(tenant_id),
        )
        if (
            ai_res.success
            and ai_res.content
            and not getattr(ai_res, "is_mock", False)
            and "mock ai completion" not in ai_res.content.lower()
        ):
            reply = ai_res.content.strip()
        else:
            hours = lead.working_hours or "Mon-Fri 9:00 AM - 6:00 PM"
            if any(w in msg.lower() for w in ("hour", "open", "time", "close")):
                reply = f"Thanks for reaching out to {lead.business_name}! Our operating hours are {hours}. Would you like me to reserve a slot for you?"
            elif any(w in msg.lower() for w in ("price", "cost", "fee", "quote")):
                reply = f"Thanks for contacting {lead.business_name}! We offer tailored {lead.services or lead.category} packages. Share your preferred day and I will connect our coordinator or book a quick consultation."
            else:
                reply = f"Welcome to {lead.business_name}! I can book your {lead.category} appointment right away or answer questions about {lead.services or 'our services'}. What day works best for you?"

        return {
            "demo_id": str(demo.id),
            "business_name": lead.business_name,
            "visitor_message": msg,
            "ai_receptionist_reply": reply,
        }


lead_hunter_demo_service = LeadHunterDemoService()
