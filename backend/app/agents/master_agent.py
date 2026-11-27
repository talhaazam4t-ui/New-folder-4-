"""Master Orchestrator Agent — Coordinates Bounded Multi-Agent Workflows (Section 10.1).

Executes the structured pipeline:
1. PlannerAgent (`complex_planning`)
2. ResearcherAgent (`deep_research`)
3. ExecutorAgent (`simple_support` / domain agent)
4. ReviewerAgent (`reviewer_validation`)

Enforces:
- Tenant agent enablement & budget limits (`TenantAgent`).
- Explicit tool permission validation (`verify_tool_permission`).
- Live Database Tool Grounding (`query_business_summary`, `query_marketing_insights`, `read_context`)
  so agents always operate on genuine tenant financial accounts, rent schedules, CRM leads,
  campaigns, integration status, and proactive episodic memories.
- Phase 1 Tiered Usage & Token Metering (`tier_quota_service`) + accurate provider attribution
  (`groq`, `gemini`, `openrouter`, `deepseek`, `mock`).
- Phase 2 Self-Reflection / Quality Control (QC) Agent & Episodic Memory persistence.
- Mandatory Human-in-the-Loop approval gate for sensitive actions (`approval_manager`).
- Full telemetry in `AgentTask`, `AgentExecution`, and `UsageRecord`.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.agents.base_agent import BaseAgent
from app.agents.executor_agent import executor_agent
from app.agents.planner_agent import planner_agent
from app.agents.researcher_agent import researcher_agent
from app.agents.reviewer_agent import reviewer_agent
from app.automation.approval_manager import approval_manager
from app.automation.budget_manager import budget_manager
from app.core.exceptions import TaloxException
from app.database.models.agent import AgentExecution, AgentTask
from app.database.models.automation import Integration, UsageRecord
from app.database.models.finance import FinancialAccount, FinancialTransaction, RentSchedule
from app.database.models.governance import TenantEpisodicMemory
from app.database.models.marketing import Lead, MarketingCampaign
from app.database.models.service import Service, ServiceSubscription
from app.schemas.agent import (
    AgentOrchestrateRequest,
    AgentOrchestrateResponse,
    AgentStageResult,
)
from app.schemas.approval import ApprovalCreateRequest
from app.services.central_orchestrator_service import central_orchestrator_service
from app.services.tier_quota_service import tier_quota_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _detect_provider_from_model(model_name: str) -> str:
    low = (model_name or "").lower()
    if "mock" in low:
        return "mock"
    if "gemini" in low:
        return "gemini"
    if ":free" in low or "/" in low:
        return "openrouter"
    if any(tok in low for tok in ("llama", "qwen", "gemma", "mixtral", "compound")):
        return "groq"
    if "deepseek" in low:
        return "deepseek"
    return "groq"


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

    async def _build_live_db_tool_context(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        target_agent: BaseAgent,
    ) -> Dict[str, Any]:
        """Execute permitted read-only database tools (`read_context`, `query_business_summary`,
        `query_marketing_insights`) so agents ground their output in real tenant records.
        """
        tools = set(target_agent.allowed_tools or set()) | set(self.allowed_tools)
        live_ctx: Dict[str, Any] = {}

        # 1. Active Services, Integrations & Episodic Memories (`read_context`)
        if "read_context" in tools:
            subs_rows = (
                await session.execute(
                    select(Service.slug, ServiceSubscription.plan_name, ServiceSubscription.status)
                    .join(Service, ServiceSubscription.service_id == Service.id)
                    .where(
                        ServiceSubscription.tenant_id == tenant_id,
                        ServiceSubscription.status.in_(("active", "trialing")),
                    )
                )
            ).all()
            ints_rows = (
                await session.execute(
                    select(Integration.provider, Integration.status).where(
                        Integration.tenant_id == tenant_id
                    )
                )
            ).all()
            memories_rows = (
                await session.execute(
                    select(TenantEpisodicMemory)
                    .where(TenantEpisodicMemory.tenant_id == tenant_id)
                    .order_by(TenantEpisodicMemory.created_at.desc())
                    .limit(4)
                )
            ).scalars().all()

            connected_providers = [p for p, st in ints_rows if st == "connected"]
            live_ctx["workspace_context"] = {
                "active_services": [
                    {"service_slug": slug, "plan": plan, "status": st}
                    for slug, plan, st in subs_rows
                ],
                "connected_integrations": connected_providers,
                "delivery_mode": (
                    "LIVE_EXTERNAL_DELIVERY_READY"
                    if any(p in connected_providers for p in ("gmail", "whatsapp"))
                    else "SANDBOX_DRAFT_ONLY (Connect Gmail/WhatsApp in /settings for live external delivery)"
                ),
                "recent_episodic_memories": [
                    {"type": m.memory_type, "key": m.context_key, "summary": m.summary[:220]}
                    for m in memories_rows
                ],
            }

        # 2. Live Financial Ledger & Rent Summary (`query_business_summary`)
        if "query_business_summary" in tools:
            accounts = (
                await session.execute(
                    select(FinancialAccount).where(FinancialAccount.tenant_id == tenant_id)
                )
            ).scalars().all()
            txs = (
                await session.execute(
                    select(FinancialTransaction)
                    .where(FinancialTransaction.tenant_id == tenant_id)
                    .order_by(FinancialTransaction.transaction_date.desc())
                    .limit(40)
                )
            ).scalars().all()
            rents = (
                await session.execute(
                    select(RentSchedule).where(RentSchedule.tenant_id == tenant_id)
                )
            ).scalars().all()

            total_balance = round(sum(float(a.current_balance or 0.0) for a in accounts), 2)
            paid_inflow = round(
                sum(float(t.amount or 0.0) for t in txs if t.type in ("income", "rent") and t.status == "paid"),
                2,
            )
            paid_outflow = round(
                sum(float(t.amount or 0.0) for t in txs if t.type == "expense" and t.status == "paid"),
                2,
            )
            overdue_or_pending = round(
                sum(
                    float(t.amount or 0.0)
                    for t in txs
                    if t.type in ("income", "rent") and t.status in ("pending", "overdue")
                ),
                2,
            )
            active_rent_mrr = round(
                sum(float(r.monthly_rent or 0.0) for r in rents if r.status == "active"),
                2,
            )
            live_ctx["live_financial_summary"] = {
                "accounts_count": len(accounts),
                "total_cash_balance_usd": total_balance,
                "paid_inflow_recent": paid_inflow,
                "paid_expense_recent": paid_outflow,
                "pending_or_overdue_receivables": overdue_or_pending,
                "active_rent_schedules": len([r for r in rents if r.status == "active"]),
                "active_monthly_rent_mrr": active_rent_mrr,
            }

        # 3. Live CRM Leads & Marketing Campaigns (`query_marketing_insights`)
        if "query_marketing_insights" in tools:
            leads = (
                await session.execute(
                    select(Lead)
                    .where(Lead.tenant_id == tenant_id)
                    .order_by(Lead.qualification_score.desc(), Lead.created_at.desc())
                    .limit(20)
                )
            ).scalars().all()
            campaigns = (
                await session.execute(
                    select(MarketingCampaign)
                    .where(MarketingCampaign.tenant_id == tenant_id)
                    .order_by(MarketingCampaign.created_at.desc())
                    .limit(10)
                )
            ).scalars().all()

            qualified_leads = [l for l in leads if float(l.qualification_score or 0.0) >= 70.0]
            live_ctx["live_marketing_and_crm"] = {
                "recent_leads_count": len(leads),
                "qualified_leads_count": len(qualified_leads),
                "top_leads": [
                    {
                        "name": l.name,
                        "email": l.email,
                        "phone": l.phone,
                        "source": l.source,
                        "status": l.status,
                        "score": float(l.qualification_score or 0.0),
                    }
                    for l in leads[:5]
                ],
                "campaigns_count": len(campaigns),
                "campaigns": [
                    {
                        "name": c.name,
                        "platform": c.platform,
                        "status": c.status,
                        "budget": float(c.budget or 0.0),
                    }
                    for c in campaigns[:5]
                ],
            }

        return live_ctx

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

        # 0. Enforce Phase 1 Tier Quota hard-lock check before starting
        await tier_quota_service.assert_not_hard_locked(session, tenant_id)

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

        # 3. Ground agent pipeline in LIVE tenant database records via permitted read tools
        live_db_ctx = await self._build_live_db_tool_context(session, tenant_id, target_agent)
        stages: List[AgentStageResult] = []
        ctx: Dict = {**live_db_ctx, **dict(request.context_data or {})}

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
                    provider=_detect_provider_from_model(stage_res.model),
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
        raw_final_output = stages[-1].output if stages else ""

        # 4. Run Phase 2 Self-Reflection / QC Agent to sanitize unsafe claims
        qc_res = central_orchestrator_service.run_self_reflection_qc(
            raw_final_output,
            max_words=350,
        )
        final_output = qc_res["final_text"]
        if stages:
            stages[-1].output = final_output

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        task.output = {
            "final_output": final_output,
            "qc_auto_revised": qc_res["auto_revised"],
            "live_db_grounded": True,
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

        # 5. Store Proactive Episodic Memory & meter Phase 1 Tier Quota
        session.add(
            TenantEpisodicMemory(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                memory_type="agent_orchestration",
                skill_slug=target_agent.name,
                context_key=request.objective[:180],
                summary=final_output[:500],
                outcome_score=90.0 if qc_res["passed_initial_check"] else 84.0,
                metadata_={"task_id": str(task.id), "tokens": total_tokens},
            )
        )
        await tier_quota_service.record_usage(
            session=session,
            tenant_id=tenant_id,
            tokens_delta=total_tokens,
            api_calls_delta=1,
            enforce_lock_before=False,
        )

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
