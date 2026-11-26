"""Phase 1 Verification Suite:
1. Strict Server-Side Tenant Isolation (`tenant_id`)
2. Tiered Usage & Token Metering (Starter -> Growth -> Enterprise, 80% Low-Balance Alert, 100% Hard-Lock HTTP 402 + Upgrade Prompt)
3. Free-First AI Router Cascade (Groq Free -> Gemini Free -> OpenRouter Free -> Paid DeepSeek Fallback) & External Provider Circuit Breakers
4. Lemon Squeezy `subscription_payment_failed` Instant Tenant Suspension & Recovery
5. Immutable Append-Only Audit Logging
"""

import hashlib
import hmac
import json
import uuid

import httpx
import pytest
from app.config import settings
from app.core.exceptions import TaloxException
from app.core.provider_circuit_breaker import provider_circuit_breaker
from app.database.models.automation import AuditLog
from app.database.supabase import get_session_factory
from app.integrations.ai_providers.router import route_and_execute_ai_task
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


async def _register_tenant(client: AsyncClient, email: str, slug: str, name: str):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"{name} Admin"},
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


def _sign_ls(secret: str, payload: dict) -> tuple[bytes, str]:
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return raw, sig


@pytest.mark.asyncio
async def test_phase1_tier_quota_80_alert_100_hard_lock_and_upgrade():
    """Verify 80% low-balance alert, 100% hard-lock with upgrade prompt (402), and tier upgrade unlock."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        t1_id, h1 = await _register_tenant(client, "p1_quota1@test.ai", "p1-quota-1", "Quota One Clinic")
        _, h2 = await _register_tenant(client, "p1_quota2@test.ai", "p1-quota-2", "Quota Two Clinic")

        # 1. Initial Starter quota (100,000 tokens, 2,500 API calls, 60 voice minutes)
        q0 = (await client.get("/api/v1/analytics/tier-quota", headers=h1)).json()["data"]
        assert q0["tier"] == "starter"
        assert q0["tokens_limit"] == 100000
        assert q0["alert_80_triggered"] is False
        assert q0["hard_locked_100"] is False

        # 2. Consume 82,000 tokens (82%) -> triggers 80% alert notification + audit log
        m80 = await client.post(
            "/api/v1/analytics/tier-quota/meter",
            json={"tokens_delta": 82000, "api_calls_delta": 10},
            headers=h1,
        )
        assert m80.status_code == 200
        d80 = m80.json()["data"]
        assert d80["alert_80_triggered"] is True
        assert d80["hard_locked_100"] is False
        assert d80["tokens_percent"] == 82.0

        # 3. Consume another 20,000 tokens (102%) -> triggers 100% hard-lock
        m100 = await client.post(
            "/api/v1/analytics/tier-quota/meter",
            json={"tokens_delta": 20000},
            headers=h1,
        )
        assert m100.status_code == 200
        d100 = m100.json()["data"]
        assert d100["hard_locked_100"] is True
        assert d100["upgrade_required"] is True
        assert d100["upgrade_url"] == "/billing"
        assert "Upgrade" in (d100["upgrade_prompt"] or "")

        # 4. Subsequent metered request while hard-locked is rejected with HTTP 402 + upgrade prompt
        blocked = await client.post(
            "/api/v1/analytics/tier-quota/meter",
            json={"tokens_delta": 500},
            headers=h1,
        )
        assert blocked.status_code == 402
        err = blocked.json()["error"]
        assert err["code"] == "QUOTA_HARD_LOCKED_UPGRADE_REQUIRED"
        assert "/billing" in err["message"]

        # Tenant 2 is completely unaffected (strict tenant isolation)
        q_t2 = (await client.get("/api/v1/analytics/tier-quota", headers=h2)).json()["data"]
        assert q_t2["tokens_used"] == 0
        assert q_t2["hard_locked_100"] is False

        # 5. Upgrade Tenant 1 from Starter -> Growth (500,000 tokens) -> unlocks hard-lock immediately!
        up_res = await client.post(
            "/api/v1/analytics/tier-quota/upgrade",
            json={"tier": "growth"},
            headers=h1,
        )
        assert up_res.status_code == 200
        up_data = up_res.json()["data"]
        assert up_data["tier"] == "growth"
        assert up_data["tokens_limit"] == 500000
        assert up_data["hard_locked_100"] is False

        # Metered execution now succeeds again
        after_up = await client.post(
            "/api/v1/analytics/tier-quota/meter",
            json={"tokens_delta": 1000},
            headers=h1,
        )
        assert after_up.status_code == 200


@pytest.mark.asyncio
async def test_phase1_free_first_ai_router_and_provider_circuit_breaker(monkeypatch):
    """Verify Free-First LLM cascade (Groq -> Gemini -> OpenRouter -> Paid DeepSeek) & circuit breaker tripping."""
    provider_circuit_breaker.reset_provider()
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "circuit_breaker_max_failures", 2)
    monkeypatch.setattr(settings, "groq_api_key", "gsk_free_live_groq_key_1234567890")
    monkeypatch.setattr(settings, "gemini_api_key", "AIzaSyFreeGeminiKey1234567890")
    monkeypatch.setattr(settings, "deepseek_api_key", "sk_paid_deepseek_key_1234567890")

    call_order: list[str] = []

    async def _fake_post(self, url, *args, **kwargs):
        u = str(url)
        req = httpx.Request("POST", u)
        if "api.groq.com" in u:
            call_order.append("groq")
            resp = httpx.Response(503, request=req, json={"error": {"message": "Groq overloaded"}})
            raise httpx.HTTPStatusError("Groq 503", request=req, response=resp)
        if "generativelanguage.googleapis.com" in u:
            call_order.append("gemini")
            if state["gemini_fail"]:
                resp = httpx.Response(429, request=req, json={"error": {"message": "Gemini quota"}})
                raise httpx.HTTPStatusError("Gemini 429", request=req, response=resp)
            return httpx.Response(
                200,
                request=req,
                json={
                    "candidates": [{"content": {"parts": [{"text": "Free Gemini completion response"}]}}],
                    "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 8},
                },
            )
        if "api.deepseek.com" in u:
            call_order.append("deepseek")
            return httpx.Response(
                200,
                request=req,
                json={
                    "choices": [{"message": {"content": "Paid DeepSeek fallback response"}}],
                    "usage": {"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 25},
                },
            )
        return httpx.Response(200, request=req, json={})

    state = {"gemini_fail": False}
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    # Call 1: Groq fails -> falls back to FREE Gemini (Paid DeepSeek is NOT called!)
    res1 = await route_and_execute_ai_task(task_type="quick_summary", prompt="Summarize clinic leads")
    assert res1.success is True
    assert res1.content == "Free Gemini completion response"
    assert res1.estimated_cost == 0.0
    assert "deepseek" not in call_order

    # Call 2: Groq fails a 2nd time -> Groq circuit breaker trips to OPEN!
    call_order.clear()
    res2 = await route_and_execute_ai_task(task_type="quick_summary", prompt="Second summary")
    assert res2.content == "Free Gemini completion response"
    snap = provider_circuit_breaker.snapshot()
    assert snap["groq"]["state"] == "OPEN"
    assert snap["gemini"]["state"] == "CLOSED"

    # Call 3: With Groq circuit OPEN and Gemini now failing, router skips Groq immediately and falls back to Paid DeepSeek
    call_order.clear()
    state["gemini_fail"] = True
    res3 = await route_and_execute_ai_task(task_type="quick_summary", prompt="Third summary")
    assert res3.success is True
    assert res3.content == "Paid DeepSeek fallback response"
    assert "groq" not in call_order  # Skipped directly because Groq circuit is OPEN!
    assert call_order == ["gemini", "deepseek"]

    provider_circuit_breaker.reset_provider()


@pytest.mark.asyncio
async def test_phase1_lemonsqueezy_payment_failure_suspension_and_immutable_audit_logs(monkeypatch):
    """Verify instant tenant suspension on Lemon Squeezy payment failure, recovery, and immutable audit logs."""
    webhook_secret = "ls_phase1_secret_key"
    monkeypatch.setattr(settings, "lemonsqueezy_webhook_secret", webhook_secret)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        t1_id, h1 = await _register_tenant(client, "ls_p1@test.ai", "ls-p1-clinic", "LS Phase1 Clinic")

        # 1. Activate Growth subscription via Lemon Squeezy webhook
        create_payload = {
            "meta": {"event_name": "subscription_created", "custom_data": {"tenant_id": str(t1_id)}},
            "data": {
                "id": "sub_p1_9001",
                "attributes": {
                    "customer_id": "cust_p1_1",
                    "product_id": "prod_1",
                    "variant_id": "var_growth",
                    "variant_name": "Growth Tier",
                    "status": "active",
                },
            },
        }
        raw_body, sig = _sign_ls(webhook_secret, create_payload)
        w1 = await client.post(
            "/api/v1/payments/webhooks/lemonsqueezy",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Signature": sig, "X-Event-Name": "subscription_created"},
        )
        assert w1.status_code == 200
        assert (await client.get("/api/v1/analytics/tier-quota", headers=h1)).json()["data"]["tier"] == "growth"

        # 2. Fire `subscription_payment_failed` webhook -> instantly suspends tenant workspace
        fail_payload = {
            "meta": {"event_name": "subscription_payment_failed", "custom_data": {"tenant_id": str(t1_id)}},
            "data": {
                "id": "sub_p1_9001",
                "attributes": {
                    "customer_id": "cust_p1_1",
                    "variant_name": "Growth Tier",
                    "status": "past_due",
                },
            },
        }
        raw_fail, sig_fail = _sign_ls(webhook_secret, fail_payload)
        w_fail = await client.post(
            "/api/v1/payments/webhooks/lemonsqueezy",
            content=raw_fail,
            headers={
                "Content-Type": "application/json",
                "X-Signature": sig_fail,
                "X-Event-Name": "subscription_payment_failed",
            },
        )
        assert w_fail.status_code == 200

        # Tenant access is now immediately blocked with 403 TENANT_SUSPENDED
        suspended_check = await client.get("/api/v1/analytics/tier-quota", headers=h1)
        assert suspended_check.status_code == 403
        assert suspended_check.json()["error"]["code"] == "TENANT_SUSPENDED"

        # 3. Fire `subscription_payment_recovered` webhook -> automatically unsuspends tenant
        rec_payload = {
            "meta": {"event_name": "subscription_payment_recovered", "custom_data": {"tenant_id": str(t1_id)}},
            "data": {
                "id": "sub_p1_9001",
                "attributes": {
                    "customer_id": "cust_p1_1",
                    "variant_name": "Enterprise Tier",
                    "status": "active",
                },
            },
        }
        raw_rec, sig_rec = _sign_ls(webhook_secret, rec_payload)
        w_rec = await client.post(
            "/api/v1/payments/webhooks/lemonsqueezy",
            content=raw_rec,
            headers={
                "Content-Type": "application/json",
                "X-Signature": sig_rec,
                "X-Event-Name": "subscription_payment_recovered",
            },
        )
        assert w_rec.status_code == 200

        restored_check = await client.get("/api/v1/analytics/tier-quota", headers=h1)
        assert restored_check.status_code == 200
        assert restored_check.json()["data"]["tier"] == "enterprise"

        # 4. Verify AuditLog Immutability (ORM before_update guard blocks modifying any audit log entry)
        factory = get_session_factory()
        async with factory() as session:
            audit_row = (
                await session.execute(select(AuditLog).where(AuditLog.tenant_id == t1_id).limit(1))
            ).scalar_one()
            audit_row.action = "tampered.action"
            with pytest.raises(TaloxException) as exc_info:
                await session.commit()
            assert exc_info.value.code == "IMMUTABLE_AUDIT_LOG"
            await session.rollback()
