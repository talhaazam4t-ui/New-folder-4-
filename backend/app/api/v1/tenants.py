"""Tenant Management & Managed Service Performance Viewer API Endpoints.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.core.exceptions import TenantIsolationError
from app.database.models.agent import TenantAgent
from app.database.models.automation import AuditLog
from app.database.models.billing import Payment
from app.database.models.business import BusinessRecord
from app.database.models.finance import FinancialTransaction
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
from app.services.auth_service import auth_service
from app.services.billing_service import (
    COMPANY_BANK_DETAILS,
    billing_service,
    get_payment_rails_info,
    normalize_industry,
)
from app.services.integration_service import integration_service
from app.services.outreach_autopilot_service import outreach_autopilot_service
from app.services.tenant_service import PROTECTED_TENANT_SETTING_KEYS, tenant_service
from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/tenants", tags=["Tenants"])

SERVICE_MODULE_MAP: Dict[str, List[str]] = {
    "business-financial-tracking": ["financial_ledger", "revenue_reports"],
    "business-finance": ["financial_ledger", "revenue_reports"],
    "ai-marketing-growth": ["marketing_growth", "lead_funnel", "outreach_campaigns"],
    "marketing-growth": ["marketing_growth", "lead_funnel", "outreach_campaigns"],
    "whatsapp-business-concierge": ["whatsapp_concierge", "appointments"],
    "whatsapp-automation": ["whatsapp_concierge", "appointments"],
    "multi-agent-orchestration": ["multi_agent_orchestration"],
    "lead-crm-qualification": ["lead_crm", "lead_funnel"],
    "executive-analytics-compliance": ["executive_analytics_compliance", "revenue_reports"],
    "office-receptionist": ["office_receptionist", "appointments"],
}


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@router.get("/{tenant_id}/overview")
async def get_tenant_overview(
    tenant_id: uuid.UUID,
    context=Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve business summary KPIs and Managed Service Performance Viewer data for the tenant dashboard.

    Strictly isolated to `tenant_id` and free of internal AI prompts, credentials, or operational controls.
    """
    if tenant_id != context.tenant_id:
        raise TenantIsolationError("Access denied: path tenant_id does not match X-Tenant-ID context")

    # Fetch tenant record
    t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = t_res.scalar_one_or_none()
    selected_industry = normalize_industry(tenant.industry if tenant else "Financing")

    # 1. Total Income (BusinessRecord + FinancialTransaction ledger)
    income_res = await session.execute(
        select(func.sum(BusinessRecord.amount)).where(
            BusinessRecord.tenant_id == tenant_id,
            BusinessRecord.record_type.in_(["income", "rent", "payment_received"]),
        )
    )
    ft_income_res = await session.execute(
        select(func.sum(FinancialTransaction.amount)).where(
            FinancialTransaction.tenant_id == tenant_id,
            FinancialTransaction.type.in_(["income", "rent"]),
            FinancialTransaction.status == "paid",
            FinancialTransaction.category != "WhatsApp Concierge",
        )
    )
    total_income = float(income_res.scalar() or 0.0) + float(ft_income_res.scalar() or 0.0)

    # 2. Total Expenses (BusinessRecord + FinancialTransaction ledger)
    expense_res = await session.execute(
        select(func.sum(BusinessRecord.amount)).where(
            BusinessRecord.tenant_id == tenant_id,
            BusinessRecord.record_type == "expense",
        )
    )
    ft_expense_res = await session.execute(
        select(func.sum(FinancialTransaction.amount)).where(
            FinancialTransaction.tenant_id == tenant_id,
            FinancialTransaction.type == "expense",
            FinancialTransaction.status == "paid",
            FinancialTransaction.category != "WhatsApp Concierge",
        )
    )
    total_expenses = float(expense_res.scalar() or 0.0) + float(ft_expense_res.scalar() or 0.0)

    # 3. Total Outstanding (BusinessRecord + pending/overdue FinancialTransaction)
    outstanding_res = await session.execute(
        select(func.sum(BusinessRecord.amount)).where(
            BusinessRecord.tenant_id == tenant_id,
            BusinessRecord.record_type == "outstanding",
        )
    )
    ft_outstanding_res = await session.execute(
        select(func.sum(FinancialTransaction.amount)).where(
            FinancialTransaction.tenant_id == tenant_id,
            FinancialTransaction.status.in_(["pending", "overdue"]),
            FinancialTransaction.category != "WhatsApp Concierge",
        )
    )
    total_outstanding = float(outstanding_res.scalar() or 0.0) + float(ft_outstanding_res.scalar() or 0.0)

    # 4. Leads, Outreach Messages Sent, Meetings Booked & Conversion Rate
    leads_rows_res = await session.execute(
        select(Lead).where(Lead.tenant_id == tenant_id).order_by(Lead.created_at.desc())
    )
    leads_rows = list(leads_rows_res.scalars().all())
    total_leads = len(leads_rows)
    qualified_leads = sum(
        1 for lead in leads_rows if lead.status in ("qualified", "converted") or float(lead.qualification_score or 0) >= 70.0
    )

    messages_sent = 0
    meetings_booked = 0
    lead_performance: List[Dict[str, Any]] = []
    appointment_performance: List[Dict[str, Any]] = []

    for lead in leads_rows:
        meta = lead.metadata_ or {}
        msg_cnt = int(meta.get("messages_sent_count", 0))
        if msg_cnt == 0 and lead.status in ("contacted", "qualified", "converted"):
            msg_cnt = 1
        messages_sent += msg_cnt

        is_booked = bool(meta.get("meeting_booked")) or lead.status == "converted"
        if is_booked:
            meetings_booked += 1
            appointment_performance.append({
                "lead_id": str(lead.id),
                "client_name": lead.name,
                "meeting_title": meta.get("meeting_title", "Consultation & Service Discovery"),
                "scheduled_at": meta.get("meeting_scheduled_at", lead.created_at.isoformat()),
                "status": "Confirmed",
            })

        lead_performance.append({
            "id": str(lead.id),
            "name": lead.name,
            "source": lead.source,
            "status": lead.status,
            "qualification_score": float(lead.qualification_score or 0.0),
            "messages_sent": msg_cnt,
            "meeting_booked": is_booked,
            "created_at": lead.created_at.isoformat(),
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

    # 6. Subscriptions, Packages & Payment Approval Status
    now = datetime.now(timezone.utc)
    onboarding_summary = await integration_service.get_onboarding_requirements(session, tenant_id)
    subscriptions = await billing_service.get_tenant_subscriptions(session, tenant_id)
    active_subs = [
        s
        for s in subscriptions
        if s.status == "active" and (s.expires_at is None or _ensure_utc(s.expires_at) >= now)
    ]
    monthly_spend = sum(float(s.price) for s in active_subs)
    current_package = (
        active_subs[0].plan_name.replace("_", " ").title()
        if active_subs
        else "No Active Package"
    )

    t_settings = dict(tenant.settings or {}) if tenant else {}
    raw_payment_approved = t_settings.get("payment_approved")
    completed_pay = await session.execute(
        select(Payment).where(Payment.tenant_id == tenant_id, Payment.status == "completed").limit(1)
    )
    has_completed_payment = completed_pay.scalar_one_or_none() is not None

    if raw_payment_approved is True:
        payment_approved = True
    elif has_completed_payment:
        payment_approved = True
    elif raw_payment_approved is None and tenant is not None and tenant.status == "active":
        payment_approved = True
    else:
        payment_approved = False

    payment_notified = bool(t_settings.get("payment_notified", False))
    payment_reference = t_settings.get("payment_reference", None)
    is_payment_approved = payment_approved

    if not tenant:
        service_status = "Suspended"
        automation_active = False
    elif tenant.status == "suspended":
        service_status = "Suspended"
        automation_active = False
    elif not is_payment_approved:
        automation_active = False
        if payment_notified:
            service_status = "Payment Transfer Submitted — Verification In Progress"
        else:
            service_status = "Awaiting Bank Transfer Payment Approval"
    elif is_payment_approved and (onboarding_summary["automation_active"] or len(active_subs) > 0):
        service_status = "Active — Delivering Outcomes"
        automation_active = True
    elif len(active_subs) > 0:
        service_status = "Pending Integration Connection"
        automation_active = False
    else:
        service_status = "Awaiting Service Selection"
        automation_active = False

    # Format purchased services precisely with slot numbers & mirroring selection
    purchased_services = []
    service_slugs = []
    for idx, srv in enumerate(onboarding_summary["purchased_services"]):
        slug_val = srv.get("service_slug", "")
        service_slugs.append(slug_val)
        purchased_services.append({
            "slot_number": idx + 1,
            "subscription_id": srv.get("subscription_id"),
            "service_id": srv.get("service_id"),
            "service_name": srv.get("service_name"),
            "service_slug": slug_val,
            "plan_name": srv.get("plan_name", "growth").replace("_", " ").title(),
            "price": float(srv.get("price", 0.0)),
            "billing_interval": srv.get("billing_interval", "monthly"),
            "status": "Active" if is_payment_approved else "Awaiting Payment Approval",
            "required_integrations": srv.get("required_integrations", []),
        })

    # Service-specific modules calculation based exclusively on client chosen services
    enabled_modules: List[str] = []
    if is_payment_approved and service_slugs:
        seen_modules = set()
        for slug_val in service_slugs:
            for mod in SERVICE_MODULE_MAP.get(slug_val, []):
                if mod not in seen_modules:
                    seen_modules.add(mod)
                    enabled_modules.append(mod)

    # Concise Outreach Tier & Multi-Channel Performance Metrics
    lead_quota = await outreach_autopilot_service.compute_tenant_lead_quota(session, tenant_id)
    gmail_drafts_ready = 0
    whatsapp_pitches_ready = 0
    linkedin_pitches_ready = 0
    pending_outreach_approvals = 0
    approved_sent_count = 0
    for lead in leads_rows:
        meta = lead.metadata_ or {}
        if meta.get("gmail_draft_body"):
            gmail_drafts_ready += 1
        if meta.get("whatsapp_pitch"):
            whatsapp_pitches_ready += 1
        if meta.get("linkedin_note"):
            linkedin_pitches_ready += 1
        app_st = meta.get("approval_status")
        if app_st == "pending_approval":
            pending_outreach_approvals += 1
        elif app_st == "approved_sent":
            approved_sent_count += 1

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

    # Clean empty state for operational metrics when payment is not yet approved
    metrics_data = {
        "income": total_income if is_payment_approved else 0.0,
        "expenses": total_expenses if is_payment_approved else 0.0,
        "net_profit": (total_income - total_expenses) if is_payment_approved else 0.0,
        "outstanding": total_outstanding if is_payment_approved else 0.0,
        "leads": total_leads if is_payment_approved else 0,
        "leads_generated": total_leads if is_payment_approved else 0,
        "qualified_leads": qualified_leads if is_payment_approved else 0,
        "messages_sent": messages_sent if is_payment_approved else 0,
        "meetings_booked": meetings_booked if is_payment_approved else 0,
        "conversion_rate": conversion_rate if is_payment_approved else 0.0,
        "active_agents": active_agents if is_payment_approved else 0,
    }

    return {
        "success": True,
        "data": {
            "tenant_id": str(tenant_id),
            "tenant_name": tenant.name if tenant else "Company Workspace",
            "role": context.role,
            "selected_industry": selected_industry,
            "service_status": service_status,
            "automation_active": automation_active,
            "is_payment_approved": is_payment_approved,
            "payment_notified": payment_notified,
            "payment_reference": payment_reference,
            "bank_details": COMPANY_BANK_DETAILS,
            "payment_rails": get_payment_rails_info(),
            "current_package": current_package,
            "purchased_services": purchased_services,
            "purchased_service_slugs": service_slugs,
            "enabled_modules": enabled_modules,
            "outreach_performance": {
                **lead_quota,
                "gmail_drafts_ready": gmail_drafts_ready if is_payment_approved else 0,
                "whatsapp_pitches_ready": whatsapp_pitches_ready if is_payment_approved else 0,
                "linkedin_pitches_ready": linkedin_pitches_ready if is_payment_approved else 0,
                "pending_outreach_approvals": pending_outreach_approvals if is_payment_approved else 0,
                "approved_sent_count": approved_sent_count if is_payment_approved else 0,
            },
            "subscription_info": {
                "active_services_count": len(active_subs),
                "current_package": current_package,
                "monthly_investment": round(monthly_spend, 2),
                "billing_cycle": active_subs[0].billing_interval if active_subs else "monthly",
                "status": "Active" if is_payment_approved else "Awaiting Payment Approval",
            },
            "integrations_status": onboarding_summary["required_integrations"],
            "metrics": metrics_data,
            "lead_performance": lead_performance[:15] if is_payment_approved else [],
            "appointment_performance": appointment_performance[:15] if is_payment_approved else [],
            "recent_activity": recent_activity,
            "reports": {
                "period": "Current Billing Cycle",
                "leads_generated": total_leads if is_payment_approved else 0,
                "qualified_leads": qualified_leads if is_payment_approved else 0,
                "messages_sent": messages_sent if is_payment_approved else 0,
                "meetings_booked": meetings_booked if is_payment_approved else 0,
                "conversion_rate": conversion_rate if is_payment_approved else 0.0,
                "net_business_value": round(total_income - total_expenses, 2) if is_payment_approved else 0.0,
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
    if tenant_id != context.tenant_id:
        raise TenantIsolationError("Access denied: path tenant_id does not match X-Tenant-ID context")

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
        profile_res = await session.execute(select(Profile).where(Profile.id == context.user_id))
        caller_profile = profile_res.scalar_one_or_none()
        is_super = (
            await auth_service.is_platform_super_admin(session, caller_profile)
            if caller_profile
            else False
        )
        incoming_settings = dict(request.settings)
        if not is_super:
            for key in PROTECTED_TENANT_SETTING_KEYS:
                incoming_settings.pop(key, None)
        merged = dict(tenant.settings or {})
        merged.update(incoming_settings)
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
    is_super = await auth_service.is_platform_super_admin(session, current_user)
    request.industry = normalize_industry(request.industry)
    return await tenant_service.create_tenant(
        session,
        current_user.id,
        request,
        is_super_admin=is_super,
    )


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
    if tenant_id != context.tenant_id:
        raise TenantIsolationError("Access denied: path tenant_id does not match X-Tenant-ID context")
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
    if tenant_id != context.tenant_id:
        raise TenantIsolationError("Access denied: path tenant_id does not match X-Tenant-ID context")
    return await tenant_service.list_tenant_members(
        session=session,
        tenant_id=tenant_id,
    )
