"""Phase 4 Tests: Native Meta IG/FB Comment-to-DM, Smart Google Review Booster, Vision OCR & ReportLab Auto-PDF."""

import base64
import hashlib
import hmac
import io
import json
import uuid

import pytest
from app.config import settings
from app.database.models.automation import Approval, Notification, ScheduledJob
from app.database.models.billing import Invoice
from app.database.models.marketing import Lead
from app.database.models.receptionist import ReceptionistConfig
from app.database.supabase import get_session_factory
from app.main import app
from httpx import ASGITransport, AsyncClient
from pypdf import PdfReader
from sqlalchemy import select


def _meta_sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def _setup_workspace(client: AsyncClient, email: str, slug: str, name: str):
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
async def test_phase4_comment_to_dm_reviews_ocr_and_reportlab_pdfs(monkeypatch):
    """End-to-end verification of Phase 4 growth upsells & strict tenant isolation."""
    meta_secret = "meta_phase4_test_secret_123"
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "whatsapp_provider", "mock")
    monkeypatch.setattr(settings, "whatsapp_verify_token", "talox_verify_phase4")
    monkeypatch.setattr(settings, "whatsapp_app_secret", meta_secret)
    monkeypatch.setattr(settings, "meta_app_secret", meta_secret)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        t1, h1 = await _setup_workspace(client, "p4.clinic@test.ai", "p4-clinic", "Emerald Dental")
        t2, h2 = await _setup_workspace(client, "p4.other@test.ai", "p4-other", "Other Studio")

        trial = await client.post("/api/v1/payments/start-trial", headers=h1)
        assert trial.status_code == 200

        # Seed ReceptionistConfig + Invoice for Appointment/Invoice PDF tests
        factory = get_session_factory()
        async with factory() as session:
            from datetime import datetime, timedelta, timezone

            session.add(
                ReceptionistConfig(
                    tenant_id=t1,
                    business_name="Emerald Dental",
                    operating_hours="Mon-Sat 9 AM - 8 PM",
                    fallback_phone_number="+923009991111",
                    calcom_booking_url="https://cal.com/emerald-dental/consult",
                )
            )
            inv = Invoice(
                tenant_id=t1,
                invoice_number="INV-P4-2026-001",
                subtotal=25000.0,
                tax=2500.0,
                total=27500.0,
                currency="PKR",
                status="issued",
                due_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
            session.add(inv)
            await session.commit()
            inv_id = inv.id

        # ==================================================================
        # 1. Native IG & FB Comment-to-DM Webhooks & Keyword Rules
        # ==================================================================
        meta_conn = await client.post(
            "/api/v1/integrations/meta_social/connect",
            json={
                "api_key": "EAAB_mock_page_token_12345",
                "account_identifier": "fb_page_1001",
                "configuration": {"page_id": "fb_page_1001", "ig_account_id": "ig_biz_2002"},
            },
            headers=h1,
        )
        assert meta_conn.status_code == 201
        assert meta_conn.json()["data"]["status"] == "connected"

        # Handshake checklist shows meta_social connected & action_url /growth-tools
        ck = await client.get("/api/v1/integrations/handshake-checklist", headers=h1)
        assert ck.status_code == 200
        meta_ck = next(i for i in ck.json()["data"]["items"] if i["key"] == "meta_social")
        assert meta_ck["status"] == "connected"
        assert meta_ck["action_url"] == "/growth-tools"

        # Meta webhook subscription verification challenge
        hub_res = await client.get(
            "/api/v1/growth/webhooks/meta",
            params={"hub.mode": "subscribe", "hub.verify_token": "talox_verify_phase4", "hub.challenge": "998877"},
        )
        assert hub_res.status_code == 200
        assert hub_res.text == "998877"

        # Create keyword rule ("PRICE") on Tenant 1
        r_res = await client.post(
            "/api/v1/growth/comment-dm/rules",
            json={
                "platform": "both",
                "keyword": "PRICE",
                "dm_template": "Hi {{name}}, here are our implant & whitening packages!",
                "booking_url": "https://cal.com/emerald-dental/vip",
            },
            headers=h1,
        )
        assert r_res.status_code == 201
        rule_id = r_res.json()["data"]["id"]

        # Unsigned/bad X-Hub-Signature-256 rejected with 403
        ig_payload = json.dumps({
            "object": "instagram",
            "entry": [{
                "id": "ig_biz_2002",
                "changes": [{
                    "field": "comments",
                    "value": {
                        "id": "ig_cmt_001",
                        "text": "Hey please share PRICE info!",
                        "from": {"id": "ig_u_55", "username": "zara_aesthetics"},
                        "media": {"id": "ig_reel_99"},
                    },
                }],
            }],
        }).encode("utf-8")

        bad_meta = await client.post(
            "/api/v1/growth/webhooks/meta",
            content=ig_payload,
            headers={"X-Hub-Signature-256": "sha256=deadbeef", "Content-Type": "application/json"},
        )
        assert bad_meta.status_code == 403

        # Valid IG comment webhook dispatches DM + embeds Cal.com link + logs CRM lead + idempotency
        ok_ig = await client.post(
            "/api/v1/growth/webhooks/meta",
            content=ig_payload,
            headers={"X-Hub-Signature-256": _meta_sig(meta_secret, ig_payload), "Content-Type": "application/json"},
        )
        assert ok_ig.status_code == 200
        ig_data = ok_ig.json()["results"][0]
        assert ig_data["processed"] is True
        assert ig_data["idempotent"] is False
        assert "https://cal.com/emerald-dental/vip" in ig_data["log"]["dm_text"]

        # Replay of exact same IG comment_id must be idempotent
        dup_ig = await client.post(
            "/api/v1/growth/webhooks/meta",
            content=ig_payload,
            headers={"X-Hub-Signature-256": _meta_sig(meta_secret, ig_payload), "Content-Type": "application/json"},
        )
        assert dup_ig.status_code == 200
        assert dup_ig.json()["results"][0]["idempotent"] is True

        # Signed FB Page comment webhook also triggers auto-DM
        fb_payload = json.dumps({
            "object": "page",
            "entry": [{
                "id": "fb_page_1001",
                "changes": [{
                    "field": "feed",
                    "value": {
                        "item": "comment",
                        "verb": "add",
                        "comment_id": "fb_cmt_002",
                        "post_id": "fb_post_77",
                        "message": "What is the price of scaling?",
                        "from": {"id": "fb_u_88", "name": "Hamza Tariq"},
                    },
                }],
            }],
        }).encode("utf-8")
        ok_fb = await client.post(
            "/api/v1/growth/webhooks/meta",
            content=fb_payload,
            headers={"X-Hub-Signature-256": _meta_sig(meta_secret, fb_payload), "Content-Type": "application/json"},
        )
        assert ok_fb.status_code == 200
        assert ok_fb.json()["results"][0]["processed"] is True
        assert ok_fb.json()["results"][0]["log"]["platform"] == "facebook"

        # Tenant isolation on rules & logs
        assert (await client.get("/api/v1/growth/comment-dm/rules", headers=h2)).json()["data"] == []
        assert (await client.delete(f"/api/v1/growth/comment-dm/rules/{rule_id}", headers=h2)).status_code == 404
        assert len((await client.get("/api/v1/growth/comment-dm/logs", headers=h1)).json()["data"]) == 2

        # ==================================================================
        # 2. Smart Google Review Booster (1-5 Star Routing + Private Shield)
        # ==================================================================
        rb_cfg = await client.put(
            "/api/v1/growth/reviews/config",
            json={
                "enabled": True,
                "google_review_url": "https://g.page/r/emerald-dental-review-unique",
                "delay_minutes": 60,
            },
            headers=h1,
        )
        assert rb_cfg.status_code == 200
        assert rb_cfg.json()["data"]["delay_minutes"] == 60

        # Booking via Cal.com tool enqueues both appointment_reminder and review_booster_prompt
        book_res = await client.post(
            f"/api/v1/receptionist/tools/{t1}/calcom/book",
            json={
                "start_iso": "2026-12-01T14:00:00Z",
                "attendee_name": "Omar Patient",
                "attendee_phone": "+923001112233",
            },
        )
        assert book_res.status_code == 200
        async with factory() as session:
            jobs = (await session.execute(select(ScheduledJob).where(ScheduledJob.tenant_id == t1))).scalars().all()
            job_types = {j.job_type for j in jobs}
            assert "appointment_reminder" in job_types
            assert "review_booster_prompt" in job_types

        # Happy 5-star customer -> receives direct Google review link
        p1 = await client.post(
            "/api/v1/growth/reviews/send-prompt",
            json={"customer_phone": "+923001112233", "customer_name": "Happy Sana"},
            headers=h1,
        )
        assert p1.status_code == 200
        req1_id = p1.json()["data"]["request"]["id"]

        r5_body = json.dumps({
            "sender_phone": "+923001112233",
            "sender_name": "Happy Sana",
            "message_text": "5 Stars - Great",
            "interactive_reply_id": f"review_rate:{req1_id}:5",
        }).encode("utf-8")
        r5_wh = await client.post(
            "/api/v1/integrations/whatsapp/webhook",
            content=r5_body,
            headers={
                "X-Tenant-ID": str(t1),
                "X-Hub-Signature-256": _meta_sig(meta_secret, r5_body),
                "Content-Type": "application/json",
            },
        )
        assert r5_wh.status_code == 200
        r5_data = r5_wh.json()["data"]
        assert r5_data["outcome"] == "google_review"
        assert "emerald-dental-review-unique" in r5_data["reply_text"]

        # Unhappy 2-star customer -> NO Google link in reply! Intercepted privately + public feedback token works
        p2 = await client.post(
            "/api/v1/growth/reviews/send-prompt",
            json={"customer_phone": "+923004445566", "customer_name": "Sad Bilal"},
            headers=h1,
        )
        assert p2.status_code == 200
        req2_token = p2.json()["data"]["request"]["feedback_token"]

        r2_body = json.dumps({
            "sender_phone": "+923004445566",
            "sender_name": "Sad Bilal",
            "message_text": "2",
        }).encode("utf-8")
        r2_wh = await client.post(
            "/api/v1/integrations/whatsapp/webhook",
            content=r2_body,
            headers={
                "X-Tenant-ID": str(t1),
                "X-Hub-Signature-256": _meta_sig(meta_secret, r2_body),
                "Content-Type": "application/json",
            },
        )
        assert r2_wh.status_code == 200
        r2_data = r2_wh.json()["data"]
        assert r2_data["outcome"] == "private_feedback"
        assert "emerald-dental-review-unique" not in r2_data["reply_text"]
        assert f"/feedback?token={req2_token}" in r2_data["reply_text"]

        fb_submit = await client.post(
            f"/api/v1/growth/reviews/private-feedback/{req2_token}",
            json={"feedback_text": "Waiting time at reception was 40 minutes long.", "customer_name": "Bilal R."},
        )
        assert fb_submit.status_code == 200
        assert fb_submit.json()["data"]["status"] == "feedback_submitted"

        rb_stats = (await client.get("/api/v1/growth/reviews/requests", headers=h1)).json()["data"]["stats"]
        assert rb_stats["google_routed_count"] == 1
        assert rb_stats["private_intercepted_count"] == 1

        # ==================================================================
        # 3. WhatsApp & Upload Vision OCR (Receipts -> HITL Approval; Rx -> CRM)
        # ==================================================================
        receipt_bytes = b"\xff\xd8\xff\xe0MOCK_JPG Faysal Bank Payment Receipt TRX99881 Paid PKR 27500"
        ocr_up = await client.post(
            "/api/v1/growth/ocr/extract",
            files={"file": ("faysal_receipt.jpg", receipt_bytes, "image/jpeg")},
            data={"sender_phone": "+923007771122", "sender_name": "Tariq Patient", "caption": "Paid receipt PKR 27500"},
            headers=h1,
        )
        assert ocr_up.status_code == 201
        ex_receipt = ocr_up.json()["data"]
        assert ex_receipt["document_type"] == "payment_receipt"
        assert ex_receipt["extracted_data"]["amount"] == 27500.0
        assert ex_receipt["status"] == "pending_approval"
        assert ex_receipt["approval_id"] is not None

        # Verify HITL Approval exists for receipt
        async with factory() as session:
            app_row = (
                await session.execute(select(Approval).where(Approval.id == uuid.UUID(ex_receipt["approval_id"])))
            ).scalar_one()
            assert app_row.action_type == "confirm_ocr_payment_receipt"
            assert app_row.status == "pending"

        # Inbound WhatsApp image webhook with prescription
        rx_b64 = base64.b64encode(b"FAKEIMG Rx Prescription Dr. Amina Amoxicillin 500mg twice daily").decode("ascii")
        rx_wh_body = json.dumps({
            "sender_phone": "+923008889900",
            "sender_name": "Rx Sender",
            "message_text": "Dr. Amina Prescription Amoxicillin 500mg",
            "image_base64": rx_b64,
            "image_mime_type": "image/jpeg",
        }).encode("utf-8")
        rx_wh = await client.post(
            "/api/v1/integrations/whatsapp/webhook",
            content=rx_wh_body,
            headers={
                "X-Tenant-ID": str(t1),
                "X-Hub-Signature-256": _meta_sig(meta_secret, rx_wh_body),
                "Content-Type": "application/json",
            },
        )
        assert rx_wh.status_code == 200
        assert rx_wh.json()["data"]["classification"] == "vision_ocr_prescription"

        async with factory() as session:
            lead_rx = (
                await session.execute(select(Lead).where(Lead.tenant_id == t1, Lead.phone == "+923008889900"))
            ).scalar_one()
            assert len(lead_rx.metadata_.get("ocr_extractions") or []) == 1

        # Cross-tenant OCR isolation
        assert (await client.get("/api/v1/growth/ocr/extractions", headers=h2)).json()["data"] == []
        assert (await client.delete(f"/api/v1/growth/ocr/extractions/{ex_receipt['id']}", headers=h2)).status_code == 404

        # ==================================================================
        # 4. Native ReportLab Auto-PDF Generator (Quote, Invoice, Appointment, ROI)
        # ==================================================================
        pdf_custom = await client.post(
            "/api/v1/growth/pdf/generate",
            json={
                "document_type": "quote",
                "title": "Implant Treatment Plan",
                "recipient_name": "Sarah Jenkins",
                "currency": "PKR",
                "line_items": [
                    {"description": "3D CBCT Dental Scan", "quantity": 1, "unit_price": 5000.0},
                    {"description": "Titanium Implant Crown", "quantity": 1, "unit_price": 45000.0},
                ],
                "notes": "Includes 12-month follow-up.",
            },
            headers=h1,
        )
        assert pdf_custom.status_code == 200
        assert pdf_custom.headers["content-type"].startswith("application/pdf")
        assert pdf_custom.content.startswith(b"%PDF-")
        custom_txt = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_custom.content)).pages)
        assert "Implant Treatment Plan" in custom_txt
        assert "50,000.00" in custom_txt

        # Invoice PDF + Tenant 2 gets 404
        pdf_inv = await client.get(f"/api/v1/growth/pdf/invoice/{inv_id}", headers=h1)
        assert pdf_inv.status_code == 200
        assert pdf_inv.content.startswith(b"%PDF-")
        inv_txt = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_inv.content)).pages)
        assert "INV-P4-2026-001" in inv_txt
        assert (await client.get(f"/api/v1/growth/pdf/invoice/{inv_id}", headers=h2)).status_code == 404

        # Simulated Call -> Appointment PDF + Weekly ROI PDF
        sim_call = await client.post(
            "/api/v1/receptionist/calls/simulate",
            json={"caller_name": "Omar Patient", "caller_phone": "+923001112233", "scenario": "appointment_booking"},
            headers=h1,
        )
        assert sim_call.status_code == 200
        call_log_id = sim_call.json()["data"]["id"]

        pdf_appt = await client.get(f"/api/v1/growth/pdf/appointment/{call_log_id}", headers=h1)
        assert pdf_appt.status_code == 200
        assert pdf_appt.content.startswith(b"%PDF-")
        assert (await client.get(f"/api/v1/growth/pdf/appointment/{call_log_id}", headers=h2)).status_code == 404

        pdf_roi = await client.get("/api/v1/growth/pdf/weekly-roi?days=7", headers=h1)
        assert pdf_roi.status_code == 200
        assert pdf_roi.content.startswith(b"%PDF-")
        roi_txt = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_roi.content)).pages)
        assert "Weekly AI Performance" in roi_txt
