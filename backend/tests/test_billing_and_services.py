import uuid

import pytest
from app.database.supabase import get_session_factory
from app.main import app
from app.services.billing_service import billing_service
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_complete_service_subscription_and_payment_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register owner & create tenant workspace
        reg = await client.post("/api/v1/auth/register", json={
            "email": "billing.client@enterprise.com",
            "password": "Password123!",
            "full_name": "Billing Client",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        tenant_res = await client.post("/api/v1/tenants", json={
            "name": "Billing Enterprise",
            "slug": "billing-enterprise",
            "industry": "Real Estate",
        }, headers=headers)
        tenant_id = uuid.UUID(tenant_res.json()["id"])
        tenant_headers = {
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": str(tenant_id),
        }

        # 2. Admin creates a service in catalog
        service_res = await client.post("/api/v1/services", json={
            "name": "Automated Rent Collection",
            "slug": "automated-rent-collection",
            "category": "finance",
            "description": "WhatsApp and ledger rent sync",
            "active": True,
        }, headers=headers)
        assert service_res.status_code == 201
        service_id = service_res.json()["id"]

        # 3. List services from catalog
        catalog_res = await client.get("/api/v1/services")
        assert catalog_res.status_code == 200
        services_list = catalog_res.json()
        assert any(s["id"] == service_id for s in services_list)

        # 4. Client subscribes to the service
        sub_res = await client.post("/api/v1/services/subscribe", json={
            "service_id": service_id,
            "plan_name": "pro",
            "billing_interval": "monthly",
            "price": 79.0,
        }, headers=tenant_headers)
        assert sub_res.status_code == 201
        sub_data = sub_res.json()
        assert sub_data["plan_name"] == "pro"
        assert sub_data["price"] == 79.0
        assert sub_data["status"] == "active"
        subscription_id = uuid.UUID(sub_data["id"])

        # 5. Verify service is active via is_service_enabled_for_tenant
        factory = get_session_factory()
        async with factory() as session:
            is_enabled = await billing_service.is_service_enabled_for_tenant(
                session, tenant_id, "automated-rent-collection"
            )
            assert is_enabled is True

            is_other_enabled = await billing_service.is_service_enabled_for_tenant(
                session, tenant_id, "non-existent-service"
            )
            assert is_other_enabled is False

        # 6. Check that an invoice was generated
        invoices_res = await client.get("/api/v1/payments/invoices", headers=tenant_headers)
        assert invoices_res.status_code == 200
        invoices = invoices_res.json()
        assert len(invoices) >= 1
        invoice = invoices[0]
        assert invoice["total"] == 79.0
        assert invoice["status"] == "issued"
        invoice_id = invoice["id"]

        # 7. Settle the invoice
        pay_res = await client.post(f"/api/v1/payments/invoices/{invoice_id}/pay", headers=tenant_headers)
        assert pay_res.status_code == 200
        pay_data = pay_res.json()
        assert pay_data["amount"] == 79.0
        assert pay_data["status"] == "completed"

        # 8. Re-query invoices to confirm status is now 'paid'
        invoices_check = await client.get("/api/v1/payments/invoices", headers=tenant_headers)
        assert invoices_check.json()[0]["status"] == "paid"

        # 9. Cancel subscription
        cancel_res = await client.post(
            f"/api/v1/services/subscriptions/{subscription_id}/cancel",
            headers=tenant_headers,
        )
        assert cancel_res.status_code == 200
        assert cancel_res.json()["success"] is True


@pytest.mark.asyncio
async def test_payment_webhook_signature_verification():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Valid webhook call
        res_ok = await client.post(
            "/api/v1/payments/webhook",
            content=b'{"event": "payment.succeeded"}',
            headers={"Stripe-Signature": "valid_test_signature"},
        )
        assert res_ok.status_code == 200
        assert res_ok.json()["success"] is True
