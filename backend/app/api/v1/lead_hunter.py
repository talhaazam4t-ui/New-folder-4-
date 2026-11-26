"""TALOX International AI Receptionist Lead Hunting + Demo + Follow-up API Router."""

import uuid
from typing import Optional

from app.config import settings
from app.core.exceptions import ResourceNotFoundError
from app.core.rate_limit import limiter
from app.core.tenant_context import TenantContext
from app.database.models.lead_hunter import HunterLead
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.services.lead_hunter_agent import lead_hunter_agent
from app.services.lead_hunter_control_service import lead_hunter_control_service
from app.services.lead_hunter_demo_service import lead_hunter_demo_service
from app.services.lead_hunter_discovery_service import (
    ALL_CITIES,
    CATEGORIES,
    CITIES_BY_COUNTRY,
    CITY_TIMEZONES,
    COUNTRIES,
    lead_hunter_discovery_service,
)
from app.services.lead_hunter_outreach_service import (
    KANBAN_STAGES,
    lead_hunter_outreach_service,
)
from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/lead-hunter", tags=["International Lead Hunter"])


# ------------------------------------------------------------------------------
# Request Schemas
# ------------------------------------------------------------------------------


class ModuleSettingUpdateRequest(BaseModel):
    is_on: Optional[bool] = None
    daily_limit: Optional[int] = Field(default=None, ge=1, le=500)


class BudgetModeRequest(BaseModel):
    budget_mode: str = Field(description="free | low_budget | full_auto")


class LeadSearchRequest(BaseModel):
    country: str = Field(min_length=2, max_length=100)
    city: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=120)
    source_mode: str = Field(
        default="openstreetmap_free",
        description="openstreetmap_free | google_places | apollo | hybrid",
    )
    max_results: int = Field(default=8, ge=1, le=20)


class PipelineStageUpdateRequest(BaseModel):
    pipeline_stage: str = Field(min_length=2, max_length=48)


class CallOutcomeRequest(BaseModel):
    outcome: str = Field(description="interested | not_interested | call_later | demo_sent | paid")
    notes: Optional[str] = Field(default=None, max_length=1000)
    deal_value_usd: Optional[float] = Field(default=None, ge=0.0)


class DemoDraftUpdateRequest(BaseModel):
    email_subject: Optional[str] = Field(default=None, max_length=300)
    email_copy: Optional[str] = Field(default=None, max_length=8000)
    whatsapp_copy: Optional[str] = Field(default=None, max_length=3000)
    voice_script: Optional[str] = Field(default=None, max_length=4000)
    chat_prompt: Optional[str] = Field(default=None, max_length=4000)


class DemoSendRequest(BaseModel):
    channel: str = Field(default="email", description="email | linkedin | whatsapp")
    manual_override: bool = False


class DemoChatPreviewRequest(BaseModel):
    visitor_message: str = Field(min_length=1, max_length=1000)


class InboundReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=3000)
    channel: str = Field(default="email", description="email | whatsapp | linkedin | call")


class ProcessFollowupsRequest(BaseModel):
    force_due_in_test: bool = False


class ApolloCsvImportRequest(BaseModel):
    csv_text: str = Field(min_length=5, max_length=500000)
    default_country: str = Field(default="USA", max_length=100)
    default_city: str = Field(default="New York", max_length=120)
    default_category: str = Field(default="Dental Clinic", max_length=120)
    inspect_websites: bool = True


class ManualOwnerEnrichRequest(BaseModel):
    owner_name: Optional[str] = Field(default=None, max_length=160)
    owner_title: Optional[str] = Field(default=None, max_length=160)
    email: Optional[str] = Field(default=None, max_length=200)
    email_verified: bool = True
    linkedin_url: Optional[str] = Field(default=None, max_length=350)
    phone: Optional[str] = Field(default=None, max_length=64)


# ------------------------------------------------------------------------------
# Control Panel, KPIs & International Catalog
# ------------------------------------------------------------------------------


@router.get("/overview")
async def get_lead_hunter_overview(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    data = await lead_hunter_control_service.get_dashboard_kpis(session, context.tenant_id)
    return {"success": True, "data": data}


@router.get("/catalog")
async def get_international_hunter_catalog():
    return {
        "success": True,
        "data": {
            "countries": COUNTRIES,
            "cities_by_country": CITIES_BY_COUNTRY,
            "all_cities": ALL_CITIES,
            "city_timezones": CITY_TIMEZONES,
            "categories": CATEGORIES,
            "kanban_stages": KANBAN_STAGES,
        },
    }


@router.patch("/settings/{module_name}")
async def toggle_hunter_module(
    module_name: str,
    request: ModuleSettingUpdateRequest,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    control = await lead_hunter_control_service.toggle_module(
        session=session,
        tenant_id=context.tenant_id,
        module_name=module_name,
        is_on=request.is_on,
        daily_limit=request.daily_limit,
        actor_id=context.user_id,
    )
    return {"success": True, "data": control, "message": f"Updated '{module_name}' cleanly"}


@router.post("/settings/budget-mode")
async def apply_hunter_budget_mode(
    request: BudgetModeRequest,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    control = await lead_hunter_control_service.apply_budget_mode(
        session=session,
        tenant_id=context.tenant_id,
        budget_mode=request.budget_mode,
        actor_id=context.user_id,
    )
    return {"success": True, "data": control, "message": f"Budget mode '{request.budget_mode}' applied"}


# ------------------------------------------------------------------------------
# Part 1, 3 & 9: Dual-Source Lead Finder, AI Detector, Leads & Kanban
# ------------------------------------------------------------------------------


@router.post("/search")
async def search_international_leads(
    request: LeadSearchRequest,
    context: TenantContext = Depends(require_permission("marketing.research")),
    session: AsyncSession = Depends(get_db),
):
    res = await lead_hunter_discovery_service.search_and_ingest_leads(
        session=session,
        tenant_id=context.tenant_id,
        country=request.country,
        city=request.city,
        category=request.category,
        source_mode=request.source_mode,
        max_results=request.max_results,
    )
    return {"success": True, "data": res, "message": f"Found {res['count']} real business lead(s)"}


@router.get("/leads")
async def list_hunter_leads(
    pipeline_stage: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    min_score: int = Query(default=0, ge=0, le=100),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    q = (
        select(HunterLead)
        .where(
            HunterLead.tenant_id == context.tenant_id,
            HunterLead.interest_score >= min_score,
        )
        .order_by(HunterLead.interest_score.desc(), HunterLead.created_at.desc())
    )
    if pipeline_stage:
        q = q.where(HunterLead.pipeline_stage == pipeline_stage.strip().lower())
    if source:
        q = q.where(HunterLead.lead_source == source.strip().lower())
    rows = (await session.execute(q)).scalars().all()
    return {
        "success": True,
        "data": [lead_hunter_discovery_service.serialize_lead(r) for r in rows],
    }


@router.post("/leads/{lead_id}/enrich-apollo")
async def enrich_single_lead_with_apollo(
    lead_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("marketing.research")),
    session: AsyncSession = Depends(get_db),
):
    data = await lead_hunter_discovery_service.enrich_lead_via_apollo(session, context.tenant_id, lead_id)
    return {"success": True, "data": data, "message": "Lead enriched via Apollo"}


@router.post("/import-apollo-csv")
async def import_apollo_free_csv(
    request: ApolloCsvImportRequest,
    context: TenantContext = Depends(require_permission("marketing.research")),
    session: AsyncSession = Depends(get_db),
):
    data = await lead_hunter_discovery_service.import_apollo_csv(
        session=session,
        tenant_id=context.tenant_id,
        csv_text=request.csv_text,
        default_country=request.default_country,
        default_city=request.default_city,
        default_category=request.default_category,
        inspect_websites=request.inspect_websites,
    )
    return {
        "success": True,
        "data": data,
        "message": f"Imported {data['imported']} & merged {data['updated']} Apollo Free leads cleanly",
    }


@router.patch("/leads/{lead_id}/owner")
async def save_manual_apollo_free_owner(
    lead_id: uuid.UUID,
    request: ManualOwnerEnrichRequest,
    context: TenantContext = Depends(require_permission("leads.update")),
    session: AsyncSession = Depends(get_db),
):
    data = await lead_hunter_discovery_service.update_lead_owner_from_apollo_free(
        session=session,
        tenant_id=context.tenant_id,
        lead_id=lead_id,
        owner_name=request.owner_name,
        owner_title=request.owner_title,
        email=request.email,
        email_verified=request.email_verified,
        linkedin_url=request.linkedin_url,
        phone=request.phone,
    )
    return {"success": True, "data": data, "message": "Decision-maker saved to lead cleanly"}


@router.post("/leads/{lead_id}/promote-hot")
async def promote_lead_to_hot_list(
    lead_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("leads.update")),
    session: AsyncSession = Depends(get_db),
):
    data = await lead_hunter_outreach_service.promote_to_hot_lead(session, context.tenant_id, lead_id)
    return {"success": True, "data": data, "message": "Lead added to Hot Call List"}


@router.patch("/leads/{lead_id}/stage")
async def move_lead_pipeline_stage(
    lead_id: uuid.UUID,
    request: PipelineStageUpdateRequest,
    context: TenantContext = Depends(require_permission("leads.update")),
    session: AsyncSession = Depends(get_db),
):
    data = await lead_hunter_outreach_service.update_pipeline_stage(
        session, context.tenant_id, lead_id, request.pipeline_stage
    )
    return {"success": True, "data": data}


@router.delete("/leads/{lead_id}")
async def delete_hunter_lead(
    lead_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("leads.update")),
    session: AsyncSession = Depends(get_db),
):
    lead = (
        await session.execute(
            select(HunterLead).where(HunterLead.id == lead_id, HunterLead.tenant_id == context.tenant_id)
        )
    ).scalar_one_or_none()
    if not lead:
        raise ResourceNotFoundError("HunterLead", str(lead_id))
    await session.delete(lead)
    await session.commit()
    return {"success": True, "message": "Lead removed"}


# ------------------------------------------------------------------------------
# Part 2: Hot Lead Finder + Direct Call List + Outcomes
# ------------------------------------------------------------------------------


@router.get("/call-list")
async def get_hot_lead_call_list(
    min_score: int = Query(default=80, ge=50, le=100),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    items = await lead_hunter_outreach_service.get_hot_call_list(session, context.tenant_id, min_score=min_score)
    return {"success": True, "data": items}


@router.post("/leads/{lead_id}/outcome")
async def record_manual_outreach_outcome(
    lead_id: uuid.UUID,
    request: CallOutcomeRequest,
    context: TenantContext = Depends(require_permission("leads.update")),
    session: AsyncSession = Depends(get_db),
):
    data = await lead_hunter_outreach_service.record_call_outcome(
        session=session,
        tenant_id=context.tenant_id,
        lead_id=lead_id,
        outcome=request.outcome,
        notes=request.notes,
        deal_value_usd=request.deal_value_usd,
        actor_id=context.user_id,
    )
    return {"success": True, "data": data, "message": f"Recorded outcome '{request.outcome}' cleanly"}


@router.post("/leads/{lead_id}/acknowledge-handover")
async def acknowledge_lead_handover(
    lead_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("leads.update")),
    session: AsyncSession = Depends(get_db),
):
    data = await lead_hunter_outreach_service.acknowledge_human_handover(session, context.tenant_id, lead_id)
    return {"success": True, "data": data}


# ------------------------------------------------------------------------------
# Part 4, 5 & 6: Personalized English Demo Generator & Approval/Send Flow
# ------------------------------------------------------------------------------


@router.get("/demos")
async def list_generated_demos(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    items = await lead_hunter_demo_service.list_demos(session, context.tenant_id, status_filter=status_filter)
    return {"success": True, "data": items}


@router.post("/leads/{lead_id}/generate-demo", status_code=status.HTTP_201_CREATED)
async def generate_english_demo_for_lead(
    lead_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("marketing.content.generate")),
    session: AsyncSession = Depends(get_db),
):
    demo = await lead_hunter_demo_service.generate_demo_for_lead(
        session=session,
        tenant_id=context.tenant_id,
        lead_id=lead_id,
        require_auto_switch=False,
        actor_id=context.user_id,
    )
    return {"success": True, "data": demo, "message": "English AI Receptionist demo saved to Draft"}


@router.post("/leads/{lead_id}/run-agent", status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.rate_limit_agent_rpm}/minute")
async def run_lead_hunter_diagnostic_agent(
    request: Request,
    lead_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("marketing.content.generate")),
    session: AsyncSession = Depends(get_db),
):
    """Run the bounded 5-step AI Diagnostic & Outreach Agent and save a HITL draft (never auto-sends)."""
    result = await lead_hunter_agent.run_for_lead(
        session=session,
        tenant_id=context.tenant_id,
        lead_id=lead_id,
        actor_id=context.user_id,
    )
    return {
        "success": True,
        "data": result,
        "message": "AI Diagnostic Agent completed and saved HITL outreach draft for approval",
    }


@router.patch("/demos/{demo_id}")
async def update_demo_draft(
    demo_id: uuid.UUID,
    request: DemoDraftUpdateRequest,
    context: TenantContext = Depends(require_permission("marketing.content.generate")),
    session: AsyncSession = Depends(get_db),
):
    demo = await lead_hunter_demo_service.update_demo_draft(
        session, context.tenant_id, demo_id, request.model_dump(exclude_unset=True)
    )
    return {"success": True, "data": demo}


@router.post("/demos/{demo_id}/approve")
async def approve_demo_draft(
    demo_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("leads.update")),
    session: AsyncSession = Depends(get_db),
):
    demo = await lead_hunter_demo_service.approve_demo(session, context.tenant_id, demo_id, actor_id=context.user_id)
    return {"success": True, "data": demo, "message": "Demo approved cleanly"}


@router.post("/demos/{demo_id}/reject")
async def reject_demo_draft(
    demo_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("leads.update")),
    session: AsyncSession = Depends(get_db),
):
    demo = await lead_hunter_demo_service.reject_demo(session, context.tenant_id, demo_id)
    return {"success": True, "data": demo, "message": "Demo rejected"}


@router.post("/demos/{demo_id}/send")
async def send_approved_demo(
    demo_id: uuid.UUID,
    request: DemoSendRequest,
    context: TenantContext = Depends(require_permission("notifications.send")),
    session: AsyncSession = Depends(get_db),
):
    data = await lead_hunter_outreach_service.send_approved_demo(
        session=session,
        tenant_id=context.tenant_id,
        demo_id=demo_id,
        channel=request.channel,
        manual_override=request.manual_override,
        actor_id=context.user_id,
    )
    return {"success": True, "data": data, "message": f"Dispatched via {request.channel}"}


@router.post("/demos/{demo_id}/chat-preview")
async def preview_demo_chat_widget(
    demo_id: uuid.UUID,
    request: DemoChatPreviewRequest,
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    data = await lead_hunter_demo_service.interactive_chat_preview(
        session, context.tenant_id, demo_id, request.visitor_message
    )
    return {"success": True, "data": data}


# ------------------------------------------------------------------------------
# Part 7: Auto Follow-up Engine, Conversations & Instant Human Handover
# ------------------------------------------------------------------------------


@router.get("/followups")
async def list_hunter_followups(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    items = await lead_hunter_outreach_service.list_followups(session, context.tenant_id)
    return {"success": True, "data": items}


@router.post("/followups/process-due")
async def process_due_hunter_followups(
    request: ProcessFollowupsRequest = ProcessFollowupsRequest(),
    context: TenantContext = Depends(require_permission("notifications.send")),
    session: AsyncSession = Depends(get_db),
):
    res = await lead_hunter_outreach_service.process_due_followups(
        session, context.tenant_id, force_due_in_test=request.force_due_in_test
    )
    return {"success": True, "data": res}


@router.get("/leads/{lead_id}/conversations")
async def list_lead_hunter_conversations(
    lead_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    items = await lead_hunter_outreach_service.list_conversations(session, context.tenant_id, lead_id)
    return {"success": True, "data": items}


@router.post("/leads/{lead_id}/reply")
async def process_lead_inbound_reply(
    lead_id: uuid.UUID,
    request: InboundReplyRequest,
    context: TenantContext = Depends(require_permission("leads.update")),
    session: AsyncSession = Depends(get_db),
):
    """Record inbound prospect reply & enforce Instant Human Handover / Opt-Out DND."""
    res = await lead_hunter_outreach_service.record_inbound_reply(
        session=session,
        tenant_id=context.tenant_id,
        lead_id=lead_id,
        message=request.message,
        channel=request.channel,
    )
    return {"success": True, "data": res}
