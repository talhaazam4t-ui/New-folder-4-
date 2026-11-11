import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_cross_tenant_isolation_violation_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register Client A and create Tenant A
        reg_a = await client.post("/api/v1/auth/register", json={
            "email": "client.a@company-a.com",
            "password": "Password123!",
            "full_name": "Alice Corp",
        })
        token_a = reg_a.json()["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        tenant_a_res = await client.post("/api/v1/tenants", json={
            "name": "Company Alpha",
            "slug": "company-alpha",
            "industry": "Retail",
        }, headers=headers_a)
        tenant_a_id = tenant_a_res.json()["id"]

        # 2. Register Client B and create Tenant B
        reg_b = await client.post("/api/v1/auth/register", json={
            "email": "client.b@company-b.com",
            "password": "Password123!",
            "full_name": "Bob Enterprise",
        })
        token_b = reg_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        tenant_b_res = await client.post("/api/v1/tenants", json={
            "name": "Company Beta",
            "slug": "company-beta",
            "industry": "Healthcare",
        }, headers=headers_b)
        tenant_b_id = tenant_b_res.json()["id"]

        # 3. Client A attempts to fetch Tenant B's details -> MUST BE REJECTED (403 Forbidden)
        cross_res = await client.get(f"/api/v1/tenants/{tenant_b_id}", headers=headers_a)
        assert cross_res.status_code == 403
        error = cross_res.json()["error"]
        assert error["code"] == "TENANT_ISOLATION_VIOLATION"

        # 4. Client B attempts to fetch Tenant A's details -> MUST BE REJECTED (403 Forbidden)
        cross_res_b = await client.get(f"/api/v1/tenants/{tenant_a_id}", headers=headers_b)
        assert cross_res_b.status_code == 403
        assert cross_res_b.json()["error"]["code"] == "TENANT_ISOLATION_VIOLATION"

        # 5. Client A accessing Tenant A succeeds
        legit_res_a = await client.get(f"/api/v1/tenants/{tenant_a_id}", headers=headers_a)
        assert legit_res_a.status_code == 200
        assert legit_res_a.json()["slug"] == "company-alpha"
