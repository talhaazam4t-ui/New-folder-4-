import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_tenant_creation_and_listing():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register owner user
        reg = await client.post("/api/v1/auth/register", json={
            "email": "owner@taloxrealestate.com",
            "password": "Password123!",
            "full_name": "Estate Owner",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create tenant workspace
        tenant_payload = {
            "name": "Talox Real Estate",
            "slug": "talox-real-estate",
            "industry": "Real Estate",
            "settings": {"currency": "USD"},
        }
        create_res = await client.post("/api/v1/tenants", json=tenant_payload, headers=headers)
        assert create_res.status_code == 201
        tenant_data = create_res.json()
        assert tenant_data["name"] == "Talox Real Estate"
        assert tenant_data["slug"] == "talox-real-estate"
        assert tenant_data["role"] == "owner"
        tenant_id = tenant_data["id"]

        # 3. Duplicate slug returns 409 Conflict
        dup_res = await client.post("/api/v1/tenants", json=tenant_payload, headers=headers)
        assert dup_res.status_code == 409

        # 4. List user tenants
        list_res = await client.get("/api/v1/tenants", headers=headers)
        assert list_res.status_code == 200
        tenants = list_res.json()
        assert len(tenants) >= 1
        assert any(t["id"] == tenant_id for t in tenants)

        # 5. Fetch specific tenant by ID
        get_res = await client.get(f"/api/v1/tenants/{tenant_id}", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["slug"] == "talox-real-estate"
