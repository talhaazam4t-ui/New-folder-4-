import app.main as main_module
import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_root_endpoint(monkeypatch):
    monkeypatch.setattr(main_module, "STATIC_DIR", None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["status"] == "online"
        assert "Talox Tech Stream" in data["data"]["name"]


@pytest.mark.asyncio
async def test_head_probes_and_static_serving_rules(tmp_path, monkeypatch):
    # Create a representative Next.js static export dir to verify static & 404 behavior deterministically
    (tmp_path / "index.html").write_text("<html><body>Talox Tech Stream</body></html>", encoding="utf-8")
    (tmp_path / "404.html").write_text("<html><body>Not Found</body></html>", encoding="utf-8")
    (tmp_path / "login").mkdir()
    (tmp_path / "login" / "index.html").write_text("<html><body>Login</body></html>", encoding="utf-8")
    (tmp_path / "dashboard").mkdir()
    (tmp_path / "dashboard" / "index.html").write_text("<html><body>Dashboard</body></html>", encoding="utf-8")

    monkeypatch.setattr(main_module, "STATIC_DIR", tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # HEAD probes return 200
        assert (await client.head("/")).status_code == 200
        assert (await client.head("/health")).status_code == 200
        assert (await client.head("/api/v1/health")).status_code == 200

        # Next.js static export routes return 200
        assert (await client.get("/")).status_code == 200
        assert (await client.get("/login")).status_code == 200
        assert (await client.get("/login/")).status_code == 200
        assert (await client.get("/dashboard")).status_code == 200

        # Missing assets return 404 (never index.html)
        robots = await client.get("/robots.txt")
        assert robots.status_code == 404
        assert (await client.get("/missing.png")).status_code == 404

        # Unknown API route returns 404 JSON
        api_missing = await client.get("/api/v1/nonexistent")
        assert api_missing.status_code == 404
        assert api_missing.json()["success"] is False

        # Unknown non-route path returns 404 with 404.html
        unknown_page = await client.get("/definitely-does-not-exist")
        assert unknown_page.status_code == 404
        assert "Not Found" in unknown_page.text


@pytest.mark.asyncio
async def test_health_check_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["status"] == "healthy"
        assert "environment" in data["data"]


@pytest.mark.asyncio
async def test_rate_limited_agent_demo_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/agent-test")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["status"] == "allowed"
