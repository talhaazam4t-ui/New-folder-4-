"""Phase 3 Tests: 1-Click pgvector RAG, No-Show Recovery, AI Call Scoring + Weekly ROI & CRM HITL Inbox."""

import hashlib
import hmac
import json
import socket
import uuid

import httpx
import pytest
from app.config import settings
from app.database.models.knowledge import OmnichannelSession, WhatsAppMessage
from app.database.models.marketing import Lead
from app.database.models.receptionist import ReceptionistConfig
from app.database.supabase import get_session_factory
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


def _build_minimal_pdf(text: str) -> bytes:
    """Construct a tiny single-page valid PDF containing literal searchable ASCII text."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream_body = f"BT\n/F1 12 Tf\n72 720 Td\n({escaped}) Tj\nET\n"
    objs = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        ),
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        (
            f"5 0 obj\n<< /Length {len(stream_body.encode('latin-1'))} >>\nstream\n"
            f"{stream_body}endstream\nendobj\n"
        ).encode("latin-1"),
    ]
    buf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(buf))
        buf.extend(obj)
    xref_pos = len(buf)
    buf.extend(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("latin-1"))
    for off in offsets[1:]:
        buf.extend(f"{off:010d} 00000 n \n".encode("latin-1"))
    buf.extend(
        (
            f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n"
            f"{xref_pos}\n%%EOF\n"
        ).encode("latin-1")
    )
    return bytes(buf)


def _wa_sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


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
        json={"name": name, "slug": slug, "industry": "Clinics / Hospitals"},
        headers=auth_h,
    )
    assert t_res.status_code in (200, 201)
    tid = t_res.json()["id"]
    return uuid.UUID(tid), {**auth_h, "X-Tenant-ID": str(tid)}


@pytest.mark.asyncio
async def test_phase3_rag_noshow_scoring_weekly_roi_and_hitl_inbox(monkeypatch):
    """End-to-end verification of Phase 3 features & strict multi-tenant isolation."""
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "resend_api_key", "")
    monkeypatch.setattr(settings, "whatsapp_provider", "mock")
    monkeypatch.setattr(settings, "whatsapp_app_secret", "wa_phase3_test_secret")
    monkeypatch.setattr(settings, "meta_app_secret", "")

    # Stub DNS resolution & HTTP GET for 1-click website scraping
    orig_getaddrinfo = socket.getaddrinfo

    def _fake_getaddrinfo(host, port, *args, **kwargs):
        if host == "clinic.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        return orig_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    orig_httpx_get = httpx.AsyncClient.get

    async def _fake_httpx_get(self, url, *args, **kwargs):
        if "clinic.example.com" in str(url):
            req = httpx.Request("GET", str(url))
            html = (
                "<html><head><title>Smile Care Dental</title></head>"
                "<body><h1>Clinic Pricing & Hours</h1>"
                "<p>Dental scaling and polishing costs PKR 6000. Open Mon-Sat 9 AM to 8 PM.</p>"
                "</body></html>"
            )
            return httpx.Response(200, request=req, headers={"content-type": "text/html"}, text=html)
        return await orig_httpx_get(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_httpx_get)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        t1, h1 = await _register_and_create_workspace(client, "p3.clinic1@test.ai", "p3-clinic-1", "Smile Care Clinic")
        t2, h2 = await _register_and_create_workspace(client, "p3.clinic2@test.ai", "p3-clinic-2", "Other Clinic")

        # Activate 7-day trial on tenant 1 so receptionist/wallet gates pass cleanly
        trial = await client.post("/api/v1/payments/start-trial", headers=h1)
        assert trial.status_code == 200

        # Seed ReceptionistConfig + waitlisted Lead
        factory = get_session_factory()
        async with factory() as session:
            session.add(
                ReceptionistConfig(
                    tenant_id=t1,
                    business_name="Smile Care Clinic",
                    operating_hours="Mon-Sat 9 AM - 8 PM",
                    fallback_phone_number="+923009998877",
                    greeting_message="Welcome to Smile Care Clinic!",
                    faqs_knowledge_base="Scaling PKR 6000.",
                )
            )
            wait_lead = Lead(
                tenant_id=t1,
                name="Waitlisted Patient Zara",
                source="manual",
                status="new",
                phone="+923005551234",
                qualification_score=80,
                metadata_={},
            )
            session.add(wait_lead)
            await session.commit()
            wait_lead_id = wait_lead.id

        # ------------------------------------------------------------------
        # 1. 1-Click RAG Website URL + PDF Upload + Tenant Isolation + Tool
        # ------------------------------------------------------------------
        url_ing = await client.post(
            "/api/v1/knowledge/ingest/url",
            json={"url": "https://clinic.example.com/services"},
            headers=h1,
        )
        assert url_ing.status_code == 201
        assert url_ing.json()["data"]["chunk_count"] >= 1

        pdf_bytes = _build_minimal_pdf("Dental implants cost PKR 45000 and include free 3D CT scan.")
        pdf_ing = await client.post(
            "/api/v1/knowledge/ingest/pdf",
            files={"file": ("implant_pricing.pdf", pdf_bytes, "application/pdf")},
            data={"title": "Implant Pricing Brochure"},
            headers=h1,
        )
        assert pdf_ing.status_code == 201
        assert pdf_ing.json()["data"]["chunk_count"] >= 1

        docs_t1 = await client.get("/api/v1/knowledge/documents", headers=h1)
        docs_t2 = await client.get("/api/v1/knowledge/documents", headers=h2)
        assert docs_t1.status_code == 200, docs_t1.text
        assert docs_t2.status_code == 200, docs_t2.text
        assert len(docs_t1.json()["data"]) == 2
        assert len(docs_t2.json()["data"]) == 0

        s_t1 = await client.post(
            "/api/v1/knowledge/search",
            json={"query": "Dental implants cost PKR 45000", "top_k": 3},
            headers=h1,
        )
        assert s_t1.status_code == 200
        assert len(s_t1.json()["data"]) >= 1
        assert any("45000" in m["content"] or "scaling" in m["content"].lower() for m in s_t1.json()["data"])

        s_t2 = await client.post(
            "/api/v1/knowledge/search",
            json={"query": "Dental implants cost PKR 45000", "top_k": 3},
            headers=h2,
        )
        assert s_t2.status_code == 200
        assert s_t2.json()["data"] == []

        retell_tool = await client.post(
            f"/api/v1/receptionist/tools/{t1}/knowledge/search",
            json={"query": "Dental scaling cost PKR 6000"},
        )
        assert retell_tool.status_code == 200
        assert len(retell_tool.json()["data"]["matches"]) >= 1

        # ------------------------------------------------------------------
        # 2. No-Show Recovery + AI Call Sentiment/Scoring + Weekly ROI
        # ------------------------------------------------------------------
        wl_res = await client.post(
            f"/api/v1/receptionist/waitlist/{wait_lead_id}",
            json={"waitlist": True},
            headers=h1,
        )
        assert wl_res.status_code == 200
        assert wl_res.json()["data"]["waitlist"] is True

        sim1 = await client.post(
            "/api/v1/receptionist/calls/simulate",
            json={
                "caller_name": "Patient Ayesha",
                "caller_phone": "+923001112233",
                "scenario": "appointment_booking",
            },
            headers=h1,
        )
        assert sim1.status_code == 200, sim1.text
        sim1_data = sim1.json()["data"]
        call1_id = sim1_data["id"]
        assert sim1_data.get("lead_tier") in ("hot", "warm", "cold")
        assert sim1_data.get("sentiment") in ("positive", "neutral", "negative")

        sim2 = await client.post(
            "/api/v1/receptionist/calls/simulate",
            json={
                "caller_name": "Patient Bilal",
                "caller_phone": "+923004445566",
                "scenario": "appointment_booking",
            },
            headers=h1,
        )
        assert sim2.status_code == 200, sim2.text
        call2_id = sim2.json()["data"]["id"]

        trig = await client.post(
            f"/api/v1/receptionist/appointments/{call1_id}/trigger-reminder",
            headers=h1,
        )
        assert trig.status_code == 200

        confirm_body = json.dumps({
            "sender_phone": "+923001112233",
            "sender_name": "Patient Ayesha",
            "message_text": "Confirm Appointment",
            "interactive_reply_id": f"appt_confirm:{call1_id}",
        }).encode("utf-8")
        confirm_wh = await client.post(
            "/api/v1/integrations/whatsapp/webhook",
            content=confirm_body,
            headers={
                "X-Tenant-ID": str(t1),
                "X-Hub-Signature-256": _wa_sig("wa_phase3_test_secret", confirm_body),
                "Content-Type": "application/json",
            },
        )
        assert confirm_wh.status_code == 200

        resched_body = json.dumps({
            "sender_phone": "+923004445566",
            "sender_name": "Patient Bilal",
            "message_text": "Reschedule",
            "interactive_reply_id": f"appt_reschedule:{call2_id}",
        }).encode("utf-8")
        resched_wh = await client.post(
            "/api/v1/integrations/whatsapp/webhook",
            content=resched_body,
            headers={
                "X-Tenant-ID": str(t1),
                "X-Hub-Signature-256": _wa_sig("wa_phase3_test_secret", resched_body),
                "Content-Type": "application/json",
            },
        )
        assert resched_wh.status_code == 200

        roi_res = await client.get("/api/v1/analytics/weekly-roi", headers=h1)
        assert roi_res.status_code == 200
        roi_data = roi_res.json()["data"]
        assert roi_data["calls_handled"] >= 2
        assert roi_data["appointments_booked"] >= 1

        roi_send = await client.post("/api/v1/analytics/weekly-roi/send", headers=h1)
        assert roi_send.status_code == 200

        # ------------------------------------------------------------------
        # 3. Unified CRM Live Inbox + 1-Click HITL Takeover
        # ------------------------------------------------------------------
        q_body = json.dumps({
            "sender_phone": "+923007778899",
            "sender_name": "Clinic Visitor",
            "message_text": "What is the price of Dental scaling?",
        }).encode("utf-8")
        q_wh = await client.post(
            "/api/v1/integrations/whatsapp/webhook",
            content=q_body,
            headers={
                "X-Tenant-ID": str(t1),
                "X-Hub-Signature-256": _wa_sig("wa_phase3_test_secret", q_body),
                "Content-Type": "application/json",
            },
        )
        assert q_wh.status_code == 200

        conv_res = await client.get("/api/v1/inbox/conversations", headers=h1)
        assert conv_res.status_code == 200
        convs = conv_res.json()["data"]
        visitor_conv = next(c for c in convs if c["external_user_id"] == "+923007778899")
        session_id = visitor_conv["id"]

        # Cross-tenant isolation check on conversation thread
        cross_conv = await client.get(f"/api/v1/inbox/conversations/{session_id}/messages", headers=h2)
        assert cross_conv.status_code == 404

        # Toggle HITL Takeover ON -> AI auto-replies immediately pause
        tk_on = await client.post(
            f"/api/v1/inbox/conversations/{session_id}/takeover",
            json={"enabled": True},
            headers=h1,
        )
        assert tk_on.status_code == 200
        assert tk_on.json()["data"]["human_takeover"] is True

        paused_body = json.dumps({
            "sender_phone": "+923007778899",
            "sender_name": "Clinic Visitor",
            "message_text": "Hello is anyone there?",
        }).encode("utf-8")
        paused_wh = await client.post(
            "/api/v1/integrations/whatsapp/webhook",
            content=paused_body,
            headers={
                "X-Tenant-ID": str(t1),
                "X-Hub-Signature-256": _wa_sig("wa_phase3_test_secret", paused_body),
                "Content-Type": "application/json",
            },
        )
        assert paused_wh.status_code == 200
        assert paused_wh.json()["data"]["ai_paused"] is True

        # Live human reply persists to thread and updates session
        human_rep = await client.post(
            f"/api/v1/inbox/conversations/{session_id}/reply",
            json={"message_body": "Hi, I am Dr. Sara taking over directly.", "enable_takeover": True},
            headers=h1,
        )
        assert human_rep.status_code == 200

        thread_res = await client.get(f"/api/v1/inbox/conversations/{session_id}/messages", headers=h1)
        assert thread_res.status_code == 200
        msgs = thread_res.json()["data"]["messages"]
        assert any("Dr. Sara taking over" in m["content"] for m in msgs)

        # DB sanity check: OmnichannelSession.human_takeover stays True
        async with factory() as session:
            sess_row = (
                await session.execute(select(OmnichannelSession).where(OmnichannelSession.id == uuid.UUID(session_id)))
            ).scalar_one()
            assert sess_row.human_takeover is True
            msg_count = len((await session.execute(select(WhatsAppMessage).where(WhatsAppMessage.tenant_id == t1))).scalars().all())
            assert msg_count >= 2
