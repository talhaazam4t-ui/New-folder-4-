"""Phase 5: Multi-Tenant White-Label Engine & Metered API-as-a-Service Router.

Exposes:
- `GET /api/v1/whitelabel/config` & `PUT /api/v1/whitelabel/config`
- `GET /api/v1/whitelabel/resolve` (Public domain/slug branding resolver)
- `POST /api/v1/whitelabel/agency/subtenants` (Agency sub-tenant provisioning)
- `POST /api/v1/developer/keys`, `GET /api/v1/developer/keys`, `DELETE /api/v1/developer/keys/{key_id}`
- `POST /api/v1/developer/v1/agents/invoke` (Metered API-as-a-Service via `X-Talox-API-Key`)
- `GET /api/v1/developer/v1/leads` (Metered CRM Leads API via `X-Talox-API-Key`)
- `GET /api/v1/developer/v1/finance/forecast` (Metered Financial Controller API via `X-Talox-API-Key`)
"""

import uuid
from typing import List, Optional

from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.services.whitelabel_and_api_service import whitelabel_and_api_service
from fastapi import APIRouter, Depends, Header, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Phase 5: White-Label Engine & Metered API-as-a-Service"])


class WhitelabelUpdateRequest(BaseModel):
    brand_name: Optional[str] = Field(default=None, max_length=255)
    logo_url: Optional[str] = Field(default=None, max_length=500)
    favicon_url: Optional[str] = Field(default=None, max_length=500)
    primary_color: Optional[str] = Field(default=None, max_length=32)
    accent_color: Optional[str] = Field(default=None, max_length=32)
    custom_domain: Optional[str] = Field(default=None, max_length=255)
    support_email: Optional[str] = Field(default=None, max_length=255)
    hide_powered_by: Optional[bool] = None
    agency_reseller_enabled: Optional[bool] = None


class AgencySubtenantCreateRequest(BaseModel):
    client_name: str = Field(..., min_length=2, max_length=200)
    client_slug: str = Field(..., min_length=2, max_length=100)
    industry: str = Field(default="general", max_length=80)
    primary_color: Optional[str] = Field(default=None, max_length=32)


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    scopes: Optional[List[str]] = None
    rate_limit_per_minute: int = Field(default=60, ge=1, le=1000)
    expires_in_days: Optional[int] = Field(default=365, ge=1, le=3650)


class MeteredAgentInvokeRequest(BaseModel):
    objective: str = Field(..., min_length=3, max_length=4000)
    task_complexity: str = Field(default="routine")
    token_budget: int = Field(default=800, ge=100, le=8000)


# ------------------------------------------------------------------------------
# 1. White-Label Branding & Agency Reseller Endpoints
# ------------------------------------------------------------------------------


@router.get("/whitelabel/config")
async def get_tenant_whitelabel_config(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    cfg = await whitelabel_and_api_service.get_or_create_whitelabel_config(session, context.tenant_id)
    return {"status": "success", "data": whitelabel_and_api_service.serialize_whitelabel(cfg)}


@router.put("/whitelabel/config")
async def update_tenant_whitelabel_config(
    payload: WhitelabelUpdateRequest,
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    data = await whitelabel_and_api_service.update_whitelabel_config(
        session=session,
        tenant_id=context.tenant_id,
        brand_name=payload.brand_name,
        logo_url=payload.logo_url,
        favicon_url=payload.favicon_url,
        primary_color=payload.primary_color,
        accent_color=payload.accent_color,
        custom_domain=payload.custom_domain,
        support_email=payload.support_email,
        hide_powered_by=payload.hide_powered_by,
        agency_reseller_enabled=payload.agency_reseller_enabled,
        actor_id=context.user_id,
    )
    return {"status": "success", "data": data}


@router.get("/whitelabel/resolve")
async def resolve_public_whitelabel_branding(
    domain: Optional[str] = Query(default=None),
    tenant_slug: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    data = await whitelabel_and_api_service.resolve_public_branding(
        session=session,
        domain=domain,
        tenant_slug=tenant_slug,
    )
    return {"status": "success", "data": data}


@router.post("/whitelabel/agency/subtenants", status_code=status.HTTP_201_CREATED)
async def create_agency_subtenant(
    payload: AgencySubtenantCreateRequest,
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    data = await whitelabel_and_api_service.provision_agency_subtenant(
        session=session,
        parent_tenant_id=context.tenant_id,
        owner_user_id=context.user_id,
        client_name=payload.client_name,
        client_slug=payload.client_slug,
        industry=payload.industry,
        primary_color=payload.primary_color,
    )
    return {"status": "success", "data": data}


# ------------------------------------------------------------------------------
# 2. Scoped Developer API Key Management
# ------------------------------------------------------------------------------


@router.post("/developer/keys", status_code=status.HTTP_201_CREATED)
async def create_developer_api_key(
    payload: ApiKeyCreateRequest,
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    data = await whitelabel_and_api_service.create_api_key(
        session=session,
        tenant_id=context.tenant_id,
        name=payload.name,
        scopes=payload.scopes,
        rate_limit_per_minute=payload.rate_limit_per_minute,
        expires_in_days=payload.expires_in_days,
        actor_id=context.user_id,
    )
    return {"status": "success", "data": data}


@router.get("/developer/keys")
async def list_developer_api_keys(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    items = await whitelabel_and_api_service.list_api_keys(session, context.tenant_id)
    return {"status": "success", "data": {"items": items, "total": len(items)}}


@router.delete("/developer/keys/{key_id}")
async def revoke_developer_api_key(
    key_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    data = await whitelabel_and_api_service.revoke_api_key(
        session=session,
        tenant_id=context.tenant_id,
        key_id=key_id,
        actor_id=context.user_id,
    )
    return {"status": "success", "data": data}


# ------------------------------------------------------------------------------
# 3. Metered Public API-as-a-Service (X-Talox-API-Key)
# ------------------------------------------------------------------------------


@router.post("/developer/v1/agents/invoke")
async def invoke_metered_agent_via_api_key(
    payload: MeteredAgentInvokeRequest,
    x_talox_api_key: Optional[str] = Header(default=None, alias="X-Talox-API-Key"),
    session: AsyncSession = Depends(get_db),
):
    data = await whitelabel_and_api_service.execute_metered_agent_task(
        session=session,
        raw_api_key=x_talox_api_key or "",
        objective=payload.objective,
        task_complexity=payload.task_complexity,
        token_budget=payload.token_budget,
    )
    return {"status": "success", "data": data}


@router.get("/developer/v1/leads")
async def list_metered_leads_via_api_key(
    limit: int = Query(default=25, ge=1, le=100),
    x_talox_api_key: Optional[str] = Header(default=None, alias="X-Talox-API-Key"),
    session: AsyncSession = Depends(get_db),
):
    data = await whitelabel_and_api_service.fetch_metered_leads(
        session=session,
        raw_api_key=x_talox_api_key or "",
        limit=limit,
    )
    return {"status": "success", "data": data}


@router.get("/developer/v1/finance/forecast")
async def get_metered_financial_forecast_via_api_key(
    x_talox_api_key: Optional[str] = Header(default=None, alias="X-Talox-API-Key"),
    session: AsyncSession = Depends(get_db),
):
    data = await whitelabel_and_api_service.fetch_metered_financial_forecast(
        session=session,
        raw_api_key=x_talox_api_key or "",
    )
    return {"status": "success", "data": data}
