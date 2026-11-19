import pytest
from app.automation.budget_manager import budget_manager
from app.config import settings
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_multi_agent_orchestration_pipeline_and_telemetry():
    """Verify 4-stage Master Orchestrator pipeline (Planner -> Researcher -> Executor -> Reviewer) and telemetry."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": "cto@multiagent.ai",
            "password": "Password123!",
            "full_name": "CTO MultiAgent",
        })
        token = reg.json()["access_token"]
        t_res = await client.post("/api/v1/tenants", json={
            "name": "Nexus AI Operations",
            "slug": "nexus-ai-ops",
            "industry": "Technology",
        }, headers={"Authorization": f"Bearer {token}"})
        tenant_id = t_res.json()["id"]
        budget_manager.admin_reset_circuit(tenant_id)
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # 1. List registered agents
        list_res = await client.get("/api/v1/agents", headers=headers)
        assert list_res.status_code == 200
        agents = list_res.json()
        assert len(agents) == 8
        agent_names = {a["name"] for a in agents}
        assert "master_orchestrator" in agent_names
        assert "finance_tracker_agent" in agent_names
        assert "campaign_strategist_agent" in agent_names
        assert "whatsapp_concierge_agent" in agent_names

        # 2. Execute full 4-stage MasterOrchestrator pipeline
        orch_res = await client.post("/api/v1/agents/orchestrate", json={
            "objective": "Prepare a monthly rent reconciliation summary and draft polite tenant reminders.",
            "agent_name": "master_orchestrator",
        }, headers=headers)
        assert orch_res.status_code == 200
        orch_data = orch_res.json()
        assert orch_data["status"] == "completed"
        assert orch_data["requires_approval"] is False
        assert len(orch_data["stages"]) == 4
        assert [s["agent_name"] for s in orch_data["stages"]] == [
            "planner_agent",
            "researcher_agent",
            "executor_agent",
            "reviewer_agent",
        ]
        assert orch_data["total_tokens"] > 0

        # 3. Verify execution telemetry logged
        exec_res = await client.get("/api/v1/agents/executions", headers=headers)
        assert exec_res.status_code == 200
        execs = exec_res.json()
        assert len(execs) >= 1
        assert execs[0]["task_id"] == orch_data["task_id"]


@pytest.mark.asyncio
async def test_agent_tool_permission_disable_and_approval_gates(monkeypatch):
    """Verify unauthorized tool blocking, disabled agent blocking, and sensitive action approval interception."""
    monkeypatch.setattr(
        settings,
        "super_admin_emails",
        [*settings.super_admin_emails, "sec@multiagent.ai"],
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": "sec@multiagent.ai",
            "password": "Password123!",
            "full_name": "Security Officer",
        })
        token = reg.json()["access_token"]
        t_res = await client.post("/api/v1/tenants", json={
            "name": "Fortress Holdings",
            "slug": "fortress-holdings",
            "industry": "Finance",
        }, headers={"Authorization": f"Bearer {token}"})
        tenant_id = t_res.json()["id"]
        budget_manager.admin_reset_circuit(tenant_id)
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # 1. Verify unauthorized tool call is blocked with 403 PERMISSION_DENIED
        unauth_tool = await client.post("/api/v1/agents/orchestrate", json={
            "objective": "Delete confirmed ledger rows directly",
            "agent_name": "finance_tracker_agent",
            "requested_tool": "modify_confirmed_ledger",
        }, headers=headers)
        assert unauth_tool.status_code == 403
        assert unauth_tool.json()["error"]["code"] == "PERMISSION_DENIED"

        # 2. Disable `whatsapp_concierge_agent` for this tenant and verify execution is blocked
        cfg_res = await client.post("/api/v1/agents/whatsapp_concierge_agent/configure", json={
            "enabled": False,
            "execution_limit": 500,
            "budget_limit": 25.0,
        }, headers=headers)
        assert cfg_res.status_code == 200
        assert cfg_res.json()["enabled_for_tenant"] is False

        disabled_run = await client.post("/api/v1/agents/orchestrate", json={
            "objective": "Reply to customer message",
            "agent_name": "whatsapp_concierge_agent",
        }, headers=headers)
        assert disabled_run.status_code == 403
        assert disabled_run.json()["error"]["code"] == "PERMISSION_DENIED"

        # 3. Verify sensitive orchestration (`publish_marketing_campaign`) is intercepted for human approval
        sens_run = await client.post("/api/v1/agents/orchestrate", json={
            "objective": "Launch live Q4 Meta Ad Campaign with $2,000 spend",
            "agent_name": "campaign_strategist_agent",
            "action_type": "publish_marketing_campaign",
        }, headers=headers)
        assert sens_run.status_code == 200
        sens_data = sens_run.json()
        assert sens_data["status"] == "awaiting_approval"
        assert sens_data["requires_approval"] is True
        assert sens_data["approval_id"] is not None
