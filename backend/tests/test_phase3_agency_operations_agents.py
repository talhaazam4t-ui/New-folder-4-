"""Phase 3 Verification Suite:
1. Content Repurposing Agent (`POST /api/v1/agents/repurpose-content`) — synthesizes high-performing campaigns
   into LinkedIn posts, SEO blog summaries, and newsletters, runs Self-Reflection QC, and queues HITL approval.
2. Automated Freelancing Pipeline (`POST /api/v1/agents/freelance/orders`, `/execute`, `/approve-deliver`) —
   scans freelance demand (`seo_audit`, `content_pack`, `bookkeeping_setup`), assigns specialized workforce
   agents, runs QC, enforces HITL review gate before delivery, auto-delivers upon approval, records episodic
   memory, and enforces strict multi-tenant isolation.
"""

import uuid

import pytest
from app.config import settings
from app.main import app
from httpx import ASGITransport, AsyncClient


async def _register_tenant(client: AsyncClient, email: str, slug: str, name: str):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"{name} Owner"},
    )
    assert reg.status_code == 201
    tok = reg.json()["access_token"]
    auth_h = {"Authorization": f"Bearer {tok}"}
    t_res = await client.post(
        "/api/v1/tenants",
        json={"name": name, "slug": slug, "industry": "Clinics / Hospitals"},
        headers=auth_h,
    )
    assert t_res.status_code in (200, 201)
    tid = t_res.json()["id"]
    return uuid.UUID(tid), {**auth_h, "X-Tenant-ID": str(tid)}


@pytest.mark.asyncio
async def test_phase3_content_repurposing_and_automated_freelancing_pipeline(monkeypatch):
    """Verify Content Repurposing Agent & Automated Freelancing Pipeline end-to-end with HITL & isolation."""
    monkeypatch.setattr(settings, "app_env", "test")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, h1 = await _register_tenant(client, "p3_agency1@test.ai", "p3-agency-1", "Alpha Agency")
        _, h2 = await _register_tenant(client, "p3_agency2@test.ai", "p3-agency-2", "Beta Agency")

        # ----------------------------------------------------------------------
        # 1. CONTENT REPURPOSING AGENT (From Existing Marketing Campaign)
        # ----------------------------------------------------------------------
        camp_res = await client.post(
            "/api/v1/marketing/campaigns",
            json={
                "name": "Q4 Dental Implant AI Receptionist Blitz",
                "platform": "linkedin",
                "objective": "lead_generation",
                "budget": 1500.0,
                "ad_copy": "Stop losing high-ticket dental implant patients to after-hours voicemail.",
            },
            headers=h1,
        )
        assert camp_res.status_code == 201
        camp_id = camp_res.json()["id"]

        rep_res = await client.post(
            "/api/v1/agents/repurpose-content",
            json={"campaign_id": camp_id},
            headers=h1,
        )
        assert rep_res.status_code == 201
        bundle = rep_res.json()["data"]
        assert bundle["source_campaign_id"] == camp_id
        assert bundle["status"] == "pending_hitl"
        assert bundle["approval_id"] is not None
        assert len(bundle["linkedin_post"].split()) <= 125
        assert len(bundle["blog_summary"].split()) <= 130
        assert len(bundle["newsletter_draft"].split()) <= 130

        # Tenant 2 sees zero repurposed bundles
        assert (await client.get("/api/v1/agents/repurpose-content", headers=h2)).json()["data"] == []

        # ----------------------------------------------------------------------
        # 2. AUTOMATED FREELANCING PIPELINE (Scan -> Execute Workforce -> HITL -> Auto-Deliver)
        # ----------------------------------------------------------------------
        order_res = await client.post(
            "/api/v1/agents/freelance/orders",
            json={
                "client_name": "Mayfair Cosmetic Dentistry",
                "project_title": "Local SEO & AI Booking Conversion Audit",
                "category": "seo_audit",
                "budget_usd": 450.0,
                "requirements": "Audit schema markup, page speed, and missed-call conversion gaps for London clinic.",
            },
            headers=h1,
        )
        assert order_res.status_code == 201
        order = order_res.json()["data"]
        order_id = order["id"]
        assert order["assigned_workforce_agent"] == "seo_auditor_agent"
        assert order["status"] == "scanned"

        # Cannot approve-deliver before workforce agent execution (400)
        early_deliver = await client.post(
            f"/api/v1/agents/freelance/orders/{order_id}/approve-deliver",
            headers=h1,
        )
        assert early_deliver.status_code == 400

        # Execute workforce agent -> produces QC-checked deliverable & queues in HITL
        exec_res = await client.post(
            f"/api/v1/agents/freelance/orders/{order_id}/execute",
            headers=h1,
        )
        assert exec_res.status_code == 200
        exec_order = exec_res.json()["data"]
        assert exec_order["status"] == "pending_hitl"
        assert exec_order["approval_id"] is not None
        assert "Mayfair Cosmetic Dentistry" in exec_order["deliverable_draft"]
        assert exec_order["qc_report"]["word_count_after"] <= 125

        # Cross-tenant isolation: Tenant 2 cannot execute or approve Tenant 1's order (404)
        cross_deliver = await client.post(
            f"/api/v1/agents/freelance/orders/{order_id}/approve-deliver",
            headers=h2,
        )
        assert cross_deliver.status_code == 404

        # Human approves in HITL -> auto-delivers & records episodic memory!
        deliv_res = await client.post(
            f"/api/v1/agents/freelance/orders/{order_id}/approve-deliver",
            headers=h1,
        )
        assert deliv_res.status_code == 200
        delivered = deliv_res.json()["data"]
        assert delivered["status"] == "approved_delivered"
        assert delivered["delivered_at"] is not None

        # Verify episodic memory was recorded for this freelance delivery
        memories = (
            await client.get("/api/v1/agents/memories?memory_type=freelance_delivery", headers=h1)
        ).json()["data"]
        assert len(memories) == 1
        assert "Mayfair Cosmetic Dentistry" in memories[0]["summary"]
