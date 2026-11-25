"""Office Receptionist (AI Voice Agent) API Endpoints — Retell AI, Telnyx, and Cal.com."""

import json
import uuid
from typing import Optional

from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import get_current_tenant, require_permission
from app.integrations.voice.receptionist_providers import retell_ai_adapter
from app.schemas.receptionist import (
    CalComAvailabilityToolRequest,
    CalComBookToolRequest,
    ReceptionistConfigUpsertRequest,
    ReceptionistFaqsUpdateRequest,
    SimulateVoiceCallRequest,
)
from app.services.noshow_recovery_service import noshow_recovery_service
from app.services.rag_service import rag_service
from app.services.receptionist_service import receptionist_service
from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/receptionist", tags=["Office Receptionist (AI Voice)"])


@router.get("/config")
async def get_receptionist_config(
    context: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve the active tenant's Office Receptionist AI Voice configuration & access flags."""
    cfg = await receptionist_service.get_config(session, context.tenant_id)
    access = await receptionist_service.get_tenant_access_state(session, context.tenant_id)
    return {
        "success": True,
        "data": cfg,
        "payment_approved": access["payment_approved"],
        "has_subscription": access["has_subscription"],
    }


@router.put("/config")
async def upsert_receptionist_config(
    request: ReceptionistConfigUpsertRequest,
    context: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """Save Office Receptionist settings; provision Telnyx + Retell AI only after payment approval."""
    is_super = context.role == "super_admin"
    cfg = await receptionist_service.upsert_config(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        request=request,
        is_super_admin=is_super,
    )
    access = await receptionist_service.get_tenant_access_state(session, context.tenant_id)
    msg = (
        "Office Receptionist draft saved. Complete your bank transfer payment on the Dashboard to activate your AI phone line."
        if cfg.get("provisioning_status") == "awaiting_payment"
        else "Office Receptionist configuration saved and voice agent synchronized."
    )
    return {
        "success": True,
        "data": cfg,
        "payment_approved": access["payment_approved"],
        "has_subscription": access["has_subscription"],
        "message": msg,
    }


@router.patch("/faqs")
async def update_receptionist_faqs(
    request: ReceptionistFaqsUpdateRequest,
    context: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """Update business FAQs, greeting, operating hours, fallback phone, or Cal.com settings."""
    is_super = context.role == "super_admin"
    cfg = await receptionist_service.update_faqs(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        request=request,
        is_super_admin=is_super,
    )
    msg = (
        "FAQs draft saved. Live AI Voice Agent will sync automatically once payment is approved."
        if cfg.get("provisioning_status") == "awaiting_payment"
        else "FAQs and knowledge base updated and synced to your AI Voice Receptionist."
    )
    return {
        "success": True,
        "data": cfg,
        "message": msg,
    }


@router.post("/provision")
async def provision_receptionist_agent(
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Provision or re-sync the tenant's Telnyx AI number, Retell AI voice agent, and Cal.com tools."""
    if context.role != "super_admin":
        access = await receptionist_service.get_tenant_access_state(session, context.tenant_id)
        if not access["has_subscription"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "SUBSCRIPTION_REQUIRED",
                    "message": "Please select an Office Receptionist subscription plan first.",
                },
            )
        if not access["payment_approved"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PAYMENT_APPROVAL_REQUIRED",
                    "message": "Office Receptionist provisioning is locked until Admin approves your bank transfer payment.",
                },
            )
    cfg = await receptionist_service.provision_voice_stack(
        session=session,
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
    )
    return {
        "success": True,
        "data": cfg,
        "message": "Telnyx number and Retell AI Voice Receptionist provisioned.",
    }


@router.get("/calls")
async def list_receptionist_calls(
    limit: int = Query(50, ge=1, le=200),
    context: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """List call logs, booked Cal.com appointments, and voice KPI summary for the tenant."""
    data = await receptionist_service.list_calls_and_summary(
        session=session,
        tenant_id=context.tenant_id,
        limit=limit,
    )
    return {"success": True, "data": data}


@router.post("/calls/simulate")
async def simulate_receptionist_call(
    request: SimulateVoiceCallRequest,
    context: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """Run a realistic simulated voice call (Cal.com booking, FAQ inquiry, or live human transfer)."""
    if context.role != "super_admin":
        access = await receptionist_service.get_tenant_access_state(session, context.tenant_id)
        if not access["payment_approved"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PAYMENT_APPROVAL_REQUIRED",
                    "message": "Test call simulation unlocks once your bank transfer payment is approved by Admin.",
                },
            )
    call = await receptionist_service.simulate_voice_call(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        request=request,
    )
    return {
        "success": True,
        "data": call,
        "message": f"Simulated '{request.scenario}' call logged cleanly.",
    }


# ------------------------------------------------------------------------------
# Retell AI Custom Function-Calling Tool Endpoints (Cal.com + Live Transfer)
# ------------------------------------------------------------------------------


@router.post("/tools/{tenant_id}/calcom/availability")
async def retell_tool_calcom_availability(
    tenant_id: uuid.UUID,
    request: CalComAvailabilityToolRequest,
    session: AsyncSession = Depends(get_db),
):
    """Retell AI tool endpoint: check live Cal.com appointment slots during an active voice call."""
    result = await receptionist_service.handle_calcom_availability_tool(
        session=session,
        tenant_id=tenant_id,
        date_str=request.date,
    )
    return {"success": True, "data": result}


class RetellKnowledgeToolRequest(BaseModel):
    query: str = Field(default="", max_length=1000)


class WaitlistToggleRequest(BaseModel):
    waitlist: bool = True


@router.post("/tools/{tenant_id}/knowledge/search")
async def retell_tool_knowledge_search(
    tenant_id: uuid.UUID,
    request: RetellKnowledgeToolRequest,
    session: AsyncSession = Depends(get_db),
):
    """Retell AI tool endpoint: retrieve top RAG chunks from the client's website/PDF knowledge base."""
    matches = await rag_service.search_knowledge(
        session=session,
        tenant_id=tenant_id,
        query=request.query,
        top_k=3,
    )
    return {"success": True, "data": {"matches": matches}}


@router.post("/appointments/{call_log_id}/trigger-reminder")
async def trigger_appointment_noshow_reminder(
    call_log_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("notifications.send")),
    session: AsyncSession = Depends(get_db),
):
    """Send an immediate WhatsApp Confirm/Reschedule interactive prompt for a booked appointment."""
    res = await noshow_recovery_service.dispatch_appointment_reminder(
        session=session,
        tenant_id=context.tenant_id,
        call_log_id=call_log_id,
    )
    return {"success": True, "data": res}


@router.post("/waitlist/{lead_id}")
async def toggle_lead_waitlist_status(
    lead_id: uuid.UUID,
    request: WaitlistToggleRequest,
    context: TenantContext = Depends(require_permission("leads.update")),
    session: AsyncSession = Depends(get_db),
):
    """Add or remove a lead from the smart appointment no-show cancellation waitlist."""
    data = await noshow_recovery_service.set_lead_waitlist(
        session=session,
        tenant_id=context.tenant_id,
        lead_id=lead_id,
        waitlisted=request.waitlist,
    )
    return {"success": True, "data": data}


@router.post("/tools/{tenant_id}/calcom/book")
async def retell_tool_calcom_book(
    tenant_id: uuid.UUID,
    request: CalComBookToolRequest,
    session: AsyncSession = Depends(get_db),
):
    """Retell AI tool endpoint: book a Cal.com appointment directly during a live voice call."""
    result = await receptionist_service.handle_calcom_book_tool(
        session=session,
        tenant_id=tenant_id,
        request=request,
    )
    return {"success": True, "data": result}


# ------------------------------------------------------------------------------
# Public Voice Webhooks (Retell AI Call Events & Telnyx Inbound Voice TeXML)
# ------------------------------------------------------------------------------


@router.post("/webhooks/retell")
async def retell_call_event_webhook(
    raw_request: Request,
    x_retell_signature: Optional[str] = Header(None, alias="x-retell-signature"),
    session: AsyncSession = Depends(get_db),
):
    """Receive Retell AI call_started / call_ended / call_analyzed webhooks and persist call logs."""
    body_bytes = await raw_request.body()
    master = await receptionist_service._resolve_master_credentials(session)
    if (master["retell_webhook_secret"] or master["retell_api_key"]) and not retell_ai_adapter.verify_webhook_signature(
        body_bytes,
        x_retell_signature,
        master["retell_webhook_secret"],
        fallback_api_key=master["retell_api_key"],
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "INVALID_RETELL_SIGNATURE", "message": "Retell webhook signature verification failed"},
        )
    try:
        payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MALFORMED_JSON", "message": "Invalid JSON payload"},
        )

    result = await receptionist_service.handle_retell_webhook(session, payload)
    return {"success": True, "data": result}


@router.post("/webhooks/telnyx/voice")
async def telnyx_inbound_voice_webhook(
    To: str = Form(default=""),
    From: str = Form(default="Unknown"),
    CallSid: str = Form(default=""),
    emergency: bool = Query(default=False),
    session: AsyncSession = Depends(get_db),
):
    """Telnyx TeXML Voice Webhook returning TeXML routing calls to Retell AI or live human transfer."""
    texml = await receptionist_service.handle_telnyx_voice_webhook(
        session=session,
        to_number=To,
        from_number=From,
        call_sid=CallSid,
        emergency_transfer=emergency,
    )
    return Response(content=texml, media_type="application/xml")


@router.post("/webhooks/telnyx/status")
async def telnyx_call_status_callback(
    CallSid: str = Form(default=""),
    CallStatus: str = Form(default="completed"),
):
    """Telnyx TeXML Voice StatusCallback acknowledgement endpoint."""
    return {"success": True, "call_sid": CallSid, "status": CallStatus}
