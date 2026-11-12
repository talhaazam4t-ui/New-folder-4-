"""Central Agent Registry & Tenant Agent Configuration Manager.
"""

import uuid
from typing import Dict, List

from app.agents.base_agent import BaseAgent
from app.agents.business_agents.finance_tracker_agent import finance_tracker_agent
from app.agents.executor_agent import executor_agent
from app.agents.marketing_agents.campaign_strategist_agent import (
    campaign_strategist_agent,
)
from app.agents.master_agent import master_orchestrator
from app.agents.planner_agent import planner_agent
from app.agents.researcher_agent import researcher_agent
from app.agents.reviewer_agent import reviewer_agent
from app.agents.support_agents.whatsapp_concierge_agent import whatsapp_concierge_agent
from app.core.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.database.models.agent import AgentExecution, AgentRegistry, TenantAgent
from app.schemas.agent import (
    AgentInfoResponse,
    AgentOrchestrateRequest,
    AgentOrchestrateResponse,
    TenantAgentConfigRequest,
)
from app.schemas.task import TaskExecutionResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class AgentRegistryManager:
    """Manages available bounded agents and per-tenant agent configuration."""

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        for agent in [
            master_orchestrator,
            planner_agent,
            researcher_agent,
            executor_agent,
            reviewer_agent,
            finance_tracker_agent,
            campaign_strategist_agent,
            whatsapp_concierge_agent,
        ]:
            self._agents[agent.name] = agent

    def get_agent(self, name: str) -> BaseAgent:
        agent = self._agents.get(name)
        if not agent:
            raise ResourceNotFoundError("Agent", name)
        return agent

    async def _ensure_db_registry(self, session: AsyncSession) -> Dict[str, AgentRegistry]:
        """Ensure all code-registered agents exist in `agent_registry` table."""
        res = await session.execute(select(AgentRegistry))
        existing = {row.name: row for row in res.scalars().all()}
        changed = False
        for name, agent in self._agents.items():
            if name not in existing:
                row = AgentRegistry(
                    name=agent.name,
                    category=agent.category,
                    description=agent.description,
                    version=agent.version,
                    configuration={
                        "allowed_tools": sorted(agent.allowed_tools),
                        "max_steps": agent.max_steps,
                    },
                    active=True,
                )
                session.add(row)
                existing[name] = row
                changed = True
        if changed:
            await session.commit()
        return existing

    async def list_agents_for_tenant(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> List[AgentInfoResponse]:
        """List all registered agents alongside tenant-specific enablement and budget settings."""
        db_registry = await self._ensure_db_registry(session)
        ta_res = await session.execute(
            select(TenantAgent).where(TenantAgent.tenant_id == tenant_id)
        )
        tenant_configs = {row.agent_id: row for row in ta_res.scalars().all()}

        responses: List[AgentInfoResponse] = []
        for name, agent in self._agents.items():
            reg_row = db_registry[name]
            t_cfg = tenant_configs.get(reg_row.id)
            responses.append(
                AgentInfoResponse(
                    name=agent.name,
                    category=agent.category,
                    description=agent.description,
                    version=agent.version,
                    allowed_tools=sorted(agent.allowed_tools),
                    max_steps=agent.max_steps,
                    enabled_for_tenant=t_cfg.enabled if t_cfg else True,
                    execution_limit=t_cfg.execution_limit if t_cfg else 1000,
                    budget_limit=float(t_cfg.budget_limit) if t_cfg else 50.0,
                )
            )
        return responses

    async def configure_tenant_agent(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        agent_name: str,
        request: TenantAgentConfigRequest,
    ) -> AgentInfoResponse:
        """Enable/disable an agent or update its execution/budget caps for a specific tenant."""
        agent = self.get_agent(agent_name)
        db_registry = await self._ensure_db_registry(session)
        reg_row = db_registry[agent.name]

        ta_res = await session.execute(
            select(TenantAgent).where(
                TenantAgent.tenant_id == tenant_id,
                TenantAgent.agent_id == reg_row.id,
            )
        )
        t_cfg = ta_res.scalar_one_or_none()
        if t_cfg:
            t_cfg.enabled = request.enabled
            t_cfg.execution_limit = request.execution_limit
            t_cfg.budget_limit = request.budget_limit
            if request.configuration is not None:
                t_cfg.configuration = request.configuration
        else:
            t_cfg = TenantAgent(
                tenant_id=tenant_id,
                agent_id=reg_row.id,
                enabled=request.enabled,
                execution_limit=request.execution_limit,
                budget_limit=request.budget_limit,
                configuration=request.configuration or {},
            )
            session.add(t_cfg)

        await session.commit()
        await session.refresh(t_cfg)

        return AgentInfoResponse(
            name=agent.name,
            category=agent.category,
            description=agent.description,
            version=agent.version,
            allowed_tools=sorted(agent.allowed_tools),
            max_steps=agent.max_steps,
            enabled_for_tenant=t_cfg.enabled,
            execution_limit=t_cfg.execution_limit,
            budget_limit=float(t_cfg.budget_limit),
        )

    async def run_orchestration(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        request: AgentOrchestrateRequest,
    ) -> AgentOrchestrateResponse:
        """Verify tenant agent enablement and execute orchestration."""
        agent = self.get_agent(request.agent_name)
        db_registry = await self._ensure_db_registry(session)
        reg_row = db_registry[agent.name]

        ta_res = await session.execute(
            select(TenantAgent).where(
                TenantAgent.tenant_id == tenant_id,
                TenantAgent.agent_id == reg_row.id,
            )
        )
        t_cfg = ta_res.scalar_one_or_none()
        if t_cfg and not t_cfg.enabled:
            raise PermissionDeniedError(
                f"Agent '{agent.name}' is currently disabled for this tenant workspace."
            )

        return await master_orchestrator.orchestrate(
            session=session,
            tenant_id=tenant_id,
            target_agent=agent,
            request=request,
        )

    async def list_executions(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        limit: int = 50,
    ) -> List[TaskExecutionResponse]:
        """List recent agent execution telemetry records for the tenant."""
        res = await session.execute(
            select(AgentExecution)
            .where(AgentExecution.tenant_id == tenant_id)
            .order_by(AgentExecution.created_at.desc())
            .limit(limit)
        )
        return [
            TaskExecutionResponse(
                id=row.id,
                tenant_id=row.tenant_id,
                task_id=row.task_id,
                agent_id=row.agent_id,
                status=row.status,
                tokens_used=row.tokens_used,
                estimated_cost=float(row.estimated_cost),
                duration_ms=row.duration_ms,
                error_message=row.error_message,
                created_at=row.created_at,
            )
            for row in res.scalars().all()
        ]


agent_registry = AgentRegistryManager()
