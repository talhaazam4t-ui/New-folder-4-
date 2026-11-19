"""Master Orchestrator Agent — Coordinates Bounded Multi-Agent Workflows (Section 10.1).

Executes the structured pipeline:
1. PlannerAgent (`complex_planning`)
2. ResearcherAgent (`deep_research`)
3. ExecutorAgent (`simple_support` / domain agent)
4. ReviewerAgent (`reviewer_validation`)

Enforces:
- Tenant agent enablement & budget limits (`TenantAgent`).
- Explicit tool permission validation (`verify_tool_permission`).
- Mandatory Human-in-the-Loop approval gate for sensitive actions (`approval_manager`).
- Full telemetry in `AgentTask`, `AgentExecution`, and `UsageRecord`.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List

from app.agents.base_agent import BaseAgent
from app.agents.executor_agent import executor_agent
from app.agents.planner_agent import planner_agent
from app.agents.researcher_agent import researcher_agent
from app.agents.reviewer_agent import reviewer_agent
from app.automation.approval_manager import approval_manager
from app.automation.budget_manager import budget_manager
from app.core.exceptions import TaloxException
from app.database.models.agent import AgentExecution, AgentTask
from app.database.models.automation import UsageRecord
from app.schemas.agent import (
    AgentOrchestrateRequest,
    AgentOrchestrateResponse,
    AgentStageResult,
)
from app.schemas.approval import ApprovalCreateRequest
from sqlalchemy.ext.asyncio import AsyncSession


class MasterOrchestratorAgent(BaseAgent):
    name = "master_orchestrator"
    role = "Master Multi-Agent Orchestrator"
    category = "orchestration"
    description = "Coordinates Planner, Researcher, Executor, and Reviewer agents within strict tenant guardrails."
    default_task_type = "complex_planning"
    allowed_tools = {
        "read_context",
        "decompose_objective",
        "query_business_summary",
        "query_marketing_insights",
        "draft_whatsapp_reply",
        "create_business_draft",
        "create_campaign_draft",
        "qualify_lead",
        "validate_output",
    }
    max_steps = 4
    timeout_seconds = 60

    async def orchestrate(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        target_agent: BaseAgent,
        request: AgentOrchestrateRequest,
    ) -> AgentOrchestrateResponse:
        """Run either the full 4-stage Master Orchestrator pipeline or a specific domain agent."""
        now = datetime.now(timezone.utc)
        start_time = time.perf_counter()

        # 1. Verify tool permission upfront if caller requested a specific tool
        if request.requested_tool:
            target_agent.verify_tool_permission(request.requested_tool)

        # 2. Check if action is sensitive and requires human approval before execution
        action_key = request.action_type or target_agent.default_task_type
        needs_approval = approval_manager.is_sensitive_action(action_key, request.context_data)

        task = AgentTask(
            tenant_id=tenant_id,
            task_type=action_key,
            input_={
                "objective": request.objective,
                "agent_name": target_agent.name,
                "context_data": request.context_data or {},
            },
            status="awaiting_approval" if needs_approval else "running",
            priority=5,
            attempts=1,
            scheduled_at=now,
            started_at=None if needs_approval else now,
        )
        session.add(task)
        await session.flush()

        if needs_approval:
            approval = await approval_manager.request_approval(
                session=session,
                tenant_id=tenant_id,
                request=ApprovalCreateRequest(
                    task_id=task.id,
                    action_type=action_key,
                    proposed_action={
                        "objective": request.objective,
                        "agent_name": target_agent.name,
                        "context_data": request.context_data or {},
                    },
                    requested_by=target_agent.name,
                ),
            )
            return AgentOrchestrateResponse(
                task_id=task.id,
                tenant_id=tenant_id,
                agent_name=target_agent.name,
                status="awaiting_approval",
                objective=request.objective,
                requires_approval=True,
                approval_id=approval.id,
                stages=[],
                final_output="Execution paused: Waiting for human approval of sensitive action.",
                total_tokens=0,
                total_estimated_cost=0.0,
            )

        # 3. Execute bounded pipeline stages
        stages: List[AgentStageResult] = []
        ctx: Dict = dict(request.context_data or {})

        if target_agent.name == self.name:
            pipeline = [planner_agent, researcher_agent, executor_agent, reviewer_agent]
        else:
            pipeline = [planner_agent, target_agent, reviewer_agent]

        try:
            for stage_agent in pipeline:
                stage_res = await stage_agent.execute_step(
                    tenant_id=tenant_id,
                    objective=request.objective,
                    context_data=ctx,
                )
                stages.append(stage_res)
                ctx[f"{stage_agent.name}_output"] = stage_res.output

                usage = UsageRecord(
                    tenant_id=tenant_id,
                    provider="deepseek",
                    model=stage_res.model,
                    input_tokens=int(stage_res.tokens_used * 0.6),
                    output_tokens=stage_res.tokens_used - int(stage_res.tokens_used * 0.6),
                    estimated_cost=stage_res.estimated_cost,
                )
                session.add(usage)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            error_msg = str(exc)
            task.status = "failed"
            task.completed_at = datetime.now(timezone.utc)
            task.output = {
                "error": error_msg,
                "stages": [s.model_dump(mode="json") for s in stages],
            }
            execution = AgentExecution(
                tenant_id=tenant_id,
                task_id=task.id,
                status="failed",
                tokens_used=sum(s.tokens_used for s in stages),
                estimated_cost=round(sum(s.estimated_cost for s in stages), 6),
                duration_ms=duration_ms,
                error_message=error_msg[:1000],
            )
            session.add(execution)
            await session.commit()
            if not (isinstance(exc, TaloxException) and exc.code == "AI_PROVIDER_ERROR"):
                budget_manager.record_failure(str(tenant_id), error_msg)
            raise

        total_tokens = sum(s.tokens_used for s in stages)
        total_cost = round(sum(s.estimated_cost for s in stages), 6)
        final_output = stages[-1].output if stages else ""
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        task.output = {
            "final_output": final_output,
            "stages": [s.model_dump(mode="json") for s in stages],
            "total_tokens": total_tokens,
            "total_estimated_cost": total_cost,
        }

        execution = AgentExecution(
            tenant_id=tenant_id,
            task_id=task.id,
            status="completed",
            tokens_used=total_tokens,
            estimated_cost=total_cost,
            duration_ms=duration_ms,
        )
        session.add(execution)
        await session.commit()

        budget_manager.record_success(
            tenant_id=str(tenant_id),
            tokens_used=total_tokens,
            estimated_cost=total_cost,
        )

        return AgentOrchestrateResponse(
            task_id=task.id,
            tenant_id=tenant_id,
            agent_name=target_agent.name,
            status="completed",
            objective=request.objective,
            requires_approval=False,
            stages=stages,
            final_output=final_output,
            total_tokens=total_tokens,
            total_estimated_cost=total_cost,
        )


master_orchestrator = MasterOrchestratorAgent()
