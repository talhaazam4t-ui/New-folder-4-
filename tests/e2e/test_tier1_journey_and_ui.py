"""Tier 1 E2E Tests — F1: Client Journey, Auth, Onboarding, Multi-Service, Support & Static UI."""

from __future__ import annotations

import re
import uuid

from e2e_helpers import (
    CANONICAL_SERVICE_SLUGS,
    approve_tenant_payment,
    create_tenant,
    register_and_login,
    subscribe_service,
)
from httpx import AsyncClient


async def test_register_login_and_auth_me_roundtrip(async_client: AsyncClient) -> None:
    email = f"client_{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPassword123!",
            "full_name": "Sara Khan",
            "phone": "+923001234567",
        },
    )
    assert reg.status_code == 201, reg.text
    reg_data = reg.json()
    assert reg_data["email"] == email
    assert reg_data["is_super_admin"] is False
    assert reg_data["access_token"]

    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPassword123!"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200, me.text
    me_data = me.json()
    assert me_data["email"] == email
    assert me_data["full_name"] == "Sara Khan"
    assert me_data["is_super_admin"] is False


async def test_tenant_creation_pending_approval_and_listing(async_client: AsyncClient) -> None:
    owner = await register_and_login(async_client, full_name="Workspace Creator")
    tenant = await create_tenant(
        async_client,
        owner["headers"],
        name="Alpha Properties",
        industry="Real Estate / Property",
    )
    assert tenant["status"] == "pending_approval"
    assert tenant["role"] == "owner"
    assert tenant["industry"] == "Real Estate / Property"

    list_res = await async_client.get("/api/v1/tenants", headers=owner["headers"])
    assert list_res.status_code == 200, list_res.text
    tenants = list_res.json()
    assert any(t["id"] == tenant["id"] for t in tenants)

    get_res = await async_client.get(f"/api/v1/tenants/{tenant['id']}", headers=owner["headers"])
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["slug"] == tenant["slug"]


async def test_service_catalog_industries_and_canonical_six_services(async_client: AsyncClient) -> None:
    ind_res = await async_client.get("/api/v1/services/industries")
    assert ind_res.status_code == 200, ind_res.text
    ind_body = ind_res.json()
    assert ind_body["success"] is True
    assert set(ind_body["industries"]) == {
        "Financing",
        "Clinics / Hospitals",
        "Real Estate / Property",
        "E-Commerce",
    }

    catalog_res = await async_client.get("/api/v1/services", params={"ensure_seeded": "true"})
    assert catalog_res.status_code == 200, catalog_res.text
    services = catalog_res.json()
    slugs = [s["slug"] for s in services]
    assert set(slugs) == set(CANONICAL_SERVICE_SLUGS), (
        f"Expected exactly canonical 6 packaged services, got: {slugs}"
    )


async def test_multi_service_subscription_bank_transfer_and_admin_approval(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    owner = await register_and_login(async_client, full_name="Multi Service Client")
    tenant = await create_tenant(
        async_client,
        owner["headers"],
        name="MultiService Corp",
        industry="Financing",
    )
    headers = tenant["headers"]

    sub1 = await subscribe_service(async_client, headers, "business-financial-tracking", plan_name="growth")
    sub2 = await subscribe_service(async_client, headers, "ai-marketing-growth", plan_name="starter")
    assert sub1["service_slug"] == "business-financial-tracking"
    assert sub2["service_slug"] == "ai-marketing-growth"

    bank_res = await async_client.get("/api/v1/payments/bank-details")
    assert bank_res.status_code == 200
    assert bank_res.json()["success"] is True

    notify_res = await async_client.post(
        "/api/v1/payments/bank-transfer/notify",
        json={
            "transaction_reference": "TXN-MULTI-001",
            "amount": sub1["price"] + sub2["price"],
            "notes": "Paid for two services",
        },
        headers=headers,
    )
    assert notify_res.status_code == 200, notify_res.text
    assert notify_res.json()["status"] == "pending_verification"

    pre_overview = await async_client.get(f"/api/v1/tenants/{tenant['id']}/overview", headers=headers)
    assert pre_overview.status_code == 200
    assert pre_overview.json()["data"]["is_payment_approved"] is False
    assert pre_overview.json()["data"]["enabled_modules"] == []

    await approve_tenant_payment(async_client, super_admin_headers, tenant["id"])

    post_overview = await async_client.get(f"/api/v1/tenants/{tenant['id']}/overview", headers=headers)
    assert post_overview.status_code == 200, post_overview.text
    data = post_overview.json()["data"]
    assert data["is_payment_approved"] is True
    assert data["automation_active"] is True
    assert set(data["enabled_modules"]) == {"financial_ledger", "marketing_growth"}


async def test_subscription_cancellation_lifecycle(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    owner = await register_and_login(async_client, full_name="Cancel Sub Owner")
    tenant = await create_tenant(async_client, owner["headers"], name="CancelCo", industry="E-Commerce")
    sub = await subscribe_service(async_client, tenant["headers"], "ai-marketing-growth")
    await approve_tenant_payment(async_client, super_admin_headers, tenant["id"])

    cancel_res = await async_client.post(
        f"/api/v1/services/subscriptions/{sub['id']}/cancel",
        headers=tenant["headers"],
    )
    assert cancel_res.status_code == 200, cancel_res.text
    assert cancel_res.json()["success"] is True

    subs_res = await async_client.get("/api/v1/services/subscriptions", headers=tenant["headers"])
    assert subs_res.status_code == 200
    matching = [s for s in subs_res.json() if s["id"] == sub["id"]]
    assert len(matching) == 1
    assert matching[0]["status"] in ("canceled", "cancelled")


async def test_support_request_create_and_list_contract(
    async_client: AsyncClient,
) -> None:
    owner = await register_and_login(async_client, full_name="Support Seeker")
    tenant = await create_tenant(async_client, owner["headers"], name="SupportCo", industry="Clinics / Hospitals")

    create_res = await async_client.post(
        "/api/v1/support/requests",
        json={
            "subject": "Need help connecting WhatsApp Business number",
            "message": "Please guide our clinic staff on Meta Embedded Signup.",
            "category": "onboarding",
            "priority": "high",
        },
        headers=tenant["headers"],
    )
    assert create_res.status_code in (200, 201), create_res.text
    created = create_res.json()
    assert created.get("success") is True
    payload_str = str(created)
    assert "03238300330" in payload_str or "923238300330" in payload_str

    list_res = await async_client.get("/api/v1/support/requests", headers=tenant["headers"])
    assert list_res.status_code == 200, list_res.text
    list_body = list_res.json()
    items = list_body["data"] if isinstance(list_body, dict) and "data" in list_body else list_body
    assert isinstance(items, list) and len(items) >= 1
    assert any("WhatsApp" in str(item) for item in items)


async def test_static_frontend_out_html_routes_and_next_assets(async_client: AsyncClient) -> None:
    expected_routes = [
        "/",
        "/login/",
        "/register/",
        "/onboarding/",
        "/dashboard/",
        "/billing/",
        "/finance/",
        "/business/",
        "/marketing/",
        "/settings/",
        "/admin/",
        "/agents/",
    ]
    discovered_asset_path: str | None = None
    for route in expected_routes:
        res = await async_client.get(route)
        assert res.status_code == 200, f"Static route {route} returned {res.status_code}"
        assert "text/html" in res.headers.get("content-type", "")
        assert "<html" in res.text.lower()
        if not discovered_asset_path:
            match = re.search(r"/_next/static/[^\"'\s>]+\.(?:js|css)", res.text)
            if match:
                discovered_asset_path = match.group(0)

    assert discovered_asset_path is not None, "No /_next/static/* asset reference found in exported HTML"
    asset_res = await async_client.get(discovered_asset_path)
    assert asset_res.status_code == 200, f"Asset {discovered_asset_path} failed: {asset_res.status_code}"


async def test_static_frontend_404_and_no_localhost_8000_leakage(async_client: AsyncClient) -> None:
    missing_route = await async_client.get("/definitely-unknown-e2e-route")
    assert missing_route.status_code == 404

    missing_asset = await async_client.get("/nonexistent-asset-e2e.png")
    assert missing_asset.status_code == 404

    missing_api = await async_client.get("/api/v1/nonexistent-endpoint-e2e")
    assert missing_api.status_code == 404
    assert missing_api.json()["success"] is False

    for route in ("/", "/login/", "/register/", "/dashboard/", "/finance/", "/marketing/"):
        html_res = await async_client.get(route)
        assert html_res.status_code == 200
        assert "http://localhost:8000" not in html_res.text


async def test_public_sales_chatbot_message_and_onboarding_transition(async_client: AsyncClient) -> None:
    res = await async_client.post(
        "/api/v1/marketing/chatbot/message",
        json={
            "message": "We run a real estate agency and want WhatsApp automation and rent tracking",
            "visitor_name": "Bilal",
            "visitor_phone": "+923009876543",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["reply"]
    assert body["whatsapp_url"]
