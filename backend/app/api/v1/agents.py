"""Multi-Agent Registry, Configuration, Orchestration & Telemetry API Endpoints.
"""

from typing import List

from app.agents.registry import agent_registry
from app.config import settings
from app.core.exceptions import PermissionDeniedError
from app.core.rate_limit import limiter
from app.core.tenant_context import TenantContext
from app.database.models.tenant import Profile
from app.database.supabase import get_db
from app.dependencies import get_current_user, require_permission
from app.schemas.agent import (
    AgentInfoResponse,
    AgentOrchestrateRequest,
    AgentOrchestrateResponse,
    OutreachAutopilotConfigUpdate,
    OutreachAutopilotRunRequest,
    TenantAgentConfigRequest,
)
from app.schemas.task import TaskExecutionResponse
from app.services.auth_service import auth_service
from app.services.outreach_autopilot_service import outreach_autopilot_service
from fastapi import APIRouter, Depends, Query, Request
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
