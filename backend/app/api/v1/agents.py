"""Multi-Agent Registry, Configuration, Orchestration & Telemetry API Endpoints.
"""

from typing import Any, Dict, List, Optional
import uuid

from app.agents.registry import agent_registry
from app.config import settings
from app.core.exceptions import PermissionDeniedError
from app.core.rate_limit import limiter
from app.core.tenant_context import TenantContext
from app.database.models.tenant import Profile
from app.database.supabase import get_db
from app.dependencies import get_current_user, require_permission, require_platform_role
from app.schemas.agent import (
    AgentInfoResponse,
    AgentOrchestrateRequest,
    AgentOrchestrateResponse,
    OutreachAutopilotConfigUpdate,
    OutreachAutopilotRunRequest,
    OutreachLeadApproveRequest,
    OutreachLeadRejectRequest,
    TenantAgentConfigRequest,
)
from app.schemas.task import TaskExecutionResponse
from app.services.auth_service import auth_service
from app.services.central_orchestrator_service import central_orchestrator_service
from app.services.outreach_autopilot_service import outreach_autopilot_service
from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/agents", tags=["Multi-Agent Orchestration"])


@router.get("", response_model=List[AgentInfoResponse])
async def list_tenant_agents(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """List all registered AI agents with tenant-specific enablement and budget settings."""
    return await agent_registry.list_agents_for_tenant(
        session=session,
        tenant_id=context.tenant_id,
    )


@router.get("/outreach-autopilot")
async def get_outreach_autopilot_state(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """Return Daily Global Lead-Finder & Gmail Draft Autopilot settings, Gmail status, and saved drafts."""
    data = await outreach_autopilot_service.get_autopilot_state(
        session=session,
        tenant_id=context.tenant_id,
    )
    return {"success": True, "data": data}


@router.put("/outreach-autopilot")
async def update_outreach_autopilot_config(
    payload: OutreachAutopilotConfigUpdate,
    context: TenantContext = Depends(require_permission("agents.execute")),
    session: AsyncSession = Depends(get_db),
):
    """Save Daily Global Lead-Finder & Gmail Draft Autopilot configuration for the workspace."""
    data = await outreach_autopilot_service.update_autopilot_config(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        payload=payload,
    )
    return {
        "success": True,
        "data": data,
        "message": "Daily Global Outreach Autopilot settings saved.",
    }


@router.post("/outreach-autopilot/run")
@limiter.limit(f"{settings.rate_limit_agent_rpm}/minute")
async def run_outreach_autopilot_now(
    request: Request,
    payload: OutreachAutopilotRunRequest,
    context: TenantContext = Depends(require_permission("agents.execute")),
    session: AsyncSession = Depends(get_db),
):
    """Discover fresh global companies for a niche/city and save tailored drafts in Gmail Drafts (never auto-sends)."""
    data = await outreach_autopilot_service.run_autopilot_cycle(
        session=session,
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        niche_override=payload.niche,
        city_override=payload.city,
        limit_override=payload.limit,
        sync_pending_crm_drafts=payload.sync_pending_crm_drafts,
    )
    return {
        "success": True,
        "data": data,
        "message": "Global lead discovery and Gmail draft creation completed.",
    }


@router.post("/outreach-autopilot/sync-drafts")
@limiter.limit(f"{settings.rate_limit_agent_rpm}/minute")
async def sync_outreach_crm_drafts_to_gmail(
    request: Request,
    context: TenantContext = Depends(require_permission("agents.execute")),
    session: AsyncSession = Depends(get_db),
):
    """Push pending CRM drafts to the workspace's connected Gmail Drafts folder."""
    data = await outreach_autopilot_service.sync_pending_crm_drafts(
        session=session,
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
    )
    return {
        "success": True,
        "data": data,
        "message": f"Synced {data['synced_count']} pending drafts into Gmail Drafts.",
    }


@router.post("/outreach-autopilot/leads/{lead_id}/approve-send")
@limiter.limit(f"{settings.rate_limit_agent_rpm}/minute")
async def approve_and_send_lead_outreach(
    request: Request,
    lead_id: uuid.UUID,
    payload: OutreachLeadApproveRequest,
    context: TenantContext = Depends(require_permission("approvals.review")),
    session: AsyncSession = Depends(get_db),
):
    """Human-in-the-Loop approval gate to dispatch a company pitch via Gmail, WhatsApp, or LinkedIn."""
    data = await outreach_autopilot_service.approve_and_dispatch_lead_outreach(
        session=session,
        tenant_id=context.tenant_id,
        reviewer_id=context.user_id,
        lead_id=lead_id,
        payload=payload,
    )
    return {
        "success": True,
        "data": data,
        "message": f"Approved and processed {payload.channel.upper()} outreach.",
    }


@router.post("/outreach-autopilot/leads/{lead_id}/reject")
async def reject_lead_outreach(
    lead_id: uuid.UUID,
    payload: OutreachLeadRejectRequest,
    context: TenantContext = Depends(require_permission("approvals.review")),
    session: AsyncSession = Depends(get_db),
):
    """Reject/skip a prepared multi-channel lead pitch without sending."""
    data = await outreach_autopilot_service.reject_lead_outreach(
        session=session,
        tenant_id=context.tenant_id,
        reviewer_id=context.user_id,
        lead_id=lead_id,
        reason=payload.reason,
    )
    return {
        "success": True,
        "data": data,
        "message": "Lead pitch skipped and marked rejected.",
    }


@router.post("/{agent_name}/configure", response_model=AgentInfoResponse)
async def configure_tenant_agent(
    agent_name: str,
    request: TenantAgentConfigRequest,
    current_user: Profile = Depends(get_current_user),
    context: TenantContext = Depends(require_permission("agents.configure")),
    session: AsyncSession = Depends(get_db),
):
    """Enable/disable an agent or configure its execution and budget caps for the tenant (Platform Owner only)."""
    if not await auth_service.is_platform_super_admin(session, current_user):
        raise PermissionDeniedError("AI agent configuration is managed exclusively by the Platform Owner.")
    return await agent_registry.configure_tenant_agent(
        session=session,
        tenant_id=context.tenant_id,
        agent_name=agent_name,
        request=request,
    )


@router.post("/orchestrate", response_model=AgentOrchestrateResponse)
@limiter.limit(f"{settings.rate_limit_agent_rpm}/minute")
async def orchestrate_agent_objective(
    request: Request,
    payload: AgentOrchestrateRequest,
    context: TenantContext = Depends(require_permission("agents.execute")),
    session: AsyncSession = Depends(get_db),
):
    """Run the MasterOrchestrator or a specialized domain agent on a tenant objective."""
    return await agent_registry.run_orchestration(
        session=session,
        tenant_id=context.tenant_id,
        request=payload,
    )


@router.get("/executions", response_model=List[TaskExecutionResponse])
async def list_agent_executions(
    limit: int = Query(50, ge=1, le=200),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """List recent agent execution telemetry records for the tenant."""
    return await agent_registry.list_executions(
        session=session,
        tenant_id=context.tenant_id,
        limit=limit,
    )


# ------------------------------------------------------------------------------
# PHASE 2: DB-Driven Registry, Episodic Memory, QC Reflection & Dynamic UI
# ------------------------------------------------------------------------------


class AgentSkillUpsertRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=200)
    service_slug: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=5, max_length=1000)
    tool_schema: Optional[Dict[str, Any]] = None
    default_model_tier: str = Field(default="fast_free", description="fast_free | reasoning")
    token_budget: int = Field(default=1500, ge=100, le=16000)
    max_words: int = Field(default=130, ge=20, le=1000)
    requires_hitl: bool = True
    active: bool = True


class EpisodicMemoryCreateRequest(BaseModel):
    memory_type: str = Field(default="interaction", min_length=2, max_length=64)
    skill_slug: Optional[str] = Field(default=None, max_length=100)
    context_key: str = Field(min_length=2, max_length=200)
    summary: str = Field(min_length=3, max_length=2000)
    outcome_score: float = Field(default=85.0, ge=0.0, le=100.0)
    metadata: Optional[Dict[str, Any]] = None


class DynamicOrchestrateRequest(BaseModel):
    objective: str = Field(min_length=3, max_length=2000)
    skill_slug: Optional[str] = Field(default=None, max_length=100)
    context_data: Optional[Dict[str, Any]] = None
    force_hitl: Optional[bool] = None


class AdminServiceToggleRequest(BaseModel):
    service_slug: str = Field(min_length=2, max_length=120)
    enabled: bool


@router.get("/registry")
async def get_dynamic_services_and_skills_registry(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """Return all active DB-driven services and agent skills ingested by the Central Orchestrator."""
    data = await central_orchestrator_service.get_dynamic_registry_context(session, context.tenant_id)
    return {"success": True, "data": data}


@router.post("/skills", status_code=status.HTTP_201_CREATED)
async def register_or_update_agent_skill(
    request: AgentSkillUpsertRequest,
    current_user: Profile = Depends(require_platform_role("super_admin")),
    session: AsyncSession = Depends(get_db),
):
    """Register or update a database-driven skill so the Orchestrator ingests it immediately (Super Admin only)."""
    skill = await central_orchestrator_service.register_or_update_skill(
        session=session,
        slug=request.slug,
        name=request.name,
        service_slug=request.service_slug,
        description=request.description,
        tool_schema=request.tool_schema,
        default_model_tier=request.default_model_tier,
        token_budget=request.token_budget,
        max_words=request.max_words,
        requires_hitl=request.requires_hitl,
        active=request.active,
        actor_id=current_user.id,
    )
    return {"success": True, "data": skill, "message": f"Skill '{skill['slug']}' registered in DB"}


@router.get("/memories")
async def list_tenant_episodic_memories(
    query: Optional[str] = Query(default=None),
    memory_type: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """Query relevant persistent episodic memories for the active tenant."""
    items = await central_orchestrator_service.query_relevant_memories(
        session=session,
        tenant_id=context.tenant_id,
        query_text=query,
        memory_type=memory_type,
        limit=limit,
    )
    return {"success": True, "data": items}


@router.post("/memories", status_code=status.HTTP_201_CREATED)
async def create_tenant_episodic_memory(
    request: EpisodicMemoryCreateRequest,
    context: TenantContext = Depends(require_permission("agents.execute")),
    session: AsyncSession = Depends(get_db),
):
    """Record a persistent episodic memory for the active tenant."""
    mem = await central_orchestrator_service.record_episodic_memory(
        session=session,
        tenant_id=context.tenant_id,
        memory_type=request.memory_type,
        skill_slug=request.skill_slug,
        context_key=request.context_key,
        summary=request.summary,
        outcome_score=request.outcome_score,
        metadata=request.metadata,
    )
    return {"success": True, "data": mem}


@router.post("/orchestrate-dynamic")
@limiter.limit(f"{settings.rate_limit_agent_rpm}/minute")
async def orchestrate_dynamic_skill_task(
    request: Request,
    payload: DynamicOrchestrateRequest,
    context: TenantContext = Depends(require_permission("agents.execute")),
    session: AsyncSession = Depends(get_db),
):
    """Run the Phase 2 DB-Driven Central Orchestrator with Episodic Memory, QC Self-Reflection & HITL Queue."""
    res = await central_orchestrator_service.orchestrate_task(
        session=session,
        tenant_id=context.tenant_id,
        objective=payload.objective,
        skill_slug=payload.skill_slug,
        context_data=payload.context_data,
        actor_id=context.user_id,
        force_hitl=payload.force_hitl,
    )
    return {"success": True, "data": res}


@router.get("/ui-config")
async def get_dynamic_workspace_ui_configuration(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """Return dynamic client dashboard configuration (provisioned modules vs Upgrade Center / Marketplace)."""
    cfg = await central_orchestrator_service.get_dynamic_ui_configuration(session, context.tenant_id)
    return {"success": True, "data": cfg}


@router.post("/admin/tenants/{tenant_id}/services/toggle")
async def admin_toggle_tenant_service_module(
    tenant_id: uuid.UUID,
    request: AdminServiceToggleRequest,
    current_user: Profile = Depends(require_platform_role("super_admin")),
    session: AsyncSession = Depends(get_db),
):
    """Granular Super Admin toggle to enable or disable a service module for a specific tenant."""
    cfg = await central_orchestrator_service.admin_toggle_tenant_service(
        session=session,
        tenant_id=tenant_id,
        service_slug=request.service_slug,
        enabled=request.enabled,
        admin_user_id=current_user.id,
    )
    return {
        "success": True,
        "data": cfg,
        "message": f"Service '{request.service_slug}' {'enabled' if request.enabled else 'disabled'} for tenant",
    }

