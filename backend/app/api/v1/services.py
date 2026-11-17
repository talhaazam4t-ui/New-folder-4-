"""Service Marketplace & Subscription Endpoints.
"""

import uuid
from typing import List, Optional

from app.core.exceptions import PermissionDeniedError
from app.database.models.tenant import Profile
from app.database.supabase import get_db
from app.dependencies import get_current_tenant, get_current_user
from app.schemas.service import (
    ServiceCreateRequest,
    ServiceResponse,
    ServiceUpdateRequest,
    SubscriptionCreateRequest,
    SubscriptionResponse,
)
from app.services.auth_service import auth_service
from app.services.billing_service import billing_service
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/services", tags=["Service Marketplace"])


@router.get("/industries")
async def list_supported_industries(
    session: AsyncSession = Depends(get_db),
):
    """Return the 4 core industry verticals and their dynamically configured service offerings."""
    await billing_service.ensure_default_catalog(session)
    all_services = await billing_service.list_services(session, active_only=True)
    industries = [
        "Financing",
        "Clinics / Hospitals",
        "Real Estate / Property",
        "E-Commerce",
    ]
    catalog_by_industry = {}
    for ind in industries:
        ind_services = []
        for srv in all_services:
            schema = srv.configuration_schema or {}
            supported = schema.get("industries", [])
            if not supported or ind in supported:
                profile = (schema.get("industry_profiles") or {}).get(ind, {})
                ind_services.append({
                    "id": str(srv.id),
                    "name": srv.name,
                    "slug": srv.slug,
                    "category": srv.category,
                    "description": srv.description,
                    "headline": profile.get("headline", srv.description),
                    "base_price": schema.get("base_price", 99.0),
                    "packages": schema.get("packages", []),
                    "features": schema.get("features", []),
                    "limitations": schema.get("limitations", ""),
                    "required_integrations": profile.get(
                        "required_integrations",
                        schema.get("required_integrations", ["whatsapp"]),
                    ),
                    "onboarding_requirements": schema.get("onboarding_requirements", []),
                })
        catalog_by_industry[ind] = ind_services

    return {
        "success": True,
        "industries": industries,
        "catalog": catalog_by_industry,
    }


@router.get("", response_model=List[ServiceResponse])
async def list_services(
    category: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    ensure_seeded: bool = Query(False),
    active_only: bool = Query(True),
    session: AsyncSession = Depends(get_db),
):
    """Browse the platform service catalog, optionally filtered by industry or category."""
    return await billing_service.list_services(
        session,
        category=category,
        industry=industry,
        active_only=active_only,
        ensure_seeded=ensure_seeded,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ServiceResponse)
async def create_service(
    request: ServiceCreateRequest,
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Register a new service into the marketplace (Platform Owner/Super Admin only)."""
    if not await auth_service.is_platform_super_admin(session, current_user):
        raise PermissionDeniedError("Platform Super Admin access required to modify the service catalog")
    return await billing_service.create_service(session, request)


@router.patch("/{service_id}", response_model=ServiceResponse)
async def update_service(
    service_id: uuid.UUID,
    request: ServiceUpdateRequest,
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Modify service pricing, packages, features, or availability (Platform Owner/Super Admin only)."""
    if not await auth_service.is_platform_super_admin(session, current_user):
        raise PermissionDeniedError("Platform Super Admin access required to modify the service catalog")
    return await billing_service.update_service(session, service_id, request)


@router.get("/subscriptions", response_model=List[SubscriptionResponse])
async def list_subscriptions(
    context=Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """List active and historical subscriptions for the authenticated tenant."""
    return await billing_service.get_tenant_subscriptions(session, context.tenant_id)


@router.post("/subscribe", status_code=status.HTTP_201_CREATED, response_model=SubscriptionResponse)
async def subscribe_service(
    request: SubscriptionCreateRequest,
    context=Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """Subscribe current tenant to a service and generate billing invoice."""
    return await billing_service.subscribe_service(session, context.tenant_id, request)


@router.post("/subscriptions/{subscription_id}/cancel")
async def cancel_subscription(
    subscription_id: uuid.UUID,
    context=Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """Cancel a tenant service subscription."""
    await billing_service.cancel_subscription(session, context.tenant_id, subscription_id)
    return {"success": True, "message": "Subscription canceled successfully"}
