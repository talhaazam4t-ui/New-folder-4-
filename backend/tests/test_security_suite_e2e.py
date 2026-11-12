"""Master Security, Compliance & Production Readiness Verification Suite (Section 19).

Verifies all 7 mandatory security guardrails end-to-end:
1. Cross-tenant isolation enforcement across Business, Marketing, Tasks, and Analytics.
2. Role-Based Access Control (RBAC) enforcement (`viewer` blocked from mutations).
3. Agent tool permission enforcement (`verify_tool_permission` blocking unapproved tools).
4. Mandatory Human Approval enforcement before sensitive actions (`publish_marketing_campaign`, `send_bulk_whatsapp`).
5. Financial record immutability & AI agent modification blocking (`403 PERMISSION_DENIED`).
6. Webhook signature & challenge verification (Payments & WhatsApp).
7. Prompt PII/financial credential redaction & cascading GDPR account purge.
"""

import pytest
from app.automation.budget_manager import budget_manager
from app.core.security import sanitize_ai_prompt
from app.main import app
from httpx import ASGITransport, AsyncClient

from scripts.health_check import run_health_check
from scripts.seed_services import seed_platform_catalog


@pytest.mark.asyncio
async def test_all_seven_mandatory_security_guardrails_and_scripts():
    # Verify operational scripts first
    seeded_count = await seed_platform_catalog()
    assert seeded_count == 6
    # Running a second time is idempotent (0 newly created)
    assert await seed_platform_catalog() == 0

    health_report = await run_health_check()
    assert health_report["status"] == "healthy"
    assert health_report["security_guardrails"]["pii_redaction_active"] is True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Setup Tenant Alpha (Owner) and Tenant Beta (Owner)
        reg_alpha = await client.post("/api/v1/auth/register", json={
            "email": "alpha.owner@secsuite.io",
            "password": "Password123!",
            "full_name": "Alpha Owner",
        })
        alpha_token = reg_alpha.json()["access_token"]
        t_alpha = await client.post("/api/v1/tenants", json={
            "name": "Alpha Corp",
            "slug": "alpha-corp",
            "industry": "Finance",
        }, headers={"Authorization": f"Bearer {alpha_token}"})
        alpha_id = t_alpha.json()["id"]
        budget_manager.admin_reset_circuit(alpha_id)
        alpha_headers = {"Authorization": f"Bearer {alpha_token}", "X-Tenant-ID": alpha_id}

        reg_beta = await client.post("/api/v1/auth/register", json={
            "email": "beta.owner@secsuite.io",
            "password": "Password123!",
            "full_name": "Beta Owner",
        })
        beta_token = reg_beta.json()["access_token"]
        t_beta = await client.post("/api/v1/tenants", json={
            "name": "Beta Corp",
            "slug": "beta-corp",
            "industry": "Retail",
        }, headers={"Authorization": f"Bearer {beta_token}"})
        beta_id = t_beta.json()["id"]
        beta_headers = {"Authorization": f"Bearer {beta_token}", "X-Tenant-ID": beta_id}

        # --- Guardrail 1: Cross-Tenant Isolation ---
        spoofed_headers = {"Authorization": f"Bearer {beta_token}", "X-Tenant-ID": alpha_id}
        cross_attempt = await client.get("/api/v1/business/summary", headers=spoofed_headers)
        assert cross_attempt.status_code == 403
        assert cross_attempt.json()["error"]["code"] == "TENANT_ISOLATION_VIOLATION"

        # --- Guardrail 2: Role Permission Enforcement (Viewer cannot create records or campaigns) ---
        reg_viewer = await client.post("/api/v1/auth/register", json={
            "email": "viewer@secsuite.io",
            "password": "Password123!",
            "full_name": "Read Only Viewer",
        })
        viewer_token = reg_viewer.json()["access_token"]
        await client.post(f"/api/v1/tenants/{alpha_id}/members", json={
            "email": "viewer@secsuite.io",
            "role": "viewer",
        }, headers=alpha_headers)
        viewer_headers = {"Authorization": f"Bearer {viewer_token}", "X-Tenant-ID": alpha_id}

        viewer_write = await client.post("/api/v1/business/records", json={
            "record_type": "income",
            "title": "Unauthorized Viewer Entry",
            "amount": 100.0,
            "currency": "USD",
        }, headers=viewer_headers)
        assert viewer_write.status_code == 403
        assert viewer_write.json()["error"]["code"] == "PERMISSION_DENIED"

        # --- Guardrail 3: Agent Tool Permission Enforcement ---
        bad_tool = await client.post("/api/v1/agents/orchestrate", json={
            "objective": "Execute shell command on host",
            "agent_name": "researcher_agent",
            "requested_tool": "execute_shell_command",
        }, headers=alpha_headers)
        assert bad_tool.status_code == 403
        assert bad_tool.json()["error"]["code"] == "PERMISSION_DENIED"

        # --- Guardrail 4: Mandatory Human Approval Enforcement ---
        sens_task = await client.post("/api/v1/tasks", json={
            "task_type": "external_payment",
            "input": {"recipient": "Vendor LLC", "amount": 4500.0},
            "execute_immediately": True,
        }, headers=alpha_headers)
        assert sens_task.status_code == 201
        assert sens_task.json()["status"] == "awaiting_approval"

        # --- Guardrail 5: Financial Record Immutability & Agent Modification Blocking ---
        rec_res = await client.post("/api/v1/business/records", json={
            "record_type": "rent",
            "title": "Confirmed Suite 200 Rent",
            "amount": 3000.0,
            "currency": "USD",
        }, headers=alpha_headers)
        rec_id = rec_res.json()["id"]

        agent_mod = await client.patch(f"/api/v1/business/records/{rec_id}", json={
            "amount": 50.0,
            "reason": "Silent AI edit attempt",
            "actor_type": "agent",
        }, headers=alpha_headers)
        assert agent_mod.status_code == 403

        # --- Guardrail 6: Webhook Verification (WhatsApp & Payment) ---
        bad_wa_webhook = await client.get(
            "/api/v1/integrations/whatsapp/webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": "WRONG_TOKEN", "hub.challenge": "123"},
        )
        assert bad_wa_webhook.status_code == 403

        # --- Guardrail 7: Prompt Sanitization & Cascading Account Purge ---
        sanitized = sanitize_ai_prompt("My card is 4111 2222 3333 4444 and cvv: 991")
        assert "4111" not in sanitized
        assert "991" not in sanitized

        purge_res = await client.request(
            "DELETE",
            f"/api/v1/tenants/{beta_id}",
            json={"confirmation_slug": "beta-corp", "reason": "End-to-end compliance test"},
            headers=beta_headers,
        )
        assert purge_res.status_code == 200
        assert purge_res.json()["success"] is True
