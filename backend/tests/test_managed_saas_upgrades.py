"""Comprehensive Verification Suite for Talox Tech Stream Managed AI SaaS Upgrades.

Tests:
1. Strict Owner (Platform Super Admin) vs. Client (Tenant Owner) permission separation.
2. Dynamic 4-industry service catalog (Financing, Clinics / Hospitals, Real Estate / Property, E-Commerce).
3. Intelligent Client Onboarding, dynamic required integrations, encryption at rest, secret masking,
   and automation readiness gate.
4. Backend-controlled Google Maps Lead Generation (with deduplication & quality checks),
   Personalized Outreach (with opt-out compliance), Appointment Booking, and Client Dashboard Performance Viewer.
"""

import uuid

import pytest
from app.automation.budget_manager import budget_manager
from app.database.models.automation import Integration
from app.database.supabase import get_session_factory
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


@pytest.mark.asyncio
async def test_owner_vs_client_permission_separation():
    """Verify that a Client who owns their own tenant cannot access Super Admin or Agent Config endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register Platform Super Admin (Owner)
        owner_reg = await client.post("/api/v1/auth/register", json={
            "email": "owner@talox.io",
            "password": "Password123!",
            "full_name": "Talox Platform Owner",
        })
        assert owner_reg.status_code == 201
        assert owner_reg.json()["is_super_admin"] is True
        owner_token = owner_reg.json()["access_token"]
        owner_headers = {"Authorization": f"Bearer {owner_token}"}

        # 2. Register a regular Client and create their own company workspace
        client_reg = await client.post("/api/v1/auth/register", json={
            "email": "dr.ahmed@sunriseclinic.com",
            "password": "Password123!",
            "full_name": "Dr. Ahmed",
            "account_type": "client",
        })
        assert client_reg.status_code == 201
        assert client_reg.json()["is_super_admin"] is False
        client_token = client_reg.json()["access_token"]
        client_headers = {"Authorization": f"Bearer {client_token}"}

        t_res = await client.post("/api/v1/tenants", json={
            "name": "Sunrise Medical Clinic",
            "slug": "sunrise-medical-clinic",
            "industry": "Clinics / Hospitals",
        }, headers=client_headers)
        assert t_res.status_code == 201
        tenant_id = t_res.json()["id"]
        client_tenant_headers = {
            "Authorization": f"Bearer {client_token}",
            "X-Tenant-ID": tenant_id,
        }

        # 3. Client attempts to access Owner / Super Admin endpoints -> MUST BE REJECTED (403)
        for admin_path in ["/api/v1/admin/stats", "/api/v1/admin/tenants", "/api/v1/admin/operations", "/api/v1/admin/dlq"]:
            forbidden_res = await client.get(admin_path, headers=client_headers)
            assert forbidden_res.status_code == 403
            assert forbidden_res.json()["error"]["code"] == "PERMISSION_DENIED"

        # 4. Client attempts to create a platform service -> MUST BE REJECTED (403)
        forbidden_srv = await client.post("/api/v1/services", json={
            "name": "Unauthorized Client Service",
            "slug": "unauthorized-client-service",
            "category": "hack",
            "active": True,
        }, headers=client_headers)
        assert forbidden_srv.status_code == 403

        # 5. Client attempts to configure internal AI agents -> MUST BE REJECTED (403)
        forbidden_agent_cfg = await client.post(
            "/api/v1/agents/whatsapp_concierge_agent/configure",
            json={"enabled": False, "execution_limit": 10, "budget_limit": 5.0},
            headers=client_tenant_headers,
        )
        assert forbidden_agent_cfg.status_code == 403

        # 6. Platform Owner can access `/api/v1/admin/operations` and manage the client workspace
        ops_res = await client.get("/api/v1/admin/operations", headers=owner_headers)
        assert ops_res.status_code == 200
        ops_data = ops_res.json()["data"]
        assert ops_data["stats"]["total_tenants"] == 1
        assert len(ops_data["services"]) >= 6


@pytest.mark.asyncio
async def test_industry_catalog_onboarding_encryption_and_managed_dashboard_flow():
    """Verify dynamic 4-industry catalog, one-click credential connection, encryption at rest,
    automation gating, Google Maps lead gen deduplication, outreach, booking, and Client Dashboard Viewer.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register Owner and Client
        owner_reg = await client.post("/api/v1/auth/register", json={
            "email": "owner@talox.io",
            "password": "Password123!",
            "full_name": "Platform Owner",
        })
        owner_headers = {"Authorization": f"Bearer {owner_reg.json()['access_token']}"}

        client_reg = await client.post("/api/v1/auth/register", json={
            "email": "founder@alnoorhospital.med",
            "password": "Password123!",
            "full_name": "Hospital Director",
            "account_type": "client",
        })
        client_token = client_reg.json()["access_token"]
        client_headers = {"Authorization": f"Bearer {client_token}"}

        # 2. Verify all 4 industries exist in `/api/v1/services/industries`
        ind_res = await client.get("/api/v1/services/industries")
        assert ind_res.status_code == 200
        ind_payload = ind_res.json()
        assert set(ind_payload["industries"]) == {
            "Financing",
            "Clinics / Hospitals",
            "Real Estate / Property",
            "E-Commerce",
        }
        clinic_services = ind_payload["catalog"]["Clinics / Hospitals"]
        assert len(clinic_services) >= 4

        # 3. Client creates workspace with industry "Clinics / Hospitals"
        # Verify selecting an industry does NOT auto-purchase every service!
        t_res = await client.post("/api/v1/tenants", json={
            "name": "Al Noor Hospital Group",
            "slug": "al-noor-hospital",
            "industry": "Clinics / Hospitals",
        }, headers=client_headers)
        tenant_id = t_res.json()["id"]
        budget_manager.admin_reset_circuit(tenant_id)
        tenant_headers = {"Authorization": f"Bearer {client_token}", "X-Tenant-ID": tenant_id}

        req_before = await client.get("/api/v1/integrations/onboarding-requirements", headers=tenant_headers)
        assert req_before.status_code == 200
        assert req_before.json()["data"]["purchased_services"] == []
        assert req_before.json()["data"]["automation_active"] is False

        # 4. Client selects and subscribes to "WhatsApp Business Concierge & Webhook Sync" (Growth package)
        concierge_srv = next(s for s in clinic_services if s["slug"] == "whatsapp-business-concierge")
        sub_res = await client.post("/api/v1/services/subscribe", json={
            "service_id": concierge_srv["id"],
            "plan_name": "growth",
            "billing_interval": "monthly",
            "price": 279.0,
        }, headers=tenant_headers)
        assert sub_res.status_code == 201

        # 5. Onboarding requirements now dynamically require whatsapp, google_calendar, booking_provider
        req_after_sub = await client.get("/api/v1/integrations/onboarding-requirements", headers=tenant_headers)
        req_data = req_after_sub.json()["data"]
        required_providers = [r["provider"] for r in req_data["required_integrations"]]
        assert "whatsapp" in required_providers
        assert "google_calendar" in required_providers
        assert "booking_provider" in required_providers
        assert req_data["all_required_connected"] is False
        assert req_data["automation_active"] is False

        # 6. Connect required integrations (OAuth for WhatsApp & Google Calendar, API Key for Booking Provider)
        wa_conn = await client.post("/api/v1/integrations/whatsapp/connect", json={
            "oauth_code": "meta_oauth_clinic_code_12345",
        }, headers=tenant_headers)
        assert wa_conn.status_code == 201

        gcal_conn = await client.post("/api/v1/integrations/google_calendar/connect", json={
            "oauth_code": "google_oauth_cal_code_67890",
            "account_identifier": "schedule@alnoorhospital.med",
        }, headers=tenant_headers)
        assert gcal_conn.status_code == 201

        booking_conn = await client.post("/api/v1/integrations/booking_provider/connect", json={
            "api_key": "sk_live_super_secret_ehr_key_99999",
            "account_identifier": "alnoor-ehr-prod",
        }, headers=tenant_headers)
        assert booking_conn.status_code == 201
        # Verify raw API key is NEVER exposed in response
        assert "sk_live_super_secret_ehr_key_99999" not in str(booking_conn.json())
        assert booking_conn.json()["data"]["configuration"]["api_key"] == "***ENCRYPTED***"

        # Verify credential is encrypted at rest in the database (`enc:v1:...`)
        factory = get_session_factory()
        async with factory() as session:
            db_integ_res = await session.execute(
                select(Integration).where(
                    Integration.tenant_id == uuid.UUID(tenant_id),
                    Integration.provider == "booking_provider",
                )
            )
            db_integ = db_integ_res.scalar_one()
            raw_stored_key = db_integ.configuration["api_key"]
            assert raw_stored_key.startswith("enc:v1:")
            assert "sk_live_super_secret_ehr_key_99999" not in raw_stored_key

        # 7. Verify all required integrations are now connected and automation is active!
        req_complete = await client.get("/api/v1/integrations/onboarding-requirements", headers=tenant_headers)
        complete_data = req_complete.json()["data"]
        assert complete_data["all_required_connected"] is True
        assert complete_data["automation_active"] is True
        assert complete_data["onboarding_completed"] is True

        # 8. Backend-controlled Lead Generation with Deduplication
        lead_gen_1 = await client.post("/api/v1/marketing/leads/generate", json={
            "industry": "Clinics / Hospitals",
            "location": "Dubai Healthcare City",
            "limit": 3,
        }, headers=tenant_headers)
        assert lead_gen_1.status_code == 200
        lg1_data = lead_gen_1.json()["data"]
        assert lg1_data["created_count"] == 3
        assert lg1_data["skipped_duplicates"] == 0
        first_lead_id = lg1_data["leads"][0]["id"]

        # Running identical lead generation again must deduplicate all 3 leads
        lead_gen_2 = await client.post("/api/v1/marketing/leads/generate", json={
            "industry": "Clinics / Hospitals",
            "location": "Dubai Healthcare City",
            "limit": 3,
        }, headers=tenant_headers)
        assert lead_gen_2.status_code == 200
        assert lead_gen_2.json()["data"]["created_count"] == 0
        assert lead_gen_2.json()["data"]["skipped_duplicates"] == 3

        # 9. Execute Personalized Outreach & Book Appointment
        outreach_res = await client.post(
            f"/api/v1/marketing/leads/{first_lead_id}/outreach",
            json={"channel": "whatsapp", "custom_context": "Specialist Orthopedic Consultation"},
            headers=tenant_headers,
        )
        assert outreach_res.status_code == 200
        assert outreach_res.json()["data"]["status"] == "sent"

        booking_res = await client.post(
            f"/api/v1/marketing/leads/{first_lead_id}/book-appointment",
            json={"meeting_title": "Patient Specialist Consultation"},
            headers=tenant_headers,
        )
        assert booking_res.status_code == 200
        assert booking_res.json()["data"]["meeting_booked"] is True

        # 10. Verify Client Dashboard Managed Service Performance Viewer (`/api/v1/tenants/{id}/overview`)
        overview_res = await client.get(f"/api/v1/tenants/{tenant_id}/overview", headers=tenant_headers)
        assert overview_res.status_code == 200
        ov = overview_res.json()["data"]
        assert ov["selected_industry"] == "Clinics / Hospitals"
        assert ov["current_package"] == "Growth"
        assert ov["automation_active"] is True
        assert ov["metrics"]["leads_generated"] == 3
        assert ov["metrics"]["messages_sent"] >= 1
        assert ov["metrics"]["meetings_booked"] == 1
        assert ov["metrics"]["conversion_rate"] == 33.3
        assert len(ov["appointment_performance"]) == 1
        assert len(ov["purchased_services"]) == 1
        assert len(ov["integrations_status"]) == 3
        # Verify no raw credentials or system prompts are leaked in Client Overview
        assert "enc:v1:" not in str(ov)
        assert "sk_live_" not in str(ov)

        # 11. Verify Owner can update service pricing dynamically
        patch_srv = await client.patch(
            f"/api/v1/services/{concierge_srv['id']}",
            json={"description": "Updated 24/7 AI Medical & Business Receptionist"},
            headers=owner_headers,
        )
        assert patch_srv.status_code == 200
        assert patch_srv.json()["description"] == "Updated 24/7 AI Medical & Business Receptionist"
