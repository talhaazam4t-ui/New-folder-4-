"""Phase 1 Tests: Auth Verification/Reset, Cloudflare Turnstile, Tiered Multi-Channel HITL Outreach, Payment Rails & Analytics."""

from datetime import datetime, timedelta, timezone
import re
import uuid

from app.automation.budget_manager import budget_manager
from app.config import settings
from app.core import turnstile as turnstile_mod
from app.core.security import encrypt_secret
from app.database.models.automation import Integration
from app.database.models.marketing import Lead
from app.database.models.service import Service, ServiceSubscription
from app.database.supabase import get_session_factory
from app.integrations.email import adapter as email_adapter_mod
from app.main import app
import httpx
from httpx import ASGITransport, AsyncClient
import pytest


@pytest.mark.asyncio
async def test_auth_verification_password_reset_and_turnstile(monkeypatch):
    """Verify email verification, single-use password reset, and Cloudflare Turnstile gating."""
    sent_emails = []

    async def _capture_email(self, to_email: str, subject: str, html_body: str, text_body: str):
        sent_emails.append({"to": to_email, "subject": subject, "text": text_body})
        return {"success": True, "provider": "captured_test", "delivered": True}

    monkeypatch.setattr(email_adapter_mod.EmailIntegrationAdapter, "send_transactional_email", _capture_email)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Public config works & defaults Turnstile off when keys unset
        pub_res = await client.get("/api/v1/auth/public-config")
        assert pub_res.status_code == 200
        assert pub_res.json()["data"]["turnstile_enabled"] is False

        # 2. Signup sends verification link & profile starts email_verified=False
        reg = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "verify_me@agency.ai",
                "password": "OldPassword123!",
                "full_name": "Verify Owner",
            },
        )
        assert reg.status_code == 201
        token = reg.json()["access_token"]
        me_before = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_before.status_code == 200
        assert me_before.json()["email_verified"] is False

        assert len(sent_emails) == 1
        verify_match = re.search(r"token=([A-Za-z0-9_-]+)", sent_emails[0]["text"])
        assert verify_match is not None
        verify_tok = verify_match.group(1)

        # 3. Verify email works once, rejects reuse
        v_res = await client.post("/api/v1/auth/verify-email", json={"token": verify_tok})
        assert v_res.status_code == 200
        me_after = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_after.json()["email_verified"] is True
        v_reuse = await client.post("/api/v1/auth/verify-email", json={"token": verify_tok})
        assert v_reuse.status_code == 400

        # 4. Forgot password -> reset password -> old password fails, new password works
        fp_res = await client.post("/api/v1/auth/forgot-password", json={"email": "verify_me@agency.ai"})
        assert fp_res.status_code == 200
        assert len(sent_emails) == 2
        reset_match = re.search(r"token=([A-Za-z0-9_-]+)", sent_emails[1]["text"])
        assert reset_match is not None
        reset_tok = reset_match.group(1)

        rp_res = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": reset_tok, "new_password": "NewStrongPassword99!"},
        )
        assert rp_res.status_code == 200

        old_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "verify_me@agency.ai", "password": "OldPassword123!"},
        )
        assert old_login.status_code == 401

        new_login = await client.post(
            "/api/v1/auth/login",
            json={"email": "verify_me@agency.ai", "password": "NewStrongPassword99!"},
        )
        assert new_login.status_code == 200

        # Reset token cannot be reused
        rp_reuse = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": reset_tok, "new_password": "AnotherPassword11!"},
        )
        assert rp_reuse.status_code == 400

        # 5. Cloudflare Turnstile enforcement when configured
        monkeypatch.setattr(settings, "turnstile_site_key", "1x00000000000000000000AA")
        monkeypatch.setattr(settings, "turnstile_secret_key", "1x0000000000000000000000000000000AA")

        pub_on = await client.get("/api/v1/auth/public-config")
        assert pub_on.json()["data"]["turnstile_enabled"] is True

        blocked = await client.post(
            "/api/v1/auth/login",
            json={"email": "verify_me@agency.ai", "password": "NewStrongPassword99!"},
        )
        assert blocked.status_code == 400
        assert blocked.json()["error"]["code"] == "TURNSTILE_REQUIRED"

        orig_post = httpx.AsyncClient.post

        class _TurnstileResp:
            status_code = 200
            text = '{"success": true}'

            def json(self):
                return {"success": True}

        async def _fake_turnstile_post(self, url, **kwargs):
            if "challenges.cloudflare.com" in str(url):
                return _TurnstileResp()
            return await orig_post(self, url, **kwargs)

        monkeypatch.setattr(turnstile_mod.httpx.AsyncClient, "post", _fake_turnstile_post)
        allowed = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "verify_me@agency.ai",
                "password": "NewStrongPassword99!",
                "turnstile_token": "cf_valid_token_123",
            },
        )
        assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_multichannel_hitl_outreach_tier_quota_and_approve_dispatch(monkeypatch):
    """Verify Gmail/WhatsApp/LinkedIn multi-channel generation, HITL approval send, reject, and quota cap."""
    gmail_calls = []
    orig_post = httpx.AsyncClient.post

    class _FakeResp:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    async def _fake_gmail_post(self, url, **kwargs):
        if "gmail.googleapis.com" in str(url):
            gmail_calls.append({"url": str(url), "json": kwargs.get("json")})
            return _FakeResp(200, {"id": f"msg_{len(gmail_calls)}", "message": {"id": f"inner_{len(gmail_calls)}"}})
        return await orig_post(self, url, **kwargs)

    monkeypatch.setattr(email_adapter_mod.httpx.AsyncClient, "post", _fake_gmail_post)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": "hitl@agency.io", "password": "Password123!", "full_name": "HITL Agency"},
        )
        token = reg.json()["access_token"]
        t_res = await client.post(
            "/api/v1/tenants",
            json={"name": "HITL Studio", "slug": "hitl-studio", "industry": "Clinics / Hospitals"},
            headers={"Authorization": f"Bearer {token}"},
        )
        tenant_id = t_res.json()["id"]
        budget_manager.admin_reset_circuit(tenant_id)
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # Seed service subscription (starter 150/mo) and connected Gmail OAuth
        factory = get_session_factory()
        async with factory() as session:
            srv = Service(
                name="Lead CRM & AI Qualification Engine",
                slug="lead-crm-qualification",
                category="sales",
                description="Tiered outreach",
                configuration_schema={
                    "packages": [
                        {"plan_name": "starter", "price": 149.0, "monthly_lead_limit": 2},
                    ]
                },
                active=True,
            )
            session.add(srv)
            await session.flush()
            session.add(
                ServiceSubscription(
                    tenant_id=uuid.UUID(tenant_id),
                    service_id=srv.id,
                    plan_name="starter",
                    price=149.0,
                    status="active",
                    started_at=datetime.now(timezone.utc),
                )
            )
            session.add(
                Integration(
                    tenant_id=uuid.UUID(tenant_id),
                    provider="gmail",
                    integration_type="messaging",
                    status="connected",
                    external_account_id="owner@hitlstudio.com",
                    configuration={
                        "access_token": encrypt_secret("ya29.live_hitl_token_987654"),
                        "refresh_token": encrypt_secret("1//04_refresh_hitl_987654"),
                        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                        "scopes_granted": [
                            "https://www.googleapis.com/auth/gmail.compose",
                            "https://www.googleapis.com/auth/gmail.send",
                        ],
                        "is_mock": False,
                    },
                )
            )
            await session.commit()

        # 1. Run autopilot cycle -> quota limits to 2 leads, saves drafts only (no send)
        run_res = await client.post(
            "/api/v1/agents/outreach-autopilot/run",
            headers=headers,
            json={"niche": "Clinics / Hospitals", "city": "Dubai", "limit": 5},
        )
        assert run_res.status_code == 200, run_res.text
        data = run_res.json()["data"]
        assert len(data["created_drafts"]) == 2
        assert all("/drafts" in c["url"] for c in gmail_calls)
        assert not any("/messages/send" in c["url"] for c in gmail_calls)

        drafts = data["state"]["drafted_leads"]
        assert len(drafts) == 2
        assert drafts[0]["whatsapp_pitch"]
        assert drafts[0]["linkedin_note"]
        assert drafts[0]["linkedin_dm"]
        assert drafts[0]["linkedin_search_url"].startswith("https://www.linkedin.com/search/results/people/")
        assert drafts[0]["approval_status"] == "pending_approval"

        # 2. Approve & Send Gmail on lead 0 -> hits /messages/send ONLY after approval
        lead0_id = drafts[0]["lead_id"]
        app_gmail = await client.post(
            f"/api/v1/agents/outreach-autopilot/leads/{lead0_id}/approve-send",
            headers=headers,
            json={"channel": "gmail", "mode": "send"},
        )
        assert app_gmail.status_code == 200, app_gmail.text
        assert any("/messages/send" in c["url"] for c in gmail_calls)
        assert app_gmail.json()["data"]["action_result"]["status"] == "sent"

        # 3. Approve WhatsApp (wa.me ready) & Reject lead 1
        app_wa = await client.post(
            f"/api/v1/agents/outreach-autopilot/leads/{lead0_id}/approve-send",
            headers=headers,
            json={"channel": "whatsapp", "mode": "send"},
        )
        assert app_wa.status_code == 200
        assert app_wa.json()["data"]["action_result"]["whatsapp_url"].startswith("https://wa.me/")

        lead1_id = drafts[1]["lead_id"]
        rej = await client.post(
            f"/api/v1/agents/outreach-autopilot/leads/{lead1_id}/reject",
            headers=headers,
            json={"reason": "Not target fit"},
        )
        assert rej.status_code == 200
        assert rej.json()["data"]["rejected"] is True

        # 4. Next run blocked when monthly quota of 2 is exhausted -> 402 LEAD_QUOTA_EXCEEDED
        exhausted = await client.post(
            "/api/v1/agents/outreach-autopilot/run",
            headers=headers,
            json={"niche": "Real Estate / Property", "city": "London", "limit": 2},
        )
        assert exhausted.status_code == 402
        assert exhausted.json()["error"]["code"] == "LEAD_QUOTA_EXCEEDED"


@pytest.mark.asyncio
async def test_integrations_checklist_payment_rails_and_analytics_funnel(monkeypatch):
    """Verify unified handshake checklist, Lemon Squeezy / Bank payment rails, and tenant-isolated analytics."""
    monkeypatch.setattr(settings, "lemonsqueezy_store_id", "525097")
    monkeypatch.setattr(settings, "lemonsqueezy_variant_id_starter", "2389098")
    monkeypatch.setattr(settings, "lemonsqueezy_test_mode", True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg1 = await client.post(
            "/api/v1/auth/register",
            json={"email": "portal1@test.ai", "password": "Password123!", "full_name": "Portal One"},
        )
        tok1 = reg1.json()["access_token"]
        t1_res = await client.post(
            "/api/v1/tenants",
            json={"name": "Portal One", "slug": "portal-one", "industry": "Real Estate / Property"},
            headers={"Authorization": f"Bearer {tok1}"},
        )
        t1 = t1_res.json()["id"]
        h1 = {"Authorization": f"Bearer {tok1}", "X-Tenant-ID": t1}

        reg2 = await client.post(
            "/api/v1/auth/register",
            json={"email": "portal2@test.ai", "password": "Password123!", "full_name": "Portal Two"},
        )
        tok2 = reg2.json()["access_token"]
        t2_res = await client.post(
            "/api/v1/tenants",
            json={"name": "Portal Two", "slug": "portal-two", "industry": "E-Commerce"},
            headers={"Authorization": f"Bearer {tok2}"},
        )
        t2 = t2_res.json()["id"]
        h2 = {"Authorization": f"Bearer {tok2}", "X-Tenant-ID": t2}

        # Checklist + Payment Rails + Overview
        ck_res = await client.get("/api/v1/integrations/handshake-checklist", headers=h1)
        assert ck_res.status_code == 200
        keys = {item["key"] for item in ck_res.json()["data"]["items"]}
        assert {"gmail", "whatsapp", "google_calendar", "office_receptionist", "linkedin", "meta_social", "payments"} <= keys

        rails_res = await client.get("/api/v1/payments/rails", headers=h1)
        assert rails_res.status_code == 200
        assert "payoneer" not in rails_res.json()["data"]
        assert rails_res.json()["data"]["lemonsqueezy"]["enabled"] is True
        assert rails_res.json()["data"]["lemonsqueezy"]["store_id"] == "525097"

        ov_res = await client.get(f"/api/v1/tenants/{t1}/overview", headers=h1)
        assert ov_res.status_code == 200
        assert "outreach_performance" in ov_res.json()["data"]
        assert "payment_rails" in ov_res.json()["data"]

        # Privacy analytics tracking + isolation
        await client.post(
            "/api/v1/analytics/events",
            json={"event_name": "page_view", "page_path": "/dashboard", "tenant_id": t1},
        )
        await client.post(
            "/api/v1/analytics/events",
            json={"event_name": "page_view", "page_path": "/billing", "tenant_id": t2},
        )

        f1 = await client.get("/api/v1/analytics/funnel", headers=h1)
        assert f1.status_code == 200
        assert f1.json()["data"]["total_events"] == 1
        assert f1.json()["data"]["top_pages"][0]["page_path"] == "/dashboard"

        f2 = await client.get("/api/v1/analytics/funnel", headers=h2)
        assert f2.status_code == 200
        assert f2.json()["data"]["total_events"] == 1
        assert f2.json()["data"]["top_pages"][0]["page_path"] == "/billing"
