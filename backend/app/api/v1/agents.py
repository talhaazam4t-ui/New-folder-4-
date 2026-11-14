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
    TenantAgentConfigRequest,
)
from app.schemas.task import TaskExecutionResponse
from app.services.auth_service import auth_service
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
