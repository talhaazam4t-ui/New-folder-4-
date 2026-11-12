import pytest
from app.automation.budget_manager import budget_manager
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_marketing_research_content_campaigns_and_approval_gate():
    """Verify competitor/audience research, AI content generation, campaign creation, and human approval publishing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": "cmo@brandgrowth.io",
            "password": "Password123!",
            "full_name": "Chief Marketing Officer",
        })
        token = reg.json()["access_token"]
        t_res = await client.post("/api/v1/tenants", json={
            "name": "Elevate Brand Studio",
            "slug": "elevate-brand-studio",
            "industry": "E-Commerce",
        }, headers={"Authorization": f"Bearer {token}"})
        tenant_id = t_res.json()["id"]
        budget_manager.admin_reset_circuit(tenant_id)
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # 1. Competitor Research
        comp_res = await client.post("/api/v1/marketing/research/competitors", json={
            "industry": "E-Commerce Apparel",
            "competitors": ["BrandX", "StyleHub"],
            "region": "North America",
        }, headers=headers)
        assert comp_res.status_code == 200
        assert comp_res.json()["success"] is True

        # 2. Audience Research
        aud_res = await client.post("/api/v1/marketing/research/audience", json={
            "product_or_service": "Sustainable Activewear",
            "target_industry": "Fitness & Lifestyle",
            "price_point": "$80 - $150",
        }, headers=headers)
        assert aud_res.status_code == 200
        assert "personas" in aud_res.json()["data"]

        # 3. AI Content Generation
        gen_res = await client.post("/api/v1/marketing/content/generate", json={
            "channel": "whatsapp",
            "topic": "VIP Early Access 20% Off",
            "tone": "friendly",
            "call_to_action": "Reply VIP to claim",
        }, headers=headers)
        assert gen_res.status_code == 200
        assert "generated_copy" in gen_res.json()["data"]

        # 4. Create Campaign (starts in 'draft' and creates pending Approval)
        camp_res = await client.post("/api/v1/marketing/campaigns", json={
            "name": "Holiday VIP Launch",
            "platform": "meta_ads",
            "objective": "conversions",
            "budget": 1200.0,
        }, headers=headers)
        assert camp_res.status_code == 201
        campaign = camp_res.json()
        assert campaign["status"] == "draft"
        campaign_id = campaign["id"]
        assert "approval_id" in campaign["configuration"]

        # 5. Update Campaign draft
        patch_res = await client.patch(f"/api/v1/marketing/campaigns/{campaign_id}", json={
            "budget": 1500.0,
            "status": "pending_approval",
        }, headers=headers)
        assert patch_res.status_code == 200
        assert patch_res.json()["budget"] == 1500.0

        # 6. Verify a 'manager' cannot approve/publish a live campaign (Owner only)
        reg_mgr = await client.post("/api/v1/auth/register", json={
            "email": "manager@brandgrowth.io",
            "password": "Password123!",
            "full_name": "Marketing Manager",
        })
        mgr_token = reg_mgr.json()["access_token"]
        await client.post(f"/api/v1/tenants/{tenant_id}/members", json={
            "email": "manager@brandgrowth.io",
            "role": "manager",
        }, headers=headers)
        mgr_headers = {"Authorization": f"Bearer {mgr_token}", "X-Tenant-ID": tenant_id}

        mgr_approve = await client.post(f"/api/v1/marketing/campaigns/{campaign_id}/approve", headers=mgr_headers)
        assert mgr_approve.status_code == 403

        # 7. Owner approves and publishes campaign
        owner_approve = await client.post(f"/api/v1/marketing/campaigns/{campaign_id}/approve", headers=headers)
        assert owner_approve.status_code == 200
        assert owner_approve.json()["status"] == "active"


@pytest.mark.asyncio
async def test_marketing_leads_qualification_and_analytics():
    """Verify lead capture, update, AI qualification scoring, and marketing ROI analytics."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": "growth@saascompany.io",
            "password": "Password123!",
            "full_name": "Growth Lead",
        })
        token = reg.json()["access_token"]
        t_res = await client.post("/api/v1/tenants", json={
            "name": "CloudScale SaaS",
            "slug": "cloudscale-saas",
            "industry": "SaaS",
        }, headers={"Authorization": f"Bearer {token}"})
        tenant_id = t_res.json()["id"]
        budget_manager.admin_reset_circuit(tenant_id)
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # 1. Create Lead
        lead_res = await client.post("/api/v1/marketing/leads", json={
            "name": "Sarah Jenkins",
            "email": "sarah@enterprisebuyer.com",
            "phone": "+15550192831",
            "source": "whatsapp",
            "notes": "Interested in annual enterprise plan for 50 seats",
        }, headers=headers)
        assert lead_res.status_code == 201
        lead_id = lead_res.json()["id"]

        # 2. Run AI Lead Qualification
        qual_res = await client.post(f"/api/v1/marketing/leads/{lead_id}/qualify", headers=headers)
        assert qual_res.status_code == 200
        qual_data = qual_res.json()
        assert qual_data["qualification_score"] >= 85.0
        assert qual_data["status"] == "qualified"
        assert qual_data["assigned_agent"] == "campaign_strategist_agent"

        # 3. Create & approve a campaign so analytics includes campaign + lead funnel metrics
        c_res = await client.post("/api/v1/marketing/campaigns", json={
            "name": "Enterprise Inbound Q4",
            "platform": "linkedin",
            "objective": "lead_generation",
            "budget": 2000.0,
        }, headers=headers)
        c_id = c_res.json()["id"]
        await client.post(f"/api/v1/marketing/campaigns/{c_id}/approve", headers=headers)

        # 4. Verify Marketing Analytics
        ana_res = await client.get("/api/v1/marketing/analytics", headers=headers)
        assert ana_res.status_code == 200
        ana = ana_res.json()
        assert ana["total_campaigns"] == 1
        assert ana["active_campaigns"] == 1
        assert ana["total_leads"] == 1
        assert ana["qualified_leads"] == 1
        assert ana["total_revenue"] > ana["total_spend"]
        assert ana["roi_percentage"] > 0.0
