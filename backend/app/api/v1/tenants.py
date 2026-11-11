"""Tenant Management & Workspace API Endpoints.
"""

import uuid
from typing import List

from app.database.models.tenant import Profile
from app.database.supabase import get_db
from app.dependencies import get_current_user
from app.schemas.tenant import TenantCreateRequest, TenantPurgeRequest, TenantResponse
from app.services.tenant_service import tenant_service
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TenantResponse)
async def create_tenant(
    request: TenantCreateRequest,
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Create a new tenant workspace and assign the authenticated user as Owner."""
    return await tenant_service.create_tenant(session, current_user.id, request)


@router.get("", response_model=List[TenantResponse])
async def list_user_tenants(
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """List all tenant workspaces where the authenticated user holds an active membership."""
    return await tenant_service.get_user_tenants(session, current_user.id)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: uuid.UUID,
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Get details for a specific tenant workspace, enforcing strict membership isolation."""
    return await tenant_service.get_tenant_by_id(session, tenant_id, current_user.id)


@router.delete("/{tenant_id}", status_code=status.HTTP_200_OK)
async def purge_tenant(
    tenant_id: uuid.UUID,
    request: TenantPurgeRequest,
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Permanently delete tenant account and trigger cascading data purge (GDPR Compliance).

    Requires caller to be the Tenant Owner and confirm by providing matching tenant slug.
    """
    await tenant_service.purge_tenant_data(
        session=session,
        tenant_id=tenant_id,
        user_id=current_user.id,
        confirmation_slug=request.confirmation_slug,
    )
    return {
        "success": True,
        "message": f"Tenant '{tenant_id}' and all associated records have been permanently purged.",
    }
