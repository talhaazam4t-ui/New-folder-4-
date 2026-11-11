import uuid

import pytest
from app.database.models.automation import AuditLog, Notification
from app.database.models.business import BusinessRecord
from app.database.models.marketing import Lead
from app.database.models.tenant import Tenant, TenantMember
from app.database.supabase import get_session_factory
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


@pytest.mark.asyncio
async def test_cascading_account_purge_deletes_all_records():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register Owner
        reg_owner = await client.post("/api/v1/auth/register", json={
            "email": "owner.purge@example.com",
            "password": "Password123!",
            "full_name": "Purge Owner",
        })
        owner_token = reg_owner.json()["access_token"]
        owner_id = uuid.UUID(reg_owner.json()["user_id"])
        owner_headers = {"Authorization": f"Bearer {owner_token}"}

        # 2. Register Non-Owner Staff User
        reg_staff = await client.post("/api/v1/auth/register", json={
            "email": "staff.user@example.com",
            "password": "Password123!",
            "full_name": "Staff User",
        })
        staff_token = reg_staff.json()["access_token"]
        staff_headers = {"Authorization": f"Bearer {staff_token}"}

        # 3. Create Tenant
        tenant_res = await client.post("/api/v1/tenants", json={
            "name": "Purge Corp",
            "slug": "purge-corp",
            "industry": "Logistics",
        }, headers=owner_headers)
        assert tenant_res.status_code == 201
        tenant_id = uuid.UUID(tenant_res.json()["id"])

        # 4. Insert related child records in database directly
        factory = get_session_factory()
        async with factory() as session:
            # Business record
            rec = BusinessRecord(
                tenant_id=tenant_id,
                record_type="income",
                title="Delivery fee",
                amount=5000.0,
                currency="USD",
                source="manual",
                recorded_by=owner_id,
            )
            session.add(rec)

            # Lead record
            lead = Lead(
                tenant_id=tenant_id,
                name="John Doe",
                email="john@example.com",
                source="website",
                status="new",
            )
            session.add(lead)

            # Notification
            notif = Notification(
                tenant_id=tenant_id,
                user_id=owner_id,
                channel="in_app",
                title="Welcome",
                message="Welcome to Purge Corp",
            )
            session.add(notif)
            await session.commit()

        # 5. Non-owner attempts to purge -> 403 Forbidden
        staff_purge_res = await client.request(
            "DELETE",
            f"/api/v1/tenants/{tenant_id}",
            json={"confirmation_slug": "purge-corp"},
            headers=staff_headers,
        )
        assert staff_purge_res.status_code == 403

        # 6. Owner attempts purge with mismatched slug -> 400 Bad Request
        bad_slug_res = await client.request(
            "DELETE",
            f"/api/v1/tenants/{tenant_id}",
            json={"confirmation_slug": "wrong-slug"},
            headers=owner_headers,
        )
        assert bad_slug_res.status_code == 400
        assert bad_slug_res.json()["error"]["code"] == "CONFIRMATION_MISMATCH"

        # 7. Owner executes valid purge with exact slug
        purge_res = await client.request(
            "DELETE",
            f"/api/v1/tenants/{tenant_id}",
            json={"confirmation_slug": "purge-corp"},
            headers=owner_headers,
        )
        assert purge_res.status_code == 200
        assert purge_res.json()["success"] is True

        # 8. VERIFY COMPLETE CASCADING DELETION IN DATABASE
        async with factory() as session:
            # Tenant deleted
            t_check = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
            assert t_check.scalar_one_or_none() is None

            # Members deleted
            m_check = await session.execute(select(TenantMember).where(TenantMember.tenant_id == tenant_id))
            assert len(m_check.scalars().all()) == 0

            # Business records deleted
            b_check = await session.execute(select(BusinessRecord).where(BusinessRecord.tenant_id == tenant_id))
            assert len(b_check.scalars().all()) == 0

            # Leads deleted
            l_check = await session.execute(select(Lead).where(Lead.tenant_id == tenant_id))
            assert len(l_check.scalars().all()) == 0

            # Notifications deleted
            n_check = await session.execute(select(Notification).where(Notification.tenant_id == tenant_id))
            assert len(n_check.scalars().all()) == 0

            # Immutable unlinked audit log exists
            a_check = await session.execute(
                select(AuditLog).where(
                    AuditLog.resource_id == tenant_id,
                    AuditLog.action == "tenant.purged"
                )
            )
            audit = a_check.scalar_one_or_none()
            assert audit is not None
            assert audit.metadata_["slug"] == "purge-corp"
