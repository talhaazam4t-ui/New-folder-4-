"""Reusable opaque-box E2E API factories and controlled state helpers for TALOXTECH."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.config import settings
from app.database.models.agent import TenantAgent
from app.database.models.automation import Approval, Integration
from app.database.models.service import ServiceSubscription
from app.database.models.tenant import Tenant
from app.database.supabase import get_session_factory
from httpx import AsyncClient
from sqlalchemy import select

CANONICAL_SERVICE_SLUGS: tuple[str, ...] = (
    "business-financial-tracking",
    "ai-marketing-growth",
    "whatsapp-business-concierge",
    "multi-agent-orchestration",
    "lead-crm-qualification",
    "executive-analytics-compliance",
)

CANONICAL_MODULE_FLAGS: tuple[str, ...] = (
    "financial_ledger",
    "marketing_growth",
    "whatsapp_concierge",
    "multi_agent_orchestration",
    "lead_crm",
    "executive_analytics_compliance",
)


async def register_and_login(
    client: AsyncClient,
    *,
    email: Optional[str] = None,
    password: str = "SecurePass123!",
    full_name: str = "E2E Client User",
    phone: Optional[str] = "+923001112233",
) -> Dict[str, Any]:
    """Register (or login if already present) and return token, user_id, and auth headers."""
    resolved_email = (email or f"user_{uuid.uuid4().hex[:10]}@example.com").strip().lower()
    reg_payload: Dict[str, Any] = {
        "email": resolved_email,
        "password": password,
        "full_name": full_name,
    }
    if phone is not None:
        reg_payload["phone"] = phone

    res = await client.post("/api/v1/auth/register", json=reg_payload)
    if res.status_code == 409:
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": resolved_email, "password": password},
        )
    assert res.status_code in (200, 201), f"Auth failed ({res.status_code}): {res.text}"
    body = res.json()
    return {
        "token": body["access_token"],
        "user_id": body["user_id"],
        "email": body["email"],
        "full_name": body["full_name"],
        "is_super_admin": body["is_super_admin"],
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
    }


async def create_tenant(
    client: AsyncClient,
    auth_headers: Dict[str, str],
    *,
    name: str = "E2E Workspace",
    slug: Optional[str] = None,
    industry: str = "Financing",
    settings_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a tenant workspace and return its JSON payload plus tenant-scoped headers."""
    resolved_slug = slug or f"ws-{uuid.uuid4().hex[:10]}"
    payload: Dict[str, Any] = {
        "name": name,
        "slug": resolved_slug,
        "industry": industry,
    }
    if settings_override is not None:
        payload["settings"] = settings_override

    res = await client.post("/api/v1/tenants", json=payload, headers=auth_headers)
    assert res.status_code == 201, f"Create tenant failed ({res.status_code}): {res.text}"
    tenant = res.json()
    tenant["headers"] = {**auth_headers, "X-Tenant-ID": tenant["id"]}
    return tenant


async def subscribe_service(
    client: AsyncClient,
    tenant_headers: Dict[str, str],
    service_slug: str,
    *,
    plan_name: str = "growth",
    billing_interval: str = "monthly",
    price: Optional[float] = None,
) -> Dict[str, Any]:
    """Discover a canonical service by slug and subscribe the tenant to it."""
    catalog_res = await client.get("/api/v1/services", params={"ensure_seeded": "true"})
    assert catalog_res.status_code == 200, f"Catalog fetch failed: {catalog_res.text}"
    services = catalog_res.json()
    match = next((s for s in services if s["slug"] == service_slug), None)
    assert match is not None, f"Service slug '{service_slug}' not found in catalog"

    resolved_price = price
    if resolved_price is None:
        packages = (match.get("configuration_schema") or {}).get("packages") or []
        pkg = next((p for p in packages if p.get("tier") == plan_name), None)
        resolved_price = float(pkg["price"]) if pkg and pkg.get("price") is not None else 199.0

    sub_res = await client.post(
        "/api/v1/services/subscribe",
        json={
            "service_id": match["id"],
            "plan_name": plan_name,
            "billing_interval": billing_interval,
            "price": resolved_price,
        },
        headers=tenant_headers,
    )
    assert sub_res.status_code == 201, f"Subscribe failed ({sub_res.status_code}): {sub_res.text}"
    return sub_res.json()


async def approve_tenant_payment(
    client: AsyncClient,
    admin_headers: Dict[str, str],
    tenant_id: str,
    *,
    notes: str = "Verified in E2E suite",
) -> Dict[str, Any]:
    """Approve a tenant's bank transfer payment via the Super Admin endpoint."""
    res = await client.post(
        f"/api/v1/admin/tenants/{tenant_id}/approve-payment",
        json={"notes": notes},
        headers=admin_headers,
    )
    assert res.status_code == 200, f"Approve payment failed ({res.status_code}): {res.text}"
    return res.json()


async def onboard_paid_tenant(
    client: AsyncClient,
    admin_headers: Dict[str, str],
    *,
    service_slugs: Iterable[str],
    industry: str = "Financing",
    owner_email: Optional[str] = None,
    owner_name: str = "Workspace Owner",
    tenant_name: str = "Acme SaaS Client",
    tenant_slug: Optional[str] = None,
    plan_name: str = "growth",
    connect_integrations: Iterable[str] = (),
) -> Dict[str, Any]:
    """Full opaque-box client onboarding: register -> tenant -> subscribe -> pay notify -> admin approve."""
    owner = await register_and_login(
        client,
        email=owner_email,
        full_name=owner_name,
    )
    tenant = await create_tenant(
        client,
        owner["headers"],
        name=tenant_name,
        slug=tenant_slug,
        industry=industry,
    )
    tenant_headers = tenant["headers"]

    subscriptions: List[Dict[str, Any]] = []
    total_price = 0.0
    for slug in service_slugs:
        sub = await subscribe_service(client, tenant_headers, slug, plan_name=plan_name)
        subscriptions.append(sub)
        total_price += float(sub.get("price", 0.0))

    notify_res = await client.post(
        "/api/v1/payments/bank-transfer/notify",
        json={
            "transaction_reference": f"BANK-{uuid.uuid4().hex[:8].upper()}",
            "amount": max(total_price, 99.0),
            "notes": "E2E automated bank transfer notification",
        },
        headers=tenant_headers,
    )
    assert notify_res.status_code == 200, f"Bank notify failed: {notify_res.text}"

    approval_result = await approve_tenant_payment(client, admin_headers, tenant["id"])

    integrations: Dict[str, Any] = {}
    for provider in connect_integrations:
        if provider == "whatsapp":
            conn_res = await client.post(
                "/api/v1/integrations/whatsapp/connect",
                json={"oauth_code": f"wa_oauth_{uuid.uuid4().hex[:8]}"},
                headers=tenant_headers,
            )
        elif provider == "booking_provider":
            conn_res = await client.post(
                "/api/v1/integrations/booking_provider/connect",
                json={
                    "api_key": f"bk_live_{uuid.uuid4().hex[:10]}",
                    "account_identifier": f"cal-{tenant['slug']}",
                },
                headers=tenant_headers,
            )
        else:
            conn_res = await client.post(
                f"/api/v1/integrations/{provider}/connect",
                json={
                    "oauth_code": f"oauth_{provider}_{uuid.uuid4().hex[:8]}",
                    "account_identifier": f"{provider}-{tenant['slug']}@example.com",
                },
                headers=tenant_headers,
            )
        assert conn_res.status_code == 201, f"Connect {provider} failed: {conn_res.text}"
        integrations[provider] = conn_res.json()["data"]

    return {
        "owner": owner,
        "tenant": tenant,
        "tenant_id": tenant["id"],
        "headers": tenant_headers,
        "subscriptions": subscriptions,
        "approval": approval_result,
        "integrations": integrations,
    }


async def invite_member_and_login(
    client: AsyncClient,
    owner_headers: Dict[str, str],
    tenant_id: str,
    *,
    role: str,
    email: Optional[str] = None,
    full_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Register a user, invite them to a tenant with the given role, and return tenant-scoped headers."""
    member_email = (email or f"{role}_{uuid.uuid4().hex[:8]}@example.com").strip().lower()
    member_auth = await register_and_login(
        client,
        email=member_email,
        full_name=full_name or f"{role.title()} Member",
    )
    invite_res = await client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        json={"email": member_email, "role": role},
        headers=owner_headers,
    )
    assert invite_res.status_code == 201, f"Invite {role} failed ({invite_res.status_code}): {invite_res.text}"
    member_auth["headers"] = {**member_auth["headers"], "X-Tenant-ID": tenant_id}
    return member_auth


async def set_subscription_expires_at(subscription_id: str, expires_at: datetime) -> None:
    """Backdate or adjust a subscription's expires_at timestamp to test expiry gating."""
    session_maker = get_session_factory()
    async with session_maker() as session:
        res = await session.execute(
            select(ServiceSubscription).where(ServiceSubscription.id == uuid.UUID(subscription_id))
        )
        sub = res.scalar_one()
        sub.expires_at = expires_at
        await session.commit()


async def set_approval_expires_at(approval_id: str, expires_at: datetime) -> None:
    """Backdate an Approval's expires_at timestamp to test APPROVAL_EXPIRED handling."""
    session_maker = get_session_factory()
    async with session_maker() as session:
        res = await session.execute(select(Approval).where(Approval.id == uuid.UUID(approval_id)))
        approval = res.scalar_one()
        approval.expires_at = expires_at
        await session.commit()


async def set_tenant_status(tenant_id: str, status_value: str) -> None:
    """Update tenant status directly (e.g. 'suspended') for boundary tests."""
    session_maker = get_session_factory()
    async with session_maker() as session:
        res = await session.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
        tenant = res.scalar_one()
        tenant.status = status_value
        await session.commit()


async def get_raw_integration_config(tenant_id: str, provider: str) -> Dict[str, Any]:
    """Read raw Integration.configuration JSON from SQLite to verify enc:v1: encryption at rest."""
    session_maker = get_session_factory()
    async with session_maker() as session:
        res = await session.execute(
            select(Integration).where(
                Integration.tenant_id == uuid.UUID(tenant_id),
                Integration.provider == provider,
            )
        )
        integ = res.scalar_one()
        return dict(integ.configuration or {})


async def get_tenant_agent_row(tenant_id: str, agent_name: str) -> Optional[TenantAgent]:
    """Inspect TenantAgent row for limit/enablement verification."""
    session_maker = get_session_factory()
    async with session_maker() as session:
        res = await session.execute(
            select(TenantAgent).where(
                TenantAgent.tenant_id == uuid.UUID(tenant_id),
                TenantAgent.agent_name == agent_name,
            )
        )
        return res.scalar_one_or_none()


__all__ = [
    "CANONICAL_MODULE_FLAGS",
    "CANONICAL_SERVICE_SLUGS",
    "approve_tenant_payment",
    "create_tenant",
    "datetime",
    "get_raw_integration_config",
    "get_tenant_agent_row",
    "invite_member_and_login",
    "onboard_paid_tenant",
    "register_and_login",
    "set_approval_expires_at",
    "set_subscription_expires_at",
    "set_tenant_status",
    "settings",
    "subscribe_service",
    "timedelta",
    "timezone",
]
