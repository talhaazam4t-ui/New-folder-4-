"""Tier 1 E2E Tests — Services 4, 5, and 6 Happy Paths (F5–F7)."""

from __future__ import annotations

from e2e_helpers import onboard_paid_tenant
from httpx import AsyncClient

# =============================================================================
# Service 4: multi-agent-orchestration (6 tests)
# =============================================================================


async def test_s4_agents_list_returns_eight_canonical_agents(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["multi-agent-orchestration"],
        industry="Financing",
    )
    res = await async_client.get("/api/v1/agents", headers=ctx["headers"])
    assert res.status_code == 200, res.text
    agents = res.json()
    names = {a["name"] for a in agents}
    assert len(names) == 8
    assert names == {
        "master_orchestrator",
        "planner_agent",
        "researcher_agent",
        "executor_agent",
        "reviewer_agent",
        "finance_tracker_agent",
        "campaign_strategist_agent",
        "whatsapp_concierge_agent",
    }


async def test_s4_agents_orchestrate_master_four_stages_and_persists_telemetry(
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

    orch_res = await async_client.post(
        "/api/v1/agents/orchestrate",
        json={
            "objective": "Prepare a monthly cashflow stabilization plan",
            "agent_name": "master_orchestrator",
        },
        headers=headers,
    )
    assert orch_res.status_code == 200, orch_res.text
    body = orch_res.json()
    assert body["status"] == "completed"
    assert body["requires_approval"] is False
    assert [s["agent_name"] for s in body["stages"]] == [
        "planner_agent",
        "researcher_agent",
        "executor_agent",
        "reviewer_agent",
    ]
    assert body["total_tokens"] > 0
    assert body["final_output"]

    execs = (await async_client.get("/api/v1/agents/executions", headers=headers)).json()
    assert len(execs) >= 1

    usage = (await async_client.get("/api/v1/analytics/usage", headers=headers)).json()["data"]
    assert len(usage["records"]) >= 4


async def test_s4_agents_sensitive_action_awaits_approval_and_resumes(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["multi-agent-orchestration"],
        industry="E-Commerce",
    )
    headers = ctx["headers"]

    orch_res = await async_client.post(
        "/api/v1/agents/orchestrate",
        json={
            "objective": "Publish multi-channel holiday campaign",
            "agent_name": "master_orchestrator",
            "action_type": "publish_marketing_campaign",
            "context_data": {"budget": 2000},
        },
        headers=headers,
    )
    assert orch_res.status_code == 200, orch_res.text
    orch = orch_res.json()
    assert orch["status"] == "awaiting_approval"
    assert orch["requires_approval"] is True
    assert orch["approval_id"] is not None

    approve_res = await async_client.post(
        f"/api/v1/approvals/{orch['approval_id']}/approve",
        json={"reason": "Budget verified by owner"},
        headers=headers,
    )
    assert approve_res.status_code == 200, approve_res.text
    res_data = approve_res.json()["data"]
    assert res_data["approval"]["status"] == "approved"
    assert res_data["task"]["status"] == "completed"


async def test_s4_agents_sensitive_approval_reject_cancels_linked_task(
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

    orch = (
        await async_client.post(
            "/api/v1/agents/orchestrate",
            json={
                "objective": "Issue bulk refund batch",
                "agent_name": "master_orchestrator",
                "action_type": "refund_payment",
            },
            headers=headers,
        )
    ).json()
    assert orch["status"] == "awaiting_approval"

    rej_res = await async_client.post(
        f"/api/v1/approvals/{orch['approval_id']}/reject",
        json={"reason": "Duplicate batch"},
        headers=headers,
    )
    assert rej_res.status_code == 200, rej_res.text
    assert rej_res.json()["status"] == "rejected"

    task_res = await async_client.get(f"/api/v1/tasks/{orch['task_id']}", headers=headers)
    assert task_res.status_code == 200
    assert task_res.json()["status"] == "cancelled"


async def test_s4_tasks_create_and_execute_lifecycle(
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

    create_res = await async_client.post(
        "/api/v1/tasks",
        json={
            "task_type": "financial_analysis",
            "agent_name": "finance_tracker_agent",
            "input": {"prompt": "Summarize weekly operating expenses"},
            "priority": 5,
        },
        headers=headers,
    )
    assert create_res.status_code == 201, create_res.text
    task = create_res.json()

    exec_res = await async_client.post(f"/api/v1/tasks/{task['id']}/execute", headers=headers)
    assert exec_res.status_code == 200, exec_res.text
    assert exec_res.json()["status"] == "completed"

    list_res = await async_client.get("/api/v1/tasks", headers=headers)
    assert list_res.status_code == 200
    assert any(t["id"] == task["id"] for t in list_res.json())


async def test_s4_agents_configure_by_super_admin_updates_limits(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["multi-agent-orchestration"],
        industry="Financing",
    )
    admin_tenant_headers = {**super_admin_headers, "X-Tenant-ID": ctx["tenant_id"]}

    cfg_res = await async_client.post(
        "/api/v1/agents/researcher_agent/configure",
        json={"enabled": True, "execution_limit": 250, "budget_limit": 125.0},
        headers=admin_tenant_headers,
    )
    assert cfg_res.status_code == 200, cfg_res.text
    cfg = cfg_res.json()
    assert cfg["execution_limit"] == 250
    assert cfg["budget_limit"] == 125.0


# =============================================================================
# Service 5: lead-crm-qualification (6 tests)
# =============================================================================


async def test_s5_leads_create_and_qualify_updates_score_and_status(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["lead-crm-qualification"],
        industry="Real Estate / Property",
    )
    headers = ctx["headers"]

    lead_res = await async_client.post(
        "/api/v1/marketing/leads",
        json={
            "name": "Zainab Malik",
            "email": "zainab@example.com",
            "phone": "+923001112244",
            "source": "whatsapp",
            "notes": "Interested in 3-bedroom apartment financing",
        },
        headers=headers,
    )
    assert lead_res.status_code == 201, lead_res.text
    lead = lead_res.json()
    assert lead["status"] == "new"
    assert lead["qualification_score"] == 0.0

    qual_res = await async_client.post(f"/api/v1/marketing/leads/{lead['id']}/qualify", headers=headers)
    assert qual_res.status_code == 200, qual_res.text
    q_lead = qual_res.json()
    assert q_lead["qualification_score"] >= 70.0
    assert q_lead["status"] == "qualified"
    assert "ai_qualification_summary" in q_lead["metadata"]


async def test_s5_leads_generate_synthetic_demo_and_deduplication(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["lead-crm-qualification"],
        industry="Real Estate / Property",
    )
    headers = ctx["headers"]

    payload = {"industry": "Real Estate / Property", "location": "Dubai", "limit": 3}
    first = await async_client.post("/api/v1/marketing/leads/generate", json=payload, headers=headers)
    assert first.status_code == 200, first.text
    d1 = first.json()["data"]
    assert d1["data_source"] == "synthetic_demo"
    assert d1["created_count"] == 3

    second = await async_client.post("/api/v1/marketing/leads/generate", json=payload, headers=headers)
    assert second.status_code == 200, second.text
    d2 = second.json()["data"]
    assert d2["created_count"] == 0
    assert d2["skipped_duplicates"] == 3


async def test_s5_leads_outreach_whatsapp_immediate_send(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["lead-crm-qualification"],
        industry="Real Estate / Property",
        connect_integrations=["whatsapp"],
    )
    headers = ctx["headers"]

    lead = (
        await async_client.post(
            "/api/v1/marketing/leads",
            json={"name": "Tariq Buyer", "phone": "+923009998877", "source": "website"},
            headers=headers,
        )
    ).json()

    outreach = await async_client.post(
        f"/api/v1/marketing/leads/{lead['id']}/outreach",
        json={"channel": "whatsapp", "custom_context": "Follow up on penthouse tour", "require_approval": False},
        headers=headers,
    )
    assert outreach.status_code == 200, outreach.text
    data = outreach.json()["data"]
    assert data["status"] == "sent"
    assert data["messages_sent_count"] == 1
    assert data["message_sent"]


async def test_s5_leads_outreach_require_approval_queues_approval(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["lead-crm-qualification"],
        industry="Real Estate / Property",
        connect_integrations=["whatsapp"],
    )
    headers = ctx["headers"]

    lead = (
        await async_client.post(
            "/api/v1/marketing/leads",
            json={"name": "Hina Prospect", "phone": "+923008887766", "source": "referral"},
            headers=headers,
        )
    ).json()

    outreach = await async_client.post(
        f"/api/v1/marketing/leads/{lead['id']}/outreach",
        json={"channel": "whatsapp", "require_approval": True},
        headers=headers,
    )
    assert outreach.status_code == 200, outreach.text
    data = outreach.json()["data"]
    assert data["status"] == "awaiting_approval"
    assert data["approval_id"] is not None
    assert data["draft_message"]


async def test_s5_leads_book_appointment_preserves_scheduled_iso(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["lead-crm-qualification"],
        industry="Clinics / Hospitals",
        connect_integrations=["google_calendar"],
    )
    headers = ctx["headers"]

    lead = (
        await async_client.post(
            "/api/v1/marketing/leads",
            json={"name": "Dr. Naveed", "email": "naveed@clinic.example.com", "source": "whatsapp"},
            headers=headers,
        )
    ).json()

    requested_iso = "2026-12-05T14:30:00Z"
    book_res = await async_client.post(
        f"/api/v1/marketing/leads/{lead['id']}/book-appointment",
        json={"meeting_title": "Dental Implant Consultation", "scheduled_iso": requested_iso},
        headers=headers,
    )
    assert book_res.status_code == 200, book_res.text
    data = book_res.json()["data"]
    assert data["meeting_booked"] is True
    assert data["status"] == "converted"
    cal_start = str(data["calendar_event"].get("start_time", ""))
    assert cal_start.startswith("2026-12-05T14:30:00"), (
        f"Expected calendar_event.start_time to honor requested scheduled_iso '{requested_iso}', got '{cal_start}'"
    )


async def test_s5_leads_patch_update_and_status_filter_query(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["lead-crm-qualification"],
        industry="E-Commerce",
    )
    headers = ctx["headers"]

    l1 = (
        await async_client.post(
            "/api/v1/marketing/leads",
            json={"name": "Lead One", "email": "one@example.com"},
            headers=headers,
        )
    ).json()
    await async_client.post(
        "/api/v1/marketing/leads",
        json={"name": "Lead Two", "email": "two@example.com"},
        headers=headers,
    )

    patch_res = await async_client.patch(
        f"/api/v1/marketing/leads/{l1['id']}",
        json={"status": "qualified", "qualification_score": 88.5, "metadata": {"notes": "VIP buyer"}},
        headers=headers,
    )
    assert patch_res.status_code == 200, patch_res.text
    assert patch_res.json()["status"] == "qualified"
    assert patch_res.json()["qualification_score"] == 88.5

    filtered = (await async_client.get("/api/v1/marketing/leads", params={"status": "qualified"}, headers=headers)).json()
    assert len(filtered) == 1
    assert filtered[0]["id"] == l1["id"]


# =============================================================================
# Service 6: executive-analytics-compliance (6 tests)
# =============================================================================


async def test_s6_analytics_overview_aggregates_finance_marketing_and_ai_governance(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=[
            "business-financial-tracking",
            "lead-crm-qualification",
            "multi-agent-orchestration",
            "executive-analytics-compliance",
        ],
        industry="Financing",
    )
    headers = ctx["headers"]

    await async_client.post(
        "/api/v1/business/records",
        json={"record_type": "income", "title": "Consulting", "amount": 2000.0, "currency": "USD"},
        headers=headers,
    )
    await async_client.post(
        "/api/v1/marketing/leads",
        json={"name": "Exec Prospect", "email": "exec@example.com"},
        headers=headers,
    )
    await async_client.post(
        "/api/v1/agents/orchestrate",
        json={"objective": "Executive risk review", "agent_name": "master_orchestrator"},
        headers=headers,
    )

    ov_res = await async_client.get("/api/v1/analytics/overview", headers=headers)
    assert ov_res.status_code == 200, ov_res.text
    ov = ov_res.json()["data"]
    assert ov["financial"]["total_income"] >= 2000.0
    assert ov["marketing"]["total_leads"] >= 1
    assert ov["ai_governance"]["total_executions"] >= 1
    assert ov["ai_governance"]["tokens_used_today"] > 0


async def test_s6_analytics_usage_returns_db_usage_records_and_quota(
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

    await async_client.post(
        "/api/v1/agents/orchestrate",
        json={"objective": "Generate board briefing", "agent_name": "planner_agent"},
        headers=headers,
    )

    usage_res = await async_client.get("/api/v1/analytics/usage", headers=headers)
    assert usage_res.status_code == 200, usage_res.text
    data = usage_res.json()["data"]
    assert data["quota"]["tokens_used_today"] > 0
    assert len(data["records"]) >= 1
    assert all(r["total_tokens"] > 0 for r in data["records"])


async def test_s6_analytics_audit_logs_and_action_filter(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["business-financial-tracking", "executive-analytics-compliance"],
        industry="Financing",
    )
    headers = ctx["headers"]

    await async_client.post(
        "/api/v1/business/records",
        json={"record_type": "expense", "title": "Audit Test Expense", "amount": 100.0, "currency": "USD"},
        headers=headers,
    )

    all_logs = (await async_client.get("/api/v1/analytics/audit-logs", headers=headers)).json()["data"]
    assert len(all_logs) >= 1
    target_action = all_logs[0]["action"]

    filtered_logs = (
        await async_client.get("/api/v1/analytics/audit-logs", params={"action": target_action}, headers=headers)
    ).json()["data"]
    assert len(filtered_logs) >= 1
    assert all(row["action"] == target_action for row in filtered_logs)


async def test_s6_tenant_overview_returns_canonical_modules_and_metrics(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["executive-analytics-compliance", "business-financial-tracking"],
        industry="Financing",
    )
    res = await async_client.get(f"/api/v1/tenants/{ctx['tenant_id']}/overview", headers=ctx["headers"])
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["is_payment_approved"] is True
    assert "executive_analytics_compliance" in data["enabled_modules"]
    assert "financial_ledger" in data["enabled_modules"]


async def test_s6_analytics_digest_generates_executive_summary_in_sandbox(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["executive-analytics-compliance", "business-financial-tracking"],
        industry="Financing",
    )
    headers = ctx["headers"]

    await async_client.post(
        "/api/v1/business/records",
        json={"record_type": "income", "title": "Digest Income", "amount": 3200.0, "currency": "USD"},
        headers=headers,
    )

    digest_res = await async_client.post(
        "/api/v1/analytics/digest",
        json={"period": "weekly"},
        headers=headers,
    )
    assert digest_res.status_code == 200, digest_res.text
    body = digest_res.json()
    assert body["success"] is True
    data = body["data"]
    assert "summary" in data or "digest" in data or "financial" in data


async def test_s6_analytics_export_csv_and_json_compliance_reports(
    async_client: AsyncClient,
    super_admin_headers: dict[str, str],
) -> None:
    ctx = await onboard_paid_tenant(
        async_client,
        super_admin_headers,
        service_slugs=["executive-analytics-compliance"],
        industry="Financing",
    )
    headers = ctx["headers"]

    csv_res = await async_client.get("/api/v1/analytics/export", params={"format": "csv"}, headers=headers)
    assert csv_res.status_code == 200, csv_res.text
    assert "text/csv" in csv_res.headers.get("content-type", "")
    assert len(csv_res.text.strip()) > 0

    json_res = await async_client.get("/api/v1/analytics/export", params={"format": "json"}, headers=headers)
    assert json_res.status_code == 200, json_res.text
    payload = json_res.json()
    assert isinstance(payload, (dict, list))
