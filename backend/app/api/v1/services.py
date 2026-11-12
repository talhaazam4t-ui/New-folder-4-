"""Service Marketplace & Subscription Endpoints.
"""

import uuid
from typing import List, Optional

from app.database.models.tenant import Profile
from app.database.supabase import get_db
from app.dependencies import get_current_tenant, get_current_user
from app.schemas.service import (
    ServiceCreateRequest,
    ServiceResponse,
    SubscriptionCreateRequest,
    SubscriptionResponse,
)
from app.services.billing_service import billing_service
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/services", tags=["Service Marketplace"])


@router.get("", response_model=List[ServiceResponse])
async def list_services(
    category: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
):
    """Browse the platform service catalog."""
    return await billing_service.list_services(session, category=category)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ServiceResponse)
async def create_service(
    request: ServiceCreateRequest,
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Register a new service into the marketplace (Platform Owner/Admin)."""
    return await billing_service.create_service(session, request)


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
