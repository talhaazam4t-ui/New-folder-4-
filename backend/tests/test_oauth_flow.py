"""End-to-End Integration Tests for Multi-Tenant OAuth 2.0 Integration Flows.

Tests:
1. OAuth 2.0 Authorization URL generation for all 4 providers:
   - whatsapp (Meta OAuth)
   - google_calendar (Google OAuth 2.0)
   - gmail (Google OAuth 2.0)
   - google_business (Google OAuth 2.0)
2. Cryptographic state verification (CSRF & tenant isolation protection).
3. Authorization code exchange & token storage (AES-128 encryption at rest).
4. Status lifecycle transition from 'disconnected' to 'connected'.
5. Live health check / verification endpoint (`/test`).
6. Tampered / expired state rejection.
"""

import pytest
from app.database.models.automation import Integration
from app.database.supabase import get_session_factory
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


@pytest.mark.asyncio
async def test_oauth_authorization_url_generation_all_providers():
    """Verify that clicking connect generates real third-party OAuth redirect URLs with signed state."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register user and tenant
        reg = await client.post("/api/v1/auth/register", json={
            "email": "sarah.connor@acmehealth.com",
            "password": "Password123!",
            "full_name": "Sarah Connor",
        })
        assert reg.status_code == 201
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        t_res = await client.post("/api/v1/tenants", json={
            "name": "Acme Health Care",
            "slug": "acme-health-care",
            "industry": "Clinics / Hospitals",
        }, headers=headers)
        assert t_res.status_code == 201
        tenant_id = t_res.json()["id"]

        tenant_headers = {
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": tenant_id,
        }

        # 1. Google Calendar
        cal_auth = await client.get(
            "/api/v1/integrations/oauth/google_calendar/authorize?return_to=/onboarding",
            headers=tenant_headers,
        )
        assert cal_auth.status_code == 200
        cal_data = cal_auth.json()["data"]
        assert "accounts.google.com/o/oauth2/v2/auth" in cal_data["authorization_url"]
        assert "scope=" in cal_data["authorization_url"]
        assert "calendar.events" in cal_data["authorization_url"]
        assert "state=" in cal_data["authorization_url"]
        assert cal_data["provider"] == "google_calendar"

        # 2. Gmail
        gmail_auth = await client.get(
            "/api/v1/integrations/oauth/gmail/authorize?return_to=/onboarding",
            headers=tenant_headers,
        )
        assert gmail_auth.status_code == 200
        gmail_data = gmail_auth.json()["data"]
        assert "accounts.google.com/o/oauth2/v2/auth" in gmail_data["authorization_url"]
        assert "gmail.send" in gmail_data["authorization_url"]
        assert gmail_data["provider"] == "gmail"

        # 3. Google Business / Maps
        gmb_auth = await client.get(
            "/api/v1/integrations/oauth/google_business/authorize?return_to=/onboarding",
            headers=tenant_headers,
        )
        assert gmb_auth.status_code == 200
        gmb_data = gmb_auth.json()["data"]
        assert "accounts.google.com/o/oauth2/v2/auth" in gmb_data["authorization_url"]
        assert "business.manage" in gmb_data["authorization_url"]
        assert gmb_data["provider"] == "google_business"

        # 4. WhatsApp Cloud API (Meta OAuth)
        wa_auth = await client.get(
            "/api/v1/integrations/oauth/whatsapp/authorize?return_to=/onboarding",
            headers=tenant_headers,
        )
        assert wa_auth.status_code == 200
        wa_data = wa_auth.json()["data"]
        assert "facebook.com" in wa_data["authorization_url"]
        assert "whatsapp_business_management" in wa_data["authorization_url"]
        assert wa_data["provider"] == "whatsapp"


@pytest.mark.asyncio
async def test_oauth_callback_token_exchange_and_encryption():
    """Verify that exchanging code + signed state stores encrypted tokens and transitions status to connected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register user and tenant
        reg = await client.post("/api/v1/auth/register", json={
            "email": "dr.smith@drsmitheyecare.com",
            "password": "Password123!",
            "full_name": "Dr. Smith",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        t_res = await client.post("/api/v1/tenants", json={
            "name": "Dr Smith Eye Care",
            "slug": "dr-smith-eye-care",
            "industry": "Clinics / Hospitals",
        }, headers=headers)
        tenant_id = t_res.json()["id"]

        tenant_headers = {
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": tenant_id,
        }

        # Step 1: Initiate OAuth to obtain signed state
        auth_res = await client.get(
            "/api/v1/integrations/oauth/google_calendar/authorize?return_to=/onboarding",
            headers=tenant_headers,
        )
        assert auth_res.status_code == 200
        state = auth_res.json()["data"]["state"]

        # Step 2: Simulate callback with authorization code
        cb_res = await client.post(
            "/api/v1/integrations/oauth/callback",
            json={
                "provider": "google_calendar",
                "code": "4/0AcvDMrBB99x_test_authorization_code",
                "state": state,
            },
            headers=tenant_headers,
        )
        assert cb_res.status_code == 200
        cb_data = cb_res.json()["data"]
        assert cb_data["status"] == "connected"
        integration_id = cb_data["id"]

        # Step 3: Check database storage - verify encryption at rest
        session_factory = get_session_factory()
        async with session_factory() as db:
            result = await db.execute(
                select(Integration).where(
                    Integration.id == integration_id,
                    Integration.tenant_id == tenant_id,
                )
            )
            integration = result.scalar_one_or_none()
            assert integration is not None
            assert integration.status == "connected"
            # Access token must be encrypted at rest with enc:v1:
            raw_cfg = integration.configuration or {}
            assert "access_token" in raw_cfg
            assert raw_cfg["access_token"].startswith("enc:v1:")

        # Step 4: Verify client response masks secrets
        assert cb_data["configuration"]["access_token"] == "***ENCRYPTED***"

        # Step 5: Test live connection verification endpoint
        test_res = await client.post(
            f"/api/v1/integrations/{integration_id}/test",
            headers=tenant_headers,
        )
        assert test_res.status_code == 200
        assert test_res.json()["success"] is True
        test_data = test_res.json()["data"]
        assert test_data["status"] == "connected"


@pytest.mark.asyncio
async def test_oauth_tampered_state_rejection():
    """Verify that forged or tampered state parameters are rejected with 400 Bad Request."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": "security@testclinic.com",
            "password": "Password123!",
            "full_name": "Security Tester",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        t_res = await client.post("/api/v1/tenants", json={
            "name": "Security Test Clinic",
            "slug": "security-test-clinic",
            "industry": "Clinics / Hospitals",
        }, headers=headers)
        tenant_id = t_res.json()["id"]
        tenant_headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # Attempt callback with completely forged state
        forged_res = await client.post(
            "/api/v1/integrations/oauth/callback",
            json={
                "provider": "google_calendar",
                "code": "sample_code",
                "state": "forged_malicious_state_token",
            },
            headers=tenant_headers,
        )
        assert forged_res.status_code == 400
        assert forged_res.json()["error"]["code"] == "INVALID_OAUTH_STATE"
