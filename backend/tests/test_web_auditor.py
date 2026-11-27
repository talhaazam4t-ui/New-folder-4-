"""Unit & Integration Tests for Automated Web Scraping, Auditing, Network Interception & Multi-Tenant Storage."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import httpx
from app.database.models.audit import WebsiteAudit
from app.database.supabase import get_session_factory
from app.main import app
from app.services.web_auditor_service import WebAuditorService, web_auditor_service
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select


SAMPLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Apex Dental Clinic | Premier Dental Care in Dubai</title>
    <meta name="description" content="Apex Dental Clinic provides advanced dental implants, teeth whitening, and 24/7 emergency dental care in Dubai. Book your appointment today.">
    <link rel="canonical" href="https://apexdental.example.com">
    <meta property="og:title" content="Apex Dental Clinic Dubai">
    <meta property="og:description" content="Award-winning dental implants and cosmetic dentistry in Dubai.">
    <meta property="og:image" content="https://apexdental.example.com/og.jpg">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Apex Dental Clinic Dubai">
    <script type="application/ld+json">{"@context": "https://schema.org", "@type": "Dentist", "name": "Apex Dental"}</script>
    <script src="https://apexdental.example.com/api/v1/config.js"></script>
</head>
<body>
    <header><nav><a href="/">Home</a><a href="/services">Services</a><a href="https://instagram.com/apex">Instagram</a></nav></header>
    <h1>Premier Dental Care & Implants in Dubai</h1>
    <h2>Our Core Services</h2>
    <p>We provide full mouth rehabilitation and cosmetic procedures.</p>
    <img src="/img/doctor.jpg" alt="Dr. John Doe Specialist Dentist">
    <img src="/img/clinic.jpg">
    <form action="/book" method="POST">
        <input type="text" name="name" placeholder="Your Name">
        <button type="submit">Book Now</button>
    </form>
</body>
</html>
"""


def test_html_parsing_and_seo_evaluator():
    """Verify HTML parsing, SEO metadata extraction, and score computation."""
    auditor = WebAuditorService()
    seo, dom = auditor._parse_html_and_seo(SAMPLE_HTML, "https://apexdental.example.com", extract_dom=True)

    assert "Apex Dental Clinic" in seo["title"]
    assert seo["title_length"] > 20
    assert "dental implants" in seo["meta_description"]
    assert seo["has_mobile_viewport"] is True
    assert seo["has_ssl"] is True
    assert seo["has_schema_ld"] is True
    assert seo["opengraph"]["title"] == "Apex Dental Clinic Dubai"
    assert seo["twitter_card"]["card"] == "summary_large_image"
    assert seo["heading_counts"]["h1"] == 1
    assert seo["heading_counts"]["h2"] == 1
    assert seo["total_images"] == 2
    assert seo["images_missing_alt_count"] == 1
    assert seo["image_alt_coverage_pct"] == 50.0
    assert seo["links"]["internal"] == 2
    assert seo["links"]["external"] == 1

    assert dom["total_forms"] == 1
    assert dom["tag_distribution"]["button"] == 1

    seo_score = auditor._compute_seo_score(seo, dom)
    assert seo_score >= 80.0

    perf = {
        "ttfb_ms": 350.0,
        "load_time_ms": 1200.0,
        "total_requests": 25,
    }
    perf_score = auditor._compute_performance_score(perf, [])
    assert perf_score >= 90.0

    proposal = auditor._generate_pitch_proposal("https://apexdental.example.com", {
        "seo_metadata": seo,
        "performance_metrics": perf,
        "seo_score": seo_score,
        "performance_score": perf_score,
    })
    assert "target_url" in proposal
    assert len(proposal["recommended_fixes"]) > 0


def test_anti_bot_detection_and_blocked_handling():
    """Verify Cloudflare and anti-bot challenge detection."""
    auditor = WebAuditorService()
    cf_html = "<html><title>Just a moment...</title><body>Checking your browser before accessing. cf-chl-bypass</body></html>"
    assert auditor._is_anti_bot_blocked(cf_html) is True

    blocked_res = auditor._build_blocked_result("https://blocked.example.com", "playwright_headless", 403, [], [])
    assert blocked_res["status_code"] == 403
    assert blocked_res["error_details"]["error_type"] == "blocked_by_waf"


def test_timeout_handling():
    """Verify timeout structured response formatting."""
    auditor = WebAuditorService()
    timeout_res = auditor._build_timeout_result("https://timeout.example.com", "http_resilient_fallback", 25)
    assert timeout_res["status_code"] == 408
    assert timeout_res["error_details"]["error_type"] == "timeout"


async def _register_and_create_tenant(client: AsyncClient, email: str, slug: str, name: str) -> tuple[str, uuid.UUID]:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"{name} Admin"},
    )
    assert reg.status_code == 201
    tok = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    t_res = await client.post(
        "/api/v1/tenants",
        json={"name": name, "slug": slug, "industry": "Clinics / Hospitals"},
        headers=headers,
    )
    assert t_res.status_code in (200, 201)
    t_body = t_res.json()
    tenant_id = uuid.UUID(t_body["id"] if "id" in t_body else t_body["data"]["id"])
    auth_headers = {"Authorization": f"Bearer {tok}", "X-Tenant-ID": str(tenant_id)}
    return auth_headers, tenant_id


@pytest.mark.asyncio
async def test_web_auditor_service_e2e_run():
    """Verify web_auditor_service.run_audit executes and persists to database."""
    session_factory = get_session_factory()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers_a, tenant_id = await _register_and_create_tenant(
            client, f"audit_e2e_{uuid.uuid4().hex[:6]}@example.com", f"audit-t-{uuid.uuid4().hex[:6]}", "Audit Clinic"
        )

    # Mock httpx to return sample HTML safely
    mock_response = Response(
        status_code=200,
        text=SAMPLE_HTML,
        headers={"content-type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", "https://apexdental.example.com"),
    )

    with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_response)):
        async with session_factory() as session:
            record = await web_auditor_service.run_audit(
                tenant_id=tenant_id,
                target_url="https://apexdental.example.com",
                session=session,
                timeout_seconds=15,
            )
            assert record.id is not None
            assert record.tenant_id == tenant_id
            assert record.status == "completed"
            assert record.audit_scores_json["seo_score"] >= 75.0
            assert "pitch_proposal_json" in record.__dict__ or record.pitch_proposal_json

            # Test listing
            audits = await web_auditor_service.list_audits(tenant_id, session)
            assert len(audits) >= 1
            assert audits[0].target_url == "https://apexdental.example.com"

            # Test get single
            fetched = await web_auditor_service.get_audit(record.id, tenant_id, session)
            assert fetched.id == record.id


@pytest.mark.asyncio
async def test_audits_api_routes_and_tenant_isolation():
    """Verify /api/v1/audits endpoints with strict multi-tenant isolation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Tenant A
        headers_a, tid_a = await _register_and_create_tenant(
            client, f"audit_a_{uuid.uuid4().hex[:6]}@example.com", f"audit-a-{uuid.uuid4().hex[:6]}", "Clinic A"
        )
        # Tenant B
        headers_b, tid_b = await _register_and_create_tenant(
            client, f"audit_b_{uuid.uuid4().hex[:6]}@example.com", f"audit-b-{uuid.uuid4().hex[:6]}", "Clinic B"
        )

        fake_audit_result = {
            "engine": "http_resilient_fallback",
            "target_url": "https://tenant-a-dental.com",
            "final_url": "https://tenant-a-dental.com",
            "status_code": 200,
            "overall_score": 95.0,
            "seo_score": 92.0,
            "performance_score": 98.0,
            "seo_metadata": {"title": "Tenant A Dental", "title_length": 15},
            "performance_metrics": {"ttfb_ms": 300, "load_time_ms": 1100},
            "dom_structure": {"total_forms": 1},
            "network_calls": [],
            "intercepted_api_calls": [],
            "audited_at": datetime.now(timezone.utc).isoformat(),
        }

        with patch.object(
            web_auditor_service,
            "_run_http_fallback_audit",
            AsyncMock(return_value=(fake_audit_result, "completed")),
        ):
            # 1. Tenant A runs an audit
            run_res = await client.post(
                "/api/v1/audits/run",
                headers=headers_a,
                json={"target_url": "https://tenant-a-dental.com", "timeout_seconds": 20},
            )
            assert run_res.status_code == 201
            audit_data = run_res.json()
            audit_id = audit_data["id"]
            assert audit_data["status"] == "completed"
            assert audit_data["target_url"] == "https://tenant-a-dental.com"
            assert "seo_metadata" in audit_data["audit_scores_json"]
            assert "performance_metrics" in audit_data["audit_scores_json"]

            # 2. Tenant A lists audits
            list_res = await client.get(
                "/api/v1/audits",
                headers=headers_a,
            )
            assert list_res.status_code == 200
            assert list_res.json()["total"] >= 1

            # 3. Tenant A views audit details
            detail_res = await client.get(
                f"/api/v1/audits/{audit_id}",
                headers=headers_a,
            )
            assert detail_res.status_code == 200
            assert detail_res.json()["id"] == audit_id

            # 4. Strict Tenant Isolation: Tenant B CANNOT view Tenant A's audit (Returns 404)
            unauth_detail = await client.get(
                f"/api/v1/audits/{audit_id}",
                headers=headers_b,
            )
            assert unauth_detail.status_code == 404
