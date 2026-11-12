import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_business_ledger_reconciliation_and_audit_history():
    """Verify financial ledger creation, summary reconciliation, revision history, and agent modification block."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register owner & create tenant
        reg = await client.post("/api/v1/auth/register", json={
            "email": "cfo@realtygroup.com",
            "password": "Password123!",
            "full_name": "Chief Financial Officer",
        })
        token = reg.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        tenant_res = await client.post("/api/v1/tenants", json={
            "name": "Apex Realty Holdings",
            "slug": "apex-realty-holdings",
            "industry": "Real Estate",
        }, headers=auth_headers)
        tenant_id = tenant_res.json()["id"]
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tenant-ID": tenant_id,
        }

        # 2. Record rent, income, payment_received, expense, and outstanding
        r_rent = await client.post("/api/v1/business/records", json={
            "record_type": "rent",
            "title": "Unit 402 Monthly Rent",
            "amount": 2500.00,
            "currency": "USD",
            "source": "whatsapp",
            "reference_id": "WA-MSG-901",
        }, headers=headers)
        assert r_rent.status_code == 201
        rent_id = r_rent.json()["id"]

        r_inc = await client.post("/api/v1/business/records", json={
            "record_type": "income",
            "title": "Property Management Fee",
            "amount": 800.00,
            "currency": "USD",
            "source": "manual",
        }, headers=headers)
        assert r_inc.status_code == 201

        r_exp = await client.post("/api/v1/business/records", json={
            "record_type": "expense",
            "title": "HVAC Maintenance Invoice",
            "amount": 450.00,
            "currency": "USD",
            "source": "manual",
        }, headers=headers)
        assert r_exp.status_code == 201

        r_out = await client.post("/api/v1/business/records", json={
            "record_type": "outstanding",
            "title": "Unit 105 Overdue Balance",
            "amount": 1200.00,
            "currency": "USD",
            "source": "manual",
        }, headers=headers)
        assert r_out.status_code == 201

        # 3. Verify financial summary reconciliation
        summary_res = await client.get("/api/v1/business/summary", headers=headers)
        assert summary_res.status_code == 200
        summary = summary_res.json()
        assert summary["total_rent"] == 2500.00
        assert summary["total_income"] == 800.00
        assert summary["total_expenses"] == 450.00
        assert summary["total_outstanding"] == 1200.00
        assert summary["gross_inflow"] == 3300.00
        assert summary["net_cashflow"] == 2850.00
        assert summary["record_count"] == 4

        # 4. Update rent record as human user with audit reason; verify revision history preserves original
        patch_res = await client.patch(f"/api/v1/business/records/{rent_id}", json={
            "amount": 2650.00,
            "reason": "Included late parking fee per signed addendum",
            "actor_type": "user",
        }, headers=headers)
        assert patch_res.status_code == 200
        updated = patch_res.json()
        assert updated["amount"] == 2650.00
        assert updated["metadata"]["original_amount"] == 2500.00
        history = updated["metadata"]["revision_history"]
        assert len(history) == 1
        assert history[0]["previous_amount"] == 2500.00
        assert history[0]["reason"] == "Included late parking fee per signed addendum"

        # 5. Verify AI agent is strictly blocked from modifying confirmed financial transactions
        agent_patch = await client.patch(f"/api/v1/business/records/{rent_id}", json={
            "amount": 100.00,
            "reason": "Autonomous agent hallucinated adjustment",
            "actor_type": "agent",
        }, headers=headers)
        assert agent_patch.status_code == 403
        assert agent_patch.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_business_metrics_import_reports_and_rbac_isolation():
    """Verify custom metrics, batch import, CSV report export, staff delete restriction, and cross-tenant isolation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Setup Tenant A (Owner)
        reg_a = await client.post("/api/v1/auth/register", json={
            "email": "owner.a@clinic.com",
            "password": "Password123!",
            "full_name": "Owner A",
        })
        token_a = reg_a.json()["access_token"]
        t_a = await client.post("/api/v1/tenants", json={
            "name": "Sunrise Dental Clinic",
            "slug": "sunrise-dental",
            "industry": "Healthcare",
        }, headers={"Authorization": f"Bearer {token_a}"})
        tenant_a_id = t_a.json()["id"]
        headers_a = {"Authorization": f"Bearer {token_a}", "X-Tenant-ID": tenant_a_id}

        # 2. Batch import records
        import_res = await client.post("/api/v1/business/import", json={
            "records": [
                {"record_type": "payment_received", "title": "Patient Implant Settlement", "amount": 3200.0, "currency": "USD"},
                {"record_type": "expense", "title": "Dental Supply Restock", "amount": 600.0, "currency": "USD"},
            ]
        }, headers=headers_a)
        assert import_res.status_code == 201
        imported = import_res.json()
        assert len(imported) == 2
        record_to_protect_id = imported[0]["id"]

        # 3. Create & list custom numerical metrics
        metric_res = await client.post("/api/v1/business/custom-metrics", json={
            "metric_name": "Occupancy Rate (%)",
            "metric_value": 94.5,
        }, headers=headers_a)
        assert metric_res.status_code == 201

        metrics_list = await client.get("/api/v1/business/metrics", headers=headers_a)
        assert metrics_list.status_code == 200
        assert len(metrics_list.json()) == 1
        assert metrics_list.json()[0]["metric_name"] == "Occupancy Rate (%)"
        assert metrics_list.json()[0]["metric_value"] == 94.5

        # 4. Generate CSV financial report
        report_res = await client.get("/api/v1/business/reports", headers=headers_a)
        assert report_res.status_code == 200
        report_data = report_res.json()["data"]
        assert "Patient Implant Settlement" in report_data["csv_content"]
        assert report_data["summary"]["total_payments_received"] == 3200.0

        # 5. Add a 'staff' user to Tenant A and verify they CANNOT delete financial records
        reg_staff = await client.post("/api/v1/auth/register", json={
            "email": "staff.a@clinic.com",
            "password": "Password123!",
            "full_name": "Staff Member",
        })
        staff_token = reg_staff.json()["access_token"]

        add_member = await client.post(f"/api/v1/tenants/{tenant_a_id}/members", json={
            "email": "staff.a@clinic.com",
            "role": "staff",
        }, headers=headers_a)
        assert add_member.status_code == 201

        headers_staff = {"Authorization": f"Bearer {staff_token}", "X-Tenant-ID": tenant_a_id}
        staff_del = await client.delete(f"/api/v1/business/records/{record_to_protect_id}", headers=headers_staff)
        assert staff_del.status_code == 403
        assert staff_del.json()["error"]["code"] == "PERMISSION_DENIED"

        # 6. Setup Tenant B and verify strict cross-tenant isolation
        reg_b = await client.post("/api/v1/auth/register", json={
            "email": "owner.b@rival.com",
            "password": "Password123!",
            "full_name": "Owner B",
        })
        token_b = reg_b.json()["access_token"]
        t_b = await client.post("/api/v1/tenants", json={
            "name": "Rival Clinic",
            "slug": "rival-clinic",
            "industry": "Healthcare",
        }, headers={"Authorization": f"Bearer {token_b}"})
        tenant_b_id = t_b.json()["id"]
        headers_b = {"Authorization": f"Bearer {token_b}", "X-Tenant-ID": tenant_b_id}

        # Tenant B cannot read Tenant A's record even with Tenant A's record_id
        cross_get = await client.get(f"/api/v1/business/records/{record_to_protect_id}", headers=headers_b)
        assert cross_get.status_code == 404

        # Owner A can delete their own record
        owner_del = await client.delete(f"/api/v1/business/records/{record_to_protect_id}", headers=headers_a)
        assert owner_del.status_code == 200
        assert owner_del.json()["success"] is True
