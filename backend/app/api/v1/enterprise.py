"""Phase 4 High-Ticket Enterprise & Vertical Modules API Router (`/api/v1/enterprise`)."""

from typing import Any, Dict, List, Optional

from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.services.enterprise_modules_service import enterprise_modules_service
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/enterprise", tags=["Phase 4 Enterprise & Vertical Modules"])


class ContractAuditCreateRequest(BaseModel):
    contract_title: str = Field(min_length=2, max_length=255)
    counterparty: str = Field(min_length=2, max_length=200)
    contract_text: str = Field(min_length=10, max_length=20000)
    sla_terms: Optional[Dict[str, Any]] = None
    milestone_status: str = Field(default="on_track", max_length=48)


class ZeroTouchKycRequest(BaseModel):
    company_legal_name: str = Field(min_length=2, max_length=255)
    registration_number: str = Field(min_length=2, max_length=120)
    tax_id: str = Field(min_length=2, max_length=120)
    jurisdiction: str = Field(min_length=2, max_length=120)
    contact_email: str = Field(min_length=5, max_length=255)
    requested_services: List[str] = Field(default_factory=list)


class ReputationMentionRequest(BaseModel):
    customer_name: str = Field(min_length=2, max_length=150)
    customer_phone: str = Field(min_length=5, max_length=60)
    rating: int = Field(ge=1, le=5)
    comment_text: str = Field(min_length=3, max_length=2000)


class ContentComplianceScreenRequest(BaseModel):
    copy_text: str = Field(min_length=3, max_length=5000)
    industry: str = Field(default="General", max_length=120)
    max_words: int = Field(default=130, ge=20, le=1000)


@router.get("/financial-controller")
async def get_ai_financial_controller_forecast_and_zoho_ledger(
    context: TenantContext = Depends(require_permission("business.records.read")),
    session: AsyncSession = Depends(get_db),
):
    """Return 30/60/90-day predictive cash-flow forecast, rent MRR, and Zoho-compatible journal entries."""
    data = await enterprise_modules_service.get_predictive_cashflow_and_zoho_ledger(session, context.tenant_id)
    return {"success": True, "data": data}


@router.post("/contracts/audit", status_code=status.HTTP_201_CREATED)
async def audit_enterprise_contract_compliance(
    payload: ContractAuditCreateRequest,
    context: TenantContext = Depends(require_permission("agents.execute")),
    session: AsyncSession = Depends(get_db),
):
    """Run the Automated Contract Compliance Agent against SLAs and route breaches to HITL."""
    data = await enterprise_modules_service.audit_contract_compliance(
        session=session,
        tenant_id=context.tenant_id,
        contract_title=payload.contract_title,
        counterparty=payload.counterparty,
        contract_text=payload.contract_text,
        sla_terms=payload.sla_terms,
        milestone_status=payload.milestone_status,
        actor_id=context.user_id,
    )
    return {"success": True, "data": data}


@router.get("/contracts/audits")
async def list_enterprise_contract_audits(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    items = await enterprise_modules_service.list_contract_audits(session, context.tenant_id)
    return {"success": True, "data": items}


@router.post("/onboarding/kyc", status_code=status.HTTP_201_CREATED)
async def submit_zero_touch_client_kyc_onboarding(
    payload: ZeroTouchKycRequest,
    context: TenantContext = Depends(require_permission("integrations.manage")),
    session: AsyncSession = Depends(get_db),
):
    """Zero-Touch Client Onboarding Specialist: verify KYC and auto-provision requested services."""
    data = await enterprise_modules_service.submit_and_provision_kyc_onboarding(
        session=session,
        tenant_id=context.tenant_id,
        company_legal_name=payload.company_legal_name,
        registration_number=payload.registration_number,
        tax_id=payload.tax_id,
        jurisdiction=payload.jurisdiction,
        contact_email=payload.contact_email,
        requested_services=payload.requested_services,
        actor_id=context.user_id,
    )
    return {"success": True, "data": data, "message": "Zero-touch KYC verified and services provisioned"}


@router.post("/reputation/route")
async def route_omnichannel_reputation_mention(
    payload: ReputationMentionRequest,
    context: TenantContext = Depends(require_permission("notifications.send")),
    session: AsyncSession = Depends(get_db),
):
    """Omnichannel Reputation Manager: route 4-5★ reviews publicly and escalate 1-3★ feedback to human support."""
    data = await enterprise_modules_service.route_reputation_mention(
        session=session,
        tenant_id=context.tenant_id,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        rating=payload.rating,
        comment_text=payload.comment_text,
        actor_id=context.user_id,
    )
    return {"success": True, "data": data}


@router.post("/compliance/screen-content")
async def screen_outbound_marketing_compliance(
    payload: ContentComplianceScreenRequest,
    context: TenantContext = Depends(require_permission("marketing.content.generate")),
):
    """Content Compliance Auditor: screen outbound marketing claims for legal safety."""
    data = enterprise_modules_service.screen_marketing_compliance(
        payload.copy_text,
        industry=payload.industry,
        max_words=payload.max_words,
    )
    return {"success": True, "data": data}


@router.get("/security/audit")
async def run_continuous_tenant_security_audit(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """Continuous Security Auditor: inspect tenant API audit logs for privilege or lock anomalies."""
    data = await enterprise_modules_service.run_continuous_security_audit(session, context.tenant_id)
    return {"success": True, "data": data}
