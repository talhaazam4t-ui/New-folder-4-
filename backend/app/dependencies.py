"""FastAPI Dependencies for Authentication, Tenant Isolation, and Permission Enforcement.
"""

import uuid
from typing import Optional

from app.core.exceptions import PermissionDeniedError, TenantIsolationError
from app.core.permissions import has_role_permission
from app.core.security import decode_access_token
from app.core.tenant_context import TenantContext
from app.database.models.tenant import Profile, TenantMember
from app.database.supabase import get_db
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

security_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    session: AsyncSession = Depends(get_db),
) -> Profile:
    """Extract and validate JWT access token; return authenticated Profile."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTHENTICATION_REQUIRED", "message": "Missing authentication token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Authentication token expired or invalid"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "MALFORMED_TOKEN", "message": "Token missing subject claim"},
        )

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_USER_ID", "message": "Subject claim is not a valid UUID"},
        )

    query = select(Profile).where(Profile.id == user_uuid)
    result = await session.execute(query)
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_NOT_FOUND", "message": "User profile not found"},
        )

    return profile


async def get_current_tenant(
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TenantContext:
    """Resolve and enforce strict tenant context.

    Validates that:
    1. X-Tenant-ID header is provided.
    2. Header contains a valid UUID.
    3. Authenticated user has an ACTIVE membership in that tenant.
    4. Prohibits any cross-tenant data access.
    """
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TENANT_HEADER_REQUIRED", "message": "X-Tenant-ID header is required for this operation"},
        )

    try:
        tenant_uuid = uuid.UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_TENANT_ID", "message": "X-Tenant-ID must be a valid UUID"},
        )

    query = select(TenantMember).where(
        TenantMember.tenant_id == tenant_uuid,
        TenantMember.user_id == current_user.id,
        TenantMember.status == "active",
    )
    result = await session.execute(query)
    membership = result.scalar_one_or_none()

    if not membership:
        raise TenantIsolationError(
            f"Access denied: User does not have authorized membership in tenant '{x_tenant_id}'"
        )

    return TenantContext(
        tenant_id=tenant_uuid,
        user_id=current_user.id,
        role=membership.role,
        status=membership.status,
        email=current_user.email,
        full_name=current_user.full_name,
    )


def require_permission(permission_name: str):
    """Dependency factory checking that the tenant member holds the required permission."""
    async def _permission_checker(
        context: TenantContext = Depends(get_current_tenant),
    ) -> TenantContext:
        if not has_role_permission(context.role, permission_name):
            raise PermissionDeniedError(
                f"Role '{context.role}' lacks required permission '{permission_name}'"
            )
        return context

    return _permission_checker
