"""Test Suite for Client Dashboard Service Synchronization, Bank Details, Admin Approval Workflow, and AI Sales Chatbot.
"""

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_bank_details_and_transfer_notification_flow():
    """Verify company bank details endpoint and client bank transfer notification."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Retrieve official company bank details
        bank_res = await client.get("/api/v1/payments/bank-details")
        assert bank_res.status_code == 200
        bank_data = bank_res.json()["data"]
        assert bank_data["bank_name"] == "Faysal Bank"
        assert bank_data["account_name"] == "Talha Azam"
        assert bank_data["account_number"] == "3398701000005292"
        assert bank_data["iban"] == "PK97FAYS3398701000005292"

        # 2. Register Client
        client_reg = await client.post("/api/v1/auth/register", json={
            "email": "transfer.client@clinic.com",
            "password": "Password123!",
            "full_name": "Clinic Founder",
        })
        assert client_reg.status_code == 201
        token = client_reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Create tenant with pending payment
        tenant_res = await client.post("/api/v1/tenants", json={
            "name": "Al Shifa Medical Center",
            "slug": "al-shifa-medical",
            "industry": "Clinics / Hospitals",
            "settings": {
                "onboarding_completed": True,
                "automation_active": False,
                "payment_approved": False,
            },
        }, headers=headers)
        assert tenant_res.status_code == 201
        tenant_id = tenant_res.json()["id"]
        tenant_headers = {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}

        # 4. Check initial dashboard: must be locked / empty state for operations
        overview_1 = await client.get(f"/api/v1/tenants/{tenant_id}/overview", headers=tenant_headers)
        assert overview_1.status_code == 200
        ov1 = overview_1.json()["data"]
        assert ov1["is_payment_approved"] is False
        assert ov1["payment_notified"] is False
        assert ov1["service_status"] == "Awaiting Bank Transfer Payment Approval"
        assert ov1["metrics"]["income"] == 0.0
        assert ov1["metrics"]["leads_generated"] == 0
        assert ov1["bank_details"]["account_number"] == "3398701000005292"

        # 5. Client submits bank transfer notification
        notify_res = await client.post(
            "/api/v1/payments/bank-transfer/notify",
            json={
                "transaction_reference": "FT2611990088",
                "notes": "Paid from Habib Bank mobile transfer",
                "amount": 249.0,
            },
            headers=tenant_headers,
        )
        assert notify_res.status_code == 200
        assert notify_res.json()["status"] == "pending_verification"
        assert notify_res.json()["transaction_reference"] == "FT2611990088"

        # 6. Check dashboard: status updates to verification in progress
        overview_2 = await client.get(f"/api/v1/tenants/{tenant_id}/overview", headers=tenant_headers)
        assert overview_2.status_code == 200
        ov2 = overview_2.json()["data"]
        assert ov2["payment_notified"] is True
        assert ov2["payment_reference"] == "FT2611990088"
        assert ov2["service_status"] == "Payment Transfer Submitted — Verification In Progress"


@pytest.mark.asyncio
async def test_admin_payment_approval_and_service_activation():
    """Verify that Platform Owner can review and approve bank transfer, activating services."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register Super Admin (first registered user in test db)
        admin_reg = await client.post("/api/v1/auth/register", json={
            "email": "super.admin@talox.com",
            "password": "Password123!",
            "full_name": "Super Admin",
        })
        admin_token = admin_reg.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 2. Register Client and Workspace
        client_reg = await client.post("/api/v1/auth/register", json={
            "email": "client.dental@care.com",
            "password": "Password123!",
            "full_name": "Dr. Dental",
        })
        client_token = client_reg.json()["access_token"]
        client_headers = {"Authorization": f"Bearer {client_token}"}

        tenant_res = await client.post("/api/v1/tenants", json={
            "name": "Prime Dental Clinic",
            "slug": "prime-dental",
            "industry": "Dental Clinics",
            "settings": {
                "onboarding_completed": True,
                "automation_active": False,
                "payment_approved": False,
            },
        }, headers=client_headers)
        tenant_id = tenant_res.json()["id"]
        tenant_headers = {"Authorization": f"Bearer {client_token}", "X-Tenant-ID": tenant_id}

        # 3. Client selects & subscribes to service package during onboarding
        cat_res = await client.get("/api/v1/services?industry=Dental%20Clinics&ensure_seeded=true")
        assert cat_res.status_code == 200
        service_id = cat_res.json()[0]["id"]

        sub_res = await client.post(
            "/api/v1/services/subscribe",
            json={
                "service_id": service_id,
                "plan_name": "growth",
                "price": 249.0,
                "billing_interval": "monthly",
            },
            headers=tenant_headers,
        )
        assert sub_res.status_code == 201

        # 4. Client notifies payment
        await client.post(
            "/api/v1/payments/bank-transfer/notify",
            json={
                "transaction_reference": "FT99887766",
                "notes": "Paid $249 via Faysal Bank",
                "amount": 249.0,
            },
            headers=tenant_headers,
        )

        # 4. Admin inspects pending payments in operations payload
        ops_res = await client.get("/api/v1/admin/operations", headers=admin_headers)
        assert ops_res.status_code == 200
        ops_data = ops_res.json()["data"]
        assert "pending_payments" in ops_data
        matching = [p for p in ops_data["pending_payments"] if p["tenant_id"] == tenant_id]
        assert len(matching) >= 1
        assert matching[0]["provider_reference"] == "FT99887766"

        # 5. Admin approves payment
        approve_res = await client.post(
            f"/api/v1/admin/tenants/{tenant_id}/approve-payment",
            json={"notes": "Confirmed on Faysal Bank statement"},
            headers=admin_headers,
        )
        assert approve_res.status_code == 200
        assert approve_res.json()["payment_approved"] is True

        # 6. Verify client dashboard is now unlocked and activated
        overview = await client.get(f"/api/v1/tenants/{tenant_id}/overview", headers=tenant_headers)
        assert overview.status_code == 200
        ov = overview.json()["data"]
        assert ov["is_payment_approved"] is True
        assert ov["service_status"] == "Active — Delivering Outcomes"


@pytest.mark.asyncio
async def test_public_sales_chatbot_capabilities_and_intent_trigger():
    """Verify Public Pre-Registration AI Sales Chatbot, hot lead detection, WhatsApp contact, and transition URL."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Ask about industries and packages
        chat_res1 = await client.post("/api/v1/marketing/chatbot/message", json={
            "message": "Hello, do you offer AI automation for dental clinics or cosmetic surgery?",
        })
        assert chat_res1.status_code == 200
        data1 = chat_res1.json()
        assert data1["detected_industry"] in ["Dental Clinics", "Cosmetic & Aesthetic Surgery"]
        assert "reply" in data1
        assert "+92 339 8701000" in data1["whatsapp_url"] or "+92 339 8701000" in data1["reply"]

        # 2. Trigger buying intent and human assistance
        chat_res2 = await client.post("/api/v1/marketing/chatbot/message", json={
            "message": "I am ready to buy your growth package right now! Can I talk to a human on WhatsApp to finalize?",
        })
        assert chat_res2.status_code == 200
        data2 = chat_res2.json()
        assert data2["hot_lead"] is True
        assert data2["alert_message"] == "A hot lead is ready to chat with you right now!"
        assert data2["whatsapp_url"] == "https://wa.me/923398701000"
        assert data2["onboarding_transition_url"] is not None
        assert "/register?" in data2["onboarding_transition_url"]
        assert "package=growth" in data2["onboarding_transition_url"]
