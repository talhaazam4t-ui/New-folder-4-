import uuid
from datetime import datetime, timedelta, timezone

import pytest
from app.config import settings
from app.core.security import ALGORITHM, decode_access_token
from app.database.models.tenant import Profile
from app.database.supabase import get_session_factory
from app.main import app
from httpx import ASGITransport, AsyncClient
from jose import jwt


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


@pytest.mark.asyncio
async def test_production_super_admin_bootstrap_gating(monkeypatch):
    admin_email = settings.super_admin_emails[0]
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "super_admin_bootstrap_password", None)
    monkeypatch.setattr(settings, "allow_super_admin_bootstrap", False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Public registration for super-admin blocked in production without gate
        reg_blocked = await client.post("/api/v1/auth/register", json={
            "email": admin_email,
            "password": "AttackerPassword123!",
            "full_name": "Attacker",
        })
        assert reg_blocked.status_code == 403

        # 2. First-login bootstrap blocked in production without secret/flag
        login_blocked = await client.post("/api/v1/auth/login", json={
            "email": admin_email,
            "password": "AttackerPassword123!",
        })
        assert login_blocked.status_code == 401

        # 3. Pre-existing profile with password_hash=None is also protected
        factory = get_session_factory()
        async with factory() as session:
            session.add(Profile(
                id=uuid.uuid4(),
                full_name="Existing Unbootstrapped Admin",
                email=admin_email,
                password_hash=None,
            ))
            await session.commit()

        null_hash_blocked = await client.post("/api/v1/auth/login", json={
            "email": admin_email,
            "password": "AttackerPassword123!",
        })
        assert null_hash_blocked.status_code == 401

        # 4. Wrong bootstrap password fails; matching SUPER_ADMIN_BOOTSTRAP_PASSWORD succeeds
        bootstrap_secret = "StrongOperatorBootstrap#2026"
        monkeypatch.setattr(settings, "super_admin_bootstrap_password", bootstrap_secret)

        wrong_boot = await client.post("/api/v1/auth/login", json={
            "email": admin_email,
            "password": "WrongBootstrapPassword!",
        })
        assert wrong_boot.status_code == 401

        ok_boot = await client.post("/api/v1/auth/login", json={
            "email": admin_email,
            "password": bootstrap_secret,
        })
        assert ok_boot.status_code == 200
        assert ok_boot.json()["is_super_admin"] is True

        # 5. Once bootstrapped, normal login succeeds even after removing SUPER_ADMIN_BOOTSTRAP_PASSWORD
        monkeypatch.setattr(settings, "super_admin_bootstrap_password", None)
        normal_login = await client.post("/api/v1/auth/login", json={
            "email": admin_email,
            "password": bootstrap_secret,
        })
        assert normal_login.status_code == 200
        assert normal_login.json()["is_super_admin"] is True


@pytest.mark.asyncio
async def test_jwt_requires_exp_and_sub():
    now = datetime.now(timezone.utc)
    no_exp = jwt.encode({"sub": str(uuid.uuid4()), "iat": now}, settings.app_secret_key, algorithm=ALGORITHM)
    assert decode_access_token(no_exp) is None

    no_sub = jwt.encode(
        {"email": "user@example.com", "exp": now + timedelta(minutes=10)},
        settings.app_secret_key,
        algorithm=ALGORITHM,
    )
    assert decode_access_token(no_sub) is None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {no_exp}"})
        assert res.status_code == 401
        assert res.headers.get("www-authenticate") == "Bearer"
