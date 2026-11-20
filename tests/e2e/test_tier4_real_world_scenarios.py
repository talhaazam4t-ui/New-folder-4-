"""Tier 4 E2E Tests — 6 Realistic End-to-End Client Scenarios (TEST_INFRA.md)."""

from __future__ import annotations

from datetime import date

from e2e_helpers import (
    CANONICAL_SERVICE_SLUGS,
    approve_tenant_payment,
    create_tenant,
    invite_member_and_login,
    onboard_paid_tenant,
    register_and_login,
    subscribe_service,
)
from httpx import AsyncClient


async def test_scenario_1_real_estate_and_financing_portfolio(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    """Real Estate & Financing Portfolio: USD+PKR accounts, rent schedules, WA payment + ambiguous approval, reminders, bridged overview."""
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=[
            "business-financial-tracking",
            "whatsapp-business-concierge",
            "executive-analytics-compliance",
        ],
        industry="Real Estate / Property",
        tenant_name="Crescent Realty & Financing",
        connect_integrations=["whatsapp"],
    )
    headers = ctx["headers"]

    usd_acc = (
        await async_client.post(
            "/api/v1/finance/accounts",
            json={"name": "USD Escrow", "currency": "USD", "current_balance": 10000.0},
            headers=headers,
        )
    ).json()
    pkr_acc = (
        await async_client.post(
            "/api/v1/finance/accounts",
            json={"name": "PKR Operations", "currency": "PKR", "current_balance": 200000.0},
            headers=headers,
        )
    ).json()

    await async_client.post(
        "/api/v1/finance/transactions",
        json={
            "account_id": usd_acc["id"],
            "type": "income",
            "category": "Management Fee",
            "amount": 2500.0,
            "currency": "USD",
            "status": "paid",
            "counterparty_name": "Overseas Investor",
        },
        headers=headers,
    )
    await async_client.post(
        "/api/v1/finance/transactions",
        json={
            "account_id": pkr_acc["id"],
            "type": "rent",
            "category": "Commercial Rent",
            "amount": 150000.0,
            "currency": "PKR",
            "status": "paid",
            "counterparty_name": "Lahore Retail Co",
        },
        headers=headers,
    )

    safe_day = min(date.today().day, 28)
    await async_client.post(
        "/api/v1/finance/rent-schedules",
        json={
            "property_unit": "Skyline Suite 14",
            "lessee_name": "Farhan Ahmed",
            "lessee_whatsapp": "+923001122334",
            "monthly_rent": 85000.0,
            "currency": "PKR",
            "billing_day": safe_day,
            "auto_remind_whatsapp": True,
        },
        headers=headers,
    )
    rem_res = await async_client.post("/api/v1/finance/whatsapp/reminders", headers=headers)
    assert rem_res.status_code == 200
    assert rem_res.json()["reminders_dispatched"] == 1

    # Confirmed WhatsApp payment
    confirmed_wa = await async_client.post(
        "/api/v1/integrations/whatsapp/simulate",
        json={
            "sender_phone": "+923001122334",
            "sender_name": "Farhan Ahmed",
            "message_text": "Paid rent $1200 for Skyline Suite 14",
            "message_id": "wamid.sc1.confirmed",
        },
        headers=headers,
    )
    assert confirmed_wa.json()["data"]["classification"] == "financial_confirmed"

    # Ambiguous WhatsApp payment -> approve
    amb_wa = await async_client.post(
        "/api/v1/integrations/whatsapp/simulate",
        json={
            "sender_phone": "+923009988776",
            "sender_name": "Tariq Lessee",
            "message_text": "Maybe transferred $600?",
            "message_id": "wamid.sc1.amb",
        },
        headers=headers,
    )
    amb_data = amb_wa.json()["data"]
    assert amb_data["classification"] == "financial_ambiguous"
    await async_client.post(
        f"/api/v1/approvals/{amb_data['approval_id']}/approve",
        json={"reason": "Confirmed bank slip"},
        headers=headers,
    )

    usd_summary = (
        await async_client.get("/api/v1/finance/summary", params={"currency": "USD"}, headers=headers)
    ).json()
    assert usd_summary["total_cash_balance"] == 12500.0
    assert usd_summary["currency_balances"]["PKR"] == 350000.0

    overview = (await async_client.get(f"/api/v1/tenants/{ctx['tenant_id']}/overview", headers=headers)).json()["data"]
    assert overview["is_payment_approved"] is True
    assert overview["metrics"]["income"] >= 3700.0


async def test_scenario_2_clinic_healthcare_concierge_and_appointment_funnel(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    """Clinic / Healthcare Concierge & Appointment Funnel."""
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=[
            "whatsapp-business-concierge",
            "lead-crm-qualification",
            "executive-analytics-compliance",
        ],
        industry="Clinics / Hospitals",
        tenant_name="Al-Shifa Dental & Diagnostics",
        connect_integrations=["whatsapp", "google_calendar", "booking_provider"],
    )
    headers = ctx["headers"]

    # Patient 1: Inbound inquiry -> qualify -> outreach -> book appointment with scheduled_iso
    inq = (
        await async_client.post(
            "/api/v1/integrations/whatsapp/simulate",
            json={
                "sender_phone": "+923211112233",
                "sender_name": "Mariam Patient",
                "message_text": "Hello, I need a root canal consultation next Tuesday.",
                "message_id": "wamid.clinic.001",
            },
            headers=headers,
        )
    ).json()["data"]
    assert inq["classification"] == "lead_inquiry"
    lead_id = inq["lead_id"]

    qual = (await async_client.post(f"/api/v1/marketing/leads/{lead_id}/qualify", headers=headers)).json()
    assert qual["status"] in ("qualified", "contacted")

    outreach = await async_client.post(
        f"/api/v1/marketing/leads/{lead_id}/outreach",
        json={"channel": "whatsapp", "custom_context": "Confirm dental slot availability"},
        headers=headers,
    )
    assert outreach.status_code == 200
    assert outreach.json()["data"]["status"] == "sent"

    requested_slot = "2026-12-15T09:30:00Z"
    booked = (
        await async_client.post(
            f"/api/v1/marketing/leads/{lead_id}/book-appointment",
            json={"meeting_title": "Root Canal Consultation", "scheduled_iso": requested_slot},
            headers=headers,
        )
    ).json()["data"]
    assert booked["status"] == "converted"
    assert str(booked["calendar_event"]["start_time"]).startswith("2026-12-15T09:30:00")

    # Patient 2: Opt-out compliance block
    opted_out = (
        await async_client.post(
            "/api/v1/marketing/leads",
            json={"name": "No Contact Patient", "phone": "+923210009999", "metadata": {"opted_out": True}},
            headers=headers,
        )
    ).json()
    blocked = await async_client.post(
        f"/api/v1/marketing/leads/{opted_out['id']}/outreach",
        json={"channel": "whatsapp"},
        headers=headers,
    )
    assert blocked.status_code == 400
    assert blocked.json()["error"]["code"] == "OPT_OUT_COMPLIANCE_BLOCK"

    # Weekly executive digest
    digest = await async_client.post("/api/v1/analytics/digest", json={"period": "weekly"}, headers=headers)
    assert digest.status_code == 200
    assert digest.json()["success"] is True


async def test_scenario_3_ecommerce_growth_campaign_launch(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    """E-Commerce Growth Campaign Launch: Research -> AI Copy -> Draft Campaign -> Approval -> Analytics -> Lead Outreach."""
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=[
            "ai-marketing-growth",
            "lead-crm-qualification",
            "executive-analytics-compliance",
        ],
        industry="E-Commerce",
        tenant_name="LuxeCart Retail",
        connect_integrations=["whatsapp", "gmail"],
    )
    headers = ctx["headers"]

    comp = await async_client.post(
        "/api/v1/marketing/research/competitors",
        json={"industry": "E-Commerce", "competitors": ["Zara", "Khaadi"], "region": "Pakistan"},
        headers=headers,
    )
    assert comp.status_code == 200

    aud = await async_client.post(
        "/api/v1/marketing/research/audience",
        json={"product_or_service": "Organic Skincare Box", "target_industry": "E-Commerce", "price_point": "$65"},
        headers=headers,
    )
    assert aud.status_code == 200

    copy_res = await async_client.post(
        "/api/v1/marketing/content/generate",
        json={"channel": "instagram", "topic": "Winter Glow Launch", "tone": "bold", "call_to_action": "Order Today"},
        headers=headers,
    )
    assert copy_res.status_code == 200
    assert copy_res.json()["data"]["generated_copy"]

    camp = (
        await async_client.post(
            "/api/v1/marketing/campaigns",
            json={"name": "Winter Glow Meta Launch", "platform": "meta_ads", "objective": "purchases", "budget": 1500.0},
            headers=headers,
        )
    ).json()
    approval_id = camp["configuration"]["approval_id"]

    await async_client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"reason": "Creative & budget approved"},
        headers=headers,
    )

    mkt_analytics = (await async_client.get("/api/v1/marketing/analytics", headers=headers)).json()
    assert mkt_analytics["active_campaigns"] == 1
    assert mkt_analytics["total_impressions"] == 0

    gen_leads = (
        await async_client.post(
            "/api/v1/marketing/leads/generate",
            json={"industry": "E-Commerce", "location": "Karachi", "limit": 2},
            headers=headers,
        )
    ).json()["data"]
    assert gen_leads["created_count"] == 2
    first_lead_id = gen_leads["leads"][0]["id"]

    outreach = await async_client.post(
        f"/api/v1/marketing/leads/{first_lead_id}/outreach",
        json={"channel": "email", "custom_context": "Wholesale retail partnership"},
        headers=headers,
    )
    assert outreach.status_code == 200


async def test_scenario_4_multi_department_agency_orchestration(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    """Multi-Department Agency Orchestration: 4-stage pipeline, sensitive approval & resume, UsageRecord governance, CSV/JSON audit export."""
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["multi-agent-orchestration", "executive-analytics-compliance"],
        industry="Financing",
        tenant_name="Nexus Multi-Department Agency",
    )
    headers = ctx["headers"]

    standard_run = (
        await async_client.post(
            "/api/v1/agents/orchestrate",
            json={"objective": "Compile weekly department risk and cashflow brief", "agent_name": "master_orchestrator"},
            headers=headers,
        )
    ).json()
    assert standard_run["status"] == "completed"
    assert len(standard_run["stages"]) == 4

    sensitive_run = (
        await async_client.post(
            "/api/v1/agents/orchestrate",
            json={
                "objective": "Broadcast Q4 renewal notice to top 50 accounts",
                "agent_name": "master_orchestrator",
                "action_type": "send_bulk_whatsapp",
            },
            headers=headers,
        )
    ).json()
    assert sensitive_run["status"] == "awaiting_approval"

    resumed = (
        await async_client.post(
            f"/api/v1/approvals/{sensitive_run['approval_id']}/approve",
            json={"reason": "Agency director sign-off"},
            headers=headers,
        )
    ).json()["data"]
    assert resumed["approval"]["status"] == "approved"
    assert resumed["task"]["status"] == "completed"

    usage = (await async_client.get("/api/v1/analytics/usage", headers=headers)).json()["data"]
    assert len(usage["records"]) >= 4
    assert usage["quota"]["tokens_used_today"] > 0

    csv_export = await async_client.get("/api/v1/analytics/export", params={"format": "csv"}, headers=headers)
    assert csv_export.status_code == 200
    assert "text/csv" in csv_export.headers.get("content-type", "")

    json_export = await async_client.get("/api/v1/analytics/export", params={"format": "json"}, headers=headers)
    assert json_export.status_code == 200


async def test_scenario_5_incomplete_onboarding_unpaid_gate_and_recovery(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    """Incomplete Onboarding, Unpaid Gate & Missing-Provider Recovery."""
    owner = await register_and_login(async_client, full_name="Recovery Client")
    tenant = await create_tenant(async_client, owner["headers"], name="Recovery Clinic", industry="Clinics / Hospitals")
    headers = tenant["headers"]

    await subscribe_service(async_client, headers, "business-financial-tracking")
    await subscribe_service(async_client, headers, "whatsapp-business-concierge")

    # Blocked before payment approval
    blocked_fin = await async_client.get("/api/v1/finance/accounts", headers=headers)
    assert blocked_fin.status_code == 403
    assert blocked_fin.json()["error"]["code"] == "PAYMENT_PENDING"

    # Unconfigured OAuth returns structured 400 OAUTH_NOT_CONFIGURED
    oauth_err = await async_client.get("/api/v1/integrations/oauth/whatsapp/authorize", headers=headers)
    assert oauth_err.status_code == 400
    assert oauth_err.json()["error"]["code"] == "OAUTH_NOT_CONFIGURED"

    # Client submits support request for onboarding assistance
    sup = await async_client.post(
        "/api/v1/support/requests",
        json={
            "subject": "Need onboarding help for Meta WhatsApp",
            "message": "Bank transfer sent, awaiting activation and Meta OAuth guidance.",
            "category": "onboarding",
        },
        headers=headers,
    )
    assert sup.status_code in (200, 201)

    # Notify bank transfer -> Super Admin approves -> services unlock
    await async_client.post(
        "/api/v1/payments/bank-transfer/notify",
        json={"transaction_reference": "REC-2026-01", "amount": 228.0},
        headers=headers,
    )
    await approve_tenant_payment(async_client, super_admin_headers, tenant["id"])

    unlocked_fin = await async_client.get("/api/v1/finance/accounts", headers=headers)
    assert unlocked_fin.status_code == 200

    ov = (await async_client.get(f"/api/v1/tenants/{tenant['id']}/overview", headers=headers)).json()["data"]
    assert ov["is_payment_approved"] is True
    assert set(ov["enabled_modules"]) == {"financial_ledger", "whatsapp_concierge"}


async def test_scenario_6_concurrent_multi_tenant_multi_role_segregation(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    """Multi-Tenant & Multi-Role Security Segregation across Tenant A & Tenant B (owner, manager, staff, viewer)."""
    tenant_a = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=CANONICAL_SERVICE_SLUGS,
        industry="Financing",
        tenant_name="Tenant Alpha",
        connect_integrations=["whatsapp"],
    )
    tenant_b = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=CANONICAL_SERVICE_SLUGS,
        industry="E-Commerce",
        tenant_name="Tenant Beta",
        connect_integrations=["whatsapp"],
    )

    a_manager = await invite_member_and_login(async_client, tenant_a["headers"], tenant_a["tenant_id"], role="manager")
    a_staff = await invite_member_and_login(async_client, tenant_a["headers"], tenant_a["tenant_id"], role="staff")
    a_viewer = await invite_member_and_login(async_client, tenant_a["headers"], tenant_a["tenant_id"], role="viewer")

    # Staff creates business record & lead in Tenant A
    rec_a = (
        await async_client.post(
            "/api/v1/business/records",
            json={"record_type": "income", "title": "Alpha Confidential Revenue", "amount": 9000.0},
            headers=a_staff["headers"],
        )
    ).json()
    lead_a = (
        await async_client.post(
            "/api/v1/marketing/leads",
            json={"name": "Alpha VIP Lead", "phone": "+923001234000"},
            headers=a_staff["headers"],
        )
    ).json()

    # Manager creates campaign draft in Tenant A, cannot publish (owner only)
    camp_a = (
        await async_client.post(
            "/api/v1/marketing/campaigns",
            json={"name": "Alpha Q4", "platform": "meta_ads", "objective": "leads", "budget": 1000.0},
            headers=a_manager["headers"],
        )
    ).json()
    assert (
        await async_client.post(f"/api/v1/marketing/campaigns/{camp_a['id']}/approve", headers=a_manager["headers"])
    ).status_code == 403

    # Owner publishes campaign
    assert (
        await async_client.post(f"/api/v1/marketing/campaigns/{camp_a['id']}/approve", headers=tenant_a["headers"])
    ).status_code == 200

    # Viewer can read Tenant A overview & analytics, cannot mutate
    assert (await async_client.get("/api/v1/analytics/overview", headers=a_viewer["headers"])).status_code == 200
    assert (
        await async_client.post(
            "/api/v1/business/records",
            json={"record_type": "expense", "title": "Blocked", "amount": 10.0},
            headers=a_viewer["headers"],
        )
    ).status_code == 403

    # Tenant B sees zero Tenant A data and gets 403/404 on cross-tenant access
    assert (await async_client.get("/api/v1/business/records", headers=tenant_b["headers"])).json() == []
    assert (await async_client.get("/api/v1/marketing/leads", headers=tenant_b["headers"])).json() == []
    assert (
        await async_client.get(f"/api/v1/business/records/{rec_a['id']}", headers=tenant_b["headers"])
    ).status_code == 404
    assert (
        await async_client.post(f"/api/v1/marketing/leads/{lead_a['id']}/qualify", headers=tenant_b["headers"])
    ).status_code == 404
    assert (
        await async_client.get(
            f"/api/v1/tenants/{tenant_a['tenant_id']}/overview",
            headers={**tenant_b["owner"]["headers"], "X-Tenant-ID": tenant_a["tenant_id"]},
        )
    ).status_code == 403
