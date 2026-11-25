"""Lemon Squeezy Checkout Metadata, X-Signature HMAC Webhook, and Tenant Subscription RLS Tests."""

import hashlib
import hmac
import json
import uuid

import pytest
from app.config import settings
from app.database.models.billing import Subscription
from app.database.supabase import get_session_factory
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


def _ls_sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def _register_and_create_workspace(client: AsyncClient, email: str, slug: str, name: str):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"{name} Owner"},
    )
    assert reg.status_code == 201
    data = reg.json()
    tok = data["access_token"]
    uid = data["user_id"]
    auth_h = {"Authorization": f"Bearer {tok}"}
    t_res = await client.post(
        "/api/v1/tenants",
        json={"name": name, "slug": slug, "industry": "SaaS / Tech"},
        headers=auth_h,
    )
    assert t_res.status_code in (200, 201)
    tid = t_res.json()["id"]
    return uuid.UUID(tid), str(uid), {**auth_h, "X-Tenant-ID": str(tid)}


@pytest.mark.asyncio
async def test_lemonsqueezy_checkout_webhooks_and_tenant_isolation(monkeypatch):
    """Verify checkout custom metadata, X-Signature HMAC verification, and subscription lifecycle."""
    secret = "ls_test_webhook_secret_40chars_12345678"
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "lemonsqueezy_store_id", "525097")
    monkeypatch.setattr(settings, "lemonsqueezy_variant_id_starter", "2389098")
    monkeypatch.setattr(settings, "lemonsqueezy_variant_id_growth", "2389099")
    monkeypatch.setattr(settings, "lemonsqueezy_variant_id_enterprise", "2389100")
    monkeypatch.setattr(
        settings,
        "lemonsqueezy_checkout_url_growth",
        "https://teloxtech.lemonsqueezy.com/checkout/buy/growth-test?enabled=2389099",
    )
    monkeypatch.setattr(settings, "lemonsqueezy_webhook_secret", secret)
    monkeypatch.setattr(settings, "lemonsqueezy_test_mode", True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        t1, u1, h1 = await _register_and_create_workspace(client, "ls.owner1@test.ai", "ls-org-1", "LS Org One")
        _, _, h2 = await _register_and_create_workspace(client, "ls.owner2@test.ai", "ls-org-2", "LS Org Two")

        # 1. Checkout URL passes authenticated tenant_id & user_id in custom params
        chk = await client.post(
            "/api/v1/payments/checkout",
            json={"provider": "lemonsqueezy", "purpose": "subscription", "plan_name": "growth", "currency": "PKR"},
            headers=h1,
        )
        assert chk.status_code == 200
        chk_url = chk.json()["data"]["checkout_url"]
        assert f"checkout[custom][tenant_id]={t1}" in chk_url
        assert f"checkout[custom][user_id]={u1}" in chk_url

        # 2. Invalid X-Signature is strictly rejected with 400
        created_payload = json.dumps({
            "meta": {
                "event_name": "subscription_created",
                "test_mode": True,
                "custom_data": {
                    "tenant_id": str(t1),
                    "user_id": u1,
                    "plan_name": "growth",
                },
            },
            "data": {
                "type": "subscriptions",
                "id": "sub_ls_1001",
                "attributes": {
                    "store_id": 525097,
                    "customer_id": 8801,
                    "order_id": 7701,
                    "product_id": 1535965,
                    "variant_id": 2389099,
                    "product_name": "TeloxTech AI Automation SaaS",
                    "variant_name": "Growth",
                    "status": "active",
                    "card_brand": "visa",
                    "card_last_four": "4242",
                    "renews_at": "2026-12-25T00:00:00Z",
                    "urls": {
                        "customer_portal": "https://app.lemonsqueezy.com/my-orders/test",
                        "update_payment_method": "https://app.lemonsqueezy.com/subscription/test/update",
                    },
                },
            },
        }).encode("utf-8")

        bad_wh = await client.post(
            "/api/webhooks/lemonsqueezy",
            content=created_payload,
            headers={"X-Signature": "deadbeef0000", "X-Event-Name": "subscription_created"},
        )
        assert bad_wh.status_code == 400

        # 3. Valid subscription_created activates tenant & stores Subscription row
        ok_created = await client.post(
            "/api/webhooks/lemonsqueezy",
            content=created_payload,
            headers={"X-Signature": _ls_sign(secret, created_payload), "X-Event-Name": "subscription_created"},
        )
        assert ok_created.status_code == 200
        assert ok_created.json()["reconciled"] is True

        sub_t1 = await client.get("/api/v1/payments/subscription", headers=h1)
        assert sub_t1.status_code == 200
        assert sub_t1.json()["data"]["provider"] == "lemon_squeezy"
        assert sub_t1.json()["data"]["tier"] == "growth"
        assert sub_t1.json()["data"]["status"] == "active"

        # Tenant isolation check: Tenant 2 must NOT see Tenant 1's subscription
        sub_t2 = await client.get("/api/v1/payments/subscription", headers=h2)
        assert sub_t2.status_code == 200
        assert sub_t2.json()["data"] is None

        ov_active = await client.get(f"/api/v1/tenants/{t1}/overview", headers=h1)
        assert ov_active.status_code == 200
        assert ov_active.json()["data"]["is_payment_approved"] is True

        # 4. Valid subscription_updated upgrades tier via /api/v1/payments/webhooks/lemonsqueezy
        updated_payload = json.dumps({
            "meta": {"event_name": "subscription_updated", "test_mode": True},
            "data": {
                "id": "sub_ls_1001",
                "attributes": {
                    "variant_id": 2389100,
                    "variant_name": "Enterprise",
                    "status": "active",
                },
            },
        }).encode("utf-8")
        ok_updated = await client.post(
            "/api/v1/payments/webhooks/lemonsqueezy",
            content=updated_payload,
            headers={"X-Signature": _ls_sign(secret, updated_payload), "X-Event-Name": "subscription_updated"},
        )
        assert ok_updated.status_code == 200
        sub_after_up = await client.get("/api/v1/payments/subscription", headers=h1)
        assert sub_after_up.json()["data"]["tier"] == "enterprise"

        # 5. Valid subscription_cancelled revokes entitlement cleanly
        cancelled_payload = json.dumps({
            "meta": {"event_name": "subscription_cancelled", "test_mode": True},
            "data": {
                "id": "sub_ls_1001",
                "attributes": {
                    "status": "cancelled",
                    "ends_at": "2026-12-25T00:00:00Z",
                },
            },
        }).encode("utf-8")
        ok_cancel = await client.post(
            "/api/webhooks/lemonsqueezy",
            content=cancelled_payload,
            headers={"X-Signature": _ls_sign(secret, cancelled_payload), "X-Event-Name": "subscription_cancelled"},
        )
        assert ok_cancel.status_code == 200
        sub_after_cancel = await client.get("/api/v1/payments/subscription", headers=h1)
        assert sub_after_cancel.json()["data"]["status"] == "cancelled"

        ov_cancelled = await client.get(f"/api/v1/tenants/{t1}/overview", headers=h1)
        assert ov_cancelled.json()["data"]["is_payment_approved"] is False

        factory = get_session_factory()
        async with factory() as session:
            db_sub = (
                await session.execute(select(Subscription).where(Subscription.provider_subscription_id == "sub_ls_1001"))
            ).scalar_one()
            assert db_sub.tenant_id == t1
            assert db_sub.status == "cancelled"
