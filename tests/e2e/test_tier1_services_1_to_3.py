"""Tier 1 E2E Tests — Services 1, 2, and 3 Happy Paths (F2–F4)."""

from __future__ import annotations

from datetime import date

from e2e_helpers import get_raw_integration_config, onboard_paid_tenant, settings
from httpx import AsyncClient

# =============================================================================
# Service 1: business-financial-tracking (6 tests)
# =============================================================================


async def test_s1_finance_status_active_and_account_creation(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["business-financial-tracking"],
        industry="Financing",
        tenant_name="FinTrack Co",
    )
    headers = ctx["headers"]

    status_res = await async_client.get("/api/v1/finance/status", headers=headers)
    assert status_res.status_code == 200, status_res.text
    assert status_res.json()["data"]["active"] is True
    assert status_res.json()["data"]["status"] == "ACTIVE"

    acc_res = await async_client.post(
        "/api/v1/finance/accounts",
        json={"name": "Operating USD Bank", "currency": "USD", "current_balance": 2500.0},
        headers=headers,
    )
    assert acc_res.status_code == 201, acc_res.text
    acc = acc_res.json()
    assert acc["name"] == "Operating USD Bank"
    assert acc["current_balance"] == 2500.0

    list_res = await async_client.get("/api/v1/finance/accounts", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1


async def test_s1_finance_transactions_paid_and_pending_update_balance(
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

    acc = (
        await async_client.post(
            "/api/v1/finance/accounts",
            json={"name": "Main Cash", "currency": "USD", "current_balance": 1000.0},
            headers=headers,
        )
    ).json()

    tx_paid = await async_client.post(
        "/api/v1/finance/transactions",
        json={
            "account_id": acc["id"],
            "type": "income",
            "category": "Client Retainer",
            "amount": 500.0,
            "currency": "USD",
            "status": "paid",
            "counterparty_name": "Client Alpha",
        },
        headers=headers,
    )
    assert tx_paid.status_code == 201, tx_paid.text

    tx_pending = await async_client.post(
        "/api/v1/finance/transactions",
        json={
            "account_id": acc["id"],
            "type": "rent",
            "category": "Property Rent",
            "amount": 300.0,
            "currency": "USD",
            "status": "pending",
            "counterparty_name": "Tenant Unit 4B",
        },
        headers=headers,
    )
    assert tx_pending.status_code == 201, tx_pending.text
    pending_id = tx_pending.json()["id"]

    # Balance should be 1000 + 500 = 1500 (pending transaction must not credit yet)
    accounts = (await async_client.get("/api/v1/finance/accounts", headers=headers)).json()
    assert accounts[0]["current_balance"] == 1500.0

    # Mark pending rent as paid -> balance becomes 1800
    patch_res = await async_client.patch(
        f"/api/v1/finance/transactions/{pending_id}",
        json={"status": "paid"},
        headers=headers,
    )
    assert patch_res.status_code == 200, patch_res.text
    accounts_after = (await async_client.get("/api/v1/finance/accounts", headers=headers)).json()
    assert accounts_after[0]["current_balance"] == 1800.0


async def test_s1_finance_rent_schedule_and_whatsapp_reminder_dispatch(
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

    today = date.today()
    safe_billing_day = min(today.day, 28)
    sched_res = await async_client.post(
        "/api/v1/finance/rent-schedules",
        json={
            "property_unit": "Tower A - Unit 12",
            "lessee_name": "Hamza Tariq",
            "lessee_whatsapp": "+923001234567",
            "monthly_rent": 45000.0,
            "currency": "PKR",
            "billing_day": safe_billing_day,
            "auto_remind_whatsapp": True,
            "status": "active",
        },
        headers=headers,
    )
    assert sched_res.status_code == 201, sched_res.text

    rem_res = await async_client.post("/api/v1/finance/whatsapp/reminders", headers=headers)
    assert rem_res.status_code == 200, rem_res.text
    body = rem_res.json()
    assert body["total_scanned"] >= 1
    assert body["reminders_dispatched"] >= 1
    assert any(r["lessee_name"] == "Hamza Tariq" for r in body["results"])


async def test_s1_finance_summary_usd_kpis_and_chart(
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

    acc = (
        await async_client.post(
            "/api/v1/finance/accounts",
            json={"name": "USD Treasury", "currency": "USD", "current_balance": 1000.0},
            headers=headers,
        )
    ).json()

    await async_client.post(
        "/api/v1/finance/transactions",
        json={
            "account_id": acc["id"],
            "type": "income",
            "category": "Consulting",
            "amount": 1200.0,
            "currency": "USD",
            "status": "paid",
            "counterparty_name": "Beta LLC",
        },
        headers=headers,
    )
    await async_client.post(
        "/api/v1/finance/transactions",
        json={
            "account_id": acc["id"],
            "type": "expense",
            "category": "Cloud Hosting",
            "amount": 200.0,
            "currency": "USD",
            "status": "paid",
            "counterparty_name": "Render Cloud",
        },
        headers=headers,
    )

    sum_res = await async_client.get("/api/v1/finance/summary", params={"currency": "USD"}, headers=headers)
    assert sum_res.status_code == 200, sum_res.text
    summary = sum_res.json()
    assert summary["currency"] == "USD"
    assert summary["total_cash_balance"] == 2000.0
    assert summary["monthly_revenue"] == 1200.0
    assert summary["monthly_expenses"] == 200.0
    assert summary["net_cash_flow"] == 1000.0
    assert isinstance(summary["monthly_chart"], list)


async def test_s1_finance_export_csv_contains_transactions(
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

    await async_client.post(
        "/api/v1/finance/transactions",
        json={
            "type": "income",
            "category": "Retainer",
            "amount": 750.0,
            "currency": "USD",
            "status": "paid",
            "counterparty_name": "CSV Counterparty Inc",
        },
        headers=headers,
    )

    csv_res = await async_client.get("/api/v1/finance/export/csv", headers=headers)
    assert csv_res.status_code == 200, csv_res.text
    assert "text/csv" in csv_res.headers.get("content-type", "")
    assert "CSV Counterparty Inc" in csv_res.text
    assert "750" in csv_res.text


async def test_s1_business_records_import_reports_and_tenant_overview_bridge(
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

    rec_res = await async_client.post(
        "/api/v1/business/records",
        json={
            "record_type": "income",
            "title": "Q4 Advisory Fee",
            "amount": 1500.0,
            "currency": "USD",
            "source": "manual",
        },
        headers=headers,
    )
    assert rec_res.status_code == 201, rec_res.text

    imp_res = await async_client.post(
        "/api/v1/business/import",
        json={
            "records": [
                {"record_type": "expense", "title": "Software License", "amount": 250.0, "currency": "USD"},
                {"record_type": "rent", "title": "Office Suite Rent", "amount": 500.0, "currency": "USD"},
            ]
        },
        headers=headers,
    )
    assert imp_res.status_code == 201, imp_res.text
    assert len(imp_res.json()) == 2

    sum_res = await async_client.get("/api/v1/business/summary", headers=headers)
    assert sum_res.status_code == 200
    assert sum_res.json()["record_count"] == 3
    assert sum_res.json()["total_expenses"] == 250.0

    rep_res = await async_client.get("/api/v1/business/reports", headers=headers)
    assert rep_res.status_code == 200
    assert "Q4 Advisory Fee" in rep_res.json()["data"]["csv_content"]

    overview = await async_client.get(f"/api/v1/tenants/{ctx['tenant_id']}/overview", headers=headers)
    assert overview.status_code == 200
    metrics = overview.json()["data"]["metrics"]
    assert metrics["income"] >= 2000.0
    assert metrics["expenses"] >= 250.0


# =============================================================================
# Service 2: ai-marketing-growth (6 tests)
# =============================================================================


async def test_s2_marketing_competitor_research_returns_analysis_and_persists(
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

    res = await async_client.post(
        "/api/v1/marketing/research/competitors",
        json={"industry": "E-Commerce", "competitors": ["BrandOne", "BrandTwo"], "region": "MENA"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["analysis"]
    assert data["tokens_used"] > 0

    logs_res = await async_client.get("/api/v1/analytics/audit-logs", headers=headers)
    assert logs_res.status_code == 200
    assert any("research" in row["action"] or "competitor" in str(row) for row in logs_res.json()["data"]), (
        "Expected competitor research run to be persisted in audit/history"
    )


async def test_s2_marketing_audience_research_returns_personas_and_persists(
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

    res = await async_client.post(
        "/api/v1/marketing/research/audience",
        json={"product_or_service": "Skincare Bundles", "target_industry": "E-Commerce", "price_point": "$79"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["personas"]
    assert data["tokens_used"] > 0

    logs_res = await async_client.get("/api/v1/analytics/audit-logs", headers=headers)
    assert logs_res.status_code == 200
    assert any("audience" in row["action"] or "research" in str(row) for row in logs_res.json()["data"]), (
        "Expected audience research run to be persisted in audit/history"
    )


async def test_s2_marketing_content_generate_includes_provider_and_persists(
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

    res = await async_client.post(
        "/api/v1/marketing/content/generate",
        json={
            "channel": "instagram",
            "topic": "Winter Collection Flash Sale",
            "tone": "energetic",
            "call_to_action": "Shop Now",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["generated_copy"]
    assert "provider" in data or "is_mock" in data or "mode" in data, (
        f"Expected provider/mode metadata in content generation response: {data}"
    )

    logs_res = await async_client.get("/api/v1/analytics/audit-logs", headers=headers)
    assert logs_res.status_code == 200
    assert any("content" in row["action"] or "marketing" in row["action"] for row in logs_res.json()["data"]), (
        "Expected generated marketing content to be persisted"
    )


async def test_s2_marketing_campaign_draft_creates_pending_approval(
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

    camp_res = await async_client.post(
        "/api/v1/marketing/campaigns",
        json={
            "name": "Q4 Festive Retargeting",
            "platform": "meta_ads",
            "objective": "conversions",
            "budget": 1200.0,
        },
        headers=headers,
    )
    assert camp_res.status_code == 201, camp_res.text
    camp = camp_res.json()
    assert camp["status"] == "draft"
    approval_id = camp["configuration"].get("approval_id")
    assert approval_id is not None

    approvals = (await async_client.get("/api/v1/approvals", params={"status": "pending"}, headers=headers)).json()
    assert any(a["id"] == approval_id for a in approvals)


async def test_s2_marketing_campaign_approve_endpoint_reconciles_approval(
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
            json={
                "name": "Spring Promo",
                "platform": "google_ads",
                "objective": "leads",
                "budget": 800.0,
            },
            headers=headers,
        )
    ).json()
    approval_id = camp["configuration"]["approval_id"]

    app_res = await async_client.post(f"/api/v1/marketing/campaigns/{camp['id']}/approve", headers=headers)
    assert app_res.status_code == 200, app_res.text
    assert app_res.json()["status"] == "active"

    approved_list = (
        await async_client.get("/api/v1/approvals", params={"status": "approved"}, headers=headers)
    ).json()
    assert any(a["id"] == approval_id for a in approved_list), (
        "Approving campaign via /marketing/campaigns/{id}/approve must resolve linked Approval"
    )


async def test_s2_approvals_approve_endpoint_activates_campaign_without_fake_metrics(
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
            json={
                "name": "Approval Driven Launch",
                "platform": "linkedin",
                "objective": "b2b_leads",
                "budget": 500.0,
            },
            headers=headers,
        )
    ).json()
    approval_id = camp["configuration"]["approval_id"]

    res = await async_client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"reason": "Approved from unified approvals inbox"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["approval"]["status"] == "approved"

    campaigns = (await async_client.get("/api/v1/marketing/campaigns", headers=headers)).json()
    target = next(c for c in campaigns if c["id"] == camp["id"])
    assert target["status"] == "active", "Approving linked Approval must activate MarketingCampaign"

    analytics = (await async_client.get("/api/v1/marketing/analytics", headers=headers)).json()
    assert analytics["active_campaigns"] == 1
    assert analytics["total_impressions"] == 0, (
        "Newly approved campaign must not fabricate 1200 hardcoded impressions"
    )


# =============================================================================
# Service 3: whatsapp-business-concierge (6 tests)
# =============================================================================


async def test_s3_whatsapp_connect_encrypts_at_rest_and_masks_in_api(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["whatsapp-business-concierge"],
        industry="Clinics / Hospitals",
    )
    headers = ctx["headers"]

    conn_res = await async_client.post(
        "/api/v1/integrations/whatsapp/connect",
        json={"oauth_code": "wa_secret_oauth_code_123"},
        headers=headers,
    )
    assert conn_res.status_code == 201, conn_res.text
    integ = conn_res.json()["data"]
    assert integ["status"] == "connected"
    cfg = integ["configuration"]
    assert cfg.get("access_token") == "***ENCRYPTED***"

    raw_cfg = await get_raw_integration_config(ctx["tenant_id"], "whatsapp")
    assert str(raw_cfg.get("access_token", "")).startswith("enc:v1:")


async def test_s3_whatsapp_webhook_get_verification_challenge(async_client: AsyncClient) -> None:
    challenge = "challenge_token_98765"
    res = await async_client.get(
        "/api/v1/integrations/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.whatsapp_verify_token,
            "hub.challenge": challenge,
        },
    )
    assert res.status_code == 200, res.text
    assert res.text == challenge


async def test_s3_whatsapp_inbound_unambiguous_payment_creates_business_record(
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

    sim_res = await async_client.post(
        "/api/v1/integrations/whatsapp/simulate",
        json={
            "sender_phone": "+923001112233",
            "sender_name": "Usman Tenant",
            "message_text": "Paid rent $1850 for Unit 12A",
            "message_id": "wamid.pay.001",
        },
        headers=headers,
    )
    assert sim_res.status_code == 200, sim_res.text
    triage = sim_res.json()["data"]
    assert triage["classification"] == "financial_confirmed"
    assert triage["requires_confirmation"] is False
    assert triage["business_record_id"] is not None

    records = (await async_client.get("/api/v1/business/records", headers=headers)).json()
    assert any(r["id"] == triage["business_record_id"] and r["amount"] == 1850.0 for r in records)


async def test_s3_whatsapp_inbound_inquiry_creates_lead_autoreply_and_history(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["whatsapp-business-concierge", "lead-crm-qualification", "executive-analytics-compliance"],
        industry="Clinics / Hospitals",
        connect_integrations=["whatsapp"],
    )
    headers = ctx["headers"]

    sim_res = await async_client.post(
        "/api/v1/integrations/whatsapp/simulate",
        json={
            "sender_phone": "+923007778899",
            "sender_name": "Ayesha Patient",
            "message_text": "Hello, do you have dental consultation slots tomorrow afternoon?",
            "message_id": "wamid.inq.001",
        },
        headers=headers,
    )
    assert sim_res.status_code == 200, sim_res.text
    triage = sim_res.json()["data"]
    assert triage["classification"] == "lead_inquiry"
    assert triage["lead_id"] is not None
    assert triage["auto_reply"]
    assert triage.get("reply_dispatched") is True or triage.get("outbound_message_id") is not None, (
        "Expected auto-reply to be dispatched via tenant-scoped WhatsApp client (mock/sandbox)"
    )

    leads = (await async_client.get("/api/v1/marketing/leads", headers=headers)).json()
    assert any(lead_row["id"] == triage["lead_id"] and lead_row["source"] == "whatsapp" for lead_row in leads)


async def test_s3_whatsapp_outbound_send_uses_mock_sandbox_safely(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["whatsapp-business-concierge"],
        industry="Clinics / Hospitals",
        connect_integrations=["whatsapp"],
    )
    headers = ctx["headers"]

    send_res = await async_client.post(
        "/api/v1/integrations/whatsapp/send",
        json={"to_phone": "+923005556677", "message_body": "Your clinic appointment is confirmed for 3 PM."},
        headers=headers,
    )
    assert send_res.status_code == 200, send_res.text
    data = send_res.json()["data"]
    assert data["success"] is True
    assert data["to"] == "+923005556677"
    assert data["is_mock"] is True
    assert data["message_id"]


async def test_s3_tenant_settings_patch_persists_concierge_and_booking_config(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["whatsapp-business-concierge"],
        industry="Clinics / Hospitals",
    )
    headers = ctx["headers"]

    patch_res = await async_client.patch(
        f"/api/v1/tenants/{ctx['tenant_id']}",
        json={
            "settings": {
                "booking_provider": "calendly",
                "concierge_tone": "warm_clinical",
                "business_hours": "09:00-18:00",
            }
        },
        headers=headers,
    )
    assert patch_res.status_code == 200, patch_res.text
    updated_settings = patch_res.json()["settings"]
    assert updated_settings["booking_provider"] == "calendly"
    assert updated_settings["concierge_tone"] == "warm_clinical"
