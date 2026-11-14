"""Tenant Management & Managed Service Performance Viewer API Endpoints.
"""

import uuid
from typing import Any, Dict, List

from app.database.models.agent import TenantAgent
from app.database.models.automation import AuditLog
from app.database.models.business import BusinessRecord
from app.database.models.marketing import Lead
from app.database.models.tenant import Profile, Tenant
from app.database.supabase import get_db
from app.dependencies import get_current_tenant, get_current_user, require_permission
from app.schemas.tenant import (
    TenantCreateRequest,
    TenantMemberInviteRequest,
    TenantMemberResponse,
    TenantPurgeRequest,
    TenantResponse,
    TenantUpdateRequest,
)
from app.services.billing_service import billing_service, normalize_industry
from app.services.integration_service import integration_service
from app.services.tenant_service import tenant_service
from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.get("/{tenant_id}/overview")
async def get_tenant_overview(
    tenant_id: uuid.UUID,
    context=Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve business summary KPIs and Managed Service Performance Viewer data for the tenant dashboard.

    Strictly isolated to `tenant_id` and free of internal AI prompts, credentials, or operational controls.
    """
    # Fetch tenant record
    t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = t_res.scalar_one_or_none()
    selected_industry = normalize_industry(tenant.industry if tenant else "Financing")

    # 1. Total Income
    income_res = await session.execute(
        select(func.sum(BusinessRecord.amount)).where(
            BusinessRecord.tenant_id == tenant_id,
            BusinessRecord.record_type.in_(["income", "rent", "payment_received"]),
        )
    )
    total_income = float(income_res.scalar() or 0.0)

    # 2. Total Expenses
    expense_res = await session.execute(
        select(func.sum(BusinessRecord.amount)).where(
            BusinessRecord.tenant_id == tenant_id,
            BusinessRecord.record_type == "expense",
        )
    )
    total_expenses = float(expense_res.scalar() or 0.0)

    # 3. Total Outstanding
    outstanding_res = await session.execute(
        select(func.sum(BusinessRecord.amount)).where(
            BusinessRecord.tenant_id == tenant_id,
            BusinessRecord.record_type == "outstanding",
        )
    )
    total_outstanding = float(outstanding_res.scalar() or 0.0)

    # 4. Leads, Outreach Messages Sent, Meetings Booked & Conversion Rate
    leads_rows_res = await session.execute(
        select(Lead).where(Lead.tenant_id == tenant_id).order_by(Lead.created_at.desc())
    )
    leads_rows = list(leads_rows_res.scalars().all())
    total_leads = len(leads_rows)
    qualified_leads = sum(
        1 for l in leads_rows if l.status in ("qualified", "converted") or float(l.qualification_score or 0) >= 70.0
    )

    messages_sent = 0
    meetings_booked = 0
    lead_performance: List[Dict[str, Any]] = []
    appointment_performance: List[Dict[str, Any]] = []

    for l in leads_rows:
        meta = l.metadata_ or {}
        msg_cnt = int(meta.get("messages_sent_count", 0))
        if msg_cnt == 0 and l.status in ("contacted", "qualified", "converted"):
            msg_cnt = 1
        messages_sent += msg_cnt

        is_booked = bool(meta.get("meeting_booked")) or l.status == "converted"
        if is_booked:
            meetings_booked += 1
            appointment_performance.append({
                "lead_id": str(l.id),
                "client_name": l.name,
                "meeting_title": meta.get("meeting_title", "Consultation & Service Discovery"),
                "scheduled_at": meta.get("meeting_scheduled_at", l.created_at.isoformat()),
                "status": "Confirmed",
            })

        lead_performance.append({
            "id": str(l.id),
            "name": l.name,
            "source": l.source,
            "status": l.status,
            "qualification_score": float(l.qualification_score or 0.0),
            "messages_sent": msg_cnt,
            "meeting_booked": is_booked,
            "created_at": l.created_at.isoformat(),
        })

    conversion_rate = round((meetings_booked / total_leads * 100.0), 1) if total_leads > 0 else 0.0

    # 5. Active Agents Count
    agents_res = await session.execute(
        select(func.count(TenantAgent.id)).where(
            TenantAgent.tenant_id == tenant_id,
            TenantAgent.enabled == True,  # noqa: E712
        )
    )
    active_agents = agents_res.scalar() or 0

    # 6. Subscriptions, Packages & Onboarding / Integration Status
    onboarding_summary = await integration_service.get_onboarding_requirements(session, tenant_id)
    subscriptions = await billing_service.get_tenant_subscriptions(session, tenant_id)
    active_subs = [s for s in subscriptions if s.status == "active"]
    monthly_spend = sum(float(s.price) for s in active_subs)
    current_package = (
        active_subs[0].plan_name.replace("_", " ").title()
        if active_subs
        else "No Active Package"
    )

    if not tenant or tenant.status != "active":
        service_status = "Suspended"
    elif onboarding_summary["automation_active"]:
        service_status = "Active — Delivering Outcomes"
    elif len(active_subs) > 0:
        service_status = "Pending Integration Connection"
    else:
        service_status = "Awaiting Service Selection"

    # 7. Recent Client-Safe Activity Feed
    audit_res = await session.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.created_at.desc())
        .limit(10)
    )
    recent_activity = [
        {
            "id": str(a.id),
            "action": a.action.replace(".", " ").title(),
            "resource_type": a.resource_type,
            "timestamp": a.created_at.isoformat(),
        }
        for a in audit_res.scalars().all()
    ]

    return {
        "success": True,
        "data": {
            "tenant_id": str(tenant_id),
            "tenant_name": tenant.name if tenant else "Company Workspace",
            "role": context.role,
            "selected_industry": selected_industry,
            "service_status": service_status,
            "automation_active": onboarding_summary["automation_active"],
            "current_package": current_package,
            "purchased_services": onboarding_summary["purchased_services"],
            "subscription_info": {
                "active_services_count": len(active_subs),
                "current_package": current_package,
                "monthly_investment": round(monthly_spend, 2),
                "billing_cycle": active_subs[0].billing_interval if active_subs else "monthly",
                "status": "Active" if active_subs else "Inactive",
            },
            "integrations_status": onboarding_summary["required_integrations"],
            "metrics": {
                "income": total_income,
                "expenses": total_expenses,
                "net_profit": total_income - total_expenses,
                "outstanding": total_outstanding,
                "leads": total_leads,
                "leads_generated": total_leads,
                "qualified_leads": qualified_leads,
                "messages_sent": messages_sent,
                "meetings_booked": meetings_booked,
                "conversion_rate": conversion_rate,
                "active_agents": active_agents,
            },
            "lead_performance": lead_performance[:15],
            "appointment_performance": appointment_performance[:15],
            "recent_activity": recent_activity,
            "reports": {
                "period": "Current Billing Cycle",
                "leads_generated": total_leads,
                "qualified_leads": qualified_leads,
                "messages_sent": messages_sent,
                "meetings_booked": meetings_booked,
                "conversion_rate": conversion_rate,
                "net_business_value": round(total_income - total_expenses, 2),
            },
        },
    }


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant_details(
    tenant_id: uuid.UUID,
    request: TenantUpdateRequest,
    context=Depends(require_permission("tenant.update")),
    session: AsyncSession = Depends(get_db),
):
    """Update tenant workspace name, selected industry, or onboarding settings."""
    t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = t_res.scalar_one_or_none()
    if not tenant:
        from app.core.exceptions import ResourceNotFoundError
        raise ResourceNotFoundError("Tenant", str(tenant_id))

    if request.name is not None:
        tenant.name = request.name
    if request.industry is not None:
        tenant.industry = normalize_industry(request.industry)
    if request.settings is not None:
        merged = dict(tenant.settings or {})
        merged.update(request.settings)
        tenant.settings = merged

    await session.commit()
    await session.refresh(tenant)
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        industry=tenant.industry,
        status=tenant.status,
        settings=tenant.settings or {},
        created_at=tenant.created_at,
        role=context.role,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TenantResponse)
async def create_tenant(
    request: TenantCreateRequest,
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Create a new tenant workspace and assign the authenticated user as Owner."""
    request.industry = normalize_industry(request.industry)
    return await tenant_service.create_tenant(session, current_user.id, request)


@router.get("", response_model=List[TenantResponse])
async def list_user_tenants(
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """List all tenant workspaces where the authenticated user holds an active membership."""
    return await tenant_service.get_user_tenants(session, current_user.id)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: uuid.UUID,
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Get details for a specific tenant workspace, enforcing strict membership isolation."""
    return await tenant_service.get_tenant_by_id(session, tenant_id, current_user.id)


@router.delete("/{tenant_id}", status_code=status.HTTP_200_OK)
async def purge_tenant(
    tenant_id: uuid.UUID,
    request: TenantPurgeRequest,
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Permanently delete tenant account and trigger cascading data purge (GDPR Compliance).

    Requires caller to be the Tenant Owner and confirm by providing matching tenant slug.
    """
    await tenant_service.purge_tenant_data(
        session=session,
        tenant_id=tenant_id,
        user_id=current_user.id,
        confirmation_slug=request.confirmation_slug,
    )
    return {
        "success": True,
        "message": f"Tenant '{tenant_id}' and all associated records have been permanently purged.",
    }


@router.post("/{tenant_id}/members", status_code=status.HTTP_201_CREATED, response_model=TenantMemberResponse)
async def add_tenant_member(
    tenant_id: uuid.UUID,
    request: TenantMemberInviteRequest,
    context=Depends(require_permission("tenant.members.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Invite or assign a registered user to a tenant workspace with a specific role."""
    return await tenant_service.add_tenant_member(
        session=session,
        tenant_id=tenant_id,
        actor_id=context.user_id,
        request=request,
    )


@router.get("/{tenant_id}/members", response_model=List[TenantMemberResponse])
async def list_tenant_members(
    tenant_id: uuid.UUID,
    context=Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """List all members of a tenant workspace."""
    return await tenant_service.list_tenant_members(
        session=session,
        tenant_id=tenant_id,
    )
