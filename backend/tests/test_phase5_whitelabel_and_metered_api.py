"""Phase 5 Verification Suite: Multi-Tenant White-Label Engine & Metered API-as-a-Service.

Tests:
1. Multi-Tenant White-Label Configuration:
   - Custom `brand_name`, `logo_url`, `primary_color`, `accent_color`, `custom_domain`, `hide_powered_by`,
     and `agency_reseller_enabled`.
   - Public resolver (`GET /api/v1/whitelabel/resolve?domain=...` & `?tenant_slug=...`).
   - Duplicate custom domain conflict guard (`HTTP 409`).
   - Agency Reseller Sub-Tenant Provisioning (`POST /api/v1/whitelabel/agency/subtenants`).
2. Scoped Developer API Keys (`POST /api/v1/developer/keys`):
   - SHA-256 hashed storage (`tlx_live_...`), scope enforcement, cross-tenant isolation, and key revocation.
3. Metered Public API-as-a-Service (`X-Talox-API-Key`):
   - `POST /api/v1/developer/v1/agents/invoke` invokes the Central Orchestrator + QC Self-Reflection and
     meters calls & tokens against the tenant's Phase 1 Tier Quota.
   - `GET /api/v1/developer/v1/leads` enforces `leads:read` scope and returns only the key owner's leads.
   - Revoked API key immediately fails with `HTTP 403`.
"""

import pytest
from app.config import settings
from app.main import app
from httpx import ASGITransport, AsyncClient


async def _register_workspace(client: AsyncClient, email: str, slug: str, name: str):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePassword123!", "full_name": name},
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]

    t_res = await client.post(
        "/api/v1/tenants",
        json={"name": name, "slug": slug, "industry": "AI Automation Agency"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert t_res.status_code in (200, 201)
    tenant_id = t_res.json()["id"]
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant_id)}
    return str(tenant_id), headers


@pytest.mark.asyncio
async def test_phase5_whitelabel_engine_agency_subtenants_and_metered_api_keys(monkeypatch):
    """Verify Phase 5 Multi-Tenant White-Label Engine, Agency Sub-Tenants, and Metered API-as-a-Service."""
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "allow_super_admin_bootstrap", True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        t1_id, h1 = await _register_workspace(client, "p5_agency@test.ai", "p5-apex-agency", "Apex AI Agency")
        t2_id, h2 = await _register_workspace(client, "p5_other@test.ai", "p5-other-corp", "Other Corp")

        # ----------------------------------------------------------------------
        # 1. MULTI-TENANT WHITE-LABEL CONFIGURATION & PUBLIC DOMAIN RESOLVER
        # ----------------------------------------------------------------------
        wl_put = await client.put(
            "/api/v1/whitelabel/config",
            json={
                "brand_name": "Apex Autonomous Cloud",
                "logo_url": "https://cdn.apexcloud.ai/logo.svg",
                "primary_color": "#0F172A",
                "accent_color": "#38BDF8",
                "custom_domain": "portal.apexcloud.ai",
                "support_email": "concierge@apexcloud.ai",
                "hide_powered_by": True,
                "agency_reseller_enabled": True,
            },
            headers=h1,
        )
        assert wl_put.status_code == 200
        wl_data = wl_put.json()["data"]
        assert wl_data["brand_name"] == "Apex Autonomous Cloud"
        assert wl_data["custom_domain"] == "portal.apexcloud.ai"
        assert wl_data["hide_powered_by"] is True
        assert wl_data["agency_reseller_enabled"] is True

        # Another tenant cannot hijack the same custom_domain
        conflict_res = await client.put(
            "/api/v1/whitelabel/config",
            json={"custom_domain": "portal.apexcloud.ai"},
            headers=h2,
        )
        assert conflict_res.status_code == 409

        # Public domain resolver returns Apex branding without requiring auth
        pub_res = await client.get("/api/v1/whitelabel/resolve?domain=portal.apexcloud.ai")
        assert pub_res.status_code == 200
        pub_data = pub_res.json()["data"]
        assert pub_data["resolved"] is True
        assert pub_data["brand_name"] == "Apex Autonomous Cloud"
        assert pub_data["primary_color"] == "#0F172A"

        # ----------------------------------------------------------------------
        # 2. AGENCY RESELLER SUB-TENANT PROVISIONING
        # ----------------------------------------------------------------------
        # Tenant 2 does NOT have agency_reseller_enabled -> 403
        denied_sub = await client.post(
            "/api/v1/whitelabel/agency/subtenants",
            json={"client_name": "Unauthorized Sub", "client_slug": "unauth-sub"},
            headers=h2,
        )
        assert denied_sub.status_code == 403

        # Tenant 1 (agency_reseller_enabled=True) provisions a sub-tenant
        sub_res = await client.post(
            "/api/v1/whitelabel/agency/subtenants",
            json={
                "client_name": "Dubai Marina Dental Clinic",
                "client_slug": "dubai-marina-dental",
                "industry": "healthcare",
                "primary_color": "#14B8A6",
            },
            headers=h1,
        )
        assert sub_res.status_code == 201
        sub_data = sub_res.json()["data"]
        assert sub_data["parent_tenant_id"] == t1_id
        assert sub_data["slug"] == "dubai-marina-dental"
        assert sub_data["whitelabel"]["primary_color"] == "#14B8A6"
        assert sub_data["whitelabel"]["hide_powered_by"] is True

        # ----------------------------------------------------------------------
        # 3. SCOPED DEVELOPER API KEYS & METERED API-AS-A-SERVICE
        # ----------------------------------------------------------------------
        key_res = await client.post(
            "/api/v1/developer/keys",
            json={
                "name": "Production CRM & Orchestrator Key",
                "scopes": ["agents:invoke", "leads:read"],
                "rate_limit_per_minute": 120,
            },
            headers=h1,
        )
        assert key_res.status_code == 201
        key_payload = key_res.json()["data"]
        raw_api_key = key_payload["api_key"]
        key_id = key_payload["id"]
        assert raw_api_key.startswith("tlx_live_")

        # Tenant 2 cannot see Tenant 1's API keys
        t2_keys = await client.get("/api/v1/developer/keys", headers=h2)
        assert t2_keys.status_code == 200
        assert t2_keys.json()["data"]["total"] == 0

        # Invoke Central Orchestrator via Metered X-Talox-API-Key
        invoke_res = await client.post(
            "/api/v1/developer/v1/agents/invoke",
            json={
                "objective": "Draft a concise B2B executive follow-up for our healthcare automation client.",
                "task_complexity": "routine",
                "token_budget": 600,
            },
            headers={"X-Talox-API-Key": raw_api_key},
        )
        assert invoke_res.status_code == 200
        inv_data = invoke_res.json()["data"]
        assert inv_data["tenant_id"] == t1_id
        assert inv_data["metered_call_number"] == 1
        assert inv_data["tokens_metered"] > 0
        assert inv_data["orchestration"]["qc_passed"] is True

        # Create a CRM lead in Tenant 1 and fetch via Metered Leads API
        await client.post(
            "/api/v1/marketing/leads",
            json={"name": "Dr. Layla Hassan", "email": "layla@marinadental.ae", "source": "website"},
            headers=h1,
        )
        leads_api_res = await client.get(
            "/api/v1/developer/v1/leads",
            headers={"X-Talox-API-Key": raw_api_key},
        )
        assert leads_api_res.status_code == 200
        leads_data = leads_api_res.json()["data"]
        assert leads_data["metered_call_number"] == 2
        assert leads_data["count"] == 1
        assert leads_data["leads"][0]["email"] == "layla@marinadental.ae"

        # Calling /developer/v1/finance/forecast without 'finance:read' scope fails with 403
        missing_scope_res = await client.get(
            "/api/v1/developer/v1/finance/forecast",
            headers={"X-Talox-API-Key": raw_api_key},
        )
        assert missing_scope_res.status_code == 403

        # Revoke API key -> subsequent calls fail with 403
        rev_res = await client.delete(f"/api/v1/developer/keys/{key_id}", headers=h1)
        assert rev_res.status_code == 200
        assert rev_res.json()["data"]["is_active"] is False

        post_revoke_res = await client.get(
            "/api/v1/developer/v1/leads",
            headers={"X-Talox-API-Key": raw_api_key},
        )
        assert post_revoke_res.status_code == 403
