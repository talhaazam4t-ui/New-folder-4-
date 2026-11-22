"""Platform Owner & Super Administrator API Endpoints.

Provides complete operational control over the managed AI SaaS platform:
1. Platform Management: Clients/tenants, activation/suspension, industry & service assignments,
   subscriptions/packages, service availability & pricing, platform-wide settings.
2. AI Agent Management: Available agents & status, execution history, errors & DLQ,
   pending human approvals, model selection & usage, token consumption & API costs, permissions.
3. Lead Generation & Outreach: Lead gen operations, qualification, outreach execution,
   messages sent, meetings booked, conversion analytics, campaign performance, client-specific lead activity.
4. Integration Management: WhatsApp, Google Business/Maps, Gmail/Email, Google Calendar,
   booking providers, credential connection status, failures, reconnection & revocation (without exposing secrets).
5. Monitoring: Global performance analytics, client-wise activity, API usage, AI model costs,
   backend errors, execution logs, audit logs, and failed integration alerts.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.agents.registry import agent_registry
from app.automation.approval_manager import approval_manager
from app.automation.budget_manager import budget_manager
from app.automation.retry import dead_letter_queue
from app.config import settings
from app.core.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.core.security import (
    encrypt_secret,
    encrypt_sensitive_config,
    get_password_hash,
    mask_sensitive_config,
)
from app.database.models.agent import AgentExecution, AgentRegistry, AgentTask
from app.database.models.automation import Approval, AuditLog, Integration, UsageRecord
from app.database.models.billing import Payment
from app.database.models.marketing import Lead, MarketingCampaign
from app.database.models.service import Service, ServiceSubscription
from app.database.models.tenant import Profile, Tenant, TenantMember
from app.database.supabase import get_db
from app.dependencies import get_current_user
from app.schemas.marketing import LeadGenerationRequest
from app.schemas.payment import BankTransferApproveRequest
from app.schemas.service import SubscriptionCreateRequest
from app.services.auth_service import auth_service
from app.services.billing_service import billing_service, normalize_industry
from app.services.marketing_service import marketing_service
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/admin", tags=["Platform Administration"])

# Runtime platform-wide settings controlled by Owner
_PLATFORM_RUNTIME_SETTINGS: Dict[str, Any] = {
    "default_fast_model": settings.ai_default_fast_model,
    "default_reasoning_model": settings.ai_default_reasoning_model,
    "default_tenant_daily_token_budget": settings.default_tenant_daily_token_budget,
    "rate_limit_agent_rpm": settings.rate_limit_agent_rpm,
    "mandatory_approval_for_campaigns": True,
    "mandatory_approval_for_bulk_outreach": True,
    "managed_service_mode": "done_for_you",
}

_STARTUP_SYNC_FLAGS: Dict[str, bool] = {
    "catalog": False,
    "registry": False,
}


def reset_sync_flags() -> None:
    """Reset one-time startup seed flags (used by test DB reset)."""
    _STARTUP_SYNC_FLAGS["catalog"] = False
    _STARTUP_SYNC_FLAGS["registry"] = False


async def _ensure_startup_synced_once(session: AsyncSession) -> None:
    """Idempotently ensure default catalog and agent registry once per process."""
    if not _STARTUP_SYNC_FLAGS["catalog"]:
        await billing_service.ensure_default_catalog(session)
        _STARTUP_SYNC_FLAGS["catalog"] = True
    if not _STARTUP_SYNC_FLAGS["registry"]:
        await agent_registry._ensure_db_registry(session)
        _STARTUP_SYNC_FLAGS["registry"] = True


async def _fetch_tenants_overview_data(
    session: AsyncSession,
) -> tuple[List[Dict[str, Any]], Dict[uuid.UUID, str], List[Integration]]:
    """Fetch tenants and related counts/subscriptions/integrations in 5 bulk queries (no N+1)."""
    tenants_res = await session.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    tenants = list(tenants_res.scalars().all())
    tenant_names_by_id: Dict[uuid.UUID, str] = {t.id: t.name for t in tenants}

    members_res = await session.execute(
        select(TenantMember.tenant_id, func.count(TenantMember.id)).group_by(TenantMember.tenant_id)
    )
    members_count_by_tenant: Dict[uuid.UUID, int] = {
        t_id: int(cnt or 0) for t_id, cnt in members_res.all()
    }

    subs_res = await session.execute(
        select(ServiceSubscription, Service.name).join(
            Service, ServiceSubscription.service_id == Service.id
        )
    )
    subs_by_tenant: Dict[uuid.UUID, List[Dict[str, Any]]] = {}
    for sub, service_name in subs_res.all():
        subs_by_tenant.setdefault(sub.tenant_id, []).append({
            "id": str(sub.id),
            "service_name": service_name,
            "plan_name": sub.plan_name,
            "price": float(sub.price),
            "status": sub.status,
        })

    leads_res = await session.execute(
        select(Lead.tenant_id, func.count(Lead.id)).group_by(Lead.tenant_id)
    )
    leads_count_by_tenant: Dict[uuid.UUID, int] = {
        t_id: int(cnt or 0) for t_id, cnt in leads_res.all()
    }

    ints_res = await session.execute(select(Integration).order_by(Integration.created_at.desc()))
    all_integrations = list(ints_res.scalars().all())
    integrations_by_tenant: Dict[uuid.UUID, List[Integration]] = {}
    for integ in all_integrations:
        integrations_by_tenant.setdefault(integ.tenant_id, []).append(integ)

    tenant_list: List[Dict[str, Any]] = []
    for t in tenants:
        subs = subs_by_tenant.get(t.id, [])
        active_subs = [s for s in subs if s["status"] == "active"]
        integrations = integrations_by_tenant.get(t.id, [])

        cfg_settings = t.settings or {}
        onboarding_plan = cfg_settings.get("plan_name") or cfg_settings.get("package_tier")
        onboarding_service = cfg_settings.get("service_name")

        tenant_list.append({
            "id": str(t.id),
            "name": t.name,
            "slug": t.slug,
            "industry": normalize_industry(t.industry),
            "status": t.status,
            "members_count": members_count_by_tenant.get(t.id, 0),
            "active_subscriptions": active_subs,
            "all_subscriptions": subs,
            "selected_package_tier": onboarding_plan or (active_subs[0]["plan_name"] if active_subs else None),
            "selected_service_name": onboarding_service or (active_subs[0]["service_name"] if active_subs else None),
            "monthly_spend": sum(float(s["price"]) for s in active_subs),
            "leads_count": leads_count_by_tenant.get(t.id, 0),
            "integrations_connected": sum(1 for i in integrations if i.status == "connected"),
            "integrations_pending": sum(1 for i in integrations if i.status == "pending_approval"),
            "integrations_failed": sum(1 for i in integrations if i.status == "error"),
            "integrations_disconnected": sum(1 for i in integrations if i.status == "disconnected"),
            "settings": cfg_settings,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })

    return tenant_list, tenant_names_by_id, all_integrations


class TenantStatusUpdateRequest(BaseModel):
    status: str  # active, suspended, pending_approval


class TenantAssignmentRequest(BaseModel):
    industry: Optional[str] = None
    status: Optional[str] = None
    automation_approved_by_owner: Optional[bool] = None
    assign_service_id: Optional[uuid.UUID] = None
    plan_name: str = "growth"
    price: float = 249.0
    billing_interval: str = "monthly"


class AdminProvisionTenantRequest(BaseModel):
    name: str
    slug: Optional[str] = None
    industry: str = "Financing"
    owner_email: str
    owner_name: Optional[str] = None
    owner_password: Optional[str] = None
    plan_name: str = "growth"
    price: float = 249.0
    status: str = "active"


class PlatformSettingsUpdateRequest(BaseModel):
    default_fast_model: Optional[str] = None
    default_reasoning_model: Optional[str] = None
    default_tenant_daily_token_budget: Optional[int] = None
    rate_limit_agent_rpm: Optional[int] = None
    mandatory_approval_for_campaigns: Optional[bool] = None
    mandatory_approval_for_bulk_outreach: Optional[bool] = None


class AdminAgentUpdateRequest(BaseModel):
    active: Optional[bool] = None
    tier: Optional[str] = None
    allowed_tools: Optional[List[str]] = None


class AdminIntegrationActionRequest(BaseModel):
    action: str  # revoke, reconnect, test, approve


class AdminConnectIntegrationRequest(BaseModel):
    provider: str
    account_identifier: Optional[str] = None
    api_key: Optional[str] = None
    oauth_code: Optional[str] = None
    status: str = "connected"
    configuration: Optional[Dict[str, Any]] = None


class AdminApprovalReviewRequest(BaseModel):
    decision: str = "approved"  # approved | rejected
    reason: Optional[str] = None


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
    """Verify that current user is the Platform Owner / Super Admin (`system.admin`).

    Regular client accounts (even if they hold `role='owner'` on their own client tenant)
    are strictly rejected with 403 Forbidden.
    """
    is_super = await auth_service.is_platform_super_admin(session, current_user)
    if not is_super:
        raise PermissionDeniedError("Only the Platform Super Administrator can access the Owner Console")
    return current_user


@router.get("/stats", response_model=GlobalAdminStats)
async def get_global_stats(
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve system-wide KPIs: MRR, total companies, payments, and agent activity."""
    total_tenants_res = await session.execute(select(func.count(Tenant.id)))
    total_tenants = total_tenants_res.scalar() or 0

    active_tenants_res = await session.execute(
        select(func.count(Tenant.id)).where(Tenant.status == "active")
    )
    active_tenants = active_tenants_res.scalar() or 0

    suspended_tenants = max(0, total_tenants - active_tenants)

    mrr_res = await session.execute(
        select(func.sum(ServiceSubscription.price)).where(
            ServiceSubscription.status == "active",
            ServiceSubscription.billing_interval == "monthly",
        )
    )
    mrr = float(mrr_res.scalar() or 0.0)

    payments_res = await session.execute(
        select(func.sum(Payment.amount)).where(Payment.status == "completed")
    )
    total_payments = float(payments_res.scalar() or 0.0)

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
    """List all registered client companies with industry, subscriptions, integrations, and lead metrics."""
    tenant_list, _, _ = await _fetch_tenants_overview_data(session)
    return {"success": True, "data": tenant_list}


@router.patch("/tenants/{tenant_id}/status")
async def update_tenant_status(
    tenant_id: uuid.UUID,
    request: TenantStatusUpdateRequest,
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Suspend, activate, or review a tenant account."""
    query = select(Tenant).where(Tenant.id == tenant_id)
    res = await session.execute(query)
    tenant = res.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    old_status = tenant.status
    tenant.status = request.status
    cfg = dict(tenant.settings or {})
    is_active = request.status == "active"
    cfg["payment_approved"] = is_active
    cfg["automation_approved_by_owner"] = is_active
    tenant.settings = cfg
    action_tag = (
        "admin.tenant.activated_and_payment_confirmed"
        if request.status == "active"
        else f"admin.tenant.status.{request.status}"
    )
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_id=admin_user.id,
            actor_type="admin",
            action=action_tag,
            resource_type="tenant",
            resource_id=tenant.id,
            metadata_={"old_status": old_status, "status": request.status, "tenant_name": tenant.name},
        )
    )
    await session.commit()

    return {
        "success": True,
        "message": f"Tenant '{tenant.name}' status updated to {request.status}",
    }


@router.post("/payments/{payment_id}/confirm")
async def confirm_tenant_payment(
    payment_id: uuid.UUID,
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Super Admin manual confirmation of payment receipt and workspace activation."""
    res = await billing_service.confirm_payment(session, payment_id)
    return {"success": True, "data": res, "message": "Payment confirmed and tenant activated"}


@router.patch("/tenants/{tenant_id}/assign")
async def assign_tenant_industry_and_service(
    tenant_id: uuid.UUID,
    request: TenantAssignmentRequest,
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Owner control to update a client's industry, approve automation readiness, or assign a service package."""
    res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = res.scalar_one_or_none()
    if not tenant:
        raise ResourceNotFoundError("Tenant", str(tenant_id))

    if request.industry is not None:
        tenant.industry = normalize_industry(request.industry)
    if request.status is not None:
        tenant.status = request.status
    if request.automation_approved_by_owner is not None:
        cfg = dict(tenant.settings or {})
        cfg["automation_approved_by_owner"] = request.automation_approved_by_owner
        tenant.settings = cfg

    assigned_subscription = None
    if request.assign_service_id is not None:
        assigned_subscription = await billing_service.subscribe_service(
            session=session,
            tenant_id=tenant.id,
            request=SubscriptionCreateRequest(
                service_id=request.assign_service_id,
                plan_name=request.plan_name,
                billing_interval=request.billing_interval,
                price=request.price,
            ),
        )

    session.add(
        AuditLog(
            tenant_id=tenant.id,
            actor_id=admin_user.id,
            actor_type="admin",
            action="admin.tenant.workspace_assigned",
            resource_type="tenant",
            resource_id=tenant.id,
            metadata_={
                "industry": tenant.industry,
                "status": tenant.status,
                "tenant_name": tenant.name,
                "plan_name": request.plan_name,
            },
        )
    )
    await session.commit()
    return {
        "success": True,
        "data": {
            "tenant_id": str(tenant.id),
            "industry": tenant.industry,
            "status": tenant.status,
            "settings": tenant.settings or {},
            "assigned_subscription": (
                assigned_subscription.model_dump(mode="json") if assigned_subscription else None
            ),
        },
        "message": "Client workspace assignment updated by Platform Owner.",
    }


@router.post("/tenants/provision")
async def admin_provision_tenant(
    request: AdminProvisionTenantRequest,
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Directly provision a new client workspace with an owner profile and subscription from the Admin Console."""
    norm_industry = normalize_industry(request.industry)
    owner_email = request.owner_email.strip().lower()

    # 1. Resolve or create Owner Profile
    owner_res = await session.execute(select(Profile).where(Profile.email == owner_email))
    owner_profile = owner_res.scalar_one_or_none()
    if not owner_profile:
        pwd = request.owner_password or "Client@12345"
        owner_id = uuid.uuid4()
        owner_profile = Profile(
            id=owner_id,
            full_name=request.owner_name or request.name,
            email=owner_email,
            password_hash=get_password_hash(pwd),
        )
        session.add(owner_profile)
        await session.flush()

    # 2. Derive unique slug
    base_slug = request.slug or re.sub(r"[^a-z0-9]+", "-", request.name.lower()).strip("-")
    if not base_slug:
        base_slug = f"client-{uuid.uuid4().hex[:6]}"

    slug = base_slug
    idx = 1
    while True:
        existing = await session.execute(select(Tenant).where(Tenant.slug == slug))
        if not existing.scalar_one_or_none():
            break
        slug = f"{base_slug}-{idx}"
        idx += 1

    # 3. Create Tenant
    tenant_status = "active" if request.status.lower() == "active" else "pending_approval"
    new_tenant = Tenant(
        name=request.name.strip(),
        slug=slug,
        industry=norm_industry,
        status=tenant_status,
        settings={
            "onboarding_completed": True,
            "automation_active": (tenant_status == "active"),
            "payment_approved": (tenant_status == "active"),
            "automation_approved_by_owner": (tenant_status == "active"),
            "plan_name": request.plan_name,
            "theme": "emerald",
        },
    )
    session.add(new_tenant)
    await session.flush()

    # 4. Create TenantMember
    membership = TenantMember(
        tenant_id=new_tenant.id,
        user_id=owner_profile.id,
        role="owner",
        status="active",
    )
    session.add(membership)

    # 5. Provision service subscription if catalog service exists
    services_res = await session.execute(select(Service).where(Service.active.is_(True)))
    catalog_service = services_res.scalars().first()

    if catalog_service:
        now_utc = datetime.now(timezone.utc)
        session.add(
            ServiceSubscription(
                tenant_id=new_tenant.id,
                service_id=catalog_service.id,
                plan_name=request.plan_name,
                billing_interval="monthly",
                price=request.price,
                status=tenant_status,
                started_at=now_utc,
            )
        )

    # 6. Audit log
    session.add(
        AuditLog(
            tenant_id=new_tenant.id,
            actor_id=admin_user.id,
            actor_type="admin",
            action="admin.tenant.provisioned_by_owner",
            resource_type="tenant",
            resource_id=new_tenant.id,
            metadata_={
                "tenant_name": new_tenant.name,
                "slug": new_tenant.slug,
                "industry": norm_industry,
                "owner_email": owner_email,
                "status": tenant_status,
            },
        )
    )
    await session.commit()
    return {
        "success": True,
        "message": f"Client workspace '{new_tenant.name}' provisioned successfully.",
        "data": {
            "id": str(new_tenant.id),
            "name": new_tenant.name,
            "slug": new_tenant.slug,
            "industry": new_tenant.industry,
            "status": new_tenant.status,
            "owner_email": owner_email,
        },
    }


@router.post("/tenants/{tenant_id}/approve-payment")
async def admin_approve_tenant_payment(
    tenant_id: uuid.UUID,
    request: BankTransferApproveRequest = BankTransferApproveRequest(),
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Owner verification and approval of client bank transfer, activating AI services."""
    return await billing_service.approve_tenant_payment(
        session=session,
        tenant_id=tenant_id,
        admin_user_id=admin_user.id,
        notes=request.notes,
    )


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


@router.get("/operations")
async def get_owner_operations_control_center(
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Single comprehensive operational control payload for the Owner / Super Admin Dashboard."""
    await _ensure_startup_synced_once(session)

    stats = await get_global_stats(admin_user, session)
    tenant_list, tenant_names_by_id, all_integrations = await _fetch_tenants_overview_data(session)
    services_rows = await billing_service.list_services(session, active_only=False)

    # Agents & Telemetry
    agents_res = await session.execute(select(AgentRegistry).order_by(AgentRegistry.name))
    agents_rows = agents_res.scalars().all()

    exec_res = await session.execute(
        select(AgentExecution).order_by(AgentExecution.created_at.desc()).limit(50)
    )
    exec_rows = exec_res.scalars().all()

    failed_tasks_res = await session.execute(
        select(AgentTask).where(AgentTask.status == "failed").order_by(AgentTask.created_at.desc()).limit(25)
    )
    failed_tasks = failed_tasks_res.scalars().all()

    # Pending Human Approvals
    approvals_res = await session.execute(
        select(Approval).order_by(Approval.created_at.desc()).limit(30)
    )
    approvals_rows = approvals_res.scalars().all()

    # Pending Bank Payments Awaiting Owner Verification
    pending_payments_res = await session.execute(
        select(Payment, Tenant.name)
        .join(Tenant, Payment.tenant_id == Tenant.id)
        .where(Payment.status.in_(["pending_verification", "pending"]))
        .order_by(Payment.created_at.desc())
    )
    pending_payments_rows = pending_payments_res.all()
    pending_payments_data = [
        {
            "id": str(p.id),
            "tenant_id": str(p.tenant_id),
            "tenant_name": t_name,
            "amount": float(p.amount),
            "currency": p.currency,
            "payment_method": p.payment_method,
            "provider_reference": p.provider_reference,
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p, t_name in pending_payments_rows
    ]

    # Leads & Outreach Campaigns across platform
    leads_res = await session.execute(select(Lead).order_by(Lead.created_at.desc()).limit(50))
    leads_rows = leads_res.scalars().all()

    campaigns_res = await session.execute(
        select(MarketingCampaign).order_by(MarketingCampaign.created_at.desc()).limit(30)
    )
    campaigns_rows = campaigns_res.scalars().all()

    # Build complete integration matrix from bulk-fetched integrations (secrets strictly masked!)
    integrations_payload = []
    seen_tenant_providers = set()
    for integ in all_integrations:
        t_name = tenant_names_by_id.get(integ.tenant_id, "Unknown Tenant")
        seen_tenant_providers.add((str(integ.tenant_id), integ.provider.lower()))
        integrations_payload.append({
            "id": str(integ.id),
            "tenant_id": str(integ.tenant_id),
            "tenant_name": t_name,
            "provider": integ.provider,
            "integration_type": integ.integration_type,
            "status": integ.status,
            "external_account_id": integ.external_account_id,
            "configuration": mask_sensitive_config(integ.configuration or {}),
            "created_at": integ.created_at.isoformat() if integ.created_at else None,
        })

    CORE_INTEGRATION_TEMPLATES = [
        {"provider": "gmail", "type": "oauth"},
        {"provider": "google_calendar", "type": "oauth"},
        {"provider": "whatsapp", "type": "oauth"},
        {"provider": "google_business", "type": "oauth"},
        {"provider": "booking_provider", "type": "api_key"},
    ]

    for t_item in tenant_list:
        t_id = t_item["id"]
        t_name = t_item["name"]
        for p in CORE_INTEGRATION_TEMPLATES:
            if (t_id, p["provider"]) not in seen_tenant_providers:
                integrations_payload.append({
                    "id": f"unlinked_{t_id}_{p['provider']}",
                    "tenant_id": t_id,
                    "tenant_name": t_name,
                    "provider": p["provider"],
                    "integration_type": p["type"],
                    "status": "disconnected",
                    "external_account_id": None,
                    "configuration": {"unlinked": True},
                    "created_at": None,
                })

    # AI Model Usage & Cost Telemetry
    usage_res = await session.execute(
        select(UsageRecord).order_by(UsageRecord.created_at.desc()).limit(50)
    )
    usage_rows = usage_res.scalars().all()
    total_tokens_consumed = sum(int(u.input_tokens or 0) + int(u.output_tokens or 0) for u in usage_rows)
    total_ai_cost = round(sum(float(u.estimated_cost or 0.0) for u in usage_rows), 6)

    # Audit Logs
    audit_res = await session.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(50)
    )
    audit_rows = audit_res.scalars().all()

    # Compute Lead Gen & Outreach summary
    total_messages_sent = 0
    total_meetings_booked = 0
    for lead in leads_rows:
        meta = lead.metadata_ or {}
        total_messages_sent += int(meta.get("messages_sent_count", 1 if lead.status != "new" else 0))
        if meta.get("meeting_booked") or lead.status == "converted":
            total_meetings_booked += 1

    total_leads_cnt = len(leads_rows)
    qualified_leads_cnt = sum(
        1 for lead in leads_rows if lead.status in ("qualified", "converted") or float(lead.qualification_score or 0) >= 70.0
    )

    return {
        "success": True,
        "data": {
            "stats": stats.model_dump(),
            "platform_settings": _PLATFORM_RUNTIME_SETTINGS,
            "tenants": tenant_list,
            "services": [
                {
                    "id": str(s.id),
                    "name": s.name,
                    "slug": s.slug,
                    "category": s.category,
                    "description": s.description,
                    "active": s.active,
                    "configuration_schema": s.configuration_schema or {},
                }
                for s in services_rows
            ],
            "ai_agents": {
                "agents": [
                    {
                        "id": str(a.id),
                        "name": a.name,
                        "category": a.category,
                        "description": a.description,
                        "version": a.version,
                        "active": a.active,
                        "tier": (a.configuration or {}).get("tier", "fast"),
                        "allowed_tools": (a.configuration or {}).get("allowed_tools", []),
                    }
                    for a in agents_rows
                ],
                "executions": [
                    {
                        "id": str(e.id),
                        "tenant_id": str(e.tenant_id),
                        "task_id": str(e.task_id),
                        "status": e.status,
                        "tokens_used": int(e.tokens_used or 0),
                        "estimated_cost": float(e.estimated_cost or 0.0),
                        "duration_ms": int(e.duration_ms or 0),
                        "error_message": e.error_message,
                        "created_at": e.created_at.isoformat() if e.created_at else None,
                    }
                    for e in exec_rows
                ],
                "failed_tasks": [
                    {
                        "id": str(ft.id),
                        "tenant_id": str(ft.tenant_id),
                        "task_type": ft.task_type,
                        "status": ft.status,
                        "attempts": ft.attempts,
                    }
                    for ft in failed_tasks
                ],
                "dlq": dead_letter_queue.list_entries(),
                "total_tokens_consumed": total_tokens_consumed,
                "total_ai_cost_usd": total_ai_cost,
            },
            "approvals": [
                {
                    "id": str(ap.id),
                    "tenant_id": str(ap.tenant_id),
                    "action_type": ap.action_type,
                    "proposed_action": ap.proposed_action or {},
                    "status": ap.status,
                    "requested_by": ap.requested_by,
                    "created_at": ap.created_at.isoformat() if ap.created_at else None,
                }
                for ap in approvals_rows
            ],
            "pending_payments": pending_payments_data,
            "lead_gen_outreach": {
                "summary": {
                    "total_leads": total_leads_cnt,
                    "qualified_leads": qualified_leads_cnt,
                    "messages_sent": total_messages_sent,
                    "meetings_booked": total_meetings_booked,
                    "conversion_rate": (
                        round(total_meetings_booked / total_leads_cnt * 100.0, 1)
                        if total_leads_cnt > 0
                        else 0.0
                    ),
                },
                "leads": [
                    {
                        "id": str(lead.id),
                        "tenant_id": str(lead.tenant_id),
                        "name": lead.name,
                        "email": lead.email,
                        "phone": lead.phone,
                        "source": lead.source,
                        "status": lead.status,
                        "qualification_score": float(lead.qualification_score or 0.0),
                        "metadata": lead.metadata_ or {},
                        "created_at": lead.created_at.isoformat() if lead.created_at else None,
                    }
                    for lead in leads_rows
                ],
                "campaigns": [
                    {
                        "id": str(c.id),
                        "tenant_id": str(c.tenant_id),
                        "name": c.name,
                        "platform": c.platform,
                        "objective": c.objective,
                        "status": c.status,
                        "budget": float(c.budget or 0.0),
                    }
                    for c in campaigns_rows
                ],
            },
            "integrations": integrations_payload,
            "monitoring": {
                "usage_records": [
                    {
                        "id": str(u.id),
                        "tenant_id": str(u.tenant_id),
                        "provider": u.provider,
                        "model": u.model,
                        "input_tokens": int(u.input_tokens or 0),
                        "output_tokens": int(u.output_tokens or 0),
                        "estimated_cost": float(u.estimated_cost or 0.0),
                        "created_at": u.created_at.isoformat() if u.created_at else None,
                    }
                    for u in usage_rows
                ],
                "audit_logs": [
                    {
                        "id": str(al.id),
                        "tenant_id": str(al.tenant_id) if al.tenant_id else None,
                        "actor_type": al.actor_type,
                        "action": al.action,
                        "resource_type": al.resource_type,
                        "metadata": mask_sensitive_config(al.metadata_ or {}),
                        "created_at": al.created_at.isoformat() if al.created_at else None,
                    }
                    for al in audit_rows
                ],
            },
        },
    }


@router.patch("/settings")
async def update_platform_settings(
    request: PlatformSettingsUpdateRequest,
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Update global platform-wide AI routing, token budget, and approval settings."""
    updates = request.model_dump(exclude_none=True)
    _PLATFORM_RUNTIME_SETTINGS.update(updates)
    session.add(
        AuditLog(
            actor_id=admin_user.id,
            actor_type="admin",
            action="admin.platform_settings.updated",
            resource_type="platform_settings",
            metadata_=updates,
        )
    )
    await session.commit()
    return {"success": True, "data": _PLATFORM_RUNTIME_SETTINGS}


@router.patch("/agents/{agent_name}")
async def update_global_agent_status(
    agent_name: str,
    request: AdminAgentUpdateRequest,
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Owner control to toggle an AI agent's operational status, model tier, or permissions."""
    await agent_registry._ensure_db_registry(session)
    res = await session.execute(select(AgentRegistry).where(AgentRegistry.name == agent_name))
    agent_row = res.scalar_one_or_none()
    if not agent_row:
        raise ResourceNotFoundError("AgentRegistry", agent_name)

    if request.active is not None:
        agent_row.active = request.active
    cfg = dict(agent_row.configuration or {})
    if request.tier is not None:
        cfg["tier"] = request.tier
    if request.allowed_tools is not None:
        cfg["allowed_tools"] = request.allowed_tools
    agent_row.configuration = cfg

    session.add(
        AuditLog(
            actor_id=admin_user.id,
            actor_type="admin",
            action="admin.agent.updated",
            resource_type="agent_registry",
            resource_id=agent_row.id,
            metadata_={"agent_name": agent_name, "active": agent_row.active},
        )
    )
    await session.commit()
    return {
        "success": True,
        "data": {
            "name": agent_row.name,
            "active": agent_row.active,
            "configuration": agent_row.configuration,
        },
    }


@router.post("/approvals/{approval_id}/review")
async def admin_review_approval(
    approval_id: uuid.UUID,
    request: AdminApprovalReviewRequest,
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Owner control to approve or reject any pending human approval request across tenants."""
    res = await session.execute(select(Approval).where(Approval.id == approval_id))
    approval = res.scalar_one_or_none()
    if not approval:
        raise ResourceNotFoundError("Approval", str(approval_id))

    reviewed = await approval_manager.resolve_approval(
        session=session,
        tenant_id=approval.tenant_id,
        approval_id=approval_id,
        reviewer_id=admin_user.id,
        approved=(request.decision == "approved"),
        reason=request.reason,
    )
    return {"success": True, "data": reviewed.model_dump(mode="json")}


@router.post("/tenants/{tenant_id}/run-lead-gen")
async def admin_trigger_tenant_lead_generation(
    tenant_id: uuid.UUID,
    request: LeadGenerationRequest,
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Owner control to run backend-managed Lead Generation for a specific client tenant."""
    data = await marketing_service.generate_leads_from_google_maps(
        session=session,
        tenant_id=tenant_id,
        user_id=admin_user.id,
        request=request,
    )
    return {"success": True, "data": data}


@router.post("/tenants/{tenant_id}/leads/{lead_id}/qualify")
async def admin_qualify_tenant_lead(
    tenant_id: uuid.UUID,
    lead_id: uuid.UUID,
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Owner-only control to AI-score and qualify a client's lead so scored results show on client dashboard."""
    lead = await marketing_service.qualify_lead(
        session=session,
        tenant_id=tenant_id,
        lead_id=lead_id,
    )
    return {"success": True, "data": lead.model_dump(mode="json")}


@router.post("/integrations/{integration_id}/action")
async def admin_manage_integration(
    integration_id: uuid.UUID,
    request: AdminIntegrationActionRequest,
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Owner control to revoke, reconnect, test, or approve a client integration without exposing secrets."""
    from app.services.integration_service import integration_service

    res = await session.execute(select(Integration).where(Integration.id == integration_id))
    integ = res.scalar_one_or_none()
    if not integ:
        raise ResourceNotFoundError("Integration", str(integration_id))

    if request.action == "test":
        tested = await integration_service.test_integration_connection(
            session=session,
            tenant_id=integ.tenant_id,
            user_id=admin_user.id,
            integration_id=integ.id,
        )
        return {
            "success": tested["status"] == "connected",
            "data": {
                "id": tested["id"],
                "provider": tested["provider"],
                "status": tested["status"],
                "configuration": tested["configuration"],
            },
        }

    if request.action == "revoke":
        integ.status = "disconnected"
        integ.configuration = {"revoked_by_owner": True, "admin_approved": False}
    elif request.action == "approve":
        integ.status = "connected"
        cfg = dict(integ.configuration or {})
        cfg["admin_approved"] = True
        cfg["approved_by"] = str(admin_user.id)
        integ.configuration = cfg
    elif request.action == "reconnect":
        integ.status = "connected"
        cfg = dict(integ.configuration or {})
        cfg["connection_tested"] = True
        cfg["last_test_result"] = "verified_by_owner"
        cfg["admin_approved"] = True
        integ.configuration = cfg

    session.add(
        AuditLog(
            tenant_id=integ.tenant_id,
            actor_id=admin_user.id,
            actor_type="admin",
            action=f"admin.integration.{request.action}",
            resource_type="integration",
            resource_id=integ.id,
            metadata_={"provider": integ.provider, "status": integ.status},
        )
    )
    await session.commit()
    await integration_service._sync_tenant_onboarding_state(session, integ.tenant_id)
    return {
        "success": True,
        "data": {
            "id": str(integ.id),
            "provider": integ.provider,
            "status": integ.status,
            "configuration": mask_sensitive_config(integ.configuration or {}),
        },
    }


@router.get("/tenants/{tenant_id}/integrations/oauth-url")
async def get_tenant_oauth_url(
    tenant_id: uuid.UUID,
    provider: str,
    return_to: str = "/admin",
    admin_user: Profile = Depends(verify_platform_admin),
):
    """Retrieve official OAuth authorization URL for a specific client integration."""
    from app.services.integration_service import integration_service

    provider_key = "booking_provider" if provider.lower() == "booking" else provider.lower()
    callback_uri = f"{settings.backend_url.rstrip('/')}/api/v1/integrations/oauth/{provider_key}/callback"
    info = integration_service.get_oauth_authorization_info(
        provider=provider_key,
        tenant_id=tenant_id,
        user_id=admin_user.id,
        return_to=return_to,
        custom_redirect_uri=callback_uri,
    )
    return {"success": True, "data": info}


@router.post("/tenants/{tenant_id}/integrations/connect")
async def admin_connect_tenant_integration(
    tenant_id: uuid.UUID,
    request: AdminConnectIntegrationRequest,
    admin_user: Profile = Depends(verify_platform_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin link or approve an integration for a client workspace."""
    from app.services.integration_service import integration_service

    provider_clean = "booking_provider" if request.provider.lower() == "booking" else request.provider.lower()
    query = select(Integration).where(
        Integration.tenant_id == tenant_id,
        Integration.provider == provider_clean,
    )
    res = await session.execute(query)
    integ = res.scalar_one_or_none()

    extra_cfg: Dict[str, Any] = encrypt_sensitive_config(dict(request.configuration or {}))
    if request.api_key:
        extra_cfg["api_key"] = encrypt_secret(request.api_key)
    if request.oauth_code:
        extra_cfg["oauth_code"] = encrypt_secret(request.oauth_code)

    if integ:
        integ.status = request.status
        if request.account_identifier:
            integ.external_account_id = request.account_identifier
        cfg = dict(integ.configuration or {})
        cfg.update(extra_cfg)
        cfg["admin_approved"] = True
        cfg["linked_by"] = str(admin_user.id)
        integ.configuration = cfg
    else:
        integ = Integration(
            tenant_id=tenant_id,
            provider=provider_clean,
            integration_type=(
                "oauth"
                if provider_clean in ("gmail", "google_calendar", "whatsapp", "google_business")
                else "api_key"
            ),
            status=request.status,
            external_account_id=request.account_identifier or f"{provider_clean}_managed",
            configuration={"admin_approved": True, "linked_by": str(admin_user.id), **extra_cfg},
        )
        session.add(integ)

    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_id=admin_user.id,
            actor_type="admin",
            action=f"admin.integration.{provider_clean}.connected",
            resource_type="integration",
            resource_id=integ.id,
            metadata_={"provider": provider_clean, "status": integ.status, "account": request.account_identifier},
        )
    )
    await session.commit()
    await integration_service._sync_tenant_onboarding_state(session, tenant_id)
    return {
        "success": True,
        "data": {
            "id": str(integ.id),
            "tenant_id": str(tenant_id),
            "provider": integ.provider,
            "status": integ.status,
            "external_account_id": integ.external_account_id,
        },
        "message": f"Integration '{provider_clean}' successfully connected and approved.",
    }
