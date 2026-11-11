import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_register_and_login_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register new user
        reg_payload = {
            "email": "sarah.connor@example.com",
            "password": "SecurePassword123!",
            "full_name": "Sarah Connor",
            "phone": "+1-555-0199",
        }
        res = await client.post("/api/v1/auth/register", json=reg_payload)
        assert res.status_code == 201
        data = res.json()
        assert "access_token" in data
        assert data["email"] == "sarah.connor@example.com"
        assert data["full_name"] == "Sarah Connor"
        token = data["access_token"]

        # 2. Duplicate registration returns 409
        dup_res = await client.post("/api/v1/auth/register", json=reg_payload)
        assert dup_res.status_code == 409

        # 3. Login with correct credentials
        login_res = await client.post("/api/v1/auth/login", json={
            "email": "sarah.connor@example.com",
            "password": "SecurePassword123!",
        })
        assert login_res.status_code == 200
        assert "access_token" in login_res.json()

        # 4. Login with bad credentials returns 401
        bad_login = await client.post("/api/v1/auth/login", json={
            "email": "sarah.connor@example.com",
            "password": "WrongPassword!",
        })
        assert bad_login.status_code == 401

        # 5. Access /me with token
        me_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_res.status_code == 200
        assert me_res.json()["email"] == "sarah.connor@example.com"

        # 6. Access /me without token returns 401
        unauth_res = await client.get("/api/v1/auth/me")
        assert unauth_res.status_code == 401
