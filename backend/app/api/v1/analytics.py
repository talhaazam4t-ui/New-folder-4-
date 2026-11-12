"""Unified Executive Analytics, AI Usage Telemetry & Immutable Audit Trail API Endpoints.
"""

from typing import Optional

from app.automation.budget_manager import budget_manager
from app.core.tenant_context import TenantContext
from app.database.models.agent import AgentExecution
from app.database.models.automation import Approval, AuditLog, UsageRecord
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.services.business_service import business_service
from app.services.marketing_service import marketing_service
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/analytics", tags=["Analytics & Telemetry"])


@router.get("/overview")
async def get_executive_analytics_overview(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve unified cross-engine analytics (Financial + Marketing + AI Budget + Approvals)."""
    financial_summary = await business_service.get_summary(session, context.tenant_id)
    marketing_summary = await marketing_service.get_analytics(session, context.tenant_id)
    budget_state = budget_manager.get_or_create_record(str(context.tenant_id))

    pending_approvals_res = await session.execute(
        select(func.count(Approval.id)).where(
            Approval.tenant_id == context.tenant_id,
            Approval.status == "pending",
        )
    )
    pending_approvals = pending_approvals_res.scalar() or 0

    exec_count_res = await session.execute(
        select(func.count(AgentExecution.id)).where(AgentExecution.tenant_id == context.tenant_id)
    )
    total_executions = exec_count_res.scalar() or 0

    return {
        "success": True,
        "data": {
            "tenant_id": str(context.tenant_id),
            "financial": financial_summary.model_dump(mode="json"),
            "marketing": marketing_summary.model_dump(mode="json"),
            "ai_governance": {
                "daily_token_limit": budget_state.daily_token_limit,
                "tokens_used_today": budget_state.tokens_used_today,
                "estimated_cost_today": round(budget_state.estimated_cost_today, 6),
                "circuit_state": budget_state.circuit_state.value,
                "consecutive_failures": budget_state.consecutive_failures,
                "total_executions": total_executions,
                "pending_approvals": pending_approvals,
            },
        },
    }


@router.get("/usage")
async def get_tenant_ai_usage_telemetry(
    limit: int = Query(50, ge=1, le=200),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve detailed AI token consumption and cost breakdown by model."""
    res = await session.execute(
        select(UsageRecord)
        .where(UsageRecord.tenant_id == context.tenant_id)
        .order_by(UsageRecord.created_at.desc())
        .limit(limit)
    )
    rows = res.scalars().all()
    records = [
        {
            "id": str(r.id),
            "provider": r.provider,
            "model": r.model,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "total_tokens": r.input_tokens + r.output_tokens,
            "estimated_cost": float(r.estimated_cost),
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
    budget_state = budget_manager.get_or_create_record(str(context.tenant_id))
    return {
        "success": True,
        "data": {
            "quota": {
                "daily_token_limit": budget_state.daily_token_limit,
                "tokens_used_today": budget_state.tokens_used_today,
                "remaining_tokens": max(0, budget_state.daily_token_limit - budget_state.tokens_used_today),
                "circuit_state": budget_state.circuit_state.value,
            },
            "records": records,
        },
    }


@router.get("/audit-logs")
async def list_tenant_audit_logs(
    action: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """List immutable audit log entries scoped strictly to the tenant."""
    query = select(AuditLog).where(AuditLog.tenant_id == context.tenant_id)
    if action:
        query = query.where(AuditLog.action == action)
    query = query.order_by(AuditLog.created_at.desc()).limit(limit)
    res = await session.execute(query)
    logs = [
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id) if row.tenant_id else None,
            "actor_id": str(row.actor_id) if row.actor_id else None,
            "actor_type": row.actor_type,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": str(row.resource_id) if row.resource_id else None,
            "metadata": row.metadata_ or {},
            "created_at": row.created_at.isoformat(),
        }
        for row in res.scalars().all()
    ]
    return {"success": True, "data": logs}
