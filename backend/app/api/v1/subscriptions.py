"""Tenant Subscriptions Management API Endpoints.
"""

import uuid
from typing import List, Optional

from app.core.exceptions import ResourceNotFoundError
from app.core.tenant_context import TenantContext
from app.database.models.service import ServiceSubscription
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.schemas.service import (
    SubscriptionCreateRequest,
    SubscriptionResponse,
)
from app.services.billing_service import billing_service
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


class SubscriptionUpdateRequest(BaseModel):
    plan_name: Optional[str] = None
    status: Optional[str] = None  # active, cancelled, paused


@router.get("", response_model=List[SubscriptionResponse])
async def list_subscriptions(
    context: TenantContext = Depends(require_permission("subscriptions.read")),
    session: AsyncSession = Depends(get_db),
):
    """List all service subscriptions for the authenticated tenant."""
    return await billing_service.get_tenant_subscriptions(session, context.tenant_id)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SubscriptionResponse)
async def create_subscription(
    request: SubscriptionCreateRequest,
    context: TenantContext = Depends(require_permission("subscriptions.update")),
    session: AsyncSession = Depends(get_db),
):
    """Subscribe the tenant to a platform service."""
    return await billing_service.subscribe_service(
        session=session,
        tenant_id=context.tenant_id,
        request=request,
    )


@router.patch("/{subscription_id}", response_model=SubscriptionResponse)
async def update_subscription(
    subscription_id: uuid.UUID,
    request: SubscriptionUpdateRequest,
    context: TenantContext = Depends(require_permission("subscriptions.update")),
    session: AsyncSession = Depends(get_db),
):
    """Upgrade, downgrade, pause, or cancel a tenant subscription."""
    res = await session.execute(
        select(ServiceSubscription).where(
            ServiceSubscription.id == subscription_id,
            ServiceSubscription.tenant_id == context.tenant_id,
        )
    )
    sub = res.scalar_one_or_none()
    if not sub:
        raise ResourceNotFoundError("ServiceSubscription", str(subscription_id))

    if request.plan_name is not None:
        sub.plan_name = request.plan_name
    if request.status is not None:
        sub.status = request.status

    await session.commit()
    await session.refresh(sub)

    return SubscriptionResponse(
        id=sub.id,
        tenant_id=sub.tenant_id,
        service_id=sub.service_id,
        plan_name=sub.plan_name,
        status=sub.status,
        billing_interval=sub.billing_interval,
        price=float(sub.price),
        started_at=sub.started_at,
        expires_at=sub.expires_at,
    )
