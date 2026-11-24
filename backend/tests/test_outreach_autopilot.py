"""Tests for Daily Global Niche Lead-Finder & Gmail Draft Autopilot."""

import base64
from datetime import datetime, timedelta, timezone
import uuid

from app.automation.budget_manager import budget_manager
from app.config import settings
from app.core.security import encrypt_secret
from app.database.models.automation import Integration
from app.database.models.tenant import Tenant
from app.database.supabase import get_session_factory
from app.integrations.email import adapter as email_adapter_mod
from app.main import app
from app.services import outreach_autopilot_service as autopilot_mod
from app.services.outreach_autopilot_service import outreach_autopilot_service
import httpx
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select


async def _register_and_create_tenant(
    client: AsyncClient,
    email: str,
    name: str,
    slug: str,
    industry: str = "Clinics / Hospitals",
) -> tuple[str, str]:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"{name} Owner"},
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    t_res = await client.post(
        "/api/v1/tenants",
        json={"name": name, "slug": slug, "industry": industry},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert t_res.status_code == 201, t_res.text
    tenant_id = t_res.json()["id"]
    budget_manager.admin_reset_circuit(tenant_id)
    return token, tenant_id


@pytest.mark.asyncio
async def test_gmail_oauth_authorize_includes_compose_scope(monkeypatch):
    """Gmail OAuth authorization URL must request gmail.compose scope so agents can save Gmail drafts."""
    monkeypatch.setattr(settings, "google_client_id", "test-google-client.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "test-google-secret")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, tenant_id = await _register_and_create_tenant(
            client, "oauth_compose@telox.ai", "Compose Studio", "compose-studio"
        )
        res = await client.get(
            "/api/v1/integrations/oauth/gmail/authorize?return_to=/agents",
            headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id},
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        assert "https://www.googleapis.com/auth/gmail.compose" in data["scopes"]
        assert "gmail.compose" in data["authorization_url"]


@pytest.mark.asyncio
async def test_autopilot_config_get_update_and_tenant_isolation():
    """Verify GET/PUT persistence of daily autopilot config and strict multi-tenant isolation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token_a, tenant_a = await _register_and_create_tenant(
            client, "owner_a@alpha.ai", "Alpha Agency", "alpha-agency"
        )
        token_b, tenant_b = await _register_and_create_tenant(
            client, "owner_b@beta.ai", "Beta Agency", "beta-agency"
        )
        headers_a = {"Authorization": f"Bearer {token_a}", "X-Tenant-ID": tenant_a}
        headers_b = {"Authorization": f"Bearer {token_b}", "X-Tenant-ID": tenant_b}

        # Defaults
        get_a = await client.get("/api/v1/agents/outreach-autopilot", headers=headers_a)
        assert get_a.status_code == 200
        cfg_a = get_a.json()["data"]["config"]
        assert cfg_a["enabled"] is False
        assert "Clinics / Hospitals" in cfg_a["niches"]

        # Update Tenant A
        put_a = await client.put(
            "/api/v1/agents/outreach-autopilot",
            headers=headers_a,
            json={
                "enabled": True,
                "niches": ["Dental & Aesthetic Clinics", "Real Estate / Property"],
                "cities": ["Dubai", "London", "Toronto"],
                "daily_draft_limit": 7,
                "run_hour_utc": 8,
                "booking_url": "https://cal.com/alpha/demo",
            },
        )
        assert put_a.status_code == 200
        updated_a = put_a.json()["data"]["config"]
        assert updated_a["enabled"] is True
        assert updated_a["niches"] == ["Dental & Aesthetic Clinics", "Real Estate / Property"]
        assert updated_a["cities"] == ["Dubai", "London", "Toronto"]
        assert updated_a["daily_draft_limit"] == 7
        assert updated_a["run_hour_utc"] == 8
        assert updated_a["booking_url"] == "https://cal.com/alpha/demo"

        # Tenant B remains unaffected
        get_b = await client.get("/api/v1/agents/outreach-autopilot", headers=headers_b)
        assert get_b.status_code == 200
        assert get_b.json()["data"]["config"]["enabled"] is False

        # Cross-tenant access blocked
        cross = await client.get(
            "/api/v1/agents/outreach-autopilot",
            headers={"Authorization": f"Bearer {token_a}", "X-Tenant-ID": tenant_b},
        )
        assert cross.status_code == 403


@pytest.mark.asyncio
async def test_autopilot_run_saves_live_gmail_drafts_without_auto_sending(monkeypatch):
    """Run autopilot with live OAuth token, verify Gmail Drafts endpoint is called (never /messages/send) and deduplicates."""
    posted_calls = []

    class _FakeResp:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self):
            return self._payload

    orig_post = httpx.AsyncClient.post

    async def _fake_post(self, url, **kwargs):
        if "gmail.googleapis.com" in str(url):
            posted_calls.append(
                {"url": str(url), "headers": kwargs.get("headers"), "json": kwargs.get("json")}
            )
            return _FakeResp(
                200,
                {"id": f"r_draft_{len(posted_calls)}", "message": {"id": f"m_{len(posted_calls)}"}},
            )
        return await orig_post(self, url, **kwargs)

    monkeypatch.setattr(email_adapter_mod.httpx.AsyncClient, "post", _fake_post)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, tenant_id = await _register_and_create_tenant(
            client, "agency_live@telox.stream", "Teloxtech Live Agency", "teloxtech-live-agency"
        )
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # Seed connected Gmail integration with live-style OAuth token + gmail.compose scope
        factory = get_session_factory()
        async with factory() as session:
            session.add(
                Integration(
                    tenant_id=uuid.UUID(tenant_id),
                    provider="gmail",
                    integration_type="messaging",
                    status="connected",
                    external_account_id="teloxtech.stream@gmail.com",
                    configuration={
                        "access_token": encrypt_secret("ya29.live_valid_token_abc123456"),
                        "refresh_token": encrypt_secret("1//04_live_refresh_token_xyz789"),
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

        run_res = await client.post(
            "/api/v1/agents/outreach-autopilot/run",
            headers=headers,
            json={"niche": "Clinics / Hospitals", "city": "Dubai", "limit": 4},
        )
        assert run_res.status_code == 200, run_res.text
        data = run_res.json()["data"]
        summary = data["run_summary"]
        assert summary["leads_discovered"] >= 1
        assert summary["drafts_saved_in_gmail"] >= 1
        assert summary["drafts_saved_in_crm"] == 0

        # Verify Gmail Drafts endpoint called, NEVER /messages/send
        assert len(posted_calls) == summary["drafts_saved_in_gmail"]
        for call in posted_calls:
            assert call["url"].endswith("/gmail/v1/users/me/drafts")
            assert "/messages/send" not in call["url"]
            raw_b64 = call["json"]["message"]["raw"]
            decoded_email = base64.urlsafe_b64decode(raw_b64.encode("ascii")).decode("utf-8", errors="replace")
            assert "From: teloxtech.stream@gmail.com" in decoded_email

        # Running same niche & city again skips already-drafted leads (no duplicate Gmail drafts)
        before_count = len(posted_calls)
        second_res = await client.post(
            "/api/v1/agents/outreach-autopilot/run",
            headers=headers,
            json={"niche": "Clinics / Hospitals", "city": "Dubai", "limit": 4},
        )
        assert second_res.status_code == 200
        assert second_res.json()["data"]["run_summary"]["drafts_saved_in_gmail"] == 0
        assert len(posted_calls) == before_count


@pytest.mark.asyncio
async def test_autopilot_refreshes_token_on_401_and_syncs_pending_crm_drafts(monkeypatch):
    """Drafts saved in CRM prior to OAuth sync into Gmail Drafts later and recover from 401 via token refresh."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, tenant_id = await _register_and_create_tenant(
            client, "sync_test@telox.stream", "Sync Test Co", "sync-test-co"
        )
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # 1. Run before Gmail OAuth is connected -> saves drafts cleanly in CRM
        pre_run = await client.post(
            "/api/v1/agents/outreach-autopilot/run",
            headers=headers,
            json={"niche": "Real Estate / Property", "city": "London", "limit": 2},
        )
        assert pre_run.status_code == 200
        pre_data = pre_run.json()["data"]
        assert pre_data["run_summary"]["drafts_saved_in_crm"] == 2
        assert pre_data["run_summary"]["drafts_saved_in_gmail"] == 0
        assert pre_data["state"]["stats"]["pending_oauth_sync_count"] == 2

        # 2. Seed Gmail integration with expired token + refresh token
        factory = get_session_factory()
        async with factory() as session:
            session.add(
                Integration(
                    tenant_id=uuid.UUID(tenant_id),
                    provider="gmail",
                    integration_type="messaging",
                    status="connected",
                    external_account_id="owner@synctest.com",
                    configuration={
                        "access_token": encrypt_secret("ya29.expired_google_token_12345"),
                        "refresh_token": encrypt_secret("1//04_valid_refresh_token_12345"),
                        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
                        "scopes_granted": ["https://www.googleapis.com/auth/gmail.compose"],
                        "is_mock": False,
                    },
                )
            )
            await session.commit()

        tokens_seen = []

        class _FakeResp:
            def __init__(self, status_code: int, payload: dict):
                self.status_code = status_code
                self._payload = payload
                self.text = str(payload)

            def json(self):
                return self._payload

        orig_post = httpx.AsyncClient.post

        async def _fake_post(self, url, **kwargs):
            if "gmail.googleapis.com" in str(url):
                auth_hdr = (kwargs.get("headers") or {}).get("Authorization", "")
                tokens_seen.append(auth_hdr)
                if "expired_google_token" in auth_hdr:
                    return _FakeResp(401, {"error": {"message": "Invalid Credentials"}})
                return _FakeResp(200, {"id": f"r_live_sync_{len(tokens_seen)}", "message": {"id": "m_sync"}})
            return await orig_post(self, url, **kwargs)

        async def _fake_refresh(refresh_token: str):
            return {
                "access_token": "ya29.fresh_refreshed_token_99999",
                "expires_in": 3600,
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            }

        monkeypatch.setattr(email_adapter_mod.httpx.AsyncClient, "post", _fake_post)
        monkeypatch.setattr(autopilot_mod, "refresh_google_access_token", _fake_refresh)

        sync_res = await client.post("/api/v1/agents/outreach-autopilot/sync-drafts", headers=headers)
        assert sync_res.status_code == 200, sync_res.text
        sync_data = sync_res.json()["data"]
        assert sync_data["synced_count"] == 2
        assert sync_data["failed_count"] == 0
        assert sync_data["state"]["stats"]["saved_in_gmail_count"] == 2
        assert sync_data["state"]["stats"]["pending_oauth_sync_count"] == 0
        assert any("expired_google_token" in hdr for hdr in tokens_seen)
        assert any("fresh_refreshed_token" in hdr for hdr in tokens_seen)


@pytest.mark.asyncio
async def test_scheduled_autopilot_tick_respects_enabled_and_daily_cooldown():
    """Scheduled daily tick executes once per active enabled tenant and skips during 24h cooldown."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token, tenant_id = await _register_and_create_tenant(
            client, "sched@telox.stream", "Scheduled Co", "scheduled-co"
        )
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # Activate tenant (new registrations start pending_approval) & enable autopilot
        put_res = await client.put(
            "/api/v1/agents/outreach-autopilot",
            headers=headers,
            json={"enabled": True, "daily_draft_limit": 2},
        )
        assert put_res.status_code == 200

        factory = get_session_factory()
        async with factory() as session:
            t_res = await session.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
            tenant = t_res.scalar_one()
            tenant.status = "active"
            await session.commit()

        async with factory() as session:
            first_tick = await outreach_autopilot_service.run_scheduled_autopilot_tick(session)
        assert first_tick["checked"] == 1
        assert first_tick["executed"] == 1
        assert first_tick["errors"] == 0

        # Immediate second tick skips due to daily cooldown
        async with factory() as session:
            second_tick = await outreach_autopilot_service.run_scheduled_autopilot_tick(session)
        assert second_tick["checked"] == 1
        assert second_tick["executed"] == 0
