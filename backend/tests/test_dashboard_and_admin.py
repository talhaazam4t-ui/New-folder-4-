import uuid

import pytest
from app.config import settings
from app.database.models.business import BusinessRecord
from app.database.models.marketing import Lead
from app.database.models.tenant import Tenant
from app.database.supabase import get_session_factory
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


@pytest.mark.asyncio
async def test_tenant_overview_metrics_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register owner and create tenant
        reg = await client.post("/api/v1/auth/register", json={
            "email": "dashboard.owner@company.com",
            "password": "Password123!",
            "full_name": "Dashboard Owner",
        })
        token = reg.json()["access_token"]
        user_id = uuid.UUID(reg.json()["user_id"])
        headers = {"Authorization": f"Bearer {token}"}

        tenant_res = await client.post("/api/v1/tenants", json={
            "name": "Dashboard Enterprise",
            "slug": "dashboard-enterprise",
            "industry": "Finance",
        }, headers=headers)
        tenant_id = uuid.UUID(tenant_res.json()["id"])
        tenant_headers = {
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": str(tenant_id),
        }

        # 2. Add sample financial and lead records & activate approved tenant
        factory = get_session_factory()
        async with factory() as session:
            t_row = (await session.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
            t_row.status = "active"
            t_row.settings = {"payment_approved": True, "automation_approved_by_owner": True}
            session.add(BusinessRecord(
                tenant_id=tenant_id,
                record_type="income",
                title="SaaS Consulting",
                amount=15000.0,
                currency="USD",
                source="manual",
                recorded_by=user_id,
            ))
            session.add(BusinessRecord(
                tenant_id=tenant_id,
                record_type="expense",
                title="Cloud Hosting",
                amount=4000.0,
                currency="USD",
                source="manual",
                recorded_by=user_id,
            ))
            session.add(BusinessRecord(
                tenant_id=tenant_id,
                record_type="outstanding",
                title="Pending Invoice",
                amount=2500.0,
                currency="USD",
                source="manual",
                recorded_by=user_id,
            ))
            session.add(Lead(
                tenant_id=tenant_id,
                name="Prospective Client",
                email="prospect@example.com",
                source="web",
            ))
            await session.commit()

        # 3. Call overview endpoint
        res = await client.get(f"/api/v1/tenants/{tenant_id}/overview", headers=tenant_headers)
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["role"] == "owner"
        metrics = data["metrics"]
        assert metrics["income"] == 15000.0
        assert metrics["expenses"] == 4000.0
        assert metrics["net_profit"] == 11000.0
        assert metrics["outstanding"] == 2500.0
        assert metrics["leads"] == 1


@pytest.mark.asyncio
async def test_admin_global_overview_and_tenant_suspension(monkeypatch):
    monkeypatch.setattr(
        settings,
        "super_admin_emails",
        [*settings.super_admin_emails, "platform.admin@talox.com"],
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register admin user & create workspace
        reg = await client.post("/api/v1/auth/register", json={
            "email": "platform.admin@talox.com",
            "password": "Password123!",
            "full_name": "Platform Admin",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        tenant_res = await client.post("/api/v1/tenants", json={
            "name": "Target Company",
            "slug": "target-company",
            "industry": "Retail",
        }, headers=headers)
        tenant_id = tenant_res.json()["id"]

        # 2. Get global stats (new tenant starts in pending_approval until activated)
        stats_res = await client.get("/api/v1/admin/stats", headers=headers)
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert stats["total_tenants"] >= 1
        assert stats["active_tenants"] >= 0

        # 3. List all tenants in admin console
        tenants_res = await client.get("/api/v1/admin/tenants", headers=headers)
        assert tenants_res.status_code == 200
        tenant_list = tenants_res.json()["data"]
        assert any(t["id"] == tenant_id for t in tenant_list)

        # 4. Suspend tenant account
        suspend_res = await client.patch(
            f"/api/v1/admin/tenants/{tenant_id}/status",
            json={"status": "suspended"},
            headers=headers,
        )
        assert suspend_res.status_code == 200
        assert suspend_res.json()["success"] is True

        # 5. Reactivate tenant account and verify active_tenants increments
        reactivate_res = await client.patch(
            f"/api/v1/admin/tenants/{tenant_id}/status",
            json={"status": "active"},
            headers=headers,
        )
        assert reactivate_res.status_code == 200
        assert reactivate_res.json()["success"] is True

        stats_after = await client.get("/api/v1/admin/stats", headers=headers)
        assert stats_after.status_code == 200
        assert stats_after.json()["active_tenants"] >= 1


@pytest.mark.asyncio
async def test_admin_direct_client_provisioning(monkeypatch):
    monkeypatch.setattr(
        settings,
        "super_admin_emails",
        [*settings.super_admin_emails, "platform.owner@talox.com"],
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register Super Admin
        admin_reg = await client.post("/api/v1/auth/register", json={
            "email": "platform.owner@talox.com",
            "password": "Password123!",
            "full_name": "Platform Owner",
        })
        admin_token = admin_reg.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 2. Provision new client workspace
        prov_res = await client.post(
            "/api/v1/admin/tenants/provision",
            json={
                "name": "Acme Real Estate",
                "industry": "Real Estate / Property",
                "owner_email": "broker@acmeproperty.com",
                "owner_name": "Broker Bob",
                "plan_name": "growth",
                "price": 249.0,
                "status": "active",
            },
            headers=admin_headers,
        )
        assert prov_res.status_code == 200
        data = prov_res.json()["data"]
        assert data["name"] == "Acme Real Estate"
        assert data["industry"] == "Real Estate / Property"
        assert data["status"] == "active"
        assert data["owner_email"] == "broker@acmeproperty.com"

        # 3. Verify it shows up in admin operations
        ops_res = await client.get("/api/v1/admin/operations", headers=admin_headers)
        assert ops_res.status_code == 200
        tenants = ops_res.json()["data"]["tenants"]
        assert any(t["slug"] == data["slug"] for t in tenants)
