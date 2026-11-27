"""Website Audits & Playwright Scraper API Endpoints.

Provides:
- POST /api/v1/audits/run: Trigger an automated headless website audit, intercept API calls, parse SEO, and evaluate performance.
- GET /api/v1/audits: List historical website audits for the authenticated tenant.
- GET /api/v1/audits/{audit_id}: Retrieve full audit metrics, DOM summary, intercepted network calls, and pitch proposal.
"""

import uuid
from typing import Optional

from app.config import settings
from app.core.rate_limit import limiter
from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.schemas.audit import AuditListResponse, AuditResponse, AuditRunRequest
from app.services.web_auditor_service import web_auditor_service
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/audits", tags=["Automated Web Scraping & Auditing"])


@router.post("/run", response_model=AuditResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.rate_limit_agent_rpm}/minute")
async def run_website_audit(
    request: Request,
    payload: AuditRunRequest,
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
) -> AuditResponse:
    """Run an automated Playwright headless audit on a target website, intercept API calls, and evaluate SEO/performance."""
    audit = await web_auditor_service.run_audit(
        tenant_id=context.tenant_id,
        target_url=payload.target_url,
        session=session,
        timeout_seconds=payload.timeout_seconds,
        extract_dom=payload.extract_dom,
        monitor_network=payload.monitor_network,
    )
    return AuditResponse.model_validate(audit)


@router.get("", response_model=AuditListResponse, status_code=status.HTTP_200_OK)
async def list_website_audits(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
) -> AuditListResponse:
    """List website audits for the current tenant."""
    audits = await web_auditor_service.list_audits(
        tenant_id=context.tenant_id,
        session=session,
        limit=limit,
        status_filter=status_filter,
    )
    return AuditListResponse(
        success=True,
        data=[AuditResponse.model_validate(a) for a in audits],
        total=len(audits),
    )


@router.get("/{audit_id}", response_model=AuditResponse, status_code=status.HTTP_200_OK)
async def get_website_audit_details(
    audit_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
) -> AuditResponse:
    """Retrieve full audit details by audit_id for the current tenant."""
    audit = await web_auditor_service.get_audit(
        audit_id=audit_id,
        tenant_id=context.tenant_id,
        session=session,
    )
    return AuditResponse.model_validate(audit)
