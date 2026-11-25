"""Master Control Panel, Budget Mode Presets & Daily Anti-Ban Quota Service.

Golden Rule:
- ALL automation and paid/credit-consuming APIs start OFF (`is_on=False`).
- ONLY `direct_call_mode` starts ON (`is_on=True`) for founder-led manual outreach.
- Daily counters reset cleanly at UTC midnight and hard-stop free-tier overages.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.core.exceptions import TaloxException
from app.database.models.automation import AuditLog
from app.database.models.lead_hunter import (
    HunterDemo,
    HunterFollowup,
    HunterLead,
    HunterModuleSetting,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_MODULE_SPECS: Dict[str, Dict[str, Any]] = {
    "free_osm_finder": {
        "label": "Free OpenStreetMap Lead Finder ($0)",
        "description": "100% free international real business search via OpenStreetMap + Website AI & Contact Scanner (zero API key or billing card required).",
        "default_on": False,
        "default_limit": 50,
    },
    "google_places_finder": {
        "label": "Google Places Lead Finder",
        "description": "Search real international businesses via Google Places API.",
        "default_on": False,
        "default_limit": 50,
    },
    "apollo_enrichment": {
        "label": "Apollo.io Enrichment (Free Tier Only)",
        "description": "Strict daily free-credit cap (10-15/day). Skips leads that already have AI.",
        "default_on": False,
        "default_limit": 10,
    },
    "auto_demo_generator": {
        "label": "Auto Demo Generator",
        "description": "Generates tailored English Email, WhatsApp, Voice & Chat AI demos.",
        "default_on": False,
        "default_limit": 25,
    },
    "auto_whatsapp_sender": {
        "label": "Auto WhatsApp Sender (UAE / Dubai Only)",
        "description": "Dispatches approved demos via WhatsApp Cloud API strictly to UAE/Dubai leads.",
        "default_on": False,
        "default_limit": 20,
    },
    "auto_email_sender": {
        "label": "Auto Email Sender (USA / UK / CA / AU)",
        "description": "Sends approved English demos via Gmail/Resend with daily warm-up cap (20/50/200).",
        "default_on": False,
        "default_limit": 20,
    },
    "auto_linkedin_sender": {
        "label": "Auto LinkedIn Sender (1-Click Manual Drafts)",
        "description": "Generates daily-capped personalized LinkedIn note & DM drafts for manual safe sending.",
        "default_on": False,
        "default_limit": 20,
    },
    "auto_followup_engine": {
        "label": "Auto Follow-up Engine (24h / 48h / 72h)",
        "description": "Schedules 3 spaced follow-ups and stops immediately on any reply.",
        "default_on": False,
        "default_limit": 30,
    },
    "auto_chat_reply": {
        "label": "Auto Chat Reply (AI Bot Reply)",
        "description": "Keep OFF while replying manually; never replies once human handover is triggered.",
        "default_on": False,
        "default_limit": 50,
    },
    "direct_call_mode": {
        "label": "Direct Call / Outreach Mode (Main Mode)",
        "description": "Prioritizes Hot Leads (Score 80+) for direct calls & manual outreach with timezone scripts.",
        "default_on": True,
        "default_limit": 100,
    },
}

MODULE_ORDER: List[str] = [
    "free_osm_finder",
    "google_places_finder",
    "apollo_enrichment",
    "auto_demo_generator",
    "auto_whatsapp_sender",
    "auto_email_sender",
    "auto_linkedin_sender",
    "auto_followup_engine",
    "auto_chat_reply",
    "direct_call_mode",
]


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class LeadHunterControlService:
    """Manages default-OFF switches, Budget Mode presets, and strict daily credit caps."""

    async def ensure_initialized(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> List[HunterModuleSetting]:
        res = await session.execute(
            select(HunterModuleSetting).where(HunterModuleSetting.tenant_id == tenant_id)
        )
        rows = list(res.scalars().all())
        by_name = {r.module_name: r for r in rows}
        today = _today_utc()
        dirty = False

        for mod_name in MODULE_ORDER:
            spec = DEFAULT_MODULE_SPECS[mod_name]
            row = by_name.get(mod_name)
            if not row:
                row = HunterModuleSetting(
                    tenant_id=tenant_id,
                    module_name=mod_name,
                    is_on=bool(spec["default_on"]),
                    budget_mode="custom",
                    daily_limit=int(spec["default_limit"]),
                    used_today=0,
                    usage_date=today,
                )
                session.add(row)
                by_name[mod_name] = row
                dirty = True
            elif row.usage_date != today:
                row.used_today = 0
                row.usage_date = today
                dirty = True

        if dirty:
            await session.commit()
            for r in by_name.values():
                await session.refresh(r)

        return [by_name[m] for m in MODULE_ORDER]

    @staticmethod
    def _serialize_setting(row: HunterModuleSetting) -> Dict[str, Any]:
        spec = DEFAULT_MODULE_SPECS.get(row.module_name, {})
        remaining = max(0, int(row.daily_limit) - int(row.used_today))
        return {
            "id": str(row.id),
            "module_name": row.module_name,
            "label": spec.get("label", row.module_name),
            "description": spec.get("description", ""),
            "is_on": bool(row.is_on),
            "budget_mode": row.budget_mode,
            "daily_limit": int(row.daily_limit),
            "used_today": int(row.used_today),
            "remaining_today": remaining,
            "usage_date": row.usage_date,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def get_control_panel(self, session: AsyncSession, tenant_id: uuid.UUID) -> Dict[str, Any]:
        rows = await self.ensure_initialized(session, tenant_id)
        items = [self._serialize_setting(r) for r in rows]
        budget_mode = rows[0].budget_mode if rows else "custom"
        return {
            "budget_mode": budget_mode,
            "modules": items,
            "module_map": {item["module_name"]: item for item in items},
        }

    async def toggle_module(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        module_name: str,
        is_on: Optional[bool] = None,
        daily_limit: Optional[int] = None,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        clean_name = module_name.strip().lower()
        if clean_name not in DEFAULT_MODULE_SPECS:
            raise TaloxException(
                message=f"Unknown Lead Hunter module '{module_name}'",
                code="INVALID_MODULE_NAME",
                status_code=400,
            )

        rows = await self.ensure_initialized(session, tenant_id)
        target = next(r for r in rows if r.module_name == clean_name)

        if is_on is not None:
            target.is_on = bool(is_on)
            target.budget_mode = "custom"
        if daily_limit is not None:
            capped = max(1, min(int(daily_limit), 500))
            if clean_name == "apollo_enrichment":
                capped = min(capped, 50)
            target.daily_limit = capped

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="lead_hunter.setting.updated",
                resource_type="hunter_setting",
                resource_id=target.id,
                metadata_={
                    "module_name": clean_name,
                    "is_on": target.is_on,
                    "daily_limit": target.daily_limit,
                },
            )
        )
        await session.commit()
        return await self.get_control_panel(session, tenant_id)

    async def apply_budget_mode(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        budget_mode: str,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        mode = budget_mode.strip().lower()
        if mode not in ("free", "low_budget", "full_auto"):
            raise TaloxException(
                message="Budget mode must be 'free', 'low_budget', or 'full_auto'",
                code="INVALID_BUDGET_MODE",
                status_code=400,
            )

        rows = await self.ensure_initialized(session, tenant_id)
        presets: Dict[str, Dict[str, bool]] = {
            "free": {
                "free_osm_finder": True,
                "google_places_finder": True,
                "apollo_enrichment": True,
                "auto_demo_generator": False,
                "auto_whatsapp_sender": False,
                "auto_email_sender": False,
                "auto_linkedin_sender": False,
                "auto_followup_engine": False,
                "auto_chat_reply": False,
                "direct_call_mode": True,
            },
            "low_budget": {
                "free_osm_finder": True,
                "google_places_finder": True,
                "apollo_enrichment": True,
                "auto_demo_generator": True,
                "auto_whatsapp_sender": False,
                "auto_email_sender": False,
                "auto_linkedin_sender": False,
                "auto_followup_engine": False,
                "auto_chat_reply": False,
                "direct_call_mode": True,
            },
            "full_auto": {k: True for k in MODULE_ORDER},
        }
        chosen = presets[mode]
        for row in rows:
            row.is_on = chosen[row.module_name]
            row.budget_mode = mode
            if row.module_name == "apollo_enrichment" and mode in ("free", "low_budget"):
                row.daily_limit = min(int(row.daily_limit or 10), 10)

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="lead_hunter.budget_mode.applied",
                resource_type="hunter_setting",
                metadata_={"budget_mode": mode},
            )
        )
        await session.commit()
        return await self.get_control_panel(session, tenant_id)

    async def get_module_row(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        module_name: str,
    ) -> HunterModuleSetting:
        rows = await self.ensure_initialized(session, tenant_id)
        for r in rows:
            if r.module_name == module_name:
                return r
        raise TaloxException(message=f"Module '{module_name}' not found", code="NOT_FOUND", status_code=404)

    async def assert_module_enabled_and_quota(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        module_name: str,
        units: int = 1,
        require_switch_on: bool = True,
    ) -> HunterModuleSetting:
        row = await self.get_module_row(session, tenant_id, module_name)
        spec = DEFAULT_MODULE_SPECS[module_name]
        if require_switch_on and not row.is_on:
            raise TaloxException(
                message=f"'{spec['label']}' is currently OFF. Turn it ON in the Control Panel to run it.",
                code="MODULE_DISABLED",
                status_code=403,
            )
        if int(row.used_today) + units > int(row.daily_limit):
            raise TaloxException(
                message=f"Daily limit reached for '{spec['label']}' ({row.used_today}/{row.daily_limit} used today). Hard-stopped to protect your quota.",
                code="DAILY_QUOTA_EXCEEDED",
                status_code=429,
            )
        return row

    async def increment_usage(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        module_name: str,
        units: int = 1,
    ) -> HunterModuleSetting:
        row = await self.get_module_row(session, tenant_id, module_name)
        row.used_today = int(row.used_today or 0) + max(0, int(units))
        row.usage_date = _today_utc()
        await session.commit()
        await session.refresh(row)
        return row

    async def get_dashboard_kpis(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Dict[str, Any]:
        control = await self.get_control_panel(session, tenant_id)
        leads = (
            await session.execute(select(HunterLead).where(HunterLead.tenant_id == tenant_id))
        ).scalars().all()
        demos = (
            await session.execute(select(HunterDemo).where(HunterDemo.tenant_id == tenant_id))
        ).scalars().all()
        followups = (
            await session.execute(select(HunterFollowup).where(HunterFollowup.tenant_id == tenant_id))
        ).scalars().all()

        hot_no_ai = [l for l in leads if int(l.interest_score or 0) >= 80 and not l.has_ai and not l.do_not_disturb]
        human_needed_leads = [l for l in leads if l.human_needed and not l.do_not_disturb]
        paid_leads = [l for l in leads if l.pipeline_stage == "paid_client" or l.call_result == "paid"]
        revenue_usd = round(sum(float(l.deal_value_usd or 0.0) for l in paid_leads), 2)
        demos_sent_cnt = sum(1 for d in demos if d.status == "sent")
        apollo_mod = control["module_map"]["apollo_enrichment"]

        return {
            "kpis": {
                "total_leads": len(leads),
                "no_ai_hot_leads": len(hot_no_ai),
                "apollo_credits_used_today": apollo_mod["used_today"],
                "apollo_daily_limit": apollo_mod["daily_limit"],
                "demos_generated": len(demos),
                "demos_sent": demos_sent_cnt,
                "replied_human_needed": len(human_needed_leads),
                "paid_clients": len(paid_leads),
                "revenue_usd": revenue_usd,
                "scheduled_followups": sum(1 for f in followups if f.status == "scheduled"),
            },
            "human_needed_alerts": [
                {
                    "lead_id": str(l.id),
                    "business_name": l.business_name,
                    "owner_name": l.owner_name,
                    "phone": l.phone,
                    "email": l.email,
                    "city": l.city,
                    "country": l.country,
                    "last_reply": (l.metadata_ or {}).get("last_inbound_message"),
                }
                for l in human_needed_leads[:10]
            ],
            "api_keys_status": {
                "openstreetmap_free_ready": True,
                "google_places_configured": bool(
                    (settings.google_places_api_key or "").strip()
                    and "your-" not in (settings.google_places_api_key or "").lower()
                ),
                "apollo_configured": bool(
                    (settings.apollo_api_key or "").strip()
                    and "your-" not in (settings.apollo_api_key or "").lower()
                ),
                "resend_configured": bool(
                    (settings.resend_api_key or "").strip()
                    and (settings.resend_api_key or "").strip() != "mock"
                    and "your-" not in (settings.resend_api_key or "").lower()
                ),
                "whatsapp_configured": settings.whatsapp_provider == "meta" and bool(settings.whatsapp_access_token),
                "gemini_configured": bool(
                    (settings.gemini_api_key or "").strip()
                    and "your-" not in (settings.gemini_api_key or "").lower()
                ),
            },
            "control_panel": control,
        }


lead_hunter_control_service = LeadHunterControlService()
