"""Unit & Integration Tests for TALOX Multi-Step AI Diagnostic & Outreach Agent."""

import json
import socket
import uuid

import httpx
import pytest
from app.config import settings
from app.database.models.lead_hunter import HunterDemo
from app.integrations.ai_providers.router import AIExecutionResult
from app.main import app
from httpx import ASGITransport, AsyncClient


async def _create_tenant_workspace(client: AsyncClient, email: str, slug: str, name: str):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": f"{name} Founder"},
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
async def test_lead_hunter_agent_multistep_tool_loop_offline_fallback_and_isolation(monkeypatch):
    """Verify 5-step bounded LLM tool loop, <130-word HITL draft, offline fallback, and strict tenant isolation."""
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "google_places_api_key", "")
    monkeypatch.setattr(settings, "apollo_api_key", "")

    orig_getaddrinfo = socket.getaddrinfo

    def _fake_getaddrinfo(host, port, *args, **kwargs):
        if host in ("apexdentalnyc.example.com", "chatlawlondon.example.com"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        return orig_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    orig_get = httpx.AsyncClient.get

    async def _fake_get(self, url, *args, **kwargs):
        u = str(url)
        req = httpx.Request("GET", u)
        if "apexdentalnyc.example.com" in u:
            return httpx.Response(
                200,
                request=req,
                text=(
                    "<html><title>Apex Dental NYC — Emergency & Cosmetic Dentistry</title>"
                    '<body><a href="mailto:dr.carter@apexdentalnyc.example.com">Email</a>'
                    '<a href="tel:+1 212 555 0191">Call</a></body></html>'
                ),
            )
        if "chatlawlondon.example.com" in u:
            return httpx.Response(
                200,
                request=req,
                text=(
                    "<html><title>ChatLaw London — Corporate Solicitors</title>"
                    '<script src="https://widget.intercom.io/widget.js"></script>'
                    "<body><form><input name='email'/></form></body></html>"
                ),
            )
        return await orig_get(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        t1_id, h1 = await _create_tenant_workspace(client, "agent_t1@test.ai", "agent-t1", "Agent One Agency")
        t2_id, h2 = await _create_tenant_workspace(client, "agent_t2@test.ai", "agent-t2", "Agent Two Agency")

        # Seed 2 leads in Tenant 1 via Apollo Free CSV Import (one No-AI Dental, one Has-AI Law Firm)
        csv_payload = (
            "First Name,Last Name,Title,Company,Email,Email Status,Corporate Phone,Website,City,Country,Industry\n"
            "Evan,Carter,Owner,Apex Dental NYC,,Verified,+1 212 555 0191,https://apexdentalnyc.example.com,New York,USA,Dental Clinic\n"
            "Claire,Vance,Managing Partner,ChatLaw London,claire@chatlawlondon.example.com,Verified,+44 20 7946 0192,https://chatlawlondon.example.com,London,UK,Law Firm\n"
        )
        imp = await client.post(
            "/api/v1/lead-hunter/import-apollo-csv",
            json={"csv_text": csv_payload, "inspect_websites": False},
            headers=h1,
        )
        assert imp.status_code == 200
        imported_leads = imp.json()["data"]["leads"]
        apex_lead = next(l for l in imported_leads if l["business_name"] == "Apex Dental NYC")
        chatlaw_lead = next(l for l in imported_leads if l["business_name"] == "ChatLaw London")

        # ----------------------------------------------------------------------
        # 1. MULTI-STEP LLM TOOL-CALLING LOOP + SPOOFED TENANT_ID REJECTION
        # ----------------------------------------------------------------------
        step_responses = [
            json.dumps(
                {
                    "tool": "scan_business_website",
                    "args": {
                        "url": "https://apexdentalnyc.example.com",
                        "tenant_id": str(t2_id),  # Malicious spoofed tenant_id — must be ignored!
                    },
                }
            ),
            json.dumps(
                {
                    "tool": "check_crm_history",
                    "args": {
                        "domain": "apexdentalnyc.example.com",
                        "tenant_id": str(t2_id),
                    },
                }
            ),
            json.dumps(
                {
                    "tool": "save_hitl_outreach_draft",
                    "args": {
                        "tenant_id": str(t2_id),
                        "lead_id": str(chatlaw_lead["id"]),  # Spoofed lead_id — must be ignored!
                        "status": "sent",  # Spoofed status — must remain 'draft'!
                        "recommended_service": "office-receptionist",
                        "diagnostic_finding": "No 24/7 AI voice/chat receptionist or online booking widget detected on Apex Dental NYC.",
                        "subject_line": "Built a custom 24/7 AI Receptionist demo for Apex Dental NYC",
                        "email_body": (
                            "Hi Dr. Evan Carter,\n\n"
                            "I audited Apex Dental NYC and noticed you don't have a 24/7 AI receptionist or instant "
                            "booking widget capturing after-hours emergency and cosmetic dental patients.\n\n"
                            "We built a live AI Receptionist preview trained on your hours and dental services that "
                            "answers calls on the first ring and books appointments directly to your calendar.\n\n"
                            "Plans start at $299/month with a 7-day free trial. Open to testing your private demo line?"
                        ),
                    },
                }
            ),
        ]
        call_counter = {"idx": 0}

        async def _mock_multistep_llm(task_type: str, prompt: str, **kwargs):
            idx = call_counter["idx"]
            call_counter["idx"] += 1
            content = step_responses[min(idx, len(step_responses) - 1)]
            return AIExecutionResult(
                success=True,
                model="llama-3.3-70b-versatile",
                task_type=task_type,
                content=content,
                is_mock=False,
            )

        monkeypatch.setattr("app.services.lead_hunter_agent.route_and_execute_ai_task", _mock_multistep_llm)

        run1 = await client.post(f"/api/v1/lead-hunter/leads/{apex_lead['id']}/run-agent", headers=h1)
        assert run1.status_code == 201
        d1 = run1.json()["data"]
        assert d1["steps_executed"] == 3
        assert d1["recommended_service"] == "office-receptionist"
        assert d1["hitl_pending_approval"] is True
        assert d1["auto_sent"] is False
        assert d1["email_word_count"] < 130
        assert d1["demo"]["status"] == "draft"
        assert d1["demo"]["tenant_id"] == str(t1_id)
        assert d1["demo"]["lead_id"] == apex_lead["id"]
        assert d1["website_scan"]["missing_live_chat"] is True
        assert d1["crm_history"]["safe_to_draft"] is True

        # Tenant 2 has ZERO demos (spoofed tenant_id was ignored)
        t2_demos = (await client.get("/api/v1/lead-hunter/demos", headers=h2)).json()["data"]
        assert t2_demos == []

        # Cross-tenant call from Tenant 2 against Tenant 1's lead returns 404
        cross_call = await client.post(f"/api/v1/lead-hunter/leads/{apex_lead['id']}/run-agent", headers=h2)
        assert cross_call.status_code == 404

        # ----------------------------------------------------------------------
        # 2. DETERMINISTIC OFFLINE / MOCK FALLBACK (Has-AI Lead -> CRM Qualification)
        # ----------------------------------------------------------------------
        async def _mock_offline_llm(task_type: str, prompt: str, **kwargs):
            return AIExecutionResult(
                success=True,
                model="deepseek-chat",
                task_type=task_type,
                content="Mock AI completion for task 'lead_hunter_diagnostic_agent'",
                is_mock=True,
            )

        monkeypatch.setattr("app.services.lead_hunter_agent.route_and_execute_ai_task", _mock_offline_llm)

        run2 = await client.post(f"/api/v1/lead-hunter/leads/{chatlaw_lead['id']}/run-agent", headers=h1)
        assert run2.status_code == 201
        d2 = run2.json()["data"]
        assert d2["steps_executed"] == 3
        assert d2["website_scan"]["has_ai"] is True
        assert d2["recommended_service"] in ("lead-crm-qualification", "ai-marketing-growth")
        assert d2["email_word_count"] < 130
        assert d2["demo"]["status"] == "draft"
        assert d2["auto_sent"] is False
