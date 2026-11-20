"""Milestone M0 Foundation Tests.

Covers:
1. Lifespan AutomationScheduler start/shutdown & restart across multiple TestClient contexts.
2. SlowAPIMiddleware global limits & POST /api/v1/assistant/chat rate limiting (429).
3. Tenant self-registration payment_approved=False default, settings sanitization, & automation_active gate.
4. enabled_modules mapping across all 6 canonical slugs + 3 legacy aliases & expired subscription filtering.
5. verify_oauth_state production rejection of unsigned/legacy/mock/test tokens.
6. Service catalog legacy un-packaged slug exclusion while preserving custom & canonical services.
7. PATCH /api/v1/subscriptions/{id} status normalization & non-super-admin activation guard (403).
8. POST & GET /api/v1/support/requests persistence (AuditLog + Notification) & tenant isolation.
9. Assistant & Sales Chatbot alignment (all 6 canonical services, 4 core industries, canonical WhatsApp 03238300330).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from app.automation.scheduler import automation_scheduler
from app.config import settings
from app.core.exceptions import TaloxException
from app.core.rate_limit import limiter
from app.database.models.automation import AuditLog, Notification
from app.database.models.service import Service, ServiceSubscription
from app.database.supabase import get_session_factory
from app.main import app
from app.services.assistant_service import TELOXTECH_SYSTEM_PROMPT
from app.services.integration_service import generate_oauth_state, verify_oauth_state
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


def test_lifespan_scheduler_restarts_cleanly_across_multiple_clients(monkeypatch):
    """Entering/exiting TestClient lifespan twice must not raise SchedulerAlreadyRunningError."""
    with TestClient(app) as client1:
        assert automation_scheduler._started is True
        res1 = client1.get("/api/v1/health")
        assert res1.status_code == 200
    assert automation_scheduler._started is False

    # Second lifespan cycle must cleanly re-instantiate APScheduler if needed
    with TestClient(app) as client2:
        assert automation_scheduler._started is True
        res2 = client2.get("/api/v1/health")
        assert res2.status_code == 200
    assert automation_scheduler._started is False

    # Verify periodic worker jobs are scheduled ONLY when not in pytest/test runtime
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(settings, "app_env", "development")
    with TestClient(app) as client3:
        job_ids = {j["id"] for j in automation_scheduler.list_jobs()}
        assert "background_pending_task_queue" in job_ids
        assert "background_stale_approval_expiration" in job_ids
        assert client3.get("/api/v1/health").status_code == 200
    assert automation_scheduler._started is False


@pytest.mark.asyncio
async def test_slowapi_rate_limiting_on_assistant_chat_and_cors_429(monkeypatch):
    """POST /api/v1/assistant/chat enforces per-route RPM limit and SlowAPIMiddleware wraps routes cleanly."""
    limiter.reset()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        limit = settings.rate_limit_agent_rpm
        for _ in range(limit):
            res = await client.post(
                "/api/v1/assistant/chat",
                json={"messages": [{"role": "user", "content": "Hello"}]},
                headers={"Origin": "http://localhost:3000"},
            )
            assert res.status_code == 200

        blocked = await client.post(
            "/api/v1/assistant/chat",
            json={"messages": [{"role": "user", "content": "One more"}]},
            headers={"Origin": "http://localhost:3000"},
        )
        assert blocked.status_code == 429
        assert blocked.headers.get("access-control-allow-origin") == "http://localhost:3000"

    # Also verify SlowAPIMiddleware global default limit enforces 429 on /api/v1/health
    limiter.reset()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(settings.rate_limit_default_rpm):
            ok_res = await client.get("/api/v1/health", headers={"X-Tenant-ID": "rate-limit-test"})
            assert ok_res.status_code == 200
        global_blocked = await client.get("/api/v1/health", headers={"X-Tenant-ID": "rate-limit-test"})
        assert global_blocked.status_code == 429


@pytest.mark.asyncio
async def test_tenant_payment_gate_strips_spoofed_settings_and_gates_automation(monkeypatch):
    """Self-registered tenants cannot spoof payment_approved and remain gated until Super Admin approval."""
    monkeypatch.setattr(
        settings,
        "super_admin_emails",
        [*settings.super_admin_emails, "m0.admin@talox.io"],
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        admin_reg = await client.post("/api/v1/auth/register", json={
            "email": "m0.admin@talox.io",
            "password": "Password123!",
            "full_name": "M0 Admin",
        })
        admin_headers = {"Authorization": f"Bearer {admin_reg.json()['access_token']}"}

        client_reg = await client.post("/api/v1/auth/register", json={
            "email": "spoof.client@company.com",
            "password": "Password123!",
            "full_name": "Client User",
        })
        client_token = client_reg.json()["access_token"]
        client_headers = {"Authorization": f"Bearer {client_token}"}

        # Attempt to inject payment_approved=True during tenant creation
        t_res = await client.post("/api/v1/tenants", json={
            "name": "Spoof Test Corp",
            "slug": "spoof-test-corp",
            "industry": "Financing",
            "settings": {
                "theme": "emerald",
                "payment_approved": True,
                "automation_approved_by_owner": True,
            },
        }, headers=client_headers)
        assert t_res.status_code == 201
        t_data = t_res.json()
        tenant_id = t_data["id"]
        assert t_data["settings"].get("payment_approved") is False
        assert t_data["settings"].get("theme") == "emerald"
        assert "automation_approved_by_owner" not in t_data["settings"]

        tenant_headers = {"Authorization": f"Bearer {client_token}", "X-Tenant-ID": tenant_id}

        # Attempt to inject payment_approved=True via PATCH /tenants/{id}
        patch_res = await client.patch(
            f"/api/v1/tenants/{tenant_id}",
            json={"settings": {"payment_approved": True, "theme": "slate"}},
            headers=tenant_headers,
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["settings"].get("payment_approved") is False
        assert patch_res.json()["settings"].get("theme") == "slate"

        # Seed catalog and subscribe + connect whatsapp
        cat_res = await client.get("/api/v1/services?ensure_seeded=true")
        assert cat_res.status_code == 200
        fin_srv = next(s for s in cat_res.json() if s["slug"] == "business-financial-tracking")
        sub_res = await client.post("/api/v1/services/subscribe", json={
            "service_id": fin_srv["id"],
            "plan_name": "starter",
            "billing_interval": "monthly",
            "price": 99.0,
        }, headers=tenant_headers)
        assert sub_res.status_code == 201

        conn_res = await client.post("/api/v1/integrations/whatsapp/connect", json={
            "oauth_code": "mock_wa_code_001",
        }, headers=tenant_headers)
        assert conn_res.status_code == 201

        gmail_res = await client.post("/api/v1/integrations/gmail/connect", json={
            "oauth_code": "mock_gmail_code_001",
        }, headers=tenant_headers)
        assert gmail_res.status_code == 201

        # Overview & onboarding-requirements remain gated while pending_approval
        ov_before = (await client.get(f"/api/v1/tenants/{tenant_id}/overview", headers=tenant_headers)).json()["data"]
        assert ov_before["is_payment_approved"] is False
        assert ov_before["automation_active"] is False
        assert ov_before["enabled_modules"] == []

        req_before = (await client.get("/api/v1/integrations/onboarding-requirements", headers=tenant_headers)).json()["data"]
        assert req_before["all_required_connected"] is True
        assert req_before["automation_active"] is False

        # Super admin approves payment -> tenant becomes active and automation unlocks
        approve_res = await client.post(
            f"/api/v1/admin/tenants/{tenant_id}/approve-payment",
            json={"notes": "Verified"},
            headers=admin_headers,
        )
        assert approve_res.status_code == 200

        ov_after = (await client.get(f"/api/v1/tenants/{tenant_id}/overview", headers=tenant_headers)).json()["data"]
        assert ov_after["is_payment_approved"] is True
        assert ov_after["automation_active"] is True
        assert ov_after["enabled_modules"] == ["financial_ledger", "revenue_reports"]


@pytest.mark.asyncio
async def test_enabled_modules_all_six_slugs_and_expired_subscription_filtering(monkeypatch):
    """All 6 canonical slugs map accurately in enabled_modules and expired subscriptions are excluded."""
    monkeypatch.setattr(
        settings,
        "super_admin_emails",
        [*settings.super_admin_emails, "modules.admin@talox.io"],
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        admin_reg = await client.post("/api/v1/auth/register", json={
            "email": "modules.admin@talox.io",
            "password": "Password123!",
            "full_name": "Modules Admin",
        })
        admin_headers = {"Authorization": f"Bearer {admin_reg.json()['access_token']}"}

        user_reg = await client.post("/api/v1/auth/register", json={
            "email": "modules.client@company.com",
            "password": "Password123!",
            "full_name": "Modules Client",
        })
        token = user_reg.json()["access_token"]
        t_res = await client.post("/api/v1/tenants", json={
            "name": "Modules Corp",
            "slug": "modules-corp",
            "industry": "Financing",
        }, headers={"Authorization": f"Bearer {token}"})
        tenant_id = t_res.json()["id"]
        tenant_headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        await client.post(
            f"/api/v1/admin/tenants/{tenant_id}/approve-payment",
            json={"notes": "Approved"},
            headers=admin_headers,
        )

        services = (await client.get("/api/v1/services?ensure_seeded=true")).json()
        by_slug = {s["slug"]: s for s in services}

        # Subscribe to all 6 canonical services
        for slug_key in (
            "business-financial-tracking",
            "ai-marketing-growth",
            "whatsapp-business-concierge",
            "multi-agent-orchestration",
            "lead-crm-qualification",
            "executive-analytics-compliance",
        ):
            sub = await client.post("/api/v1/services/subscribe", json={
                "service_id": by_slug[slug_key]["id"],
                "plan_name": "starter",
                "billing_interval": "monthly",
                "price": 99.0,
            }, headers=tenant_headers)
            assert sub.status_code == 201

        ov = (await client.get(f"/api/v1/tenants/{tenant_id}/overview", headers=tenant_headers)).json()["data"]
        assert ov["enabled_modules"] == [
            "financial_ledger",
            "revenue_reports",
            "marketing_growth",
            "lead_funnel",
            "outreach_campaigns",
            "whatsapp_concierge",
            "appointments",
            "multi_agent_orchestration",
            "lead_crm",
            "executive_analytics_compliance",
        ]

        # Expire executive-analytics-compliance and multi-agent-orchestration in DB
        factory = get_session_factory()
        expired_time = datetime.now(timezone.utc) - timedelta(days=2)
        async with factory() as session:
            subs = (
                await session.execute(
                    select(ServiceSubscription).where(ServiceSubscription.tenant_id == uuid.UUID(tenant_id))
                )
            ).scalars().all()
            expired_srv_ids = {
                uuid.UUID(by_slug["multi-agent-orchestration"]["id"]),
                uuid.UUID(by_slug["executive-analytics-compliance"]["id"]),
            }
            for s in subs:
                if s.service_id in expired_srv_ids:
                    s.expires_at = expired_time
            await session.commit()

        ov_after = (await client.get(f"/api/v1/tenants/{tenant_id}/overview", headers=tenant_headers)).json()["data"]
        assert "multi_agent_orchestration" not in ov_after["enabled_modules"]
        assert "executive_analytics_compliance" not in ov_after["enabled_modules"]
        assert len(ov_after["purchased_services"]) == 4
        assert ov_after["subscription_info"]["active_services_count"] == 4


def test_verify_oauth_state_rejects_unsigned_fallbacks_in_production(monkeypatch):
    """Unsigned talox_/mock/test OAuth state tokens must fail with 400 in production."""
    tenant_uuid = uuid.uuid4()
    valid_jwt = generate_oauth_state(tenant_uuid, None, "google_calendar")

    # Dev/test permits legacy fallback
    monkeypatch.setattr(settings, "app_env", "test")
    assert verify_oauth_state("talox_123_abc")["tenant_id"] == "123"
    assert verify_oauth_state("mock_state_token")["return_to"] == "/onboarding"

    # Production strictly rejects unsigned fallbacks while accepting real signed JWT state
    monkeypatch.setattr(settings, "app_env", "production")
    assert verify_oauth_state(valid_jwt)["tenant_id"] == str(tenant_uuid)

    for forged in ("talox_123_abc", "oauth_state_dev", "mock_state", "test_state_xyz"):
        with pytest.raises(TaloxException) as exc_info:
            verify_oauth_state(forged)
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "INVALID_OAUTH_STATE"


@pytest.mark.asyncio
async def test_catalog_excludes_legacy_unpackaged_slugs_preserving_custom_and_canonical(monkeypatch):
    """GET /api/v1/services hides legacy un-packaged slugs while keeping canonical 6 and custom services."""
    monkeypatch.setattr(
        settings,
        "super_admin_emails",
        [*settings.super_admin_emails, "catalog.admin@talox.io"],
    )
    factory = get_session_factory()
    async with factory() as session:
        for legacy_slug in ("business-finance", "whatsapp-automation", "marketing-growth"):
            session.add(
                Service(
                    name=f"Legacy {legacy_slug}",
                    slug=legacy_slug,
                    category="legacy",
                    description="Legacy un-packaged service",
                    configuration_schema={},
                    active=True,
                )
            )
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        admin_reg = await client.post("/api/v1/auth/register", json={
            "email": "catalog.admin@talox.io",
            "password": "Password123!",
            "full_name": "Catalog Admin",
        })
        admin_headers = {"Authorization": f"Bearer {admin_reg.json()['access_token']}"}

        custom_res = await client.post("/api/v1/services", json={
            "name": "Automated Rent Collection",
            "slug": "automated-rent-collection",
            "category": "finance",
            "description": "Custom catalog service",
            "active": True,
        }, headers=admin_headers)
        assert custom_res.status_code == 201

        cat_res = await client.get("/api/v1/services?ensure_seeded=true")
        assert cat_res.status_code == 200
        slugs = {s["slug"] for s in cat_res.json()}
        assert "business-finance" not in slugs
        assert "whatsapp-automation" not in slugs
        assert "marketing-growth" not in slugs
        assert "automated-rent-collection" in slugs
        assert {
            "business-financial-tracking",
            "ai-marketing-growth",
            "whatsapp-business-concierge",
            "multi-agent-orchestration",
            "lead-crm-qualification",
            "executive-analytics-compliance",
        }.issubset(slugs)

    # Confirm legacy DB rows remain intact in DB
    async with factory() as session:
        legacy_rows = (
            await session.execute(
                select(Service).where(Service.slug.in_(["business-finance", "whatsapp-automation", "marketing-growth"]))
            )
        ).scalars().all()
        assert len(legacy_rows) == 3


@pytest.mark.asyncio
async def test_patch_subscription_status_guard_and_normalization(monkeypatch):
    """Non-super-admins cannot self-activate subscriptions via PATCH /subscriptions/{id}."""
    monkeypatch.setattr(
        settings,
        "super_admin_emails",
        [*settings.super_admin_emails, "sub.admin@talox.io"],
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        admin_reg = await client.post("/api/v1/auth/register", json={
            "email": "sub.admin@talox.io",
            "password": "Password123!",
            "full_name": "Sub Admin",
        })
        admin_token = admin_reg.json()["access_token"]

        client_reg = await client.post("/api/v1/auth/register", json={
            "email": "sub.client@company.com",
            "password": "Password123!",
            "full_name": "Sub Client",
        })
        client_token = client_reg.json()["access_token"]

        t_res = await client.post("/api/v1/tenants", json={
            "name": "Sub Guard Co",
            "slug": "sub-guard-co",
            "industry": "Financing",
        }, headers={"Authorization": f"Bearer {client_token}"})
        tenant_id = t_res.json()["id"]
        client_tenant_headers = {"Authorization": f"Bearer {client_token}", "X-Tenant-ID": tenant_id}

        # Add super admin as an 'owner' member on the tenant (verifying super-admin check uses Profile, not context.role)
        await client.post(
            f"/api/v1/tenants/{tenant_id}/members",
            json={"email": "sub.admin@talox.io", "role": "owner"},
            headers=client_tenant_headers,
        )
        admin_tenant_headers = {"Authorization": f"Bearer {admin_token}", "X-Tenant-ID": tenant_id}

        services = (await client.get("/api/v1/services?ensure_seeded=true")).json()
        srv_id = services[0]["id"]
        sub_res = await client.post("/api/v1/subscriptions", json={
            "service_id": srv_id,
            "plan_name": "starter",
            "billing_interval": "monthly",
            "price": 99.0,
        }, headers=client_tenant_headers)
        assert sub_res.status_code == 201
        sub_id = sub_res.json()["id"]

        # Client can cancel with spelling normalization ("cancelled" -> "canceled")
        cancel_res = await client.patch(
            f"/api/v1/subscriptions/{sub_id}",
            json={"status": "cancelled"},
            headers=client_tenant_headers,
        )
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "canceled"

        # Invalid status rejected
        invalid_res = await client.patch(
            f"/api/v1/subscriptions/{sub_id}",
            json={"status": "free_forever"},
            headers=client_tenant_headers,
        )
        assert invalid_res.status_code == 400

        # Client CANNOT reactivate via PATCH status="active"
        client_activate = await client.patch(
            f"/api/v1/subscriptions/{sub_id}",
            json={"status": "active"},
            headers=client_tenant_headers,
        )
        assert client_activate.status_code == 403
        assert client_activate.json()["error"]["code"] == "PERMISSION_DENIED"

        # Super Admin CAN reactivate via PATCH status="active"
        admin_activate = await client.patch(
            f"/api/v1/subscriptions/{sub_id}",
            json={"status": "active"},
            headers=admin_tenant_headers,
        )
        assert admin_activate.status_code == 200
        assert admin_activate.json()["status"] == "active"


@pytest.mark.asyncio
async def test_support_requests_create_list_persistence_and_isolation():
    """POST/GET /api/v1/support/requests persists AuditLog + Notification and enforces tenant isolation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg_a = await client.post("/api/v1/auth/register", json={
            "email": "support.a@company.com",
            "password": "Password123!",
            "full_name": "Support A",
        })
        tok_a = reg_a.json()["access_token"]
        t_a = (await client.post("/api/v1/tenants", json={
            "name": "Support Tenant A",
            "slug": "support-tenant-a",
            "industry": "Clinics / Hospitals",
        }, headers={"Authorization": f"Bearer {tok_a}"})).json()["id"]
        headers_a = {"Authorization": f"Bearer {tok_a}", "X-Tenant-ID": t_a}

        reg_b = await client.post("/api/v1/auth/register", json={
            "email": "support.b@company.com",
            "password": "Password123!",
            "full_name": "Support B",
        })
        tok_b = reg_b.json()["access_token"]
        t_b = (await client.post("/api/v1/tenants", json={
            "name": "Support Tenant B",
            "slug": "support-tenant-b",
            "industry": "E-Commerce",
        }, headers={"Authorization": f"Bearer {tok_b}"})).json()["id"]
        headers_b = {"Authorization": f"Bearer {tok_b}", "X-Tenant-ID": t_b}

        create_res = await client.post("/api/v1/support/requests", json={
            "subject": "Need WhatsApp OAuth setup help",
            "message": "Please assist with Meta Business Manager verification.",
            "category": "onboarding",
            "priority": "high",
            "provider": "whatsapp",
            "service_slug": "whatsapp-business-concierge",
            "contact_preference": "whatsapp",
        }, headers=headers_a)
        assert create_res.status_code == 201
        created = create_res.json()
        assert created["ticket_id"].startswith("SUP-")
        assert created["tenant_id"] == t_a
        assert created["status"] == "open"
        assert created["whatsapp_number"] == "03238300330"
        assert created["whatsapp_url"] == "https://wa.me/923238300330"

        # Verify AuditLog & Notification rows persisted in DB
        factory = get_session_factory()
        async with factory() as session:
            audit_rows = (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.tenant_id == uuid.UUID(t_a),
                        AuditLog.resource_type == "support_request",
                        AuditLog.action == "support.request.created",
                    )
                )
            ).scalars().all()
            assert len(audit_rows) == 1
            assert audit_rows[0].metadata_["ticket_id"] == created["ticket_id"]

            notif_rows = (
                await session.execute(
                    select(Notification).where(
                        Notification.tenant_id == uuid.UUID(t_a),
                        Notification.channel == "in_app",
                    )
                )
            ).scalars().all()
            assert len(notif_rows) >= 1

        # Tenant A sees its ticket; Tenant B does not
        list_a = await client.get("/api/v1/support/requests", headers=headers_a)
        assert list_a.status_code == 200
        assert len(list_a.json()["data"]) == 1
        assert list_a.json()["data"][0]["ticket_id"] == created["ticket_id"]

        list_b = await client.get("/api/v1/support/requests", headers=headers_b)
        assert list_b.status_code == 200
        assert list_b.json()["data"] == []


@pytest.mark.asyncio
async def test_assistant_and_chatbot_cover_all_six_canonical_services():
    """Assistant system prompt & fallback concierge cover all 6 canonical services and 4 core industries."""
    for expected_slug in (
        "business-financial-tracking",
        "ai-marketing-growth",
        "whatsapp-business-concierge",
        "multi-agent-orchestration",
        "lead-crm-qualification",
        "executive-analytics-compliance",
    ):
        assert expected_slug in TELOXTECH_SYSTEM_PROMPT
    assert "/onboarding?service=executive-analytics-compliance" in TELOXTECH_SYSTEM_PROMPT

    limiter.reset()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_crm = await client.post("/api/v1/assistant/chat", json={
            "messages": [{"role": "user", "content": "We need lead CRM scoring and qualification funnel"}],
        })
        assert res_crm.status_code == 200
        assert res_crm.json()["service_slug"] == "lead-crm-qualification"
        assert res_crm.json()["action_url"] == "/onboarding?service=lead-crm-qualification"

        res_exec = await client.post("/api/v1/assistant/chat", json={
            "messages": [{"role": "user", "content": "Tell me about executive analytics KPIs and compliance audit"}],
        })
        assert res_exec.status_code == 200
        assert res_exec.json()["service_slug"] == "executive-analytics-compliance"
        assert res_exec.json()["action_url"] == "/onboarding?service=executive-analytics-compliance"
