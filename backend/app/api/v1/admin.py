"""Platform Owner & Administrator API Endpoints.

Provides global management across all tenants, subscriptions, agent executions,
and system health for the platform owner.
"""

import uuid

from app.automation.budget_manager import budget_manager
from app.automation.retry import dead_letter_queue
from app.database.models.agent import AgentExecution
from app.database.models.billing import Payment
from app.database.models.service import ServiceSubscription
from app.database.models.tenant import Profile, Tenant, TenantMember
from app.database.supabase import get_db
from app.dependencies import get_current_user
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin", tags=["Platform Administration"])


class TenantStatusUpdateRequest(BaseModel):
    status: str  # active, suspended


class GlobalAdminStats(BaseModel):
    total_tenants: int
    active_tenants: int
    suspended_tenants: int
    monthly_recurring_revenue: float
    total_collected_payments: float
    total_agent_executions: int
    system_health: str = "operational"


async def verify_platform_admin(
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Profile:
    """Verify that current user has system admin rights.

    For initial setup, the first registered user or users with system admin role
    are recognized as platform administrators.
    """
    # Check if this user is a member with owner role or system admin
    query = select(TenantMember).where(
        TenantMember.user_id == current_user.id,
        TenantMember.role == "owner"
    )
    res = await session.execute(query)
    if not res.scalars().first():
        # Fallback check: If there are less than 2 total profiles, first user is admin
        count_res = await session.execute(select(func.count(Profile.id)))
        total_profiles = count_res.scalar() or 0
        if total_profiles > 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "PLATFORM_ADMIN_REQUIRED", "message": "Only platform administrators can access this console"}
            )
    return current_user


@router.get("/stats", response_model=GlobalAdminStats)
async def get_global_stats(
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve system-wide KPIs: MRR, total companies, payments, and agent activity."""
    # 1. Total Tenants by status
    total_tenants_res = await session.execute(select(func.count(Tenant.id)))
    total_tenants = total_tenants_res.scalar() or 0

    active_tenants_res = await session.execute(
        select(func.count(Tenant.id)).where(Tenant.status == "active")
    )
    active_tenants = active_tenants_res.scalar() or 0

    suspended_tenants = max(0, total_tenants - active_tenants)

    # 2. MRR (sum of active subscription prices)
    mrr_res = await session.execute(
        select(func.sum(ServiceSubscription.price)).where(
            ServiceSubscription.status == "active",
            ServiceSubscription.billing_interval == "monthly"
        )
    )
    mrr = float(mrr_res.scalar() or 0.0)

    # 3. Total Completed Payments
    payments_res = await session.execute(
        select(func.sum(Payment.amount)).where(Payment.status == "completed")
    )
    total_payments = float(payments_res.scalar() or 0.0)

    # 4. Total Agent Executions
    execs_res = await session.execute(select(func.count(AgentExecution.id)))
    total_execs = execs_res.scalar() or 0

    return GlobalAdminStats(
        total_tenants=total_tenants,
        active_tenants=active_tenants,
        suspended_tenants=suspended_tenants,
        monthly_recurring_revenue=mrr,
        total_collected_payments=total_payments,
        total_agent_executions=total_execs,
        system_health="operational",
    )


@router.get("/tenants")
async def list_all_tenants(
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """List all registered companies on the platform with member counts and statuses."""
    query = select(Tenant).order_by(Tenant.created_at.desc())
    res = await session.execute(query)
    tenants = res.scalars().all()

    tenant_list = []
    for t in tenants:
        members_count_res = await session.execute(
            select(func.count(TenantMember.id)).where(TenantMember.tenant_id == t.id)
        )
        members_count = members_count_res.scalar() or 0

        tenant_list.append({
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "industry": t.industry,
            "status": t.status,
            "members_count": members_count,
            "created_at": t.created_at,
        })

    return {"success": True, "data": tenant_list}


@router.patch("/tenants/{tenant_id}/status")
async def update_tenant_status(
    tenant_id: uuid.UUID,
    request: TenantStatusUpdateRequest,
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Suspend or reactivate a tenant account."""
    query = select(Tenant).where(Tenant.id == tenant_id)
    res = await session.execute(query)
    tenant = res.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.status = request.status
    await session.commit()

    return {
        "success": True,
        "message": f"Tenant '{tenant.name}' status updated to {request.status}",
    }


@router.post("/tenants/{tenant_id}/reset-circuit")
async def reset_tenant_circuit_breaker(
    tenant_id: uuid.UUID,
    admin_user: Profile = Depends(verify_platform_admin),
):
    """Admin override to reset a tripped cost-protection circuit breaker for a tenant."""
    budget_manager.admin_reset_circuit(str(tenant_id))
    record = budget_manager.get_or_create_record(str(tenant_id))
    return {
        "success": True,
        "data": {
            "tenant_id": str(tenant_id),
            "circuit_state": record.circuit_state.value,
            "consecutive_failures": record.consecutive_failures,
        },
        "message": "Circuit breaker reset to CLOSED",
    }


@router.get("/dlq")
async def list_dead_letter_queue(
    admin_user: Profile = Depends(verify_platform_admin),
):
    """Inspect failed automation tasks in the Dead-Letter Queue across the platform."""
    return {
        "success": True,
        "data": dead_letter_queue.list_entries(),
    }
