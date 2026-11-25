"""WhatsApp & Dashboard Gemini Flash Vision OCR Extraction Service.

Extracts structured fields from images of payment receipts, prescriptions,
lab reports, invoices, and IDs cleanly into Supabase CRM + `document_extractions`.
Enforces HITL safety: detected payment receipts ALWAYS queue an `Approval` record
via `ApprovalManager` rather than writing blindly to the financial ledger.
"""

import base64
import json
import re
import uuid
from typing import Any, Dict, List, Optional

import httpx
from app.automation.approval_manager import approval_manager
from app.config import settings
from app.core.exceptions import ResourceNotFoundError, TaloxException
from app.core.logging import logger
from app.database.models.automation import AuditLog
from app.database.models.marketing import Lead
from app.database.models.upsells import DocumentExtraction
from app.schemas.approval import ApprovalCreateRequest
from app.services.inbox_service import inbox_service
from app.services.notification_service import notification_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class VisionOcrService:
    """In-house Gemini Flash Vision + deterministic fallback document extractor."""

    @staticmethod
    def _serialize(row: DocumentExtraction) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "lead_id": str(row.lead_id) if row.lead_id else None,
            "session_id": str(row.session_id) if row.session_id else None,
            "approval_id": str(row.approval_id) if row.approval_id else None,
            "source_channel": row.source_channel,
            "document_type": row.document_type,
            "mime_type": row.mime_type,
            "sender_phone": row.sender_phone,
            "sender_name": row.sender_name,
            "media_id": row.media_id,
            "extracted_data": row.extracted_data or {},
            "raw_summary": row.raw_summary,
            "confidence": float(row.confidence or 0.0),
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    async def _call_gemini_vision(
        image_bytes: bytes,
        mime_type: str,
        caption: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        api_key = (settings.gemini_api_key or "").strip()
        if not api_key or api_key in ("mock", "your-gemini-api-key") or settings.app_env == "test":
            return None

        model_name = (settings.gemini_model or "gemini-2.5-flash").strip()
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        b64_img = base64.b64encode(image_bytes).decode("ascii")
        prompt = (
            "You are a precision business OCR extractor. Inspect this image and return ONLY valid JSON with keys:\n"
            '{"document_type": "payment_receipt|prescription|lab_report|invoice|id_document|unknown", '
            '"confidence": 0.92, '
            '"summary": "one concise sentence", '
            '"fields": {"amount": number|null, "currency": "PKR|USD|null", "reference_number": string|null, '
            '"date": string|null, "vendor": string|null, "patient_name": string|null, "medications": [string], "test_results": [string]}}'
        )
        if caption:
            prompt += f"\nImage caption hint: {caption[:400]}"

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(
                    endpoint,
                    json={
                        "contents": [
                            {
                                "parts": [
                                    {"text": prompt},
                                    {"inline_data": {"mime_type": mime_type, "data": b64_img}},
                                ]
                            }
                        ],
                        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
                    },
                )
                if resp.status_code != 200:
                    logger.warning("Gemini Vision API non-200", status_code=resp.status_code)
                    return None
                body = resp.json()
                text_out = (
                    ((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}]
                )[0].get("text")
                if text_out:
                    parsed = json.loads(text_out)
                    if isinstance(parsed, dict) and parsed.get("document_type"):
                        return parsed
        except Exception as exc:
            logger.warning("Gemini Vision OCR call failed; falling back to local extractor", error=str(exc))
        return None

    @staticmethod
    def _heuristic_extract(
        image_bytes: bytes,
        caption: Optional[str] = None,
        sender_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Offline/test deterministic OCR parser inspecting caption and embedded ASCII text in image bytes."""
        embedded_ascii = ""
        if image_bytes:
            embedded_ascii = "".join(
                chr(b) if 32 <= b <= 126 or b in (10, 13, 9) else " "
                for b in image_bytes[:8192]
            )
            embedded_ascii = re.sub(r"\s+", " ", embedded_ascii).strip()

        combined = f"{caption or ''} {embedded_ascii}".strip()
        lower = combined.lower()

        fields: Dict[str, Any] = {}
        doc_type = "unknown"
        confidence = 0.78

        amt_match = re.search(r"(?:\b(?:pkr|usd|rs\.?|eur)\s*|\$)(\d[\d,]*(?:\.\d{1,2})?)", lower)
        if amt_match:
            fields["amount"] = float(amt_match.group(1).replace(",", ""))
        curr_match = re.search(r"\b(pkr|usd|eur)\b", lower)
        if curr_match:
            fields["currency"] = curr_match.group(1).upper()
        elif "$" in lower:
            fields["currency"] = "USD"
        elif fields.get("amount"):
            fields["currency"] = "PKR"

        ref_match = re.search(r"(?:trx|ref|id|inv|#)\s*[:#-]?\s*([a-z0-9-]{4,24})", lower)
        if ref_match:
            fields["reference_number"] = ref_match.group(1).upper()

        if any(w in lower for w in ("receipt", "paid", "transfer", "faysal", "jazzcash", "easypaisa", "iban", "trx")):
            doc_type = "payment_receipt"
            confidence = 0.91
        elif any(w in lower for w in ("rx", "prescription", "tablet", "capsule", "mg", "amoxicillin", "dosage", "dr.")):
            doc_type = "prescription"
            confidence = 0.90
            meds = re.findall(r"([A-Za-z][A-Za-z0-9\s-]{2,28}\s+\d+\s*(?:mg|ml))", combined, re.IGNORECASE)
            if meds:
                fields["medications"] = [m.strip() for m in meds[:8]]
            if sender_name:
                fields["patient_name"] = sender_name
        elif any(w in lower for w in ("lab", "report", "hemoglobin", "glucose", "wbc", "ct scan", "x-ray")):
            doc_type = "lab_report"
            confidence = 0.89
            if sender_name:
                fields["patient_name"] = sender_name
        elif any(w in lower for w in ("invoice", "bill to", "due date")):
            doc_type = "invoice"
            confidence = 0.88

        summary = (
            f"Extracted {doc_type.replace('_', ' ')} "
            + (f"({fields['currency']} {fields['amount']:,.2f}) " if fields.get("amount") else "")
            + (f"Ref: {fields['reference_number']}" if fields.get("reference_number") else (caption or "from image attachment")[:120])
        ).strip()

        return {
            "document_type": doc_type,
            "confidence": confidence,
            "summary": summary,
            "fields": fields,
        }

    async def extract_from_image(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        source_channel: str = "whatsapp",
        sender_phone: Optional[str] = None,
        sender_name: Optional[str] = None,
        caption: Optional[str] = None,
        media_id: Optional[str] = None,
        user_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        if not image_bytes and not caption:
            raise TaloxException(message="Image payload or caption is required for Vision OCR", code="EMPTY_OCR_INPUT", status_code=400)
        if len(image_bytes) > 10 * 1024 * 1024:
            raise TaloxException(message="Image size exceeds 10 MB limit", code="IMAGE_TOO_LARGE", status_code=400)

        vision_res = None
        if image_bytes:
            vision_res = await self._call_gemini_vision(image_bytes, mime_type, caption)
        parsed = vision_res or self._heuristic_extract(image_bytes, caption, sender_name)

        doc_type = str(parsed.get("document_type") or "unknown").lower()
        fields = dict(parsed.get("fields") or {})
        summary = str(parsed.get("summary") or f"Vision OCR processed {doc_type}")
        conf = float(parsed.get("confidence") or 0.85)

        # Link or create CRM Lead + Inbox Session when sender info is known
        lead: Optional[Lead] = None
        if sender_phone:
            l_res = await session.execute(
                select(Lead).where(Lead.tenant_id == tenant_id, Lead.phone == sender_phone.strip()).limit(1)
            )
            lead = l_res.scalar_one_or_none()
            if not lead:
                lead = Lead(
                    tenant_id=tenant_id,
                    name=sender_name or f"WhatsApp ({sender_phone[-4:]})",
                    phone=sender_phone.strip(),
                    source=source_channel,
                    status="qualified" if doc_type in ("payment_receipt", "prescription", "lab_report") else "new",
                    qualification_score=85 if doc_type == "payment_receipt" else 72,
                    metadata_={},
                )
                session.add(lead)
                await session.flush()

        chat_session_id: Optional[uuid.UUID] = None
        if sender_phone:
            chat_sess = await inbox_service.get_or_create_session(
                session=session,
                tenant_id=tenant_id,
                channel="whatsapp",
                external_user_id=sender_phone.strip(),
                contact_name=sender_name,
                lead_id=lead.id if lead else None,
            )
            chat_session_id = chat_sess.id

        status_val = "synced_crm" if lead else "extracted"
        approval_id: Optional[uuid.UUID] = None

        # HITL Safety Rule: Detected payment receipts require Admin Approval before ledger write
        raw_amount = fields.get("amount")
        if doc_type == "payment_receipt" and raw_amount is not None and float(raw_amount) > 0:
            approval = await approval_manager.request_approval(
                session=session,
                tenant_id=tenant_id,
                request=ApprovalCreateRequest(
                    action_type="confirm_ocr_payment_receipt",
                    proposed_action={
                        "document_type": doc_type,
                        "amount": float(raw_amount),
                        "currency": fields.get("currency") or "PKR",
                        "reference_number": fields.get("reference_number"),
                        "sender_phone": sender_phone,
                        "sender_name": sender_name,
                        "summary": summary,
                    },
                    requested_by=str(user_id or "whatsapp_vision_ocr"),
                ),
            )
            approval_id = approval.id
            status_val = "pending_approval"
            await notification_service.send_notification(
                session=session,
                tenant_id=tenant_id,
                title="Payment Receipt Image Detected (Needs Approval)",
                message=f"Vision OCR extracted {fields.get('currency') or 'PKR'} {float(raw_amount):,.2f} receipt from {sender_name or sender_phone or 'upload'}.",
                channel="in_app",
            )

        extraction = DocumentExtraction(
            tenant_id=tenant_id,
            lead_id=lead.id if lead else None,
            session_id=chat_session_id,
            approval_id=approval_id,
            source_channel=source_channel,
            document_type=doc_type,
            mime_type=mime_type,
            sender_phone=sender_phone,
            sender_name=sender_name,
            media_id=media_id,
            extracted_data=fields,
            raw_summary=summary,
            confidence=conf,
            status=status_val,
        )
        session.add(extraction)
        await session.flush()

        if lead:
            l_meta = dict(lead.metadata_ or {})
            history = list(l_meta.get("ocr_extractions") or [])
            history.append({
                "extraction_id": str(extraction.id),
                "document_type": doc_type,
                "summary": summary,
                "fields": fields,
            })
            l_meta["ocr_extractions"] = history[-10:]
            lead.metadata_ = l_meta

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=user_id,
                actor_type="user" if user_id else "system",
                action="growth.vision_ocr.extracted",
                resource_type="document_extraction",
                resource_id=extraction.id,
                metadata_={"document_type": doc_type, "status": status_val},
            )
        )
        await session.commit()
        await session.refresh(extraction)
        return self._serialize(extraction)

    async def list_extractions(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        res = await session.execute(
            select(DocumentExtraction)
            .where(DocumentExtraction.tenant_id == tenant_id)
            .order_by(DocumentExtraction.created_at.desc())
            .limit(limit)
        )
        return [self._serialize(r) for r in res.scalars().all()]

    async def delete_extraction(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        extraction_id: uuid.UUID,
    ) -> None:
        res = await session.execute(
            select(DocumentExtraction).where(
                DocumentExtraction.id == extraction_id,
                DocumentExtraction.tenant_id == tenant_id,
            )
        )
        row = res.scalar_one_or_none()
        if not row:
            raise ResourceNotFoundError("DocumentExtraction", str(extraction_id))
        await session.delete(row)
        await session.commit()


vision_ocr_service = VisionOcrService()
