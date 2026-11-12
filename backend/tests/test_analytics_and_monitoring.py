import pytest
from app.automation.budget_manager import budget_manager
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_executive_analytics_usage_audit_logs_and_admin_circuit_reset():
    """Verify cross-engine analytics overview, AI token usage telemetry, audit logs, users/me, subscriptions, and admin circuit reset."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": "exec@enterpriseanalytics.io",
            "password": "Password123!",
            "full_name": "Executive Founder",
        })
        token = reg.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 1. Verify /api/v1/users/me GET and PATCH
        me_res = await client.get("/api/v1/users/me", headers=auth_headers)
        assert me_res.status_code == 200
        assert me_res.json()["email"] == "exec@enterpriseanalytics.io"

        patch_me = await client.patch("/api/v1/users/me", json={
            "full_name": "Executive Founder Updated",
            "phone": "+15559990000",
        }, headers=auth_headers)
        assert patch_me.status_code == 200
        assert patch_me.json()["full_name"] == "Executive Founder Updated"

        # 2. Create tenant workspace
        t_res = await client.post("/api/v1/tenants", json={
            "name": "Apex Executive Group",
            "slug": "apex-executive-group",
            "industry": "Consulting",
        }, headers=auth_headers)
        tenant_id = t_res.json()["id"]
        budget_manager.admin_reset_circuit(tenant_id)
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # 3. Create service & test /api/v1/subscriptions endpoints
        srv_res = await client.post("/api/v1/services", json={
            "name": "AI Executive Intelligence Suite",
            "slug": "ai-exec-suite",
            "category": "analytics",
            "description": "Cross-engine analytics and reporting",
            "active": True,
        }, headers=auth_headers)
        service_id = srv_res.json()["id"]

        sub_create = await client.post("/api/v1/subscriptions", json={
            "service_id": service_id,
            "plan_name": "enterprise",
            "billing_interval": "monthly",
            "price": 199.0,
        }, headers=headers)
        assert sub_create.status_code == 201
        sub_id = sub_create.json()["id"]

        sub_list = await client.get("/api/v1/subscriptions", headers=headers)
        assert sub_list.status_code == 200
        assert len(sub_list.json()) == 1

        sub_patch = await client.patch(f"/api/v1/subscriptions/{sub_id}", json={
            "plan_name": "enterprise_plus",
        }, headers=headers)
        assert sub_patch.status_code == 200
        assert sub_patch.json()["plan_name"] == "enterprise_plus"

        # 4. Generate financial, marketing, and AI agent activity
        await client.post("/api/v1/business/records", json={
            "record_type": "income",
            "title": "Q4 Retainer Fee",
            "amount": 5000.0,
            "currency": "USD",
        }, headers=headers)

        await client.post("/api/v1/tasks", json={
            "task_type": "whatsapp_reply",
            "input": {"prompt": "Acknowledge client retainer receipt"},
            "execute_immediately": True,
        }, headers=headers)

        # 5. Verify /api/v1/analytics/overview
        ov_res = await client.get("/api/v1/analytics/overview", headers=headers)
        assert ov_res.status_code == 200
        ov_data = ov_res.json()["data"]
        assert ov_data["financial"]["total_income"] == 5000.0
        assert ov_data["ai_governance"]["total_executions"] >= 1
        assert ov_data["ai_governance"]["tokens_used_today"] > 0

        # 6. Verify /api/v1/analytics/usage
        usage_res = await client.get("/api/v1/analytics/usage", headers=headers)
        assert usage_res.status_code == 200
        usage_data = usage_res.json()["data"]
        assert len(usage_data["records"]) >= 1
        assert usage_data["quota"]["tokens_used_today"] > 0

        # 7. Verify /api/v1/analytics/audit-logs
        audit_res = await client.get("/api/v1/analytics/audit-logs", headers=headers)
        assert audit_res.status_code == 200
        audit_logs = audit_res.json()["data"]
        assert len(audit_logs) >= 2

        # 8. Trip circuit breaker and verify Admin reset endpoint + DLQ endpoint
        for _ in range(3):
            budget_manager.record_failure(tenant_id, "Simulated failure")
        assert budget_manager.get_or_create_record(tenant_id).circuit_state.value == "OPEN"

        reset_res = await client.post(
            f"/api/v1/admin/tenants/{tenant_id}/reset-circuit",
            headers=auth_headers,
        )
        assert reset_res.status_code == 200
        assert reset_res.json()["data"]["circuit_state"] == "CLOSED"

        dlq_res = await client.get("/api/v1/admin/dlq", headers=auth_headers)
        assert dlq_res.status_code == 200
        assert dlq_res.json()["success"] is True
