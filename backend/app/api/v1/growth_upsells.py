"""Phase 4 Growth Upsells Router:
- Native IG & FB Comment-to-DM Webhooks & Keyword Rules (`/api/v1/growth/webhooks/meta`, `/comment-dm/*`)
- Smart Google Review Booster 1-5 Star Routing (`/api/v1/growth/reviews/*`)
- WhatsApp & Dashboard Gemini Flash Vision OCR (`/api/v1/growth/ocr/*`)
- Native ReportLab Auto-PDF Generator (`/api/v1/growth/pdf/*`)
"""

import json
import uuid
from typing import Any, Dict, List, Optional

from app.core.tenant_context import TenantContext
from app.database.models.receptionist import ReceptionistCallLog
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.services.pdf_generator_service import pdf_generator_service
from app.services.review_booster_service import review_booster_service
from app.services.social_dm_service import social_dm_service
from app.services.vision_ocr_service import vision_ocr_service
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/growth", tags=["Phase 4 Growth Upsells"])


# ------------------------------------------------------------------------------
# Request Schemas
# ------------------------------------------------------------------------------


class CommentRuleCreateRequest(BaseModel):
    platform: str = Field(default="both", description="instagram | facebook | both")
    keyword: str = Field(min_length=1, max_length=120)
    post_id: Optional[str] = Field(default=None, max_length=150)
    dm_template: str = Field(min_length=2, max_length=1200)
    reply_comment_template: Optional[str] = Field(default=None, max_length=500)
    booking_url: Optional[str] = Field(default=None, max_length=500)


class CommentRuleUpdateRequest(BaseModel):
    platform: Optional[str] = None
    keyword: Optional[str] = Field(default=None, min_length=1, max_length=120)
    post_id: Optional[str] = Field(default=None, max_length=150)
    dm_template: Optional[str] = Field(default=None, min_length=2, max_length=1200)
    reply_comment_template: Optional[str] = Field(default=None, max_length=500)
    booking_url: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None


class SimulateCommentDmRequest(BaseModel):
    platform: str = Field(default="instagram")
    comment_text: str = Field(min_length=1, max_length=1000)
    commenter_name: str = Field(default="Amina Khan", max_length=150)
    commenter_id: Optional[str] = Field(default="ig_user_demo_1", max_length=150)
    post_id: Optional[str] = Field(default=None, max_length=150)


class ReviewBoosterConfigUpdateRequest(BaseModel):
    enabled: bool = True
    google_review_url: Optional[str] = Field(default=None, max_length=800)
    delay_minutes: int = Field(default=60, ge=5, le=1440)
    business_name: Optional[str] = Field(default=None, max_length=200)


class DispatchReviewPromptRequest(BaseModel):
    customer_phone: str = Field(min_length=5, max_length=60)
    customer_name: Optional[str] = Field(default=None, max_length=150)
    call_log_id: Optional[uuid.UUID] = None
    lead_id: Optional[uuid.UUID] = None


class PrivateFeedbackSubmitRequest(BaseModel):
    feedback_text: str = Field(min_length=3, max_length=3000)
    customer_name: Optional[str] = Field(default=None, max_length=150)


class PdfLineItem(BaseModel):
    description: str = Field(min_length=1, max_length=250)
    quantity: float = Field(default=1.0, gt=0)
    unit_price: float = Field(default=0.0, ge=0)


class CustomPdfGenerateRequest(BaseModel):
    document_type: str = Field(default="quote", description="invoice | quote | prescription | summary")
    title: str = Field(min_length=2, max_length=200)
    recipient_name: Optional[str] = Field(default=None, max_length=150)
    recipient_contact: Optional[str] = Field(default=None, max_length=150)
    line_items: List[PdfLineItem] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None, max_length=3000)
    currency: str = Field(default="PKR", max_length=10)


# ------------------------------------------------------------------------------
# 1. Native Instagram & Facebook Comment-to-DM Endpoints + Meta Webhooks
# ------------------------------------------------------------------------------


@router.get("/webhooks/meta", response_class=PlainTextResponse)
async def verify_meta_comment_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """Meta Graph API GET webhook subscription verification for IG & FB Comment-to-DM."""
    return social_dm_service.verify_webhook_challenge(
        hub_mode=hub_mode,
        hub_verify_token=hub_verify_token,
        hub_challenge=hub_challenge,
    )


@router.post("/webhooks/meta")
async def process_meta_comment_webhook(
    raw_request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    session: AsyncSession = Depends(get_db),
):
    """Verified Meta Graph API webhook processing Instagram comments and Facebook Page feed comments."""
    body_bytes = await raw_request.body()
    if not social_dm_service.verify_meta_signature(body_bytes, x_hub_signature_256):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "INVALID_META_SIGNATURE", "message": "X-Hub-Signature-256 verification failed"},
        )
    try:
        payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MALFORMED_JSON", "message": "Invalid JSON webhook payload"},
        )

    fallback_tenant_uuid: Optional[uuid.UUID] = None
    header_tid = raw_request.headers.get("x-tenant-id")
    if header_tid:
        try:
            fallback_tenant_uuid = uuid.UUID(header_tid.strip())
        except ValueError:
            fallback_tenant_uuid = None

    data = await social_dm_service.handle_meta_webhook_payload(
        session=session,
        payload=payload,
        fallback_tenant_id=fallback_tenant_uuid,
    )
    return {"success": True, **data}


@router.get("/comment-dm/rules")
async def list_comment_dm_rules(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    rules = await social_dm_service.list_rules(session, context.tenant_id)
    return {"success": True, "data": rules}


@router.post("/comment-dm/rules", status_code=status.HTTP_201_CREATED)
async def create_comment_dm_rule(
    request: CommentRuleCreateRequest,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    rule = await social_dm_service.create_rule(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        platform=request.platform,
        keyword=request.keyword,
        dm_template=request.dm_template,
        reply_comment_template=request.reply_comment_template,
        post_id=request.post_id,
        booking_url=request.booking_url,
    )
    return {"success": True, "data": rule, "message": "Comment-to-DM rule created cleanly"}


@router.patch("/comment-dm/rules/{rule_id}")
async def update_comment_dm_rule(
    rule_id: uuid.UUID,
    request: CommentRuleUpdateRequest,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    rule = await social_dm_service.update_rule(
        session=session,
        tenant_id=context.tenant_id,
        rule_id=rule_id,
        updates=request.model_dump(exclude_unset=True),
    )
    return {"success": True, "data": rule}


@router.delete("/comment-dm/rules/{rule_id}")
async def delete_comment_dm_rule(
    rule_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    await social_dm_service.delete_rule(session, context.tenant_id, rule_id)
    return {"success": True, "message": "Rule deleted"}


@router.get("/comment-dm/logs")
async def list_comment_dm_logs(
    limit: int = Query(50, ge=1, le=200),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    logs = await social_dm_service.list_dm_logs(session, context.tenant_id, limit=limit)
    return {"success": True, "data": logs}


@router.post("/comment-dm/simulate")
async def simulate_comment_to_dm(
    request: SimulateCommentDmRequest,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Test matching a keyword rule on an IG/FB comment & generating an AI DM with Cal.com link."""
    res = await social_dm_service.process_comment_event(
        session=session,
        tenant_id=context.tenant_id,
        platform=request.platform,
        comment_text=request.comment_text,
        commenter_name=request.commenter_name,
        commenter_id=request.commenter_id,
        comment_id=None,
        post_id=request.post_id,
        dispatch_live=False,
    )
    return {"success": True, "data": res}


# ------------------------------------------------------------------------------
# 2. Smart Google Review Booster Endpoints
# ------------------------------------------------------------------------------


@router.get("/reviews/config")
async def get_review_booster_config(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    cfg = await review_booster_service.get_config(session, context.tenant_id)
    return {"success": True, "data": cfg}


@router.put("/reviews/config")
async def update_review_booster_config(
    request: ReviewBoosterConfigUpdateRequest,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    cfg = await review_booster_service.update_config(
        session=session,
        tenant_id=context.tenant_id,
        enabled=request.enabled,
        google_review_url=request.google_review_url,
        delay_minutes=request.delay_minutes,
        business_name=request.business_name,
    )
    return {"success": True, "data": cfg, "message": "Review Booster settings saved"}


@router.get("/reviews/requests")
async def list_review_booster_requests(
    limit: int = Query(50, ge=1, le=200),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    data = await review_booster_service.list_requests_and_stats(session, context.tenant_id, limit=limit)
    return {"success": True, "data": data}


@router.post("/reviews/send-prompt")
async def send_review_booster_prompt(
    request: DispatchReviewPromptRequest,
    context: TenantContext = Depends(require_permission("notifications.send")),
    session: AsyncSession = Depends(get_db),
):
    res = await review_booster_service.dispatch_review_prompt(
        session=session,
        tenant_id=context.tenant_id,
        customer_phone=request.customer_phone,
        customer_name=request.customer_name,
        call_log_id=request.call_log_id,
        lead_id=request.lead_id,
    )
    return {"success": True, "data": res}


@router.post("/reviews/trigger/{call_log_id}")
async def trigger_review_prompt_for_call(
    call_log_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("notifications.send")),
    session: AsyncSession = Depends(get_db),
):
    call_res = await session.execute(
        select(ReceptionistCallLog).where(
            ReceptionistCallLog.id == call_log_id,
            ReceptionistCallLog.tenant_id == context.tenant_id,
        )
    )
    call_log = call_res.scalar_one_or_none()
    if not call_log:
        raise HTTPException(status_code=404, detail="Appointment call log not found")
    res = await review_booster_service.dispatch_review_prompt(
        session=session,
        tenant_id=context.tenant_id,
        customer_phone=call_log.caller_phone,
        customer_name=call_log.caller_name,
        call_log_id=call_log.id,
    )
    return {"success": True, "data": res}


@router.post("/reviews/private-feedback/{feedback_token}")
async def submit_private_review_feedback(
    feedback_token: str,
    request: PrivateFeedbackSubmitRequest,
    session: AsyncSession = Depends(get_db),
):
    """Public token-scoped form endpoint capturing 1-3 star private feedback cleanly."""
    data = await review_booster_service.submit_public_private_feedback(
        session=session,
        feedback_token=feedback_token,
        feedback_text=request.feedback_text,
        customer_name=request.customer_name,
    )
    return {"success": True, "data": data, "message": "Thank you! Your private feedback has been delivered to management."}


# ------------------------------------------------------------------------------
# 3. WhatsApp & Dashboard Vision OCR Endpoints
# ------------------------------------------------------------------------------


@router.get("/ocr/extractions")
async def list_vision_ocr_extractions(
    limit: int = Query(50, ge=1, le=200),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    items = await vision_ocr_service.list_extractions(session, context.tenant_id, limit=limit)
    return {"success": True, "data": items}


@router.post("/ocr/extract", status_code=status.HTTP_201_CREATED)
async def extract_document_from_upload(
    file: UploadFile = File(...),
    caption: Optional[str] = Form(default=None),
    sender_name: Optional[str] = Form(default=None),
    sender_phone: Optional[str] = Form(default=None),
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Extract structured JSON from an uploaded receipt, prescription, lab report, or invoice image."""
    img_bytes = await file.read()
    data = await vision_ocr_service.extract_from_image(
        session=session,
        tenant_id=context.tenant_id,
        image_bytes=img_bytes,
        mime_type=file.content_type or "image/jpeg",
        source_channel="dashboard_upload",
        sender_phone=sender_phone,
        sender_name=sender_name,
        caption=caption or file.filename,
        user_id=context.user_id,
    )
    return {"success": True, "data": data, "message": "Document extracted cleanly via Vision OCR"}


@router.delete("/ocr/extractions/{extraction_id}")
async def delete_vision_ocr_extraction(
    extraction_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    await vision_ocr_service.delete_extraction(session, context.tenant_id, extraction_id)
    return {"success": True, "message": "Extraction removed"}


# ------------------------------------------------------------------------------
# 4. Native Auto-PDF Generator Endpoints (ReportLab)
# ------------------------------------------------------------------------------


@router.post("/pdf/generate")
async def generate_custom_pdf_document(
    request: CustomPdfGenerateRequest,
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    pdf_bytes, filename = await pdf_generator_service.generate_custom_document_pdf(
        session=session,
        tenant_id=context.tenant_id,
        document_type=request.document_type,
        title=request.title,
        recipient_name=request.recipient_name,
        recipient_contact=request.recipient_contact,
        line_items=[item.model_dump() for item in request.line_items],
        notes=request.notes,
        currency=request.currency,
        actor_id=context.user_id,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pdf/invoice/{invoice_id}")
async def download_invoice_pdf(
    invoice_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("payments.read")),
    session: AsyncSession = Depends(get_db),
):
    pdf_bytes, filename = await pdf_generator_service.generate_invoice_pdf(session, context.tenant_id, invoice_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pdf/appointment/{call_log_id}")
async def download_appointment_pdf(
    call_log_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    pdf_bytes, filename = await pdf_generator_service.generate_appointment_pdf(session, context.tenant_id, call_log_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pdf/weekly-roi")
async def download_weekly_roi_pdf(
    days: int = Query(7, ge=1, le=90),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    pdf_bytes, filename = await pdf_generator_service.generate_weekly_roi_pdf(session, context.tenant_id, days=days)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
