"""Phase 2 Verification Suite:
1. Database-Driven Service & Skill Registry (`public.services` + `public.agent_skills`) — newly registered DB skills
   are ingested dynamically by the Orchestrator without code changes.
2. Proactive Episodic Memory (`public.tenant_episodic_memories`) — queried before task execution and isolated per `tenant_id`.
3. Self-Reflection / Quality Control (QC) Agent — intercepts spammy claims (`100% guaranteed`, `BUY NOW!!!`),
   enforces word limits (`< 130` words), and auto-revises before output.
4. Dynamic Auto-Configure UI (`provisioned_services` vs `upgrade_marketplace_addons`), Super Admin granular
   service toggles, and HITL Approval Queue routing.
"""

import uuid

import pytest
from app.config import settings
from app.integrations.ai_providers.router import AIExecutionResult
from app.main import app
from httpx import ASGITransport, AsyncClient


async def _register_workspace(client: AsyncClient, email: str, slug: str, name: str, industry: str = "Real Estate / Property"):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"{name} User"},
    )
    assert reg.status_code == 201
    tok = reg.json()["access_token"]
    auth_h = {"Authorization": f"Bearer {tok}"}
    t_res = await client.post(
        "/api/v1/tenants",
        json={"name": name, "slug": slug, "industry": industry},
        headers=auth_h,
    )
    assert t_res.status_code in (200, 201)
    tid = t_res.json()["id"]
    return uuid.UUID(tid), {**auth_h, "X-Tenant-ID": str(tid)}


@pytest.mark.asyncio
async def test_phase2_db_registry_episodic_memory_and_qc_self_reflection(monkeypatch):
    """Verify DB-driven skill ingestion, episodic memory recall, QC auto-revision, and HITL queue routing."""
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "allow_super_admin_bootstrap", True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Super Admin (`talhaazam4t@gmail.com`) registers to manage DB skill registry
        _, admin_h = await _register_workspace(
            client, "talhaazam4t@gmail.com", "talox-hq-p2", "Talox HQ"
        )
        t1_id, h1 = await _register_workspace(client, "client_p2_1@test.ai", "p2-client-1", "Skyline Realty")
        _, h2 = await _register_workspace(client, "client_p2_2@test.ai", "p2-client-2", "Harbor Clinic")

        # 1. Inspect seeded DB Registry (7 active canonical services + 7 seeded skills)
        reg_res = await client.get("/api/v1/agents/registry", headers=h1)
        assert reg_res.status_code == 200
        reg_data = reg_res.json()["data"]
        assert reg_data["services_count"] >= 7
        assert reg_data["skills_count"] >= 7

        # 2. Non-admin cannot register a new global DB skill (403); Super Admin registers a new skill dynamically!
        forbidden_skill = await client.post(
            "/api/v1/agents/skills",
            json={
                "slug": "custom_str_occupancy_optimizer",
                "name": "Short-Term Rental Occupancy Optimizer",
                "service_slug": "business-financial-tracking",
                "description": "Optimizes Airbnb/rental pricing and drafts owner revenue summaries.",
                "token_budget": 1000,
                "max_words": 80,
                "requires_hitl": True,
            },
            headers=h1,
        )
        assert forbidden_skill.status_code == 403

        new_skill = await client.post(
            "/api/v1/agents/skills",
            json={
                "slug": "custom_str_occupancy_optimizer",
                "name": "Short-Term Rental Occupancy Optimizer",
                "service_slug": "business-financial-tracking",
                "description": "Optimizes Airbnb/rental pricing and drafts owner revenue summaries.",
                "token_budget": 1000,
                "max_words": 80,
                "requires_hitl": True,
            },
            headers=admin_h,
        )
        assert new_skill.status_code == 201
        assert new_skill.json()["data"]["slug"] == "custom_str_occupancy_optimizer"

        # 3. Record an Episodic Memory in Tenant 1 & verify Tenant 2 cannot see it
        mem_res = await client.post(
            "/api/v1/agents/memories",
            json={
                "memory_type": "pitch_outcome",
                "skill_slug": "custom_str_occupancy_optimizer",
                "context_key": "Dubai Marina luxury apartments rental pitch",
                "summary": "Mentioning automated rent reminders and net yield increased owner reply rate by 38%.",
                "outcome_score": 95.0,
            },
            headers=h1,
        )
        assert mem_res.status_code == 201

        t2_mems = (await client.get("/api/v1/agents/memories", headers=h2)).json()["data"]
        assert t2_mems == []

        # 4. Mock LLM returning an overly long (>80 words) & spammy draft ("100% guaranteed", "BUY NOW!!!")
        #    -> Verify Self-Reflection QC Agent intercepts, sanitizes claims, trims to <=80 words,
        #       attaches factual service reference, and queues in HITL Approvals!
        spammy_words = " ".join(["rental_yield_analysis"] * 95)
        spammy_draft = (
            f"100% guaranteed profit!! BUY NOW!!! This is a once in a lifetime offer with free money!! {spammy_words}"
        )

        async def _fake_ai_task(task_type: str, prompt: str, **kwargs):
            # Verify the Orchestrator injected our DB episodic memory into the prompt!
            assert "Dubai Marina" in prompt or "38%" in prompt
            return AIExecutionResult(
                success=True,
                model="llama-3.3-70b-versatile",
                task_type=task_type,
                content=spammy_draft,
                total_tokens=210,
                is_mock=False,
            )

        monkeypatch.setattr(
            "app.services.central_orchestrator_service.route_and_execute_ai_task",
            _fake_ai_task,
        )

        orch_res = await client.post(
            "/api/v1/agents/orchestrate-dynamic",
            json={
                "objective": "Prepare Dubai Marina luxury rental occupancy and rent collection pitch",
                "skill_slug": "custom_str_occupancy_optimizer",
            },
            headers=h1,
        )
        assert orch_res.status_code == 200
        odata = orch_res.json()["data"]
        assert odata["selected_skill"]["slug"] == "custom_str_occupancy_optimizer"
        assert len(odata["episodic_memories_used"]) >= 1
        assert odata["qc_report"]["auto_revised"] is True
        assert odata["qc_report"]["word_count_after"] <= 80
        assert "100% guaranteed" not in odata["final_output"].lower()
        assert "buy now" not in odata["final_output"].lower()
        assert odata["hitl_status"] == "pending_approval"
        assert odata["approval_id"] is not None

        # Verify the action landed in Tenant 1's HITL Approval Queue
        approvals = (await client.get("/api/v1/approvals", headers=h1)).json()
        assert any(a["id"] == odata["approval_id"] and a["status"] == "pending" for a in approvals)


@pytest.mark.asyncio
async def test_phase2_dynamic_ui_configuration_and_super_admin_service_toggles(monkeypatch):
    """Verify dynamic UI hides unprovisioned modules, shows Upgrade Marketplace, and obeys Super Admin toggles."""
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "allow_super_admin_bootstrap", True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, admin_h = await _register_workspace(
            client, "talhaazam4t@gmail.com", "talox-admin-ui", "Talox Admin WS"
        )
        t1_id, h1 = await _register_workspace(
            client, "clinic_ui@test.ai", "clinic-ui-ws", "Smile Clinic", industry="Clinics / Hospitals"
        )

        # 1. Before subscribing or admin toggle: all 7 services appear in Upgrade Marketplace Add-ons
        ui0 = (await client.get("/api/v1/agents/ui-config", headers=h1)).json()["data"]
        assert ui0["industry"] == "Clinics / Hospitals"
        assert len(ui0["provisioned_services"]) == 0
        assert len(ui0["upgrade_marketplace_addons"]) >= 7

        # 2. Super Admin enables `office-receptionist` and `whatsapp-business-concierge` for Tenant 1
        t_on1 = await client.post(
            f"/api/v1/agents/admin/tenants/{t1_id}/services/toggle",
            json={"service_slug": "office-receptionist", "enabled": True},
            headers=admin_h,
        )
        assert t_on1.status_code == 200
        t_on2 = await client.post(
            f"/api/v1/agents/admin/tenants/{t1_id}/services/toggle",
            json={"service_slug": "whatsapp-business-concierge", "enabled": True},
            headers=admin_h,
        )
        assert t_on2.status_code == 200
        ui1 = t_on2.json()["data"]
        prov_slugs = {s["slug"] for s in ui1["provisioned_services"]}
        addon_slugs = {s["slug"] for s in ui1["upgrade_marketplace_addons"]}
        assert prov_slugs == {"office-receptionist", "whatsapp-business-concierge"}
        assert "office-receptionist" not in addon_slugs
        assert "business-financial-tracking" in addon_slugs

        # 3. Super Admin disables `whatsapp-business-concierge` -> moves back to Upgrade Marketplace
        t_off = await client.post(
            f"/api/v1/agents/admin/tenants/{t1_id}/services/toggle",
            json={"service_slug": "whatsapp-business-concierge", "enabled": False},
            headers=admin_h,
        )
        assert t_off.status_code == 200
        ui2 = t_off.json()["data"]
        assert {s["slug"] for s in ui2["provisioned_services"]} == {"office-receptionist"}
        assert "whatsapp-business-concierge" in {s["slug"] for s in ui2["upgrade_marketplace_addons"]}
