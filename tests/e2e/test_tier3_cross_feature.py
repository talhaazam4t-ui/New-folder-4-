"""Tier 3 E2E Tests — Pairwise Cross-Feature Combinations & Full Journey Integration."""

from __future__ import annotations

from datetime import date

from e2e_helpers import (
    approve_tenant_payment,
    create_tenant,
    onboard_paid_tenant,
    register_and_login,
    subscribe_service,
)
from httpx import AsyncClient


async def test_cf01_multi_service_selective_unlock_services_1_and_3_only(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["business-financial-tracking", "whatsapp-business-concierge"],
        industry="Real Estate / Property",
    )
    headers = ctx["headers"]

    # Unlocked
    assert (await async_client.get("/api/v1/finance/accounts", headers=headers)).status_code == 200
    assert (
        await async_client.post(
            "/api/v1/integrations/whatsapp/simulate",
            json={"sender_phone": "+923001112233", "message_text": "Hello"},
            headers=headers,
        )
    ).status_code == 200

    # Locked
    for url in (
        "/api/v1/marketing/campaigns",
        "/api/v1/agents",
        "/api/v1/marketing/leads",
        "/api/v1/analytics/overview",
    ):
        res = await async_client.get(url, headers=headers)
        assert res.status_code == 403, f"Expected 403 on {url}, got {res.status_code}"

    ov = (await async_client.get(f"/api/v1/tenants/{ctx['tenant_id']}/overview", headers=headers)).json()["data"]
    assert set(ov["enabled_modules"]) == {"financial_ledger", "whatsapp_concierge"}


async def test_cf02_whatsapp_payment_flows_to_finance_and_tenant_overview(
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

    sim = await async_client.post(
        "/api/v1/integrations/whatsapp/simulate",
        json={
            "sender_phone": "+923004445566",
            "sender_name": "Raza Lessee",
            "message_text": "Paid rent $2100 for Villa 9",
            "message_id": "wamid.cf02.001",
        },
        headers=headers,
    )
    assert sim.status_code == 200
    assert sim.json()["data"]["classification"] == "financial_confirmed"

    biz_sum = (await async_client.get("/api/v1/business/summary", headers=headers)).json()
    assert biz_sum["gross_inflow"] >= 2100.0

    fin_sum = (await async_client.get("/api/v1/finance/summary", params={"currency": "USD"}, headers=headers)).json()
    assert fin_sum["monthly_revenue"] >= 2100.0

    ov = (await async_client.get(f"/api/v1/tenants/{ctx['tenant_id']}/overview", headers=headers)).json()["data"]
    assert ov["metrics"]["income"] >= 2100.0


async def test_cf03_finance_rent_schedule_triggers_whatsapp_reminder_and_audit_log(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=[
            "business-financial-tracking",
            "whatsapp-business-concierge",
            "executive-analytics-compliance",
        ],
        industry="Real Estate / Property",
        connect_integrations=["whatsapp"],
    )
    headers = ctx["headers"]

    safe_day = min(date.today().day, 28)
    await async_client.post(
        "/api/v1/finance/rent-schedules",
        json={
            "property_unit": "Commercial Floor 2",
            "lessee_name": "Nadia Traders",
            "lessee_whatsapp": "+923008889900",
            "monthly_rent": 75000.0,
            "currency": "PKR",
            "billing_day": safe_day,
            "auto_remind_whatsapp": True,
        },
        headers=headers,
    )

    rem = await async_client.post("/api/v1/finance/whatsapp/reminders", headers=headers)
    assert rem.status_code == 200
    assert rem.json()["reminders_dispatched"] == 1

    logs = (await async_client.get("/api/v1/analytics/audit-logs", headers=headers)).json()["data"]
    assert any("rent" in row["action"] or "whatsapp" in row["action"] for row in logs)


async def test_cf04_whatsapp_inquiry_creates_lead_then_outreach_and_appointment(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["whatsapp-business-concierge", "lead-crm-qualification"],
        industry="Clinics / Hospitals",
        connect_integrations=["whatsapp", "google_calendar"],
    )
    headers = ctx["headers"]

    sim = (
        await async_client.post(
            "/api/v1/integrations/whatsapp/simulate",
            json={
                "sender_phone": "+923007771122",
                "sender_name": "Sana Patient",
                "message_text": "I want to book an orthodontic consultation next week.",
                "message_id": "wamid.cf04.001",
            },
            headers=headers,
        )
    ).json()["data"]
    lead_id = sim["lead_id"]

    qual = (await async_client.post(f"/api/v1/marketing/leads/{lead_id}/qualify", headers=headers)).json()
    assert qual["status"] in ("qualified", "contacted")

    outreach = (
        await async_client.post(
            f"/api/v1/marketing/leads/{lead_id}/outreach",
            json={"channel": "whatsapp", "custom_context": "Confirm orthodontic slot"},
            headers=headers,
        )
    ).json()["data"]
    assert outreach["status"] == "sent"

    book = (
        await async_client.post(
            f"/api/v1/marketing/leads/{lead_id}/book-appointment",
            json={"meeting_title": "Orthodontic Assessment", "scheduled_iso": "2026-12-10T11:00:00Z"},
            headers=headers,
        )
    ).json()["data"]
    assert book["status"] == "converted"
    assert book["meeting_booked"] is True


async def test_cf05_marketing_campaign_approval_syncs_to_analytics_and_audit_logs(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["ai-marketing-growth", "executive-analytics-compliance"],
        industry="E-Commerce",
    )
    headers = ctx["headers"]

    camp = (
        await async_client.post(
            "/api/v1/marketing/campaigns",
            json={"name": "CrossFeature Promo", "platform": "instagram", "objective": "conversions", "budget": 950.0},
            headers=headers,
        )
    ).json()
    approval_id = camp["configuration"]["approval_id"]

    await async_client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"reason": "Ready to launch"},
        headers=headers,
    )

    ov = (await async_client.get("/api/v1/analytics/overview", headers=headers)).json()["data"]
    assert ov["marketing"]["active_campaigns"] == 1
    assert ov["marketing"]["total_budget_allocated"] >= 950.0
    assert ov["ai_governance"]["pending_approvals"] == 0

    logs = (await async_client.get("/api/v1/analytics/audit-logs", headers=headers)).json()["data"]
    assert any("campaign" in row["action"] or "approval" in row["action"] for row in logs)


async def test_cf06_multi_agent_orchestration_feeds_usage_and_executive_analytics(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["multi-agent-orchestration", "executive-analytics-compliance"],
        industry="Financing",
    )
    headers = ctx["headers"]

    orch = (
        await async_client.post(
            "/api/v1/agents/orchestrate",
            json={"objective": "Synthesize quarterly portfolio strategy", "agent_name": "master_orchestrator"},
            headers=headers,
        )
    ).json()
    assert orch["status"] == "completed"

    usage = (await async_client.get("/api/v1/analytics/usage", headers=headers)).json()["data"]
    assert len(usage["records"]) >= 4

    ov = (await async_client.get("/api/v1/analytics/overview", headers=headers)).json()["data"]
    assert ov["ai_governance"]["total_executions"] >= 1
    assert ov["ai_governance"]["tokens_used_today"] >= orch["total_tokens"]


async def test_cf07_ambiguous_whatsapp_approval_flows_to_analytics_and_audit_log(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=[
            "whatsapp-business-concierge",
            "business-financial-tracking",
            "executive-analytics-compliance",
        ],
        industry="Financing",
        connect_integrations=["whatsapp"],
    )
    headers = ctx["headers"]

    amb = (
        await async_client.post(
            "/api/v1/integrations/whatsapp/simulate",
            json={
                "sender_phone": "+923003334455",
                "sender_name": "Ambiguous Payer",
                "message_text": "Maybe I paid $1500 invoice?",
                "message_id": "wamid.cf07.001",
            },
            headers=headers,
        )
    ).json()["data"]
    assert amb["classification"] == "financial_ambiguous"

    await async_client.post(
        f"/api/v1/approvals/{amb['approval_id']}/approve",
        json={"reason": "Verified deposit"},
        headers=headers,
    )

    ov = (await async_client.get("/api/v1/analytics/overview", headers=headers)).json()["data"]
    assert ov["financial"]["total_income"] >= 1500.0
    logs = (await async_client.get("/api/v1/analytics/audit-logs", headers=headers)).json()["data"]
    assert any("approval" in row["action"] for row in logs)


async def test_cf08_lead_outreach_approval_resume_dispatches_and_updates_lead(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["lead-crm-qualification", "multi-agent-orchestration"],
        industry="E-Commerce",
        connect_integrations=["whatsapp"],
    )
    headers = ctx["headers"]

    lead = (
        await async_client.post(
            "/api/v1/marketing/leads",
            json={"name": "Approval Lead", "phone": "+923006667788", "source": "website"},
            headers=headers,
        )
    ).json()

    outreach = (
        await async_client.post(
            f"/api/v1/marketing/leads/{lead['id']}/outreach",
            json={"channel": "whatsapp", "require_approval": True},
            headers=headers,
        )
    ).json()["data"]
    assert outreach["status"] == "awaiting_approval"

    approve = await async_client.post(
        f"/api/v1/approvals/{outreach['approval_id']}/approve",
        json={"reason": "Approved outreach draft"},
        headers=headers,
    )
    assert approve.status_code == 200

    leads = (await async_client.get("/api/v1/marketing/leads", headers=headers)).json()
    updated = next(lead_row for lead_row in leads if lead_row["id"] == lead["id"])
    assert updated["status"] in ("contacted", "qualified", "converted")


async def test_cf09_full_client_journey_register_to_support_request(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    owner = await register_and_login(async_client, full_name="Full Journey Client")
    tenant = await create_tenant(
        async_client,
        owner["headers"],
        name="Journey Holdings",
        industry="Financing",
    )
    headers = tenant["headers"]

    await subscribe_service(async_client, headers, "business-financial-tracking")
    await subscribe_service(async_client, headers, "executive-analytics-compliance")

    await async_client.post(
        "/api/v1/payments/bank-transfer/notify",
        json={"transaction_reference": "JOURNEY-999", "amount": 500.0},
        headers=headers,
    )
    await approve_tenant_payment(async_client, super_admin_headers, tenant["id"])

    await async_client.post(
        "/api/v1/business/records",
        json={"record_type": "income", "title": "First Invoice", "amount": 1000.0},
        headers=headers,
    )
    ov = (await async_client.get("/api/v1/analytics/overview", headers=headers)).json()["data"]
    assert ov["financial"]["total_income"] == 1000.0

    sup = await async_client.post(
        "/api/v1/support/requests",
        json={"subject": "Enable custom domain", "message": "Please help configure domain.", "category": "general"},
        headers=headers,
    )
    assert sup.status_code in (200, 201)


async def test_cf10_payment_approval_unlocks_onboarding_automation_and_modules(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    owner = await register_and_login(async_client, full_name="Gate Toggle Owner")
    tenant = await create_tenant(async_client, owner["headers"], name="GateToggleCo", industry="Clinics / Hospitals")
    headers = tenant["headers"]

    await subscribe_service(async_client, headers, "whatsapp-business-concierge")
    await async_client.post(
        "/api/v1/integrations/whatsapp/connect",
        json={"oauth_code": "wa_gate_123"},
        headers=headers,
    )
    await async_client.post(
        "/api/v1/integrations/google_calendar/connect",
        json={"oauth_code": "gcal_gate_123"},
        headers=headers,
    )
    await async_client.post(
        "/api/v1/integrations/booking_provider/connect",
        json={"api_key": "bk_gate_123", "account_identifier": "clinic-cal"},
        headers=headers,
    )

    pre_req = (await async_client.get("/api/v1/integrations/onboarding-requirements", headers=headers)).json()["data"]
    assert pre_req["automation_active"] is False

    await approve_tenant_payment(async_client, super_admin_headers, tenant["id"])

    post_req = (await async_client.get("/api/v1/integrations/onboarding-requirements", headers=headers)).json()["data"]
    assert post_req["automation_active"] is True

    post_ov = (await async_client.get(f"/api/v1/tenants/{tenant['id']}/overview", headers=headers)).json()["data"]
    assert post_ov["is_payment_approved"] is True
    assert "whatsapp_concierge" in post_ov["enabled_modules"]
