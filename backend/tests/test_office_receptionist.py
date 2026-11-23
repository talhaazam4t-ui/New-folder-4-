"""End-to-End Test Suite for Office Receptionist (AI Voice Agent — Retell AI, Telnyx, Cal.com).

Verifies:
1. "Office Receptionist" tier is seeded in the service catalog across industries with empty OAuth requirements.
2. Super Admin master voice credentials vault (`GET`/`PUT /api/v1/admin/voice-credentials`) encrypts
   secrets at rest, masks outputs, and blocks non-admin users (`403`).
3. Client onboarding flow (`PUT /api/v1/receptionist/config`) stores business info, operating hours,
   fallback phone, FAQs, greeting, encrypted Cal.com key, auto-provisions Telnyx + Retell AI, and
   generates a personalized Call Forwarding setup guide.
4. Client live FAQ updates (`PATCH /api/v1/receptionist/faqs`) re-sync cleanly.
5. Retell AI custom tools (`calcom/availability` & `calcom/book`), Retell call webhooks, Telnyx live
   human transfer TeXML (`<Dial>`), simulated calls, KPI summary, and strict cross-tenant isolation.
"""

import hashlib
import hmac
import json

import pytest
from app.config import settings
from app.database.models.receptionist import PlatformVoiceCredential, ReceptionistConfig
from app.database.supabase import get_session_factory
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


async def _register_and_create_tenant(
    client: AsyncClient,
    email: str,
    full_name: str,
    tenant_name: str,
    tenant_slug: str,
    industry: str = "Clinics / Hospitals",
):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": full_name},
    )
    assert reg.status_code in (200, 201), reg.text
    token = reg.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    t_res = await client.post(
        "/api/v1/tenants",
        json={"name": tenant_name, "slug": tenant_slug, "industry": industry},
        headers=auth_headers,
    )
    assert t_res.status_code == 201, t_res.text
    tenant_id = t_res.json()["id"]
    return {
        "token": token,
        "tenant_id": tenant_id,
        "auth_headers": auth_headers,
        "headers": {**auth_headers, "X-Tenant-ID": tenant_id},
    }


@pytest.mark.asyncio
async def test_office_receptionist_full_lifecycle_and_security():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Verify Office Receptionist is seeded in the service catalog
        svc_res = await client.get("/api/v1/services", params={"ensure_seeded": "true"})
        assert svc_res.status_code == 200, svc_res.text
        services = svc_res.json()
        recep_svc = next((s for s in services if s["slug"] == "office-receptionist"), None)
        assert recep_svc is not None, "office-receptionist service missing from catalog"
        assert "Office Receptionist" in recep_svc["name"]
        assert recep_svc["configuration_schema"].get("required_integrations") == []

        # 2. Register Super Admin (using configured super_admin_email) & two isolated clients
        admin_reg = await client.post(
            "/api/v1/auth/register",
            json={
                "email": settings.super_admin_emails[0],
                "password": "AdminPassword123!",
                "full_name": "Platform Owner",
            },
        )
        assert admin_reg.status_code in (200, 201), admin_reg.text
        admin_headers = {"Authorization": f"Bearer {admin_reg.json()['access_token']}"}

        client_a = await _register_and_create_tenant(
            client,
            email="clinic.owner@receptionist.io",
            full_name="Dr. Amina",
            tenant_name="Al Noor Dental Clinic",
            tenant_slug="al-noor-dental",
        )
        client_b = await _register_and_create_tenant(
            client,
            email="other.client@receptionist.io",
            full_name="Other Owner",
            tenant_name="Other Office LLC",
            tenant_slug="other-office-llc",
        )

        # 3. Non-admin cannot access or modify master voice credentials
        unauth_cred = await client.get(
            "/api/v1/admin/voice-credentials", headers=client_a["auth_headers"]
        )
        assert unauth_cred.status_code == 403

        # 4. Super Admin stores master Retell AI, Telnyx & Cal.com credentials encrypted at rest
        raw_retell_key = "key_test_retell_secret_987654321"
        raw_webhook_secret = "whsec_test_signing_secret_123456"
        raw_calcom_key = "cal_live_master_secret_555666"
        save_creds = await client.put(
            "/api/v1/admin/voice-credentials",
            json={
                "retell_api_key": raw_retell_key,
                "retell_webhook_secret": raw_webhook_secret,
                "telnyx_default_number": "+14155550188",
                "telnyx_default_country": "US",
                "calcom_api_key": raw_calcom_key,
            },
            headers=admin_headers,
        )
        assert save_creds.status_code == 200, save_creds.text
        creds_data = save_creds.json()["data"]
        assert creds_data["retell"]["configured"] is True
        assert creds_data["retell"]["source"] == "encrypted_vault"
        assert raw_retell_key not in json.dumps(creds_data)
        assert raw_calcom_key not in json.dumps(creds_data)
        assert creds_data["telnyx"]["default_number"] == "+14155550188"

        # Verify ciphertext stored in DB, NOT plaintext
        async with get_session_factory()() as db_sess:
            vault_row = (
                await db_sess.execute(
                    select(PlatformVoiceCredential).where(
                        PlatformVoiceCredential.provider == "retell"
                    )
                )
            ).scalar_one()
            assert vault_row.encrypted_config["api_key"] != raw_retell_key

        # 5. Client subscribes ONLY to Office Receptionist -> onboarding requires zero unrelated OAuth apps
        sub_res = await client.post(
            "/api/v1/services/subscribe",
            json={
                "service_id": recep_svc["id"],
                "plan_name": "growth",
                "billing_interval": "monthly",
                "price": 399.0,
            },
            headers=client_a["headers"],
        )
        assert sub_res.status_code in (200, 201), sub_res.text

        onb_req = await client.get(
            "/api/v1/integrations/onboarding-requirements", headers=client_a["headers"]
        )
        assert onb_req.status_code == 200, onb_req.text
        onb_data = onb_req.json()["data"]
        assert onb_data["required_integrations"] == []
        assert any(
            p["service_slug"] == "office-receptionist" for p in onb_data["purchased_services"]
        )
        # Before saving Receptionist config & before payment approval, onboarding & automation are incomplete
        assert onb_data["onboarding_completed"] is False
        assert onb_data["automation_active"] is False

        # 6. Before payment approval, PUT /config saves an awaiting_payment draft (does NOT provision Telnyx/Retell)
        client_cal_secret = "cal_live_client_alnoor_secret_999"
        draft_res = await client.put(
            "/api/v1/receptionist/config",
            json={
                "business_name": "Al Noor Dental Clinic",
                "operating_hours": "Mon-Sat 9:00 AM - 7:00 PM",
                "fallback_phone_number": "+14155550101",
                "greeting_message": "Thank you for calling Al Noor Dental Clinic! How can I help you?",
                "faqs_knowledge_base": "Q: Do you accept insurance?\nA: Yes, all major dental plans.",
                "calcom_booking_url": "https://cal.com/al-noor-dental/checkup",
                "calcom_event_type_id": "44210",
                "calcom_api_key": client_cal_secret,
                "auto_provision": True,
            },
            headers=client_a["headers"],
        )
        assert draft_res.status_code == 200, draft_res.text
        draft_body = draft_res.json()
        assert draft_body["payment_approved"] is False
        draft_cfg = draft_body["data"]
        assert draft_cfg["provisioning_status"] == "awaiting_payment"
        assert draft_cfg["telnyx_phone_number"] is None
        assert draft_cfg["retell_agent_id"] is None
        assert draft_cfg["calcom_api_key_configured"] is True
        assert client_cal_secret not in json.dumps(draft_cfg)

        # Unpaid clients are blocked (403) from manual provisioning & test call simulation
        unpaid_prov = await client.post("/api/v1/receptionist/provision", headers=client_a["headers"])
        assert unpaid_prov.status_code == 403
        unpaid_sim = await client.post(
            "/api/v1/receptionist/calls/simulate",
            json={"caller_name": "Test Caller", "scenario": "faq_inquiry"},
            headers=client_a["headers"],
        )
        assert unpaid_sim.status_code == 403

        # Onboarding is now marked complete (config saved), while automation remains locked awaiting payment
        onb_pre_pay = (
            await client.get("/api/v1/integrations/onboarding-requirements", headers=client_a["headers"])
        ).json()["data"]
        assert onb_pre_pay["all_required_connected"] is True
        assert onb_pre_pay["onboarding_completed"] is True
        assert onb_pre_pay["automation_active"] is False

        # Verify client Cal.com key is encrypted in DB
        async with get_session_factory()() as db_sess:
            cfg_row = (
                await db_sess.execute(
                    select(ReceptionistConfig).where(
                        ReceptionistConfig.tenant_id == client_a["tenant_id"]
                    )
                )
            ).scalar_one()
            assert cfg_row.encrypted_calcom_api_key != client_cal_secret

        # 6b. Admin approves payment -> automatically provisions Telnyx + Retell AI + Call Forwarding guide
        approve_res = await client.post(
            f"/api/v1/admin/tenants/{client_a['tenant_id']}/approve-payment",
            json={"notes": "Bank transfer verified"},
            headers=admin_headers,
        )
        assert approve_res.status_code == 200, approve_res.text
        assert approve_res.json()["payment_approved"] is True
        assert approve_res.json()["receptionist_provisioned"] is True

        # Verify GET /receptionist/config now reflects provisioned active status & guide
        cfg_get = await client.get("/api/v1/receptionist/config", headers=client_a["headers"])
        assert cfg_get.status_code == 200, cfg_get.text
        assert cfg_get.json()["payment_approved"] is True
        assert cfg_get.json()["has_subscription"] is True
        cfg = cfg_get.json()["data"]
        assert cfg["business_name"] == "Al Noor Dental Clinic"
        assert cfg["fallback_phone_number"] == "+14155550101"
        assert cfg["telnyx_phone_number"] == "+14155550188"
        assert cfg["retell_agent_id"] is not None
        guide = cfg["call_forwarding_guide"]
        assert guide["assigned_ai_number"] == "+14155550188"
        assert "*21*+14155550188#" == guide["quick_dial_codes"]["forward_all_calls_gsm"]
        assert len(guide["steps"]) >= 4

        # Office-Receptionist-only client now has full onboarding & automation readiness active
        onb_post_pay = (
            await client.get("/api/v1/integrations/onboarding-requirements", headers=client_a["headers"])
        ).json()["data"]
        assert onb_post_pay["all_required_connected"] is True
        assert onb_post_pay["onboarding_completed"] is True
        assert onb_post_pay["automation_active"] is True

        # 7. Client updates FAQs from dashboard
        faq_res = await client.patch(
            "/api/v1/receptionist/faqs",
            json={
                "faqs_knowledge_base": "Q: Emergency toothache?\nA: Ask for a human to transfer immediately.",
            },
            headers=client_a["headers"],
        )
        assert faq_res.status_code == 200, faq_res.text
        assert "Emergency toothache" in faq_res.json()["data"]["faqs_knowledge_base"]

        # 8. Retell AI custom function-calling tools (wrapped `{name, call, args}` payload format!)
        avail_res = await client.post(
            f"/api/v1/receptionist/tools/{client_a['tenant_id']}/calcom/availability",
            json={
                "name": "check_calcom_availability",
                "call": {"call_id": "call_retell_live_001"},
                "args": {"date": "2026-11-28"},
            },
        )
        assert avail_res.status_code == 200, avail_res.text
        assert len(avail_res.json()["data"]["slots"]) >= 1

        book_res = await client.post(
            f"/api/v1/receptionist/tools/{client_a['tenant_id']}/calcom/book",
            json={
                "name": "book_calcom_appointment",
                "call": {"call_id": "call_retell_live_001"},
                "args": {
                    "start_iso": "2026-11-28T14:00:00Z",
                    "attendee_name": "Omar Hassan",
                    "attendee_phone": "+14155550222",
                    "notes": "Routine dental cleaning",
                },
            },
        )
        assert book_res.status_code == 200, book_res.text
        assert book_res.json()["data"]["status"] == "booked"

        # 9. Retell AI signed webhook logs duration, summary, and transcript (official `v=ts,d=hex` format)
        webhook_payload = {
            "event": "call_analyzed",
            "call": {
                "call_id": "call_retell_live_001",
                "agent_id": cfg["retell_agent_id"],
                "from_number": "+14155550222",
                "to_number": cfg["telnyx_phone_number"],
                "duration_seconds": 135,
                "call_analysis": {
                    "call_summary": "Caller Omar Hassan booked a dental cleaning via Cal.com.",
                },
                "transcript": "AI: Thank you for calling Al Noor Dental Clinic!\nCaller: Please book Saturday at 2 PM.",
            },
        }
        raw_body = json.dumps(webhook_payload).encode("utf-8")
        # Invalid signature must be rejected (403)
        bad_sig = await client.post(
            "/api/v1/receptionist/webhooks/retell",
            content=raw_body,
            headers={"Content-Type": "application/json", "x-retell-signature": "v=1700000000000,d=invalid"},
        )
        assert bad_sig.status_code == 403

        ts_str = "1700000000000"
        retell_digest = hmac.new(
            raw_webhook_secret.encode("utf-8"),
            raw_body + ts_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        ok_hook = await client.post(
            "/api/v1/receptionist/webhooks/retell",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "x-retell-signature": f"v={ts_str},d={retell_digest}",
            },
        )
        assert ok_hook.status_code == 200, ok_hook.text
        assert ok_hook.json()["data"]["processed"] is True

        # 10. Telnyx TeXML Voice Webhook live emergency transfer returns <Dial> TeXML to fallback number
        tx_res = await client.post(
            "/api/v1/receptionist/webhooks/telnyx/voice?emergency=true",
            data={
                "To": cfg["telnyx_phone_number"],
                "From": "+14155550333",
                "CallSid": "TX_EMERGENCY_001",
            },
        )
        assert tx_res.status_code == 200
        assert '<Dial timeout="25">+14155550101</Dial>' in tx_res.text

        # 11. Simulate FAQ call & verify call logs + KPI summary + cross-tenant isolation
        sim_res = await client.post(
            "/api/v1/receptionist/calls/simulate",
            json={
                "caller_name": "Nadia Khan",
                "caller_phone": "+14155550444",
                "scenario": "faq_inquiry",
            },
            headers=client_a["headers"],
        )
        assert sim_res.status_code == 200, sim_res.text

        calls_res = await client.get("/api/v1/receptionist/calls", headers=client_a["headers"])
        assert calls_res.status_code == 200, calls_res.text
        calls_data = calls_res.json()["data"]
        assert calls_data["summary"]["total_calls"] == 3
        assert calls_data["summary"]["appointments_booked"] == 1
        assert calls_data["summary"]["human_transfers"] == 1
        assert len(calls_data["booked_appointments"]) == 1

        # Cross-tenant isolation: Client B sees zero of Client A's config or calls BEFORE onboarding
        b_cfg = await client.get("/api/v1/receptionist/config", headers=client_b["headers"])
        assert b_cfg.status_code == 200
        assert b_cfg.json()["data"] is None

        b_calls = await client.get("/api/v1/receptionist/calls", headers=client_b["headers"])
        assert b_calls.status_code == 200
        assert b_calls.json()["data"]["summary"]["total_calls"] == 0

        # 12. Multi-client isolation: Client B subscribes, gets paid approval, must get a DISTINCT Telnyx number
        #     and must NOT inherit Admin's master Cal.com key/event
        b_sub = await client.post(
            "/api/v1/services/subscribe",
            json={
                "service_id": recep_svc["id"],
                "plan_name": "starter",
                "billing_interval": "monthly",
                "price": 199.0,
            },
            headers=client_b["headers"],
        )
        assert b_sub.status_code in (200, 201), b_sub.text
        await client.post(
            f"/api/v1/admin/tenants/{client_b['tenant_id']}/approve-payment",
            json={"notes": "Client B paid"},
            headers=admin_headers,
        )
        b_upsert = await client.put(
            "/api/v1/receptionist/config",
            json={
                "business_name": "Other Office LLC",
                "operating_hours": "Mon-Fri 9:00 AM - 5:00 PM",
                "fallback_phone_number": "+14155550999",
                "greeting_message": "Hello from Other Office.",
                "faqs_knowledge_base": "General services.",
                "auto_provision": True,
            },
            headers=client_b["headers"],
        )
        assert b_upsert.status_code == 200, b_upsert.text
        b_data = b_upsert.json()["data"]
        assert b_data["telnyx_phone_number"] is not None
        assert b_data["telnyx_phone_number"] != cfg["telnyx_phone_number"]

        b_avail = await client.post(
            f"/api/v1/receptionist/tools/{client_b['tenant_id']}/calcom/availability",
            json={"date": "2026-11-28"},
        )
        assert b_avail.status_code == 200
        assert b_avail.json()["data"]["calcom_connected"] is False
        assert b_avail.json()["data"]["is_live"] is False

        b_book = await client.post(
            f"/api/v1/receptionist/tools/{client_b['tenant_id']}/calcom/book",
            json={
                "start_iso": "2026-11-28T15:00:00Z",
                "attendee_name": "Bilal Ahmed",
            },
        )
        assert b_book.status_code == 200
        b_book_data = b_book.json()["data"]
        assert b_book_data["calcom_connected"] is False
        assert b_book_data["is_live"] is False
        assert b_book_data["booking_uid"].startswith("local_req_")

        # Verify Admin /operations endpoint returns arranged 7 services + platform_keys_status cleanly
        ops_res = await client.get("/api/v1/admin/operations", headers=admin_headers)
        assert ops_res.status_code == 200, ops_res.text
        ops_data = ops_res.json()["data"]
        assert len(ops_data["services"]) == 7
        assert ops_data["services"][0]["tier_number"] == 1
        assert len(ops_data["platform_keys_status"]) == 7
        assert ops_data["services_performance"]["total_services"] == 7

        # Spoofing Client A's X-Tenant-ID with Client B's JWT is blocked with 403
        spoof = await client.get(
            "/api/v1/receptionist/calls",
            headers={**client_b["auth_headers"], "X-Tenant-ID": client_a["tenant_id"]},
        )
        assert spoof.status_code == 403
