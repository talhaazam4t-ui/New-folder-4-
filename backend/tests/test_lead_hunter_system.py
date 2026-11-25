"""Tests for TALOX International AI Receptionist Lead Hunting + Demo + Follow-up System."""

import socket
import uuid

import httpx
import pytest
from app.config import settings
from app.main import app
from httpx import ASGITransport, AsyncClient


async def _register_and_create_workspace(client: AsyncClient, email: str, slug: str, name: str):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"{name} Owner"},
    )
    assert reg.status_code == 201
    tok = reg.json()["access_token"]
    auth_h = {"Authorization": f"Bearer {tok}"}
    t_res = await client.post(
        "/api/v1/tenants",
        json={"name": name, "slug": slug, "industry": "Dental Clinic"},
        headers=auth_h,
    )
    assert t_res.status_code in (200, 201)
    tid = t_res.json()["id"]
    return uuid.UUID(tid), {**auth_h, "X-Tenant-ID": str(tid)}


@pytest.mark.asyncio
async def test_lead_hunter_control_panel_discovery_demo_handover_and_isolation(monkeypatch):
    """Verify default-OFF golden rule, real-key guardrails, AI detector, HITL demo, handover & isolation."""
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "resend_api_key", "")
    monkeypatch.setattr(settings, "google_places_api_key", "")
    monkeypatch.setattr(settings, "apollo_api_key", "")

    # Safe DNS stub for synthetic test domains only
    orig_getaddrinfo = socket.getaddrinfo

    def _fake_getaddrinfo(host, port, *args, **kwargs):
        if host in ("brightsmile.example.com", "robotchat.example.com"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        return orig_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    orig_get = httpx.AsyncClient.get
    orig_post = httpx.AsyncClient.post
    apollo_calls = []

    async def _fake_get(self, url, *args, **kwargs):
        u = str(url)
        req = httpx.Request("GET", u)
        if "maps.googleapis.com/maps/api/place/textsearch" in u:
            return httpx.Response(
                200,
                request=req,
                json={
                    "status": "OK",
                    "results": [
                        {"place_id": "pl_noai_1", "name": "Bright Smile Dental"},
                        {"place_id": "pl_hasai_2", "name": "RobotChat Dental"},
                    ],
                },
            )
        if "maps.googleapis.com/maps/api/place/details" in u:
            params = kwargs.get("params") or {}
            pid = params.get("place_id") or ("pl_noai_1" if "pl_noai_1" in u else "pl_hasai_2")
            if pid == "pl_noai_1":
                return httpx.Response(
                    200,
                    request=req,
                    json={
                        "result": {
                            "place_id": "pl_noai_1",
                            "name": "Bright Smile Dental",
                            "formatted_address": "120 Madison Ave, New York, NY",
                            "international_phone_number": "+1 212 555 0144",
                            "website": "https://brightsmile.example.com",
                            "rating": 3.9,
                            "user_ratings_total": 42,
                            "opening_hours": {"weekday_text": ["Monday: 8:00 AM - 6:00 PM"]},
                            "reviews": [{"text": "Great dentist but nobody picks up the phone, always goes to voicemail and missed calls!"}],
                        }
                    },
                )
            return httpx.Response(
                200,
                request=req,
                json={
                    "result": {
                        "place_id": "pl_hasai_2",
                        "name": "RobotChat Dental",
                        "formatted_address": "400 Broadway, New York, NY",
                        "international_phone_number": "+1 212 555 0199",
                        "website": "https://robotchat.example.com",
                        "rating": 4.7,
                        "user_ratings_total": 90,
                        "reviews": [{"text": "Quick online booking via live chat."}],
                    }
                },
            )
        if "brightsmile.example.com" in u:
            return httpx.Response(
                200,
                request=req,
                text="<html><title>Bright Smile Dental NYC — Implants & Whitening</title><body><p>Call us for veneers.</p></body></html>",
            )
        if "robotchat.example.com" in u:
            return httpx.Response(
                200,
                request=req,
                text='<html><title>RobotChat Dental</title><script src="https://code.tidio.co/demo123.js"></script></html>',
            )
        return await orig_get(self, url, *args, **kwargs)

    async def _fake_post(self, url, *args, **kwargs):
        u = str(url)
        if "api.apollo.io/api/v1/mixed_people/search" in u:
            apollo_calls.append(kwargs.get("json") or {})
            req = httpx.Request("POST", u)
            return httpx.Response(
                200,
                request=req,
                json={
                    "people": [
                        {
                            "name": "Dr. Sarah Miller",
                            "title": "Owner & Lead Dentist",
                            "email": "sarah@brightsmile.example.com",
                            "email_status": "verified",
                            "linkedin_url": "https://www.linkedin.com/in/drsarahmiller-nyc",
                            "organization": {"name": "Bright Smile Dental", "website_url": "https://brightsmile.example.com"},
                        }
                    ]
                },
            )
        return await orig_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        _, h1 = await _register_and_create_workspace(client, "hunter1@test.ai", "hunter-one", "Talox Agency")
        _, h2 = await _register_and_create_workspace(client, "hunter2@test.ai", "hunter-two", "Other Agency")

        # 1. GOLDEN RULE: Everything OFF by default EXCEPT direct_call_mode ON
        ov1 = await client.get("/api/v1/lead-hunter/overview", headers=h1)
        assert ov1.status_code == 200
        mod_map = ov1.json()["data"]["control_panel"]["module_map"]
        assert mod_map["direct_call_mode"]["is_on"] is True
        for off_mod in (
            "google_places_finder",
            "apollo_enrichment",
            "auto_demo_generator",
            "auto_whatsapp_sender",
            "auto_email_sender",
            "auto_linkedin_sender",
            "auto_followup_engine",
            "auto_chat_reply",
        ):
            assert mod_map[off_mod]["is_on"] is False, f"{off_mod} must default to OFF"

        # Searching while Google Places Finder is OFF is rejected with 403
        blocked_search = await client.post(
            "/api/v1/lead-hunter/search",
            json={"country": "USA", "city": "New York", "category": "Dental Clinic", "source_mode": "google_places"},
            headers=h1,
        )
        assert blocked_search.status_code == 403

        # Apply FREE MODE ($0) -> Google Places ON + Apollo ON (max 10/day), senders stay OFF
        free_res = await client.post(
            "/api/v1/lead-hunter/settings/budget-mode",
            json={"budget_mode": "free"},
            headers=h1,
        )
        assert free_res.status_code == 200
        free_map = free_res.json()["data"]["module_map"]
        assert free_map["google_places_finder"]["is_on"] is True
        assert free_map["apollo_enrichment"]["is_on"] is True
        assert free_map["apollo_enrichment"]["daily_limit"] == 10
        assert free_map["auto_email_sender"]["is_on"] is False

        # 2. STRICT REAL-DATA RULE: Missing keys return 400 with zero fake leads
        no_key = await client.post(
            "/api/v1/lead-hunter/search",
            json={"country": "USA", "city": "New York", "category": "Dental Clinic", "source_mode": "google_places"},
            headers=h1,
        )
        assert no_key.status_code == 400
        assert "Google Places API Key" in no_key.json()["error"]["message"]
        assert (await client.get("/api/v1/lead-hunter/leads", headers=h1)).json()["data"] == []

        # Enable live keys & run Hybrid Discovery
        monkeypatch.setattr(settings, "google_places_api_key", "gplaces_live_key_test")
        no_apollo = await client.post(
            "/api/v1/lead-hunter/search",
            json={"country": "USA", "city": "New York", "category": "Dental Clinic", "source_mode": "hybrid"},
            headers=h1,
        )
        assert no_apollo.status_code == 400
        assert "Apollo API Key" in no_apollo.json()["error"]["message"]

        monkeypatch.setattr(settings, "apollo_api_key", "apollo_live_key_test")
        # Set Apollo daily limit = 1 to test Free-Tier Hard Stop right after 1 enrichment!
        await client.patch("/api/v1/lead-hunter/settings/apollo_enrichment", json={"daily_limit": 1}, headers=h1)

        hybrid_res = await client.post(
            "/api/v1/lead-hunter/search",
            json={"country": "USA", "city": "New York", "category": "Dental Clinic", "source_mode": "hybrid"},
            headers=h1,
        )
        assert hybrid_res.status_code == 200
        h_data = hybrid_res.json()["data"]
        assert h_data["count"] == 2
        # Place B (RobotChat with Tidio) was skipped from Apollo -> ONLY 1 Apollo call made!
        assert h_data["apollo_credits_used"] == 1
        assert h_data["skipped_has_ai_apollo"] == 1
        assert len(apollo_calls) == 1

        leads = h_data["leads"]
        bright = next(l for l in leads if l["business_name"] == "Bright Smile Dental")
        robot = next(l for l in leads if l["business_name"] == "RobotChat Dental")
        assert bright["has_ai"] is False
        assert bright["owner_name"] == "Dr. Sarah Miller"
        assert bright["email_verified"] is True
        assert bright["interest_score"] >= 80
        assert robot["has_ai"] is True
        assert robot["interest_score"] < 50

        # Apollo Free Cap reached (1/1) -> extra enrichment strictly hard-stopped (429)
        cap_stop = await client.post(f"/api/v1/lead-hunter/leads/{bright['id']}/enrich-apollo", headers=h1)
        assert cap_stop.status_code == 429

        # 3. HOT LEAD CALL LIST (Score 80+ Only) + Call Later (+24h reminder)
        call_list = (await client.get("/api/v1/lead-hunter/call-list", headers=h1)).json()["data"]
        assert len(call_list) == 1
        assert call_list[0]["business_name"] == "Bright Smile Dental"
        assert "Cold" in call_list[0]["cold_call_script"] or "Bright Smile Dental" in call_list[0]["cold_call_script"]

        later_res = await client.post(
            f"/api/v1/lead-hunter/leads/{bright['id']}/outcome",
            json={"outcome": "call_later", "notes": "Left voicemail, callback tomorrow"},
            headers=h1,
        )
        assert later_res.status_code == 200
        assert later_res.json()["data"]["next_followup_at"] is not None

        # 4. DEMO GENERATOR (Draft -> Approved -> Sent HITL Workflow) & Interactive Chat
        demo_res = await client.post(f"/api/v1/lead-hunter/leads/{bright['id']}/generate-demo", headers=h1)
        assert demo_res.status_code == 201
        demo = demo_res.json()["data"]
        assert demo["status"] == "draft"
        assert "$299/month" in demo["email_copy"]
        assert demo["email_subject"] == "I made a FREE AI Receptionist Demo for Bright Smile Dental"

        chat_prev = await client.post(
            f"/api/v1/lead-hunter/demos/{demo['id']}/chat-preview",
            json={"visitor_message": "What are your opening hours?"},
            headers=h1,
        )
        assert chat_prev.status_code == 200
        assert "Bright Smile Dental" in chat_prev.json()["data"]["ai_receptionist_reply"]

        # Unapproved draft CANNOT be sent
        blocked_send = await client.post(
            f"/api/v1/lead-hunter/demos/{demo['id']}/send",
            json={"channel": "email"},
            headers=h1,
        )
        assert blocked_send.status_code == 403

        await client.post(f"/api/v1/lead-hunter/demos/{demo['id']}/approve", headers=h1)

        # Even when approved, email sender switch OFF blocks sending
        off_send = await client.post(
            f"/api/v1/lead-hunter/demos/{demo['id']}/send",
            json={"channel": "email"},
            headers=h1,
        )
        assert off_send.status_code == 403

        # UAE-only WhatsApp restriction blocks USA lead
        await client.patch("/api/v1/lead-hunter/settings/auto_whatsapp_sender", json={"is_on": True}, headers=h1)
        uae_only_err = await client.post(
            f"/api/v1/lead-hunter/demos/{demo['id']}/send",
            json={"channel": "whatsapp"},
            headers=h1,
        )
        assert uae_only_err.status_code == 400

        # Turn ON Email Sender + Auto Follow-up Engine -> sends & schedules 3 follow-ups
        await client.patch("/api/v1/lead-hunter/settings/auto_email_sender", json={"is_on": True, "daily_limit": 20}, headers=h1)
        await client.patch("/api/v1/lead-hunter/settings/auto_followup_engine", json={"is_on": True}, headers=h1)
        ok_send = await client.post(
            f"/api/v1/lead-hunter/demos/{demo['id']}/send",
            json={"channel": "email"},
            headers=h1,
        )
        assert ok_send.status_code == 200
        assert ok_send.json()["data"]["followups_scheduled"] == 3

        # 5. CRITICAL HUMAN HANDOVER -> Reply stops follow-ups & flags Human Needed!
        handover = await client.post(
            f"/api/v1/lead-hunter/leads/{bright['id']}/reply",
            json={"message": "YES interested, please share pricing and give me a call!", "channel": "email"},
            headers=h1,
        )
        assert handover.status_code == 200
        h_info = handover.json()["data"]
        assert h_info["human_needed"] is True
        assert h_info["cancelled_followups"] == 3
        assert h_info["auto_reply_sent"] is False

        ov_alert = (await client.get("/api/v1/lead-hunter/overview", headers=h1)).json()["data"]
        assert len(ov_alert["human_needed_alerts"]) == 1

        # Running due follow-ups respects handover / never sends to human_needed leads
        fu_run = await client.post(
            "/api/v1/lead-hunter/followups/process-due",
            json={"force_due_in_test": True},
            headers=h1,
        )
        assert fu_run.status_code == 200
        assert fu_run.json()["data"]["sent"] == 0

        # Record Paid ($299 USD) -> Revenue KPI updates!
        paid = await client.post(
            f"/api/v1/lead-hunter/leads/{bright['id']}/outcome",
            json={"outcome": "paid", "deal_value_usd": 499.0},
            headers=h1,
        )
        assert paid.status_code == 200
        kpis_after = (await client.get("/api/v1/lead-hunter/overview", headers=h1)).json()["data"]["kpis"]
        assert kpis_after["paid_clients"] == 1
        assert kpis_after["revenue_usd"] == 499.0

        # 6. DND Opt-Out on Lead 2 + Multi-Tenant Isolation
        dnd = await client.post(
            f"/api/v1/lead-hunter/leads/{robot['id']}/reply",
            json={"message": "No thanks, STOP and unsubscribe me.", "channel": "email"},
            headers=h1,
        )
        assert dnd.status_code == 200
        assert dnd.json()["data"]["do_not_disturb"] is True

        # Cross-tenant isolation checks (Tenant 2 sees zero & gets 404)
        assert (await client.get("/api/v1/lead-hunter/leads", headers=h2)).json()["data"] == []
        assert (
            await client.patch(
                f"/api/v1/lead-hunter/leads/{bright['id']}/stage",
                json={"pipeline_stage": "paid_client"},
                headers=h2,
            )
        ).status_code == 404
