"""Phase 2 Tests: Native Asyncio Job Engine, Prepaid Credit Wallet, Free Trial, Multi-Currency Gateways & HITL Refunds."""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from app.config import settings
from app.database.models.automation import AuditLog, ScheduledJob
from app.database.models.billing import Payment
from app.database.models.marketing import Lead
from app.database.models.receptionist import ReceptionistConfig
from app.database.models.service import Service, ServiceSubscription
from app.database.models.tenant import Tenant
from app.database.supabase import get_session_factory
from app.main import app
from app.services.job_engine_service import job_engine_service
from app.services.wallet_service import wallet_service
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


async def _register_and_create_workspace(client: AsyncClient, email: str, slug: str, name: str = "Phase2 Co"):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Phase2 Owner"},
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}
    t_res = await client.post(
        "/api/v1/tenants",
        json={"name": name, "slug": slug, "industry": "Clinics / Hospitals"},
        headers=auth_headers,
    )
    assert t_res.status_code in (200, 201)
    tenant_id = t_res.json()["id"]
    tenant_headers = {**auth_headers, "X-Tenant-ID": str(tenant_id)}
    return uuid.UUID(tenant_id), auth_headers, tenant_headers


@pytest.mark.asyncio
async def test_native_job_engine_retry_dlq_and_cron_tick_auth(monkeypatch):
    """Verify delayed job enqueue, idempotency, exponential retry, dead-letter queue, and secret-protected cron tick."""
    monkeypatch.setattr(settings, "cron_secret", "phase2_super_cron_secret_123")
    attempts_seen = []

    async def _flaky_handler(session, job):
        attempts_seen.append(job.attempts)
        if job.attempts < 2:
            raise RuntimeError("transient upstream timeout")
        return {"ok": True}

    async def _always_fail_handler(session, job):
        raise RuntimeError("permanent upstream failure")

    job_engine_service.register_handler("test_flaky_job", _flaky_handler)
    job_engine_service.register_handler("test_dead_job", _always_fail_handler)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tenant_id, _, tenant_headers = await _register_and_create_workspace(
            client, "jobs.owner@agency.ai", "jobs-owner-ws"
        )

        # 1. Missing or invalid X-Cron-Secret must fail with 401
        bad_cron = await client.post("/api/v1/internal/cron/tick")
        assert bad_cron.status_code == 401
        wrong_cron = await client.post(
            "/api/v1/internal/cron/tick", headers={"X-Cron-Secret": "wrong_secret"}
        )
        assert wrong_cron.status_code == 401

        # 2. Enqueue via API + deduplication by idempotency_key
        enq1 = await client.post(
            "/api/v1/internal/jobs/enqueue",
            json={
                "job_type": "low_balance_alert",
                "payload": {"title": "Cron Alert", "message": "Test job fired cleanly"},
                "delay_seconds": 0,
                "idempotency_key": f"idem_{tenant_id}",
            },
            headers=tenant_headers,
        )
        assert enq1.status_code == 201
        enq2 = await client.post(
            "/api/v1/internal/jobs/enqueue",
            json={
                "job_type": "low_balance_alert",
                "payload": {"title": "Duplicate"},
                "delay_seconds": 0,
                "idempotency_key": f"idem_{tenant_id}",
            },
            headers=tenant_headers,
        )
        assert enq2.status_code == 201
        assert enq2.json()["data"]["idempotent"] is True

        # 3. Valid cron tick executes queued job and returns engine summary
        ok_cron = await client.post(
            "/api/v1/internal/cron/tick",
            headers={"X-Cron-Secret": "phase2_super_cron_secret_123"},
        )
        assert ok_cron.status_code == 200
        assert ok_cron.json()["data"]["scheduled_jobs"]["completed"] >= 1

        # 4. Flaky job retries with backoff and completes on 2nd attempt; always-fail hits dead_letter
        factory = get_session_factory()
        async with factory() as session:
            flaky = await job_engine_service.enqueue_job(
                session, job_type="test_flaky_job", tenant_id=tenant_id, max_attempts=3
            )
            dead = await job_engine_service.enqueue_job(
                session, job_type="test_dead_job", tenant_id=tenant_id, max_attempts=2
            )
            res1 = await job_engine_service.process_due_jobs(session)
            assert res1["retried"] == 2

            # Force due immediately to verify backoff progression & completion / dead_letter
            for jid in (uuid.UUID(flaky["id"]), uuid.UUID(dead["id"])):
                row = (
                    await session.execute(select(ScheduledJob).where(ScheduledJob.id == jid))
                ).scalar_one()
                row.run_at = datetime.now(timezone.utc) - timedelta(seconds=5)
            await session.commit()

            res2 = await job_engine_service.process_due_jobs(session)
            assert res2["completed"] == 1
            assert res2["dead_lettered"] == 1

            dead_row = (
                await session.execute(
                    select(ScheduledJob).where(ScheduledJob.id == uuid.UUID(dead["id"]))
                )
            ).scalar_one()
            assert dead_row.status == "dead_letter"

        # 5. Tenant can inspect jobs and retry dead-lettered job
        jobs_list = await client.get("/api/v1/internal/jobs", headers=tenant_headers)
        assert jobs_list.status_code == 200
        assert any(j["status"] == "dead_letter" for j in jobs_list.json()["data"]["jobs"])

        retry_res = await client.post(
            f"/api/v1/internal/jobs/{dead['id']}/retry", headers=tenant_headers
        )
        assert retry_res.status_code == 200
        assert retry_res.json()["data"]["status"] == "queued"


@pytest.mark.asyncio
async def test_wallet_auto_pause_deductions_and_free_trial_lifecycle(monkeypatch):
    """Verify credit wallet deductions, low-balance alerts, 402 auto-pause, 7-day trial, and cron expiration."""
    monkeypatch.setattr(settings, "cron_secret", "trial_cron_secret_xyz")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tenant_id, _, tenant_headers = await _register_and_create_workspace(
            client, "wallet.owner@clinic.ai", "wallet-clinic-ws"
        )

        # 1. Start 7-Day Free Trial (grants 100 credits, activates auto-pause, unlocks workspace)
        trial_res = await client.post("/api/v1/payments/start-trial", headers=tenant_headers)
        assert trial_res.status_code == 200
        trial_data = trial_res.json()["data"]
        assert trial_data["wallet"]["balance_credits"] == 100.0
        assert trial_data["wallet"]["auto_pause_enabled"] is True
        assert trial_data["trial"]["trial_active"] is True
        assert trial_data["trial"]["trial_used"] is True

        # Duplicate trial attempt rejected cleanly with 409
        dup_trial = await client.post("/api/v1/payments/start-trial", headers=tenant_headers)
        assert dup_trial.status_code == 409

        # Overview reflects wallet balance & active trial unlock
        ov = await client.get(f"/api/v1/tenants/{tenant_id}/overview", headers=tenant_headers)
        assert ov.status_code == 200
        assert ov.json()["data"]["is_payment_approved"] is True
        assert ov.json()["data"]["wallet_summary"]["balance_credits"] == 100.0
        assert ov.json()["data"]["trial_info"]["trial_active"] is True

        # 2. Seed ReceptionistConfig + Lead for call simulation & outreach deduction verification
        factory = get_session_factory()
        async with factory() as session:
            session.add(
                ReceptionistConfig(
                    tenant_id=tenant_id,
                    business_name="Wallet Clinic",
                    operating_hours="Mon-Fri 9-5",
                    fallback_phone_number="+15551112222",
                    greeting_message="Hello!",
                    faqs_knowledge_base="Open daily.",
                )
            )
            lead = Lead(
                tenant_id=tenant_id,
                name="Sample Dental Clinic",
                source="openstreetmap_live",
                status="new",
                phone="+923001112233",
                qualification_score=88,
                metadata_={
                    "whatsapp_pitch": "Hi Sample Dental Clinic team, book an AI Receptionist demo!",
                    "approval_status": "pending_approval",
                },
            )
            session.add(lead)
            await session.commit()
            lead_id = lead.id

        # 3. Simulated call (74s -> 2 mins -> 10 credits) + WhatsApp outbound (1 cr) + HITL outreach (1 cr)
        sim_res = await client.post(
            "/api/v1/receptionist/calls/simulate",
            json={"caller_name": "Patient Ali", "caller_phone": "+923001234567", "scenario": "faq_inquiry"},
            headers=tenant_headers,
        )
        assert sim_res.status_code == 200

        wa_send = await client.post(
            "/api/v1/integrations/whatsapp/send",
            json={"to_phone": "+923001234567", "message_body": "Appointment reminder!"},
            headers=tenant_headers,
        )
        assert wa_send.status_code == 200

        outreach_send = await client.post(
            f"/api/v1/agents/outreach-autopilot/leads/{lead_id}/approve-send",
            json={"channel": "whatsapp", "mode": "send"},
            headers=tenant_headers,
        )
        assert outreach_send.status_code == 200

        w_check = await client.get("/api/v1/payments/wallet", headers=tenant_headers)
        w_payload = w_check.json()["data"]
        assert w_payload["wallet"]["balance_credits"] == 88.0  # 100 - 10 - 1 - 1
        assert len(w_payload["ledger"]) >= 4

        # 4. Deplete remaining credits -> auto-pause triggers + blocks paid sends with 402
        async with factory() as session:
            await wallet_service.debit_credits(
                session=session,
                tenant_id=tenant_id,
                category="whatsapp_message",
                unit_count=88.0,
                description="Bulk campaign test depletion",
            )
        w_paused = await client.get("/api/v1/payments/wallet", headers=tenant_headers)
        assert w_paused.json()["data"]["wallet"]["balance_credits"] == 0.0
        assert w_paused.json()["data"]["wallet"]["is_paused"] is True

        blocked_wa = await client.post(
            "/api/v1/integrations/whatsapp/send",
            json={"to_phone": "+923001234567", "message_body": "Should be paused"},
            headers=tenant_headers,
        )
        assert blocked_wa.status_code == 402

        blocked_call = await client.post(
            "/api/v1/receptionist/calls/simulate",
            json={"caller_name": "Blocked Caller", "caller_phone": "+923001234567", "scenario": "faq_inquiry"},
            headers=tenant_headers,
        )
        assert blocked_call.status_code == 402

        # 5. Crediting wallet automatically unpauses
        async with factory() as session:
            await wallet_service.credit_wallet(
                session=session,
                tenant_id=tenant_id,
                credits=25.0,
                category="manual_topup",
                description="Top up unpause",
            )
        unpaused_wa = await client.post(
            "/api/v1/integrations/whatsapp/send",
            json={"to_phone": "+923001234567", "message_body": "Unpaused now!"},
            headers=tenant_headers,
        )
        assert unpaused_wa.status_code == 200

        # 6. Simulate expired 7-day trial -> internal cron tick reverts unpaid workspace to pending_approval
        async with factory() as session:
            t_obj = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
            s_copy = dict(t_obj.settings or {})
            s_copy["trial_ends_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            t_obj.settings = s_copy
            await session.commit()

        cron_res = await client.post(
            "/api/v1/internal/cron/tick", headers={"X-Cron-Secret": "trial_cron_secret_xyz"}
        )
        assert cron_res.status_code == 200
        assert cron_res.json()["data"]["trial_expiration"]["expired"] >= 1

        ov_expired = await client.get(f"/api/v1/tenants/{tenant_id}/overview", headers=tenant_headers)
        assert ov_expired.json()["data"]["is_payment_approved"] is False
        assert ov_expired.json()["data"]["trial_info"]["trial_expired"] is True


@pytest.mark.asyncio
async def test_multi_currency_checkout_webhooks_and_hitl_refunds(monkeypatch):
    """Verify PayFast/Safepay PKR, Stripe/Payoneer USD checkout + HMAC webhook provisioning + HITL refunds."""
    monkeypatch.setattr(settings, "payfast_secured_key", "pf_secret_key_test")
    monkeypatch.setattr(settings, "safepay_webhook_secret", "sp_secret_key_test")
    monkeypatch.setattr(settings, "payoneer_account_email", "payouts@teloxtech.stream")
    monkeypatch.setattr(settings, "payoneer_webhook_secret", "pynr_secret_key_test")
    monkeypatch.setattr(
        settings,
        "super_admin_emails",
        [*settings.super_admin_emails, "gateway.admin@enterprise.com"],
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tenant_id, admin_headers, tenant_headers = await _register_and_create_workspace(
            client, "gateway.admin@enterprise.com", "gateway-enterprise"
        )

        # 1. Create a PKR PayFast wallet top-up checkout session
        pf_checkout = await client.post(
            "/api/v1/payments/checkout",
            json={"provider": "payfast", "purpose": "wallet_topup", "pack_id": "pack_starter", "currency": "PKR"},
            headers=tenant_headers,
        )
        assert pf_checkout.status_code == 200
        pf_data = pf_checkout.json()["data"]
        assert pf_data["currency"] == "PKR"
        assert pf_data["amount"] == 7000.0
        pf_ref = pf_data["reference_id"]

        # Invalid PayFast signature rejected with 400
        pf_payload = json.dumps({
            "event": "payment.completed",
            "BASKET_ID": pf_ref,
            "TXNAMT": 7000.0,
            "CURRENCY_CODE": "PKR",
            "metadata": {
                "tenant_id": str(tenant_id),
                "purpose": "wallet_topup",
                "credits": 250,
            },
        }).encode("utf-8")

        bad_wh = await client.post(
            "/api/v1/payments/webhooks/payfast",
            content=pf_payload,
            headers={"X-PayFast-Signature": "deadbeef"},
        )
        assert bad_wh.status_code == 400

        # Valid HMAC signature provisions credits idempotently
        pf_sig = hmac.new(b"pf_secret_key_test", pf_payload, hashlib.sha256).hexdigest()
        ok_wh = await client.post(
            "/api/v1/payments/webhooks/payfast",
            content=pf_payload,
            headers={"X-PayFast-Signature": pf_sig},
        )
        assert ok_wh.status_code == 200
        assert ok_wh.json()["reconciled"] is True
        assert ok_wh.json()["credits_granted"] == 250.0
        payment_id = ok_wh.json()["payment_id"]

        # Replay of exact same webhook must be idempotent (zero duplicate credit)
        replay_wh = await client.post(
            "/api/v1/payments/webhooks/payfast",
            content=pf_payload,
            headers={"X-PayFast-Signature": pf_sig},
        )
        assert replay_wh.status_code == 200
        assert replay_wh.json()["idempotent"] is True

        # 2. Verify Safepay PKR & Payoneer USD checkout + webhook signatures
        sf_checkout = await client.post(
            "/api/v1/payments/checkout",
            json={"provider": "safepay", "purpose": "subscription", "amount": 41400.0, "currency": "PKR"},
            headers=tenant_headers,
        )
        assert sf_checkout.status_code == 200
        sf_ref = sf_checkout.json()["data"]["reference_id"]
        sf_payload = json.dumps({
            "event": "payment.succeeded",
            "data": {"token": sf_ref, "metadata": {"tenant_id": str(tenant_id), "purpose": "subscription"}},
            "amount": 41400.0,
            "currency": "PKR",
        }).encode("utf-8")
        sf_sig = hmac.new(b"sp_secret_key_test", sf_payload, hashlib.sha256).hexdigest()
        sf_wh = await client.post(
            "/api/v1/payments/webhooks/safepay",
            content=sf_payload,
            headers={"X-SFPY-SIGNATURE": sf_sig},
        )
        assert sf_wh.status_code == 200
        assert sf_wh.json()["reconciled"] is True

        pynr_checkout = await client.post(
            "/api/v1/payments/checkout",
            json={"provider": "payoneer", "purpose": "wallet_topup", "pack_id": "pack_growth", "currency": "USD"},
            headers=tenant_headers,
        )
        assert pynr_checkout.status_code == 200
        assert "payouts@teloxtech.stream" in pynr_checkout.json()["data"]["instructions"]

        # 3. Wallet balance accumulated cleanly: 250 (PayFast) + 500 (Safepay plan grant) = 750
        w_after = await client.get("/api/v1/payments/wallet", headers=tenant_headers)
        assert w_after.json()["data"]["wallet"]["balance_credits"] == 750.0

        # 4. Refund request goes through HITL ApprovalManager (never auto-refunds!)
        refund_req = await client.post(
            f"/api/v1/payments/{payment_id}/refund-request",
            json={"reason": "Customer requested duplicate top-up refund"},
            headers=tenant_headers,
        )
        assert refund_req.status_code == 201
        approval_id = refund_req.json()["data"]["approval"]["id"]
        assert refund_req.json()["data"]["payment_status"] == "completed"

        # Before approval, Payment is still completed
        payments_before = await client.get("/api/v1/payments", headers=tenant_headers)
        target_before = [p for p in payments_before.json() if p["id"] == payment_id][0]
        assert target_before["status"] == "completed"

        # Approving the HITL request marks payment refunded
        approve_res = await client.post(
            f"/api/v1/approvals/{approval_id}/approve",
            json={"reason": "Verified duplicate charge"},
            headers=tenant_headers,
        )
        assert approve_res.status_code == 200
        assert approve_res.json()["data"]["refund"]["status"] == "refunded"

        payments_after = await client.get("/api/v1/payments", headers=tenant_headers)
        target_after = [p for p in payments_after.json() if p["id"] == payment_id][0]
        assert target_after["status"] == "refunded"
