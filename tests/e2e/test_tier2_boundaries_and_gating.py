"""Tier 2 E2E Tests — Boundaries, Gating, Cross-Tenant Isolation, RBAC & Error States (F1–F7)."""

from __future__ import annotations

import hashlib
import hmac
import json

from e2e_helpers import (
    CANONICAL_SERVICE_SLUGS,
    create_tenant,
    datetime,
    invite_member_and_login,
    onboard_paid_tenant,
    register_and_login,
    set_approval_expires_at,
    set_subscription_expires_at,
    set_tenant_status,
    settings,
    subscribe_service,
    timedelta,
    timezone,
)
from httpx import AsyncClient


def _error_code(response_json: dict) -> str:
    return str((response_json.get("error") or {}).get("code") or "")


# =============================================================================
# F1 & Global Subscription / Payment / Auth / OAuth Gating (8 tests)
# =============================================================================


async def test_b1_unsubscribed_tenant_blocked_403_subscription_required(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=[],
        industry="Financing",
    )
    headers = ctx["headers"]

    targets = [
        ("GET", "/api/v1/finance/accounts", None),
        ("POST", "/api/v1/business/records", {"record_type": "income", "title": "Test", "amount": 10.0}),
        ("POST", "/api/v1/marketing/campaigns", {"name": "C1", "platform": "meta_ads", "objective": "leads", "budget": 50.0}),
        ("POST", "/api/v1/integrations/whatsapp/simulate", {"sender_phone": "+923001112233", "message_text": "Hi"}),
        ("POST", "/api/v1/agents/orchestrate", {"objective": "Test objective", "agent_name": "planner_agent"}),
        ("POST", "/api/v1/marketing/leads", {"name": "Lead A", "phone": "+923001112233"}),
        ("GET", "/api/v1/analytics/overview", None),
    ]
    for method, url, payload in targets:
        res = await async_client.request(method, url, json=payload, headers=headers)
        assert res.status_code == 403, f"Expected 403 on {method} {url}, got {res.status_code}: {res.text}"
        assert _error_code(res.json()) == "SUBSCRIPTION_REQUIRED", (
            f"Expected SUBSCRIPTION_REQUIRED on {method} {url}, got {res.json()}"
        )


async def test_b2_unpaid_tenant_blocked_403_payment_pending(
    async_client: AsyncClient,
) -> None:
    owner = await register_and_login(async_client, full_name="Unpaid Owner")
    tenant = await create_tenant(async_client, owner["headers"], name="UnpaidCo", industry="Financing")
    headers = tenant["headers"]
    for slug in CANONICAL_SERVICE_SLUGS:
        await subscribe_service(async_client, headers, slug)

    overview = await async_client.get(f"/api/v1/tenants/{tenant['id']}/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["data"]["is_payment_approved"] is False
    assert overview.json()["data"]["enabled_modules"] == []

    targets = [
        ("GET", "/api/v1/finance/accounts", None),
        ("POST", "/api/v1/business/records", {"record_type": "income", "title": "Unpaid", "amount": 50.0}),
        ("POST", "/api/v1/marketing/campaigns", {"name": "Unpaid", "platform": "meta_ads", "objective": "leads", "budget": 10.0}),
        ("POST", "/api/v1/integrations/whatsapp/simulate", {"sender_phone": "+923001112233", "message_text": "Hi"}),
        ("POST", "/api/v1/agents/orchestrate", {"objective": "Unpaid run", "agent_name": "planner_agent"}),
        ("POST", "/api/v1/marketing/leads", {"name": "Unpaid Lead"}),
        ("GET", "/api/v1/analytics/overview", None),
    ]
    for method, url, payload in targets:
        res = await async_client.request(method, url, json=payload, headers=headers)
        assert res.status_code == 403, f"Expected 403 PAYMENT_PENDING on {method} {url}, got {res.status_code}"
        assert _error_code(res.json()) == "PAYMENT_PENDING", (
            f"Expected PAYMENT_PENDING on {method} {url}, got {res.json()}"
        )


async def test_b3_expired_subscription_blocked_403(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["business-financial-tracking", "ai-marketing-growth"],
        industry="Financing",
    )
    for sub in ctx["subscriptions"]:
        await set_subscription_expires_at(sub["id"], datetime.now(timezone.utc) - timedelta(days=2))

    fin_res = await async_client.get("/api/v1/finance/accounts", headers=ctx["headers"])
    assert fin_res.status_code == 403, fin_res.text
    assert _error_code(fin_res.json()) == "SUBSCRIPTION_REQUIRED"

    mkt_res = await async_client.get("/api/v1/marketing/campaigns", headers=ctx["headers"])
    assert mkt_res.status_code == 403, mkt_res.text
    assert _error_code(mkt_res.json()) == "SUBSCRIPTION_REQUIRED"


async def test_b4_single_service_subscription_isolates_unsubscribed_services(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["business-financial-tracking"],
        industry="Financing",
    )
    headers = ctx["headers"]

    fin_ok = await async_client.get("/api/v1/finance/accounts", headers=headers)
    assert fin_ok.status_code == 200

    for method, url, payload in (
        ("GET", "/api/v1/marketing/campaigns", None),
        ("POST", "/api/v1/integrations/whatsapp/simulate", {"sender_phone": "+923001112233", "message_text": "Hi"}),
        ("GET", "/api/v1/agents", None),
        ("GET", "/api/v1/marketing/leads", None),
        ("GET", "/api/v1/analytics/overview", None),
    ):
        res = await async_client.request(method, url, json=payload, headers=headers)
        assert res.status_code == 403, f"Expected 403 on unsubscribed {method} {url}, got {res.status_code}"
        assert _error_code(res.json()) == "SUBSCRIPTION_REQUIRED"


async def test_b5_non_admin_patch_subscription_status_active_bypass_blocked(
    async_client: AsyncClient,
) -> None:
    owner = await register_and_login(async_client, full_name="Bypass Attacker")
    tenant = await create_tenant(async_client, owner["headers"], name="BypassCo", industry="Financing")
    sub = await subscribe_service(async_client, tenant["headers"], "business-financial-tracking")

    # Simulate paused/pending subscription then try self-activating via PATCH /subscriptions/{id}
    patch_res = await async_client.patch(
        f"/api/v1/subscriptions/{sub['id']}",
        json={"status": "active"},
        headers=tenant["headers"],
    )
    assert patch_res.status_code == 403, (
        f"Non-admin tenant owner must NOT be able to set subscription status='active', got {patch_res.status_code}: {patch_res.text}"
    )


async def test_b6_invalid_jwt_and_missing_tenant_header(async_client: AsyncClient) -> None:
    no_auth = await async_client.get("/api/v1/auth/me")
    assert no_auth.status_code == 401
    assert _error_code(no_auth.json()) == "AUTHENTICATION_REQUIRED"

    bad_auth = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert bad_auth.status_code == 401

    owner = await register_and_login(async_client)
    no_tenant = await async_client.get("/api/v1/finance/status", headers=owner["headers"])
    assert no_tenant.status_code == 400
    assert _error_code(no_tenant.json()) == "TENANT_HEADER_REQUIRED"

    bad_uuid = await async_client.get(
        "/api/v1/finance/status",
        headers={**owner["headers"], "X-Tenant-ID": "invalid-uuid"},
    )
    assert bad_uuid.status_code == 400
    assert _error_code(bad_uuid.json()) == "INVALID_TENANT_ID"


async def test_b7_oauth_authorize_unconfigured_returns_400_oauth_not_configured(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["whatsapp-business-concierge"],
        industry="Clinics / Hospitals",
    )
    for provider in ("whatsapp", "gmail", "google_calendar"):
        res = await async_client.get(
            f"/api/v1/integrations/oauth/{provider}/authorize",
            headers=ctx["headers"],
        )
        assert res.status_code == 400, f"{provider} expected 400 OAUTH_NOT_CONFIGURED, got {res.status_code}"
        assert _error_code(res.json()) == "OAUTH_NOT_CONFIGURED"


async def test_b8_invalid_oauth_state_rejected_in_production_mode(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["whatsapp-business-concierge"],
        industry="Clinics / Hospitals",
    )
    prev_env = settings.app_env
    try:
        settings.app_env = "production"
        for forged_state in ("mock", "test", "talox_forged_state", "oauth_state_123"):
            res = await async_client.post(
                "/api/v1/integrations/oauth/callback",
                json={"code": "some_code", "state": forged_state},
                headers=ctx["headers"],
            )
            assert res.status_code == 400, (
                f"Forged state '{forged_state}' in production must fail with 400, got {res.status_code}: {res.text}"
            )
            assert _error_code(res.json()) == "INVALID_OAUTH_STATE"
    finally:
        settings.app_env = prev_env


# =============================================================================
# F2: Service 1 (business-financial-tracking) Boundaries (6 tests)
# =============================================================================


async def test_b9_finance_cross_tenant_account_id_ownership_rejected(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    tenant_a = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["business-financial-tracking"],
        tenant_name="Tenant A",
    )
    tenant_b = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["business-financial-tracking"],
        tenant_name="Tenant B",
    )
    acc_a = (
        await async_client.post(
            "/api/v1/finance/accounts",
            json={"name": "A Bank", "currency": "USD", "current_balance": 500.0},
            headers=tenant_a["headers"],
        )
    ).json()

    tx_res = await async_client.post(
        "/api/v1/finance/transactions",
        json={
            "account_id": acc_a["id"],
            "type": "income",
            "category": "Hijack Test",
            "amount": 100.0,
            "currency": "USD",
            "status": "paid",
            "counterparty_name": "Evil Actor",
        },
        headers=tenant_b["headers"],
    )
    assert tx_res.status_code in (403, 404), (
        f"Tenant B must NOT attach Tenant A's account_id to a transaction, got {tx_res.status_code}"
    )

    acc_a_after = (await async_client.get("/api/v1/finance/accounts", headers=tenant_a["headers"])).json()
    assert acc_a_after[0]["current_balance"] == 500.0


async def test_b10_finance_mixed_currency_summary_isolates_usd_and_pkr(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["business-financial-tracking"],
        industry="Real Estate / Property",
    )
    headers = ctx["headers"]

    usd_acc = (
        await async_client.post(
            "/api/v1/finance/accounts",
            json={"name": "USD Bank", "currency": "USD", "current_balance": 100.0},
            headers=headers,
        )
    ).json()
    pkr_acc = (
        await async_client.post(
            "/api/v1/finance/accounts",
            json={"name": "PKR Bank", "currency": "PKR", "current_balance": 50000.0},
            headers=headers,
        )
    ).json()

    await async_client.post(
        "/api/v1/finance/transactions",
        json={
            "account_id": usd_acc["id"],
            "type": "income",
            "category": "Retainer",
            "amount": 200.0,
            "currency": "USD",
            "status": "paid",
            "counterparty_name": "US Client",
        },
        headers=headers,
    )
    await async_client.post(
        "/api/v1/finance/transactions",
        json={
            "account_id": pkr_acc["id"],
            "type": "rent",
            "category": "Rent",
            "amount": 40000.0,
            "currency": "PKR",
            "status": "paid",
            "counterparty_name": "Local Lessee",
        },
        headers=headers,
    )

    summary = (
        await async_client.get("/api/v1/finance/summary", params={"currency": "USD"}, headers=headers)
    ).json()
    assert summary["currency"] == "USD"
    assert summary["total_cash_balance"] == 300.0, (
        f"USD total_cash_balance must NOT sum PKR 90000 directly! Got {summary['total_cash_balance']}"
    )
    assert summary["monthly_revenue"] == 200.0, (
        f"USD monthly_revenue must NOT sum PKR 40000 directly! Got {summary['monthly_revenue']}"
    )
    assert summary["currency_balances"]["USD"] == 300.0
    assert summary["currency_balances"]["PKR"] == 90000.0


async def test_b11_finance_rent_reminder_same_day_deduplication(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["business-financial-tracking"],
        industry="Real Estate / Property",
        connect_integrations=["whatsapp"],
    )
    headers = ctx["headers"]

    from datetime import date

    safe_day = min(date.today().day, 28)
    await async_client.post(
        "/api/v1/finance/rent-schedules",
        json={
            "property_unit": "Unit 7C",
            "lessee_name": "Dedup Lessee",
            "lessee_whatsapp": "+923001239999",
            "monthly_rent": 35000.0,
            "currency": "PKR",
            "billing_day": safe_day,
            "auto_remind_whatsapp": True,
        },
        headers=headers,
    )

    first = (await async_client.post("/api/v1/finance/whatsapp/reminders", headers=headers)).json()
    assert first["reminders_dispatched"] == 1

    second = (await async_client.post("/api/v1/finance/whatsapp/reminders", headers=headers)).json()
    assert second["reminders_dispatched"] == 0, (
        f"Second same-day reminder call must deduplicate and dispatch 0 reminders, got {second['reminders_dispatched']}"
    )


async def test_b12_finance_validation_rejects_invalid_amount_and_billing_day(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["business-financial-tracking"],
        industry="Real Estate / Property",
    )
    headers = ctx["headers"]

    bad_tx = await async_client.post(
        "/api/v1/finance/transactions",
        json={
            "type": "income",
            "category": "Sales",
            "amount": 0,
            "currency": "USD",
            "counterparty_name": "Zero Test",
        },
        headers=headers,
    )
    assert bad_tx.status_code == 422

    bad_sched = await async_client.post(
        "/api/v1/finance/rent-schedules",
        json={
            "property_unit": "Unit 1",
            "lessee_name": "Zero Day",
            "lessee_whatsapp": "+923001112233",
            "monthly_rent": 1000.0,
            "billing_day": 0,
        },
        headers=headers,
    )
    assert bad_sched.status_code == 422


async def test_b13_business_record_patch_blocks_agent_actor_type_403(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["business-financial-tracking"],
        industry="Financing",
    )
    headers = ctx["headers"]

    rec = (
        await async_client.post(
            "/api/v1/business/records",
            json={"record_type": "income", "title": "Protected Record", "amount": 500.0},
            headers=headers,
        )
    ).json()

    patch_res = await async_client.patch(
        f"/api/v1/business/records/{rec['id']}",
        json={"amount": 999.0, "reason": "Automated adjustment attempt", "actor_type": "agent"},
        headers=headers,
    )
    assert patch_res.status_code == 403
    assert _error_code(patch_res.json()) == "PERMISSION_DENIED"


async def test_b14_business_record_delete_forbidden_for_staff_role(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["business-financial-tracking"],
        industry="Financing",
    )
    staff = await invite_member_and_login(
        async_client,
        ctx["headers"],
        ctx["tenant_id"],
        role="staff",
    )

    rec = (
        await async_client.post(
            "/api/v1/business/records",
            json={"record_type": "expense", "title": "Staff Created", "amount": 40.0},
            headers=staff["headers"],
        )
    ).json()

    del_res = await async_client.delete(
        f"/api/v1/business/records/{rec['id']}",
        headers=staff["headers"],
    )
    assert del_res.status_code == 403
    assert _error_code(del_res.json()) == "PERMISSION_DENIED"


# =============================================================================
# F3: Service 2 (ai-marketing-growth) Boundaries (5 tests)
# =============================================================================


async def test_b15_marketing_campaign_approve_forbidden_for_manager(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["ai-marketing-growth"],
        industry="E-Commerce",
    )
    manager = await invite_member_and_login(
        async_client,
        ctx["headers"],
        ctx["tenant_id"],
        role="manager",
    )

    camp = (
        await async_client.post(
            "/api/v1/marketing/campaigns",
            json={"name": "Mgr Camp", "platform": "meta_ads", "objective": "leads", "budget": 300.0},
            headers=manager["headers"],
        )
    ).json()

    pub_res = await async_client.post(
        f"/api/v1/marketing/campaigns/{camp['id']}/approve",
        headers=manager["headers"],
    )
    assert pub_res.status_code == 403
    assert _error_code(pub_res.json()) == "PERMISSION_DENIED"


async def test_b16_marketing_campaign_patch_direct_active_status_rejected_422(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["ai-marketing-growth"],
        industry="E-Commerce",
    )
    headers = ctx["headers"]

    camp = (
        await async_client.post(
            "/api/v1/marketing/campaigns",
            json={"name": "Draft Camp", "platform": "meta_ads", "objective": "clicks", "budget": 150.0},
            headers=headers,
        )
    ).json()

    patch_res = await async_client.patch(
        f"/api/v1/marketing/campaigns/{camp['id']}",
        json={"status": "active"},
        headers=headers,
    )
    assert patch_res.status_code == 422
    assert _error_code(patch_res.json()) == "VALIDATION_ERROR"

    bad_obj = await async_client.post(
        "/api/v1/marketing/campaigns",
        json={"name": "Bad Obj", "platform": "meta_ads", "objective": "a", "budget": 100.0},
        headers=headers,
    )
    assert bad_obj.status_code == 422


async def test_b17_marketing_campaign_reject_approval_blocks_activation(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["ai-marketing-growth"],
        industry="E-Commerce",
    )
    headers = ctx["headers"]

    camp = (
        await async_client.post(
            "/api/v1/marketing/campaigns",
            json={"name": "Rejected Launch", "platform": "linkedin", "objective": "leads", "budget": 400.0},
            headers=headers,
        )
    ).json()
    approval_id = camp["configuration"]["approval_id"]

    rej_res = await async_client.post(
        f"/api/v1/approvals/{approval_id}/reject",
        json={"reason": "Creative off-brand"},
        headers=headers,
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "rejected"

    pub_res = await async_client.post(
        f"/api/v1/marketing/campaigns/{camp['id']}/approve",
        headers=headers,
    )
    assert pub_res.status_code in (400, 409), (
        f"Publishing a campaign whose Approval was rejected must fail, got {pub_res.status_code}"
    )


async def test_b18_marketing_expired_approval_returns_400_approval_expired(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["ai-marketing-growth"],
        industry="E-Commerce",
    )
    headers = ctx["headers"]

    camp = (
        await async_client.post(
            "/api/v1/marketing/campaigns",
            json={"name": "Expired Approval", "platform": "meta_ads", "objective": "sales", "budget": 200.0},
            headers=headers,
        )
    ).json()
    approval_id = camp["configuration"]["approval_id"]
    await set_approval_expires_at(approval_id, datetime.now(timezone.utc) - timedelta(hours=2))

    res = await async_client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"reason": "Late approval"},
        headers=headers,
    )
    assert res.status_code == 400
    assert _error_code(res.json()) == "APPROVAL_EXPIRED"


async def test_b19_marketing_cross_tenant_campaign_and_approval_isolation(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    tenant_a = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["ai-marketing-growth"],
        tenant_name="Mkt A",
    )
    tenant_b = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["ai-marketing-growth"],
        tenant_name="Mkt B",
    )

    camp_a = (
        await async_client.post(
            "/api/v1/marketing/campaigns",
            json={"name": "Secret A", "platform": "meta_ads", "objective": "leads", "budget": 500.0},
            headers=tenant_a["headers"],
        )
    ).json()
    app_a_id = camp_a["configuration"]["approval_id"]

    res1 = await async_client.post(
        f"/api/v1/marketing/campaigns/{camp_a['id']}/approve",
        headers=tenant_b["headers"],
    )
    assert res1.status_code == 404

    res2 = await async_client.post(
        f"/api/v1/approvals/{app_a_id}/approve",
        json={"reason": "Cross tenant hijack"},
        headers=tenant_b["headers"],
    )
    assert res2.status_code == 404


# =============================================================================
# F4: Service 3 (whatsapp-business-concierge) Boundaries (6 tests)
# =============================================================================


async def test_b20_whatsapp_ambiguous_message_approval_writes_only_on_approve(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["whatsapp-business-concierge", "business-financial-tracking"],
        industry="Real Estate / Property",
        connect_integrations=["whatsapp"],
    )
    headers = ctx["headers"]

    # Case 1: Ambiguous message -> reject -> ledger stays empty
    amb_rej = (
        await async_client.post(
            "/api/v1/integrations/whatsapp/simulate",
            json={
                "sender_phone": "+923001110001",
                "sender_name": "Ambiguous Reject",
                "message_text": "Maybe I paid $900 or $950 last week?",
                "message_id": "wamid.amb.rej",
            },
            headers=headers,
        )
    ).json()["data"]
    assert amb_rej["classification"] == "financial_ambiguous"
    assert amb_rej["requires_confirmation"] is True
    assert amb_rej["business_record_id"] is None

    await async_client.post(
        f"/api/v1/approvals/{amb_rej['approval_id']}/reject",
        json={"reason": "Not confirmed"},
        headers=headers,
    )
    records_after_rej = (await async_client.get("/api/v1/business/records", headers=headers)).json()
    assert len(records_after_rej) == 0

    # Case 2: Ambiguous message -> approve -> creates BusinessRecord
    amb_app = (
        await async_client.post(
            "/api/v1/integrations/whatsapp/simulate",
            json={
                "sender_phone": "+923001110002",
                "sender_name": "Ambiguous Approve",
                "message_text": "Maybe paid $750 for maintenance?",
                "message_id": "wamid.amb.app",
            },
            headers=headers,
        )
    ).json()["data"]

    app_res = await async_client.post(
        f"/api/v1/approvals/{amb_app['approval_id']}/approve",
        json={"reason": "Confirmed via bank statement"},
        headers=headers,
    )
    assert app_res.status_code == 200, app_res.text

    records_after_app = (await async_client.get("/api/v1/business/records", headers=headers)).json()
    assert len(records_after_app) == 1, (
        f"Approving confirm_ambiguous_whatsapp_transaction must create 1 BusinessRecord, got {len(records_after_app)}"
    )


async def test_b21_whatsapp_webhook_wamid_deduplication(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["whatsapp-business-concierge", "business-financial-tracking"],
        industry="Real Estate / Property",
        connect_integrations=["whatsapp"],
    )
    headers = ctx["headers"]

    dup_payload = {
        "sender_phone": "+923002223344",
        "sender_name": "Repeat Sender",
        "message_text": "Paid rent $1200 for Office 2B",
        "message_id": "wamid.dup.unique.001",
    }

    r1 = await async_client.post("/api/v1/integrations/whatsapp/webhook", json=dup_payload, headers=headers)
    assert r1.status_code == 200
    r2 = await async_client.post("/api/v1/integrations/whatsapp/webhook", json=dup_payload, headers=headers)
    assert r2.status_code == 200

    records = (await async_client.get("/api/v1/business/records", headers=headers)).json()
    matching = [r for r in records if r.get("reference_id") == "wamid.dup.unique.001"]
    assert len(matching) == 1, f"Duplicate wamid must be deduplicated, found {len(matching)} records"


async def test_b22_whatsapp_webhook_invalid_verify_token_and_hmac_return_403(
    async_client: AsyncClient,
) -> None:
    bad_get = await async_client.get(
        "/api/v1/integrations/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong_token", "hub.challenge": "12345"},
    )
    assert bad_get.status_code == 403

    prev_secret = settings.whatsapp_app_secret
    try:
        settings.whatsapp_app_secret = "super_secret_meta_app_key"
        body_bytes = json.dumps({"entry": []}).encode("utf-8")
        bad_sig = "sha256=" + hmac.new(b"wrong_secret", body_bytes, hashlib.sha256).hexdigest()

        bad_post = await async_client.post(
            "/api/v1/integrations/whatsapp/webhook",
            content=body_bytes,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": bad_sig},
        )
        assert bad_post.status_code == 403
        assert _error_code(bad_post.json()) == "INVALID_META_SIGNATURE"
    finally:
        settings.whatsapp_app_secret = prev_secret


async def test_b23_whatsapp_webhook_unmatched_phone_number_id_no_db_writes(
    async_client: AsyncClient,
) -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "9999999999999"},
                            "contacts": [{"wa_id": "+923001112233", "profile": {"name": "Unknown"}}],
                            "messages": [{"id": "wamid.unmatched.1", "from": "+923001112233", "text": {"body": "Paid $500"}}],
                        }
                    }
                ]
            }
        ]
    }
    res = await async_client.post("/api/v1/integrations/whatsapp/webhook", json=payload)
    assert res.status_code == 200
    assert res.json()["processed"] == 0


async def test_b24_whatsapp_send_unconfigured_in_non_mock_mode_returns_provider_error(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["whatsapp-business-concierge"],
        industry="Clinics / Hospitals",
    )
    prev_wa_provider = settings.whatsapp_provider
    try:
        settings.whatsapp_provider = "meta"
        res = await async_client.post(
            "/api/v1/integrations/whatsapp/send",
            json={"to_phone": "+923005556677", "message_body": "Should fail when unconfigured"},
            headers=ctx["headers"],
        )
        assert res.status_code in (400, 422, 502), (
            f"Unconfigured live WhatsApp send must NOT silently succeed! Got {res.status_code}: {res.text}"
        )
        assert _error_code(res.json()) in ("PROVIDER_NOT_CONFIGURED", "INTEGRATION_REQUIRED", "WHATSAPP_API_ERROR")
    finally:
        settings.whatsapp_provider = prev_wa_provider


async def test_b25_whatsapp_cross_tenant_integration_isolation(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    tenant_a = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["whatsapp-business-concierge"],
        connect_integrations=["whatsapp"],
        tenant_name="WA A",
    )
    tenant_b = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["whatsapp-business-concierge"],
        tenant_name="WA B",
    )
    integ_a_id = tenant_a["integrations"]["whatsapp"]["id"]

    del_res = await async_client.delete(
        f"/api/v1/integrations/{integ_a_id}",
        headers=tenant_b["headers"],
    )
    assert del_res.status_code == 404

    test_res = await async_client.post(
        f"/api/v1/integrations/{integ_a_id}/test",
        headers=tenant_b["headers"],
    )
    assert test_res.status_code == 404


# =============================================================================
# F5: Service 4 (multi-agent-orchestration) Boundaries (5 tests)
# =============================================================================


async def test_b26_agents_configure_forbidden_for_tenant_owner_non_super_admin(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["multi-agent-orchestration"],
        industry="Financing",
    )
    res = await async_client.post(
        "/api/v1/agents/planner_agent/configure",
        json={"enabled": True, "execution_limit": 500, "budget_limit": 100.0},
        headers=ctx["headers"],
    )
    assert res.status_code == 403
    assert _error_code(res.json()) == "PERMISSION_DENIED"


async def test_b27_agents_orchestrate_unauthorized_tool_and_disabled_agent(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["multi-agent-orchestration"],
        industry="Financing",
    )
    headers = ctx["headers"]

    bad_tool = await async_client.post(
        "/api/v1/agents/orchestrate",
        json={
            "objective": "Run forbidden tool",
            "agent_name": "planner_agent",
            "requested_tool": "drop_production_database",
        },
        headers=headers,
    )
    assert bad_tool.status_code == 403
    assert _error_code(bad_tool.json()) == "PERMISSION_DENIED"

    admin_tenant_headers = {**super_admin_headers, "X-Tenant-ID": ctx["tenant_id"]}
    await async_client.post(
        "/api/v1/agents/researcher_agent/configure",
        json={"enabled": False, "execution_limit": 100, "budget_limit": 50.0},
        headers=admin_tenant_headers,
    )

    disabled_res = await async_client.post(
        "/api/v1/agents/orchestrate",
        json={"objective": "Research competitors", "agent_name": "researcher_agent"},
        headers=headers,
    )
    assert disabled_res.status_code == 403
    assert _error_code(disabled_res.json()) == "PERMISSION_DENIED"

    unknown_res = await async_client.post(
        "/api/v1/agents/orchestrate",
        json={"objective": "Unknown agent", "agent_name": "nonexistent_agent_xyz"},
        headers=headers,
    )
    assert unknown_res.status_code == 404


async def test_b28_agents_tripped_circuit_breaker_blocks_and_admin_resets(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    from app.automation.budget_manager import budget_manager

    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["multi-agent-orchestration"],
        industry="Financing",
    )
    headers = ctx["headers"]

    for i in range(settings.circuit_breaker_max_failures):
        budget_manager.record_failure(ctx["tenant_id"], f"Simulated failure {i + 1}")

    tripped_res = await async_client.post(
        "/api/v1/agents/orchestrate",
        json={"objective": "Should be blocked by circuit breaker", "agent_name": "planner_agent"},
        headers=headers,
    )
    assert tripped_res.status_code in (403, 429, 503)
    assert _error_code(tripped_res.json()) == "CIRCUIT_BREAKER_OPEN"

    reset_res = await async_client.post(
        f"/api/v1/admin/tenants/{ctx['tenant_id']}/reset-circuit",
        headers=super_admin_headers,
    )
    assert reset_res.status_code == 200

    ok_res = await async_client.post(
        "/api/v1/agents/orchestrate",
        json={"objective": "Recovered execution", "agent_name": "planner_agent"},
        headers=headers,
    )
    assert ok_res.status_code == 200


async def test_b29_agents_tenant_execution_limit_enforced(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["multi-agent-orchestration"],
        industry="Financing",
    )
    headers = ctx["headers"]
    admin_tenant_headers = {**super_admin_headers, "X-Tenant-ID": ctx["tenant_id"]}

    await async_client.post(
        "/api/v1/agents/planner_agent/configure",
        json={"enabled": True, "execution_limit": 1, "budget_limit": 50.0},
        headers=admin_tenant_headers,
    )

    first = await async_client.post(
        "/api/v1/agents/orchestrate",
        json={"objective": "First execution within limit", "agent_name": "planner_agent"},
        headers=headers,
    )
    assert first.status_code == 200

    second = await async_client.post(
        "/api/v1/agents/orchestrate",
        json={"objective": "Second execution exceeding limit", "agent_name": "planner_agent"},
        headers=headers,
    )
    assert second.status_code in (403, 429), (
        f"Expected TenantAgent execution_limit=1 to block 2nd run, got {second.status_code}: {second.text}"
    )


async def test_b30_agents_cross_tenant_task_and_approval_isolation(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    tenant_a = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["multi-agent-orchestration"],
        tenant_name="Agents A",
    )
    tenant_b = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["multi-agent-orchestration"],
        tenant_name="Agents B",
    )

    orch_a = (
        await async_client.post(
            "/api/v1/agents/orchestrate",
            json={"objective": "Sensitive A", "agent_name": "master_orchestrator", "action_type": "delete_records"},
            headers=tenant_a["headers"],
        )
    ).json()

    get_task = await async_client.get(f"/api/v1/tasks/{orch_a['task_id']}", headers=tenant_b["headers"])
    assert get_task.status_code == 404

    app_b = await async_client.post(
        f"/api/v1/approvals/{orch_a['approval_id']}/approve",
        json={"reason": "Cross-tenant attempt"},
        headers=tenant_b["headers"],
    )
    assert app_b.status_code == 404


# =============================================================================
# F6: Service 5 (lead-crm-qualification) Boundaries (5 tests)
# =============================================================================


async def test_b31_leads_outreach_opted_out_returns_400_opt_out_compliance_block(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["lead-crm-qualification"],
        connect_integrations=["whatsapp"],
    )
    headers = ctx["headers"]

    lead = (
        await async_client.post(
            "/api/v1/marketing/leads",
            json={"name": "Opted Out User", "phone": "+923001112255", "metadata": {"opted_out": True}},
            headers=headers,
        )
    ).json()

    res = await async_client.post(
        f"/api/v1/marketing/leads/{lead['id']}/outreach",
        json={"channel": "whatsapp"},
        headers=headers,
    )
    assert res.status_code == 400
    assert _error_code(res.json()) == "OPT_OUT_COMPLIANCE_BLOCK"


async def test_b32_leads_outreach_disconnected_integration_returns_400(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["lead-crm-qualification"],
    )
    headers = ctx["headers"]

    lead = (
        await async_client.post(
            "/api/v1/marketing/leads",
            json={"name": "No WA Integration", "phone": "+923001112266"},
            headers=headers,
        )
    ).json()

    res = await async_client.post(
        f"/api/v1/marketing/leads/{lead['id']}/outreach",
        json={"channel": "whatsapp"},
        headers=headers,
    )
    assert res.status_code == 400
    assert _error_code(res.json()) == "INTEGRATION_REQUIRED"


async def test_b33_leads_outreach_missing_phone_or_email_must_not_return_sent(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["lead-crm-qualification"],
        connect_integrations=["whatsapp", "gmail"],
    )
    headers = ctx["headers"]

    no_phone_lead = (
        await async_client.post(
            "/api/v1/marketing/leads",
            json={"name": "Email Only Lead", "email": "onlyemail@example.com"},
            headers=headers,
        )
    ).json()
    wa_res = await async_client.post(
        f"/api/v1/marketing/leads/{no_phone_lead['id']}/outreach",
        json={"channel": "whatsapp"},
        headers=headers,
    )
    assert wa_res.status_code in (400, 422), (
        f"WhatsApp outreach to lead without phone must fail, NOT return sent! Got {wa_res.status_code}: {wa_res.text}"
    )

    no_email_lead = (
        await async_client.post(
            "/api/v1/marketing/leads",
            json={"name": "Phone Only Lead", "phone": "+923004445566"},
            headers=headers,
        )
    ).json()
    em_res = await async_client.post(
        f"/api/v1/marketing/leads/{no_email_lead['id']}/outreach",
        json={"channel": "email"},
        headers=headers,
    )
    assert em_res.status_code in (400, 422), (
        f"Email outreach to lead without email must fail, NOT return sent! Got {em_res.status_code}: {em_res.text}"
    )


async def test_b34_leads_generate_in_production_without_places_key_returns_400(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["lead-crm-qualification"],
    )
    prev_env = settings.app_env
    try:
        settings.app_env = "production"
        res = await async_client.post(
            "/api/v1/marketing/leads/generate",
            json={"industry": "Real Estate / Property", "location": "Dubai", "limit": 2},
            headers=ctx["headers"],
        )
        assert res.status_code == 400
        assert _error_code(res.json()) == "GOOGLE_PLACES_NOT_CONFIGURED"
    finally:
        settings.app_env = prev_env


async def test_b35_leads_cross_tenant_qualify_outreach_book_return_404(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    tenant_a = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["lead-crm-qualification"],
        tenant_name="CRM A",
    )
    tenant_b = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["lead-crm-qualification"],
        connect_integrations=["whatsapp"],
        tenant_name="CRM B",
    )

    lead_a = (
        await async_client.post(
            "/api/v1/marketing/leads",
            json={"name": "Tenant A Lead", "phone": "+923001119988"},
            headers=tenant_a["headers"],
        )
    ).json()

    assert (
        await async_client.post(f"/api/v1/marketing/leads/{lead_a['id']}/qualify", headers=tenant_b["headers"])
    ).status_code == 404
    assert (
        await async_client.post(
            f"/api/v1/marketing/leads/{lead_a['id']}/outreach",
            json={"channel": "whatsapp"},
            headers=tenant_b["headers"],
        )
    ).status_code == 404
    assert (
        await async_client.post(
            f"/api/v1/marketing/leads/{lead_a['id']}/book-appointment",
            json={"meeting_title": "Hijack Call"},
            headers=tenant_b["headers"],
        )
    ).status_code == 404


# =============================================================================
# F7: Service 6 & RBAC / Tenant Suspension Boundaries (5 tests)
# =============================================================================


async def test_b36_analytics_empty_tenant_zero_division_safety(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["executive-analytics-compliance"],
        industry="Financing",
    )
    ov = await async_client.get("/api/v1/analytics/overview", headers=ctx["headers"])
    assert ov.status_code == 200
    data = ov.json()["data"]
    assert data["financial"]["net_cashflow"] == 0.0
    assert data["marketing"]["roi_percentage"] == 0.0
    assert data["ai_governance"]["total_executions"] == 0

    t_ov = await async_client.get(f"/api/v1/tenants/{ctx['tenant_id']}/overview", headers=ctx["headers"])
    assert t_ov.status_code == 200
    assert t_ov.json()["data"]["metrics"]["conversion_rate"] == 0.0


async def test_b37_analytics_cross_tenant_header_and_overview_mismatch_403(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    tenant_a = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["executive-analytics-compliance"],
        tenant_name="Analytics A",
    )
    tenant_b = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["executive-analytics-compliance"],
        tenant_name="Analytics B",
    )

    # Tenant B user passing Tenant A's X-Tenant-ID
    forged_headers = {**tenant_b["owner"]["headers"], "X-Tenant-ID": tenant_a["tenant_id"]}
    res = await async_client.get("/api/v1/analytics/overview", headers=forged_headers)
    assert res.status_code == 403
    assert _error_code(res.json()) == "TENANT_ISOLATION_VIOLATION"

    # Path mismatch on /tenants/{id}/overview
    mismatch = await async_client.get(
        f"/api/v1/tenants/{tenant_a['tenant_id']}/overview",
        headers=tenant_b["headers"],
    )
    assert mismatch.status_code == 403
    assert _error_code(mismatch.json()) == "TENANT_ISOLATION_VIOLATION"


async def test_b38_rbac_viewer_blocked_from_mutations_across_services(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=CANONICAL_SERVICE_SLUGS,
        industry="Financing",
    )
    viewer = await invite_member_and_login(
        async_client,
        ctx["headers"],
        ctx["tenant_id"],
        role="viewer",
    )

    # Viewer can read analytics
    assert (await async_client.get("/api/v1/analytics/overview", headers=viewer["headers"])).status_code == 200

    # Viewer blocked from mutating across all services
    for method, url, payload in (
        ("POST", "/api/v1/business/records", {"record_type": "income", "title": "V", "amount": 10.0}),
        ("POST", "/api/v1/finance/accounts", {"name": "Viewer Bank", "currency": "USD"}),
        ("POST", "/api/v1/marketing/leads", {"name": "Viewer Lead"}),
        ("POST", "/api/v1/agents/orchestrate", {"objective": "Viewer run", "agent_name": "planner_agent"}),
    ):
        res = await async_client.request(method, url, json=payload, headers=viewer["headers"])
        assert res.status_code == 403, f"Viewer must be blocked on {method} {url}, got {res.status_code}"
        assert _error_code(res.json()) == "PERMISSION_DENIED"


async def test_b39_rbac_staff_blocked_from_approvals_and_campaign_publish(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["ai-marketing-growth", "multi-agent-orchestration"],
        industry="E-Commerce",
    )
    staff = await invite_member_and_login(
        async_client,
        ctx["headers"],
        ctx["tenant_id"],
        role="staff",
    )

    camp = (
        await async_client.post(
            "/api/v1/marketing/campaigns",
            json={"name": "Staff Camp", "platform": "meta_ads", "objective": "leads", "budget": 100.0},
            headers=ctx["headers"],
        )
    ).json()
    approval_id = camp["configuration"]["approval_id"]

    pub_res = await async_client.post(
        f"/api/v1/marketing/campaigns/{camp['id']}/approve",
        headers=staff["headers"],
    )
    assert pub_res.status_code == 403
    assert _error_code(pub_res.json()) == "PERMISSION_DENIED"

    app_res = await async_client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"reason": "Staff self-approve"},
        headers=staff["headers"],
    )
    assert app_res.status_code == 403
    assert _error_code(app_res.json()) == "PERMISSION_DENIED"


async def test_b40_suspended_tenant_blocked_403_tenant_suspended(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["business-financial-tracking"],
        industry="Financing",
    )
    await set_tenant_status(ctx["tenant_id"], "suspended")

    res = await async_client.get("/api/v1/finance/accounts", headers=ctx["headers"])
    assert res.status_code == 403
    assert _error_code(res.json()) == "TENANT_SUSPENDED"
