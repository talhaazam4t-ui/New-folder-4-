"""Lightweight Multi-Step AI Diagnostic & Outreach Agent for TALOX Lead Hunter.

Architecture & Guardrails:
- Native Python asyncio bounded tool-calling loop (`MAX_STEPS = 5`) over `route_and_execute_ai_task`.
- Strictly ZERO n8n, ZERO LangChain, and ZERO Twilio.
- Strict Server-Side Context Enforcement: `tenant_id` and `lead_id` are NEVER trusted from LLM
  tool arguments; they are bound exclusively from the authenticated request context.
- Strict HITL Approval Gate: `save_hitl_outreach_draft` ALWAYS saves in `status="draft"` and
  NEVER auto-sends emails or messages.
"""

import json
import re
import uuid
from typing import Any, Dict, List, Optional

from app.config import settings
from app.core.exceptions import ResourceNotFoundError
from app.database.models.automation import AuditLog
from app.database.models.lead_hunter import HunterDemo, HunterLead
from app.database.models.marketing import Lead
from app.integrations.ai_providers.router import route_and_execute_ai_task
from app.services.lead_hunter_demo_service import lead_hunter_demo_service
from app.services.lead_hunter_discovery_service import (
    _extract_domain,
    lead_hunter_discovery_service,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

MAX_STEPS = 5

ALLOWED_RECOMMENDED_SERVICES = {
    "office-receptionist",
    "lead-crm-qualification",
    "ai-marketing-growth",
}

SERVICE_TITLES: Dict[str, str] = {
    "office-receptionist": "24/7 AI Voice & Chat Office Receptionist ($299/month)",
    "lead-crm-qualification": "Lead CRM & Instant AI Qualification Engine ($149/month)",
    "ai-marketing-growth": "AI Marketing, Review Booster & Social Growth Suite ($149/month)",
}


def _count_words(text: str) -> int:
    return len([w for w in re.split(r"\s+", (text or "").strip()) if w])


def _enforce_word_limit(text: str, max_words: int = 125) -> str:
    words = [w for w in re.split(r"(\s+)", (text or "").strip()) if w]
    result_tokens: List[str] = []
    word_cnt = 0
    for token in words:
        if not token.isspace():
            if word_cnt >= max_words:
                break
            word_cnt += 1
        result_tokens.append(token)
    trimmed = "".join(result_tokens).strip()
    return trimmed


def _parse_agent_tool_call(raw_content: str) -> Optional[Dict[str, Any]]:
    """Parse a structured JSON tool call `{"tool": "...", "args": {...}}` from LLM output."""
    text = (raw_content or "").strip()
    if not text:
        return None

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    candidates: List[str] = []
    if fenced:
        candidates.append(fenced.group(1))

    brace_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if brace_match:
        candidates.append(brace_match.group(0))
    candidates.append(text)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if not isinstance(parsed, dict):
                continue
            tool_name = str(parsed.get("tool") or parsed.get("action") or parsed.get("name") or "").strip()
            if not tool_name:
                continue
            raw_args = parsed.get("args")
            if raw_args is None:
                raw_args = parsed.get("arguments")
            if raw_args is None:
                raw_args = parsed.get("parameters")
            args = dict(raw_args) if isinstance(raw_args, dict) else {}
            return {"tool": tool_name, "args": args}
        except Exception:
            continue
    return None


def _choose_recommended_service(
    requested_service: Optional[str],
    lead: HunterLead,
    scan_obs: Optional[Dict[str, Any]],
) -> str:
    cleaned = (requested_service or "").strip().lower()
    if cleaned in ALLOWED_RECOMMENDED_SERVICES:
        return cleaned

    has_ai = bool(scan_obs.get("has_ai")) if scan_obs else bool(lead.has_ai)
    missing_booking = bool(scan_obs.get("missing_online_booking", True)) if scan_obs else True
    if not has_ai:
        return "office-receptionist"
    if missing_booking or (lead.rating and float(lead.rating) >= 4.3):
        return "lead-crm-qualification"
    return "ai-marketing-growth"


def _build_diagnostic_finding(
    lead: HunterLead,
    scan_obs: Optional[Dict[str, Any]],
    crm_obs: Optional[Dict[str, Any]],
    recommended_service: str,
) -> str:
    gaps: List[str] = []
    has_ai = bool(scan_obs.get("has_ai")) if scan_obs else bool(lead.has_ai)
    widgets = (scan_obs or {}).get("detected_widgets") or []
    if not has_ai:
        gaps.append("no 24/7 AI chat or voice receptionist widget detected on website")
    else:
        gaps.append(f"existing widget detected ({', '.join(widgets[:2]) or 'chat widget'})")

    if scan_obs and scan_obs.get("missing_online_booking"):
        gaps.append("no instant self-serve appointment booking widget detected")
    if lead.pain_points:
        gaps.append(f"customer reviews mention missed-call friction ({lead.pain_points[0][:80]})")
    if crm_obs and crm_obs.get("already_contacted"):
        gaps.append("prior outreach exists in CRM (review before re-sending)")

    gap_str = "; ".join(gaps) if gaps else f"high-potential {lead.category} in {lead.city} without automated intake"
    return f"Diagnostic for {lead.business_name}: {gap_str}. Recommended solution: {SERVICE_TITLES[recommended_service]}."


def _build_concise_english_email(
    lead: HunterLead,
    recommended_service: str,
    diagnostic_finding: str,
) -> tuple[str, str]:
    recipient = lead.owner_name or f"{lead.business_name} Team"
    demo_link = f"{settings.frontend_url.rstrip('/')}/lead-hunter?demo_lead={lead.id}"

    if recommended_service == "office-receptionist":
        subject = f"Quick diagnostic + free 24/7 AI Receptionist demo for {lead.business_name}"
        body = (
            f"Hi {recipient},\n\n"
            f"I ran a quick intake diagnostic on {lead.business_name} in {lead.city} and noticed you currently have "
            f"no 24/7 AI voice or live chat receptionist capturing after-hours callers and appointment requests.\n\n"
            f"We built a live 24/7 AI Office Receptionist demo tailored to {lead.business_name} ({lead.category}) "
            f"that answers calls on the first ring, handles FAQs, and books appointments directly to your calendar:\n"
            f"{demo_link}\n\n"
            f"Plans start at $299/month ($499 white-glove setup) with a 7-day free trial. "
            f"Would you be open to testing your private demo line this week?\n\n"
            f"Best regards,\nTaloxTech AI Automation Team"
        )
    elif recommended_service == "lead-crm-qualification":
        subject = f"Capturing & qualifying more {lead.category} inquiries for {lead.business_name}"
        body = (
            f"Hi {recipient},\n\n"
            f"While auditing {lead.business_name}'s website in {lead.city}, I saw you already greet visitors online, "
            f"but inbound form and phone prospects aren't automatically scored or routed into an instant booking pipeline.\n\n"
            f"I prepared a custom TaloxTech Lead CRM & AI Qualification preview for {lead.business_name} that scores "
            f"high-intent clients in seconds and follows up automatically:\n"
            f"{demo_link}\n\n"
            f"Our managed setup is $149/month with a 7-day free trial. "
            f"Can I share a 2-minute walkthrough tailored to your practice?\n\n"
            f"Best regards,\nTaloxTech AI Automation Team"
        )
    else:
        subject = f"Automated Google reviews & patient growth idea for {lead.business_name}"
        body = (
            f"Hi {recipient},\n\n"
            f"I reviewed {lead.business_name} in {lead.city} ({diagnostic_finding[:90]}). "
            f"You have a great foundation to turn daily client visits into 5-star Google reviews and automated social DMs.\n\n"
            f"I created a tailored TaloxTech AI Marketing & Review Booster preview for {lead.business_name} here:\n"
            f"{demo_link}\n\n"
            f"Plans start at $149/month with Human-in-the-Loop approval and a 7-day free trial. "
            f"Would you like to test the live preview link today?\n\n"
            f"Best regards,\nTaloxTech AI Automation Team"
        )

    return subject[:300], _enforce_word_limit(body, max_words=125)


class LeadHunterDiagnosticAgent:
    """Bounded `MAX_STEPS = 5` diagnostic & HITL draft-generation agent for Lead Hunter."""

    async def _tool_scan_business_website(
        self,
        session: AsyncSession,
        lead: HunterLead,
        url_arg: Optional[str] = None,
    ) -> Dict[str, Any]:
        target_url = (lead.website or url_arg or "").strip() or None
        audit = await lead_hunter_discovery_service.inspect_website_and_ai(
            website_url=target_url,
            reviews=[],
        )
        widgets = list(audit.get("detected_widgets") or [])
        services_hint = audit.get("services_hint") or lead.services or f"{lead.category} services"
        booking_keywords = (
            "calendly",
            "cal.com",
            "acuity",
            "mindbody",
            "zocdoc",
            "doctolib",
            "resy",
            "opentable",
            "nexhealth",
            "book online",
            "schedule appointment",
        )
        combined_signals = (" ".join(widgets) + " " + str(services_hint)).lower()
        has_online_booking = any(k in combined_signals for k in booking_keywords)
        has_contact_form = bool(audit.get("scraped_email") or audit.get("html_checked"))

        # Safely enrich lead with freshly discovered public signals
        lead.has_ai = bool(audit.get("has_ai"))
        lead.ai_evidence = audit
        if audit.get("scraped_email") and not lead.email:
            lead.email = audit["scraped_email"]
        if audit.get("scraped_phone") and not lead.phone:
            lead.phone = audit["scraped_phone"]
        if audit.get("scraped_linkedin") and not lead.linkedin_url:
            lead.linkedin_url = audit["scraped_linkedin"]
        if audit.get("favicon_url") and not lead.favicon_url:
            lead.favicon_url = audit["favicon_url"]
        if audit.get("services_hint"):
            lead.services = audit["services_hint"]
        await session.flush()

        return {
            "url": target_url,
            "html_checked": bool(audit.get("html_checked")),
            "has_ai": bool(audit.get("has_ai")),
            "missing_live_chat": not bool(audit.get("has_ai")),
            "detected_widgets": widgets,
            "has_online_booking": has_online_booking,
            "missing_online_booking": not has_online_booking,
            "has_contact_form": has_contact_form,
            "services_detected": services_hint,
            "scraped_email": audit.get("scraped_email") or lead.email,
            "scraped_phone": audit.get("scraped_phone") or lead.phone,
            "scraped_linkedin": audit.get("scraped_linkedin") or lead.linkedin_url,
        }

    async def _tool_check_crm_history(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        lead: HunterLead,
        domain_arg: Optional[str] = None,
    ) -> Dict[str, Any]:
        norm_domain = (
            _extract_domain(lead.website)
            or _extract_domain(domain_arg)
            or (domain_arg or "").strip().lower()
            or None
        )

        # Check sent demos for this lead inside the same authenticated tenant
        sent_demos = (
            await session.execute(
                select(HunterDemo).where(
                    HunterDemo.tenant_id == tenant_id,
                    HunterDemo.lead_id == lead.id,
                    HunterDemo.status == "sent",
                )
            )
        ).scalars().all()

        # Check duplicate HunterLead records in this tenant
        other_hunter_rows = (
            await session.execute(
                select(HunterLead).where(
                    HunterLead.tenant_id == tenant_id,
                    HunterLead.id != lead.id,
                )
            )
        ).scalars().all()
        duplicate_hunter = [
            r
            for r in other_hunter_rows
            if r.business_name.strip().lower() == lead.business_name.strip().lower()
            or (norm_domain and _extract_domain(r.website) == norm_domain)
        ]

        # Check main CRM `leads` table in this tenant
        crm_rows = (
            await session.execute(
                select(Lead).where(Lead.tenant_id == tenant_id)
            )
        ).scalars().all()
        crm_matches = [
            c
            for c in crm_rows
            if c.name.strip().lower() == lead.business_name.strip().lower()
            or (norm_domain and c.email and norm_domain in c.email.lower())
        ]

        already_contacted = (
            len(sent_demos) > 0
            or lead.pipeline_stage in ("demo_sent", "followup_1", "followup_2", "followup_3", "replied_hot", "paid_client")
            or any(d.pipeline_stage in ("demo_sent", "replied_hot", "paid_client") for d in duplicate_hunter)
        )
        return {
            "domain": norm_domain,
            "already_contacted": already_contacted,
            "existing_demos_sent": len(sent_demos),
            "duplicate_hunter_leads": len(duplicate_hunter),
            "crm_matches": len(crm_matches),
            "safe_to_draft": not already_contacted and not bool(lead.do_not_disturb),
        }

    async def _tool_save_hitl_outreach_draft(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        lead: HunterLead,
        actor_id: Optional[uuid.UUID],
        recommended_service: Optional[str],
        diagnostic_finding: Optional[str],
        subject_line: Optional[str],
        email_body: Optional[str],
        scan_obs: Optional[Dict[str, Any]],
        crm_obs: Optional[Dict[str, Any]],
        steps_trace: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Save personalized English draft strictly in `status='draft'` (HITL pending approval)."""
        final_service = _choose_recommended_service(recommended_service, lead, scan_obs)
        final_finding = (diagnostic_finding or "").strip() or _build_diagnostic_finding(
            lead, scan_obs, crm_obs, final_service
        )

        fallback_subject, fallback_body = _build_concise_english_email(lead, final_service, final_finding)
        final_subject = (subject_line or "").strip()[:300] or fallback_subject
        raw_body = (email_body or "").strip() or fallback_body
        final_body = _enforce_word_limit(raw_body, max_words=125)
        word_count = _count_words(final_body)

        recipient = lead.owner_name or f"{lead.business_name} Team"
        hours = lead.working_hours or "Mon-Fri 9:00 AM - 6:00 PM"
        services = lead.services or f"{lead.category} appointments and consultations"
        demo_link = f"{settings.frontend_url.rstrip('/')}/lead-hunter?demo_lead={lead.id}"

        whatsapp_copy = (
            f"Hi {recipient}, our AI Diagnostic Agent audited {lead.business_name} ({final_finding[:110]}). "
            f"Preview your custom {SERVICE_TITLES[final_service]} demo here: {demo_link}"
        )
        voice_script = (
            f"Hello, thank you for calling {lead.business_name}. I am your 24/7 AI Receptionist. "
            f"I can help book your appointment, share our hours ({hours}), or connect you with our team for {services}."
        )
        chat_prompt = (
            f"You are the 24/7 AI Assistant for {lead.business_name} ({lead.category}) in {lead.city}, {lead.country}. "
            f"Recommended service: {final_service}. Diagnostic finding: {final_finding}"
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
            "pain_points": list(lead.pain_points or []),
            "recommended_service": final_service,
            "recommended_service_title": SERVICE_TITLES[final_service],
            "diagnostic_finding": final_finding,
            "email_word_count": word_count,
            "crm_history": crm_obs or {},
            "website_scan": scan_obs or {},
            "agent_steps": steps_trace,
            "hitl_status": "pending_human_approval",
            "usd_pricing": "$299/month | $499 setup (7-Day Free Trial)"
            if final_service == "office-receptionist"
            else "$149/month (7-Day Free Trial)",
        }

        # Reuse existing unapproved draft for this lead if present; never touch approved/sent demos
        existing_draft = (
            await session.execute(
                select(HunterDemo)
                .where(
                    HunterDemo.tenant_id == tenant_id,
                    HunterDemo.lead_id == lead.id,
                    HunterDemo.status == "draft",
                )
                .order_by(HunterDemo.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if existing_draft:
            existing_draft.email_subject = final_subject
            existing_draft.email_copy = final_body
            existing_draft.whatsapp_copy = whatsapp_copy
            existing_draft.voice_script = voice_script
            existing_draft.chat_prompt = chat_prompt
            existing_draft.business_snapshot = snapshot
            existing_draft.status = "draft"
            demo = existing_draft
        else:
            demo = HunterDemo(
                tenant_id=tenant_id,
                lead_id=lead.id,
                email_subject=final_subject,
                email_copy=final_body,
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
        meta = dict(lead.metadata_ or {})
        meta["last_agent_diagnosis"] = {
            "recommended_service": final_service,
            "diagnostic_finding": final_finding,
            "email_word_count": word_count,
        }
        lead.metadata_ = meta
        await session.flush()

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="lead_hunter.agent.executed",
                resource_type="hunter_demo",
                resource_id=demo.id,
                metadata_={
                    "lead_id": str(lead.id),
                    "business_name": lead.business_name,
                    "recommended_service": final_service,
                    "steps_executed": len(steps_trace),
                    "word_count": word_count,
                },
            )
        )
        await session.commit()
        await session.refresh(demo)
        await session.refresh(lead)
        return lead_hunter_demo_service.serialize_demo(demo, lead)

    async def run_for_lead(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        lead_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Run the bounded `MAX_STEPS = 5` AI Diagnostic & Outreach Agent for a specific tenant lead."""
        lead = (
            await session.execute(
                select(HunterLead).where(
                    HunterLead.id == lead_id,
                    HunterLead.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if not lead:
            raise ResourceNotFoundError("HunterLead", str(lead_id))

        steps_trace: List[Dict[str, Any]] = []
        scan_obs: Optional[Dict[str, Any]] = None
        crm_obs: Optional[Dict[str, Any]] = None
        saved_demo: Optional[Dict[str, Any]] = None

        system_instruction = (
            "You are the TaloxTech AI Diagnostic & Outreach Agent. "
            "You operate in a strict tool-calling loop (MAX_STEPS = 5). "
            "At each step, respond ONLY with a single JSON object: "
            '{"tool": "<tool_name>", "args": {...}}. '
            "Available tools:\n"
            '1. "scan_business_website": {"url": "<website_url>"}\n'
            '2. "check_crm_history": {"domain": "<domain>"}\n'
            '3. "save_hitl_outreach_draft": {'
            '"recommended_service": "office-receptionist | lead-crm-qualification | ai-marketing-growth", '
            '"diagnostic_finding": "<concise 1-2 sentence finding>", '
            '"subject_line": "<native English email subject>", '
            '"email_body": "<personalized native English cold email under 130 words>"'
            "}\n"
            "Always run scan_business_website first, check_crm_history second, and save_hitl_outreach_draft third."
        )

        for step_num in range(1, MAX_STEPS + 1):
            prompt = (
                f"Step {step_num}/{MAX_STEPS}\n"
                f"Lead Business: {lead.business_name} ({lead.category} in {lead.city}, {lead.country})\n"
                f"Owner: {lead.owner_name or 'Decision Maker'}\n"
                f"Website: {lead.website or 'None'}\n"
                f"Known Pain Points: {lead.pain_points or []}\n"
                f"Prior Tool Observations: {json.dumps(steps_trace)}\n"
                "Return the next JSON tool call now."
            )
            ai_res = await route_and_execute_ai_task(
                task_type="lead_hunter_diagnostic_agent",
                prompt=prompt,
                tenant_id=str(tenant_id),
                system_instruction=system_instruction,
                temperature=0.1,
                max_tokens=700,
            )

            if getattr(ai_res, "is_mock", False) or "mock ai completion" in (ai_res.content or "").lower():
                # Deterministic offline execution path below
                break

            parsed_call = _parse_agent_tool_call(ai_res.content)
            if not parsed_call:
                break

            tool_name = parsed_call["tool"]
            raw_args = parsed_call["args"]
            # SECURITY: Strip any LLM-supplied tenant_id / lead_id to enforce server-side context isolation
            safe_args = {
                k: v
                for k, v in raw_args.items()
                if k.lower() not in ("tenant_id", "lead_id", "actor_id", "status", "auto_send")
            }

            if tool_name == "scan_business_website":
                scan_obs = await self._tool_scan_business_website(
                    session, lead, url_arg=str(safe_args.get("url") or lead.website or "")
                )
                steps_trace.append({"step": step_num, "tool": tool_name, "observation": scan_obs})
            elif tool_name == "check_crm_history":
                crm_obs = await self._tool_check_crm_history(
                    session, tenant_id, lead, domain_arg=str(safe_args.get("domain") or lead.website or "")
                )
                steps_trace.append({"step": step_num, "tool": tool_name, "observation": crm_obs})
            elif tool_name == "save_hitl_outreach_draft":
                if scan_obs is None:
                    scan_obs = await self._tool_scan_business_website(session, lead, url_arg=lead.website)
                if crm_obs is None:
                    crm_obs = await self._tool_check_crm_history(session, tenant_id, lead, domain_arg=lead.website)
                steps_trace.append(
                    {
                        "step": step_num,
                        "tool": tool_name,
                        "observation": {"status": "draft_saved_pending_hitl"},
                    }
                )
                saved_demo = await self._tool_save_hitl_outreach_draft(
                    session,
                    tenant_id=tenant_id,
                    lead=lead,
                    actor_id=actor_id,
                    recommended_service=safe_args.get("recommended_service"),
                    diagnostic_finding=safe_args.get("diagnostic_finding"),
                    subject_line=safe_args.get("subject_line"),
                    email_body=safe_args.get("email_body"),
                    scan_obs=scan_obs,
                    crm_obs=crm_obs,
                    steps_trace=steps_trace,
                )
                break
            else:
                break

        # Deterministic completion safety net (offline/mock mode or if LLM stopped before saving draft)
        if scan_obs is None and len(steps_trace) < MAX_STEPS:
            scan_obs = await self._tool_scan_business_website(session, lead, url_arg=lead.website)
            steps_trace.append(
                {
                    "step": len(steps_trace) + 1,
                    "tool": "scan_business_website",
                    "observation": scan_obs,
                }
            )

        if crm_obs is None and len(steps_trace) < MAX_STEPS:
            crm_obs = await self._tool_check_crm_history(session, tenant_id, lead, domain_arg=lead.website)
            steps_trace.append(
                {
                    "step": len(steps_trace) + 1,
                    "tool": "check_crm_history",
                    "observation": crm_obs,
                }
            )

        if saved_demo is None:
            steps_trace.append(
                {
                    "step": min(MAX_STEPS, len(steps_trace) + 1),
                    "tool": "save_hitl_outreach_draft",
                    "observation": {"status": "draft_saved_pending_hitl"},
                }
            )
            saved_demo = await self._tool_save_hitl_outreach_draft(
                session,
                tenant_id=tenant_id,
                lead=lead,
                actor_id=actor_id,
                recommended_service=None,
                diagnostic_finding=None,
                subject_line=None,
                email_body=None,
                scan_obs=scan_obs,
                crm_obs=crm_obs,
                steps_trace=steps_trace,
            )

        snap = saved_demo.get("business_snapshot") or {}
        return {
            "lead_id": str(lead.id),
            "tenant_id": str(tenant_id),
            "recommended_service": snap.get("recommended_service"),
            "recommended_service_title": snap.get("recommended_service_title"),
            "diagnostic_finding": snap.get("diagnostic_finding"),
            "email_word_count": snap.get("email_word_count"),
            "steps_executed": len(steps_trace),
            "max_steps": MAX_STEPS,
            "steps_trace": steps_trace,
            "website_scan": scan_obs,
            "crm_history": crm_obs,
            "demo": saved_demo,
            "hitl_pending_approval": True,
            "auto_sent": False,
        }


lead_hunter_agent = LeadHunterDiagnosticAgent()
