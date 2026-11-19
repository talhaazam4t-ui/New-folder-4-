import pytest
from app.automation.budget_manager import budget_manager
from app.config import settings
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_whatsapp_embedded_signup_webhook_and_ambiguity_guardrails():
    """Verify Meta Embedded Signup connection, webhook challenge, confirmed payment extraction, and ambiguous payment human approval."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": "ops@propertyhub.com",
            "password": "Password123!",
            "full_name": "Property Hub Owner",
        })
        token = reg.json()["access_token"]
        t_res = await client.post("/api/v1/tenants", json={
            "name": "Property Hub Management",
            "slug": "property-hub-mgmt",
            "industry": "Real Estate",
        }, headers={"Authorization": f"Bearer {token}"})
        tenant_id = t_res.json()["id"]
        budget_manager.admin_reset_circuit(tenant_id)
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # 1. Connect WhatsApp Business via Meta Embedded Signup
        conn_res = await client.post("/api/v1/integrations/whatsapp/connect", json={
            "oauth_code": "meta_oauth_code_test_88123",
        }, headers=headers)
        assert conn_res.status_code == 201
        conn_data = conn_res.json()["data"]
        assert conn_data["provider"] == "whatsapp"
        assert conn_data["status"] == "connected"

        # 2. Verify GET webhook challenge
        challenge_res = await client.get(
            "/api/v1/integrations/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": settings.whatsapp_verify_token,
                "hub.challenge": "challenge_accepted_991",
            },
        )
        assert challenge_res.status_code == 200
        assert challenge_res.text == "challenge_accepted_991"

        # 3. Process UNAMBIGUOUS WhatsApp rent payment -> creates BusinessRecord automatically
        unambig_res = await client.post("/api/v1/integrations/whatsapp/webhook", json={
            "sender_phone": "+15550102030",
            "sender_name": "Alice (Unit 12A)",
            "message_text": "Paid rent $1850 for Unit 12A",
            "message_id": "wamid.unambig.001",
        }, headers=headers)
        assert unambig_res.status_code == 200
        unambig_data = unambig_res.json()["data"]
        assert unambig_data["classification"] == "financial_confirmed"
        assert unambig_data["requires_confirmation"] is False
        assert unambig_data["business_record_id"] is not None
        assert unambig_data["amount"] == 1850.0

        # 4. Process AMBIGUOUS WhatsApp financial message -> MUST NOT create BusinessRecord; routes to Approval
        ambig_res = await client.post("/api/v1/integrations/whatsapp/webhook", json={
            "sender_phone": "+15550109988",
            "sender_name": "Bob (Unit 7C)",
            "message_text": "I think I paid rent maybe $900 or $950 not sure?",
            "message_id": "wamid.ambig.002",
        }, headers=headers)
        assert ambig_res.status_code == 200
        ambig_data = ambig_res.json()["data"]
        assert ambig_data["classification"] == "financial_ambiguous"
        assert ambig_data["requires_confirmation"] is True
        assert ambig_data["business_record_id"] is None
        assert ambig_data["approval_id"] is not None

        # Verify ledger only has the 1 confirmed transaction ($1850), NOT the ambiguous one
        summary = (await client.get("/api/v1/business/summary", headers=headers)).json()
        assert summary["record_count"] == 1
        assert summary["total_rent"] == 1850.0

        # 5. Process general WhatsApp customer inquiry -> captures Lead & generates AI auto-reply
        inq_res = await client.post("/api/v1/integrations/whatsapp/webhook", json={
            "sender_phone": "+15550177777",
            "sender_name": "Prospective Tenant",
            "message_text": "Hi, do you have any 2-bedroom apartments available next month?",
        }, headers=headers)
        assert inq_res.status_code == 200
        inq_data = inq_res.json()["data"]
        assert inq_data["classification"] == "lead_inquiry"
        assert inq_data["lead_id"] is not None
        assert len(inq_data["auto_reply"]) > 0

        # 6. Verify Notifications were generated and can be marked as read
        notifs_res = await client.get("/api/v1/notifications", headers=headers)
        assert notifs_res.status_code == 200
        notifs = notifs_res.json()["data"]
        assert len(notifs) >= 2
        notif_id = notifs[0]["id"]

        read_res = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=headers)
        assert read_res.status_code == 200
        assert read_res.json()["data"]["status"] == "read"


@pytest.mark.asyncio
async def test_whatsapp_webhook_unmatched_phone_and_missing_tenant_no_leak(monkeypatch):
    """Unmatched Meta phone_number_id or missing X-Tenant-ID must never leak records into another tenant."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": "isolated.tenant@example.com",
            "password": "Password123!",
            "full_name": "Isolated Owner",
        })
        token = reg.json()["access_token"]
        t_res = await client.post("/api/v1/tenants", json={
            "name": "Isolated Tenant Corp",
            "slug": "isolated-tenant-corp",
            "industry": "Real Estate",
        }, headers={"Authorization": f"Bearer {token}"})
        tenant_id = t_res.json()["id"]
        headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # 1. Meta webhook with unknown phone_number_id returns 200 with processed=0 and creates zero records
        meta_payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "unknown_phone_id_999"},
                                "contacts": [{"wa_id": "15559990001", "profile": {"name": "Stranger"}}],
                                "messages": [{"id": "wamid.unknown.1", "from": "15559990001", "text": {"body": "Paid rent $5000"}}],
                            }
                        }
                    ]
                }
            ]
        }
        res_unknown = await client.post("/api/v1/integrations/whatsapp/webhook", json=meta_payload)
        assert res_unknown.status_code == 200
        assert res_unknown.json()["processed"] == 0

        # 2. Simple JSON fallback without X-Tenant-ID is rejected (400) and creates zero records
        res_no_header = await client.post(
            "/api/v1/integrations/whatsapp/webhook",
            json={"sender_phone": "+15558887777", "sender_name": "NoHeader", "message_text": "Paid rent $999"},
        )
        assert res_no_header.status_code == 400

        # 3. Verify zero leads and zero business records leaked into the active tenant
        summary = (await client.get("/api/v1/business/summary", headers=headers)).json()
        assert summary["record_count"] == 0
        leads = (await client.get("/api/v1/marketing/leads", headers=headers)).json()
        assert leads == []
