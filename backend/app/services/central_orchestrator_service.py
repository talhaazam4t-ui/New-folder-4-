"""Phase 2 Central Orchestrator, DB-Driven Service & Skill Registry, Proactive Episodic Memory,
Self-Reflection Quality Control (QC) Agent, Dynamic Auto-Configure UI, and Granular Service Toggles.

Key Capabilities:
1. Database-Driven Service & Skill Registry (`public.services` + `public.agent_skills`):
   Automatically ingests newly added services and skills into the Orchestrator's live context
   without code changes.
2. Proactive Episodic Memory (`public.tenant_episodic_memories`):
   Queries tenant-scoped past interactions, pitch outcomes, and conversion scores before every task
   and persists new episodic learnings afterward.
3. Self-Reflection / Quality Control (QC) Agent:
   Intercepts generated drafts, checks tone (removes aggressive/spammy claims), enforces word limits
   (e.g., `< 130` words), checks factual alignment with the database catalog, and auto-revises.
4. Dynamic Auto-Configure UI & Super Admin Service Toggles + HITL Queue:
   Tailors the client dashboard to show only provisioned services while keeping an Upgrade Center /
   Marketplace visible for add-ons, allows Super Admin per-tenant module toggles, and routes sensitive
   actions to the tenant's HITL Approval Queue.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.automation.approval_manager import approval_manager
from app.core.exceptions import ResourceNotFoundError, TaloxException
from app.database.models.automation import AuditLog
from app.database.models.governance import AgentSkill, TenantEpisodicMemory
from app.database.models.service import Service, ServiceSubscription
from app.database.models.tenant import Tenant
from app.integrations.ai_providers.router import route_and_execute_ai_task
from app.schemas.approval import ApprovalCreateRequest
from app.services.billing_service import billing_service
from app.services.tier_quota_service import tier_quota_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_SKILLS_SEED: List[Dict[str, Any]] = [
    {
        "slug": "lead_diagnostic_pitch",
        "name": "Lead Diagnostic & Cold Pitch Generator",
        "service_slug": "lead-crm-qualification",
        "description": "Audits prospect website gaps and drafts a personalized <130-word B2B outreach email.",
        "tool_schema": {"tools": ["scan_business_website", "check_crm_history", "save_hitl_outreach_draft"]},
        "default_model_tier": "fast_free",
        "token_budget": 1200,
        "max_words": 125,
        "requires_hitl": True,
    },
    {
        "slug": "voice_receptionist_triage",
        "name": "24/7 Voice Receptionist & Cal.com Booking Triage",
        "service_slug": "office-receptionist",
        "description": "Qualifies inbound voice callers, checks Cal.com slots, and escalates urgent calls.",
        "tool_schema": {"tools": ["calcom_availability", "calcom_book", "human_transfer"]},
        "default_model_tier": "fast_free",
        "token_budget": 1000,
        "max_words": 110,
        "requires_hitl": False,
    },
    {
        "slug": "property_rent_reconciliation",
        "name": "Property & Rent Ledger Reconciliation Specialist",
        "service_slug": "business-financial-tracking",
        "description": "Reconciles multi-currency rent schedules, audits overdue invoices, and drafts payment reminders.",
        "tool_schema": {"tools": ["reconcile_ledger", "ocr_receipt_audit", "draft_rent_reminder"]},
        "default_model_tier": "fast_free",
        "token_budget": 1500,
        "max_words": 125,
        "requires_hitl": True,
    },
    {
        "slug": "whatsapp_concierge_reply",
        "name": "WhatsApp Omnichannel Concierge Responder",
        "service_slug": "whatsapp-business-concierge",
        "description": "Answers customer FAQs from RAG knowledge chunks and escalates complex inquiries to human inbox.",
        "tool_schema": {"tools": ["rag_knowledge_search", "send_whatsapp_reply", "escalate_to_human"]},
        "default_model_tier": "fast_free",
        "token_budget": 900,
        "max_words": 100,
        "requires_hitl": False,
    },
    {
        "slug": "campaign_repurpose_engine",
        "name": "Omnichannel Content & Review Booster Strategist",
        "service_slug": "ai-marketing-growth",
        "description": "Synthesizes high-performing campaigns into LinkedIn posts, newsletters, and review replies.",
        "tool_schema": {"tools": ["repurpose_campaign", "route_google_review", "meta_comment_dm"]},
        "default_model_tier": "fast_free",
        "token_budget": 1600,
        "max_words": 125,
        "requires_hitl": True,
    },
    {
        "slug": "multi_agent_workflow_planner",
        "name": "Multi-Agent Task Decomposer & Coordinator",
        "service_slug": "multi-agent-orchestration",
        "description": "Decomposes complex agency objectives across specialized sub-skills with token budget guards.",
        "tool_schema": {"tools": ["decompose_goal", "delegate_skill", "verify_qc"]},
        "default_model_tier": "reasoning",
        "token_budget": 2000,
        "max_words": 130,
        "requires_hitl": True,
    },
    {
        "slug": "executive_roi_compliance_auditor",
        "name": "Executive ROI & Contract Compliance Auditor",
        "service_slug": "executive-analytics-compliance",
        "description": "Audits weekly cross-engine ROI, SLA compliance flags, and token governance metrics.",
        "tool_schema": {"tools": ["compile_weekly_roi", "flag_contract_breach", "export_pdf_report"]},
        "default_model_tier": "reasoning",
        "token_budget": 1800,
        "max_words": 130,
        "requires_hitl": True,
    },
]

SPAM_OR_UNSAFE_PHRASES: Dict[str, str] = {
    "100% guaranteed": "proven",
    "guaranteed results": "measurable results",
    "buy now": "explore your live demo",
    "act immediately": "let us know when convenient",
    "once in a lifetime": "tailored",
    "no risk": "7-day free trial",
    "free money": "cost savings",
}


def _count_words(text: str) -> int:
    return len([w for w in re.split(r"\s+", (text or "").strip()) if w])


def _trim_to_max_words(text: str, max_words: int) -> str:
    tokens = [t for t in re.split(r"(\s+)", (text or "").strip()) if t]
    out: List[str] = []
    cnt = 0
    for tok in tokens:
        if not tok.isspace():
            if cnt >= max_words:
                break
            cnt += 1
        out.append(tok)
    trimmed = "".join(out).strip()
    if trimmed and trimmed[-1] not in ".!?":
        trimmed += "."
    return trimmed


class CentralOrchestratorService:
    """Phase 2 DB-Driven Central Orchestrator, Episodic Memory & Self-Reflection QC Engine."""

    @staticmethod
    def serialize_skill(row: AgentSkill) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "slug": row.slug,
            "name": row.name,
            "service_slug": row.service_slug,
            "description": row.description,
            "tool_schema": row.tool_schema or {},
            "default_model_tier": row.default_model_tier,
            "token_budget": int(row.token_budget),
            "max_words": int(row.max_words),
            "requires_hitl": bool(row.requires_hitl),
            "active": bool(row.active),
        }

    @staticmethod
    def serialize_memory(row: TenantEpisodicMemory) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "memory_type": row.memory_type,
            "skill_slug": row.skill_slug,
            "context_key": row.context_key,
            "summary": row.summary,
            "outcome_score": round(float(row.outcome_score or 0.0), 2),
            "metadata": row.metadata_ or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    async def ensure_default_skills_seeded(self, session: AsyncSession) -> List[AgentSkill]:
        res = await session.execute(select(AgentSkill))
        existing = {r.slug: r for r in res.scalars().all()}
        dirty = False
        for item in DEFAULT_SKILLS_SEED:
            if item["slug"] not in existing:
                row = AgentSkill(
                    slug=item["slug"],
                    name=item["name"],
                    service_slug=item["service_slug"],
                    description=item["description"],
                    tool_schema=item["tool_schema"],
                    default_model_tier=item["default_model_tier"],
                    token_budget=int(item["token_budget"]),
                    max_words=int(item["max_words"]),
                    requires_hitl=bool(item["requires_hitl"]),
                    active=True,
                )
                session.add(row)
                existing[item["slug"]] = row
                dirty = True
        if dirty:
            await session.commit()
            for r in existing.values():
                await session.refresh(r)
        return list(existing.values())

    async def register_or_update_skill(
        self,
        session: AsyncSession,
        *,
        slug: str,
        name: str,
        service_slug: str,
        description: str,
        tool_schema: Optional[Dict[str, Any]] = None,
        default_model_tier: str = "fast_free",
        token_budget: int = 1500,
        max_words: int = 130,
        requires_hitl: bool = True,
        active: bool = True,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Dynamically add or update an agent skill in the database without hardcoding."""
        await self.ensure_default_skills_seeded(session)
        clean_slug = slug.strip().lower()
        existing = (
            await session.execute(select(AgentSkill).where(AgentSkill.slug == clean_slug))
        ).scalar_one_or_none()

        if existing:
            existing.name = name.strip()
            existing.service_slug = service_slug.strip().lower()
            existing.description = description.strip()
            if tool_schema is not None:
                existing.tool_schema = tool_schema
            existing.default_model_tier = default_model_tier
            existing.token_budget = max(100, min(int(token_budget), 16000))
            existing.max_words = max(20, min(int(max_words), 1000))
            existing.requires_hitl = bool(requires_hitl)
            existing.active = bool(active)
            row = existing
        else:
            row = AgentSkill(
                slug=clean_slug,
                name=name.strip(),
                service_slug=service_slug.strip().lower(),
                description=description.strip(),
                tool_schema=tool_schema or {},
                default_model_tier=default_model_tier,
                token_budget=max(100, min(int(token_budget), 16000)),
                max_words=max(20, min(int(max_words), 1000)),
                requires_hitl=bool(requires_hitl),
                active=bool(active),
            )
            session.add(row)

        await session.commit()
        await session.refresh(row)
        return self.serialize_skill(row)

    async def get_dynamic_registry_context(
        self,
        session: AsyncSession,
        tenant_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Load all active services & skills directly from Supabase DB so new rows appear immediately."""
        await billing_service.ensure_default_catalog(session)
        await self.ensure_default_skills_seeded(session)

        services = await billing_service.list_services(session, active_only=True)
        skills_rows = (
            await session.execute(
                select(AgentSkill).where(AgentSkill.active == True).order_by(AgentSkill.created_at.asc())  # noqa: E712
            )
        ).scalars().all()

        service_list: List[Dict[str, Any]] = []
        for srv in services:
            schema = srv.configuration_schema or {}
            service_list.append(
                {
                    "id": str(srv.id),
                    "slug": srv.slug,
                    "name": srv.name,
                    "category": srv.category,
                    "description": srv.description,
                    "base_price": schema.get("base_price", 99.0),
                    "packages": schema.get("packages", []),
                    "required_integrations": schema.get("required_integrations", []),
                }
            )

        skills_list = [self.serialize_skill(sk) for sk in skills_rows]
        return {
            "services_count": len(service_list),
            "skills_count": len(skills_list),
            "services": service_list,
            "skills": skills_list,
        }

    async def record_episodic_memory(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        memory_type: str,
        context_key: str,
        summary: str,
        skill_slug: Optional[str] = None,
        outcome_score: float = 80.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store a tenant-isolated episodic memory of an interaction, pitch, or conversion outcome."""
        row = TenantEpisodicMemory(
            tenant_id=tenant_id,
            memory_type=memory_type.strip().lower()[:64],
            skill_slug=skill_slug.strip().lower()[:100] if skill_slug else None,
            context_key=context_key.strip()[:200],
            summary=summary.strip()[:2000],
            outcome_score=round(float(outcome_score), 2),
            metadata_=dict(metadata or {}),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return self.serialize_memory(row)

    async def query_relevant_memories(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        query_text: Optional[str] = None,
        memory_type: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant tenant episodic memories prior to executing an agent action."""
        q = select(TenantEpisodicMemory).where(TenantEpisodicMemory.tenant_id == tenant_id)
        if memory_type:
            q = q.where(TenantEpisodicMemory.memory_type == memory_type.strip().lower())
        q = q.order_by(TenantEpisodicMemory.outcome_score.desc(), TenantEpisodicMemory.created_at.desc()).limit(30)
        rows = list((await session.execute(q)).scalars().all())

        if query_text and query_text.strip():
            keywords = [w.lower() for w in re.findall(r"[a-zA-Z0-9]{3,}", query_text)][:8]
            if keywords:
                rows.sort(
                    key=lambda r: (
                        sum(1 for kw in keywords if kw in (r.summary + " " + r.context_key).lower()),
                        float(r.outcome_score or 0.0),
                    ),
                    reverse=True,
                )

        return [self.serialize_memory(r) for r in rows[:limit]]

    def run_self_reflection_qc(
        self,
        draft_text: str,
        *,
        max_words: int = 130,
        required_brand_or_service: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Self-Reflection / Quality Control (QC) Agent:
        Checks tone, prohibited claims, word count limit, and factual context; auto-revises before output.
        """
        original = (draft_text or "").strip()
        revised = original
        issues_fixed: List[str] = []
        words_before = _count_words(original)

        # 1. Tone & Legal Claim Screening
        for bad_phrase, safe_replacement in SPAM_OR_UNSAFE_PHRASES.items():
            pattern = re.compile(re.escape(bad_phrase), flags=re.IGNORECASE)
            if pattern.search(revised):
                revised = pattern.sub(safe_replacement, revised)
                issues_fixed.append(f"replaced_unsafe_claim:{bad_phrase}")

        # Strip excessive exclamation marks (!!! -> .)
        if "!!" in revised:
            revised = re.sub(r"!{2,}", ".", revised)
            issues_fixed.append("normalized_excessive_exclamation")

        # 2. Factual Grounding Check
        if required_brand_or_service and required_brand_or_service.lower() not in revised.lower():
            revised = f"{revised}\n\nRecommended Service: {required_brand_or_service}."
            issues_fixed.append("appended_factual_service_reference")

        # 3. Strict Word Limit Enforcement
        effective_cap = max(10, int(max_words) - 2) if int(max_words) == 130 else max(10, int(max_words))
        if _count_words(revised) > effective_cap:
            revised = _trim_to_max_words(revised, effective_cap)
            issues_fixed.append(f"trimmed_to_word_limit:{effective_cap}")

        words_after = _count_words(revised)
        return {
            "passed_initial_check": len(issues_fixed) == 0,
            "auto_revised": len(issues_fixed) > 0,
            "word_count_before": words_before,
            "word_count_after": words_after,
            "max_words_limit": max_words,
            "issues_fixed": issues_fixed,
            "final_text": revised,
        }

    async def orchestrate_task(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        objective: str,
        skill_slug: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
        actor_id: Optional[uuid.UUID] = None,
        force_hitl: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Decompose & execute a task using DB-driven skills, episodic memory, Free-First routing,
        Self-Reflection QC, and HITL Approval Queue routing.
        """
        # 1. Verify tenant quota is not hard-locked at 100%
        await tier_quota_service.assert_not_hard_locked(session, tenant_id)

        # 2. Load DB-driven services & skills registry dynamically
        registry = await self.get_dynamic_registry_context(session, tenant_id)
        skills = registry["skills"]
        if not skills:
            raise TaloxException(message="No active agent skills in registry", code="NO_ACTIVE_SKILLS", status_code=400)

        selected_skill = None
        if skill_slug:
            selected_skill = next((s for s in skills if s["slug"] == skill_slug.strip().lower()), None)
            if not selected_skill:
                raise ResourceNotFoundError("AgentSkill", skill_slug)
        else:
            obj_low = objective.lower()
            for s in skills:
                if any(tok in obj_low for tok in s["slug"].split("_")) or s["service_slug"] in obj_low:
                    selected_skill = s
                    break
            if not selected_skill:
                selected_skill = skills[0]

        # 3. Query tenant's proactive episodic memories before acting
        memories = await self.query_relevant_memories(
            session,
            tenant_id=tenant_id,
            query_text=f"{selected_skill['slug']} {objective}",
            limit=4,
        )
        memory_context = (
            "\n".join(f"- [{m['memory_type']}] {m['summary']} (score: {m['outcome_score']})" for m in memories)
            if memories
            else "No prior episodic memories recorded for this tenant yet."
        )

        # 4. Route task via Free-First AI Router (routine -> fast_free tier; complex -> reasoning tier)
        task_type = (
            "complex_planning"
            if selected_skill["default_model_tier"] == "reasoning"
            else "quick_summary"
        )
        token_budget = min(int(selected_skill["token_budget"]), 4000)
        max_words = int(selected_skill["max_words"] or 130)

        catalog_summary = ", ".join(
            f"{srv['name']} ({srv['slug']}: ${srv['base_price']}/mo)"
            for srv in registry["services"]
        )
        prompt = (
            f"Active Skill: {selected_skill['name']} ({selected_skill['slug']})\n"
            f"Linked Service: {selected_skill['service_slug']}\n"
            f"Available Catalog Services: {catalog_summary}\n"
            f"Tenant Episodic Memories:\n{memory_context}\n\n"
            f"Task Objective: {objective}\n"
            f"Additional Context: {context_data or {}}\n"
            f"Write a concise, professional response under {max_words} words."
        )

        ai_res = await route_and_execute_ai_task(
            task_type=task_type,
            prompt=prompt,
            tenant_id=str(tenant_id),
            system_instruction=(
                "You are the TaloxTech Central Orchestrator Agent. "
                "Follow tenant episodic memory learnings, stay under the requested word limit, "
                "and never make exaggerated or guaranteed claims."
            ),
            max_tokens=token_budget,
        )

        if getattr(ai_res, "is_mock", False) or "mock ai completion" in (ai_res.content or "").lower():
            raw_draft = (
                f"Prepared {selected_skill['name']} deliverable for objective: {objective[:120]}. "
                f"Grounded in TaloxTech service '{selected_skill['service_slug']}' and {len(memories)} prior episodic memory record(s). "
                f"Ready for human review."
            )
        else:
            raw_draft = ai_res.content.strip()

        # 5. Run Self-Reflection / Quality Control (QC) Agent
        qc_report = self.run_self_reflection_qc(
            raw_draft,
            max_words=max_words,
            required_brand_or_service=selected_skill["service_slug"],
        )
        final_output = qc_report["final_text"]

        # 6. Meter token usage against tenant's subscription tier quota
        tokens_consumed = min(int(ai_res.total_tokens or 120), token_budget)
        quota_snapshot = await tier_quota_service.record_usage(
            session=session,
            tenant_id=tenant_id,
            tokens_delta=tokens_consumed,
            api_calls_delta=1,
            enforce_lock_before=False,
            actor_id=actor_id,
        )

        # 7. Route sensitive actions to the tenant's HITL Approval Queue
        requires_hitl = bool(force_hitl) if force_hitl is not None else bool(selected_skill["requires_hitl"])
        approval_id: Optional[str] = None
        if requires_hitl:
            approval_obj = await approval_manager.request_approval(
                session=session,
                tenant_id=tenant_id,
                request=ApprovalCreateRequest(
                    action_type=f"orchestrator.{selected_skill['slug']}",
                    proposed_action={
                        "skill_slug": selected_skill["slug"],
                        "service_slug": selected_skill["service_slug"],
                        "objective": objective,
                        "output": final_output,
                        "qc_report": qc_report,
                    },
                    requested_by=str(actor_id) if actor_id else "central_orchestrator",
                    expires_in_hours=48,
                ),
            )
            approval_id = str(approval_obj.id)

        # 8. Store new episodic memory & immutable audit log
        memory_saved = await self.record_episodic_memory(
            session,
            tenant_id=tenant_id,
            memory_type="orchestrated_task",
            skill_slug=selected_skill["slug"],
            context_key=objective[:180],
            summary=final_output[:500],
            outcome_score=90.0 if qc_report["passed_initial_check"] else 82.0,
            metadata={"approval_id": approval_id, "auto_revised": qc_report["auto_revised"]},
        )

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="orchestrator.task.executed",
                resource_type="agent_skill",
                metadata_={
                    "skill_slug": selected_skill["slug"],
                    "service_slug": selected_skill["service_slug"],
                    "tokens_consumed": tokens_consumed,
                    "requires_hitl": requires_hitl,
                    "approval_id": approval_id,
                    "qc_auto_revised": qc_report["auto_revised"],
                },
            )
        )
        await session.commit()

        return {
            "tenant_id": str(tenant_id),
            "selected_skill": selected_skill,
            "episodic_memories_used": memories,
            "episodic_memory_saved": memory_saved,
            "raw_draft": raw_draft,
            "final_output": final_output,
            "qc_report": qc_report,
            "requires_hitl": requires_hitl,
            "hitl_status": "pending_approval" if requires_hitl else "auto_approved",
            "approval_id": approval_id,
            "tokens_consumed": tokens_consumed,
            "token_budget": token_budget,
            "tier_quota": quota_snapshot,
        }

    async def get_dynamic_ui_configuration(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Auto-configure the client's dashboard based on industry, active subscriptions,
        and Super Admin granular service toggles—hiding unprovisioned modules while exposing
        the Upgrade Center / Marketplace for add-ons.
        """
        registry = await self.get_dynamic_registry_context(session, tenant_id)
        tenant = (
            await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        ).scalar_one_or_none()
        if not tenant:
            raise ResourceNotFoundError("Tenant", str(tenant_id))

        subs = (
            await session.execute(
                select(ServiceSubscription, Service)
                .join(Service, ServiceSubscription.service_id == Service.id)
                .where(ServiceSubscription.tenant_id == tenant_id)
            )
        ).all()

        t_settings = dict(tenant.settings or {})
        admin_overrides: Dict[str, bool] = dict(t_settings.get("admin_service_toggles") or {})
        subscribed_active_slugs = {
            srv.slug
            for sub, srv in subs
            if sub.status in ("active", "on_trial", "pending_payment")
        }

        provisioned_services: List[Dict[str, Any]] = []
        upgrade_marketplace_addons: List[Dict[str, Any]] = []
        hidden_unprovisioned_slugs: List[str] = []

        for srv in registry["services"]:
            slug = srv["slug"]
            if slug in admin_overrides:
                is_enabled = bool(admin_overrides[slug])
            else:
                is_enabled = slug in subscribed_active_slugs

            linked_skills = [sk for sk in registry["skills"] if sk["service_slug"] == slug]
            item = {
                **srv,
                "enabled": is_enabled,
                "admin_override": admin_overrides.get(slug),
                "skills": linked_skills,
            }
            if is_enabled:
                provisioned_services.append(item)
            else:
                hidden_unprovisioned_slugs.append(slug)
                upgrade_marketplace_addons.append(item)

        return {
            "tenant_id": str(tenant_id),
            "tenant_name": tenant.name,
            "industry": tenant.industry,
            "provisioned_services": provisioned_services,
            "hidden_unprovisioned_slugs": hidden_unprovisioned_slugs,
            "upgrade_marketplace_addons": upgrade_marketplace_addons,
            "admin_service_toggles": admin_overrides,
        }

    async def admin_toggle_tenant_service(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        service_slug: str,
        enabled: bool,
        admin_user_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Super Admin granular toggle to enable or disable a specific service module for a tenant."""
        await billing_service.ensure_default_catalog(session)
        tenant = (
            await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        ).scalar_one_or_none()
        if not tenant:
            raise ResourceNotFoundError("Tenant", str(tenant_id))

        clean_slug = service_slug.strip().lower()
        srv = (
            await session.execute(select(Service).where(Service.slug == clean_slug))
        ).scalar_one_or_none()
        if not srv:
            raise ResourceNotFoundError("Service", clean_slug)

        curr_settings = dict(tenant.settings or {})
        toggles = dict(curr_settings.get("admin_service_toggles") or {})
        toggles[clean_slug] = bool(enabled)
        curr_settings["admin_service_toggles"] = toggles

        enabled_mods = list(curr_settings.get("enabled_modules") or [])
        if enabled and clean_slug not in enabled_mods:
            enabled_mods.append(clean_slug)
        elif not enabled and clean_slug in enabled_mods:
            enabled_mods.remove(clean_slug)
        curr_settings["enabled_modules"] = enabled_mods
        tenant.settings = curr_settings

        # Also sync or create ServiceSubscription row
        sub = (
            await session.execute(
                select(ServiceSubscription).where(
                    ServiceSubscription.tenant_id == tenant_id,
                    ServiceSubscription.service_id == srv.id,
                )
            )
        ).scalar_one_or_none()
        if sub:
            sub.status = "active" if enabled else "paused"
        elif enabled:
            schema = srv.configuration_schema or {}
            session.add(
                ServiceSubscription(
                    tenant_id=tenant_id,
                    service_id=srv.id,
                    plan_name="growth",
                    status="active",
                    billing_interval="monthly",
                    price=float(schema.get("base_price") or 99.0),
                    started_at=datetime.now(timezone.utc),
                )
            )

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=admin_user_id,
                actor_type="admin",
                action="admin.service_module.toggled",
                resource_type="service",
                resource_id=srv.id,
                metadata_={"service_slug": clean_slug, "enabled": bool(enabled)},
            )
        )
        await session.commit()
        return await self.get_dynamic_ui_configuration(session, tenant_id)


central_orchestrator_service = CentralOrchestratorService()
