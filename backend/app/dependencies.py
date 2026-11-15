"""FastAPI Dependencies for Authentication, Tenant Isolation, and Permission Enforcement.
"""

import uuid
from typing import Optional

from app.config import settings
from app.core.exceptions import PermissionDeniedError, TenantIsolationError
from app.core.permissions import has_role_permission
from app.core.security import decode_access_token
from app.core.tenant_context import TenantContext
from app.database.models.tenant import Profile, Tenant, TenantMember
from app.database.supabase import get_db
from app.services.auth_service import auth_service
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

    # 1. Verify tenant workspace existence and operational status
    tenant_query = select(Tenant).where(Tenant.id == tenant_uuid)
    tenant_res = await session.execute(tenant_query)
    tenant = tenant_res.scalar_one_or_none()
    if not tenant:
        raise TenantIsolationError(f"Tenant workspace '{x_tenant_id}' does not exist")

    if tenant.status == "suspended":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TENANT_SUSPENDED",
                "message": "Tenant workspace is suspended. Please contact platform administration.",
            },
        )

    # 2. Verify active membership for authenticated user
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


def require_platform_role(*allowed_roles: str):
    """Dependency factory checking that the authenticated user possesses an allowed platform admin role."""
    target_roles = set(allowed_roles) if allowed_roles else {"super_admin"}

    async def _platform_role_checker(
        current_user: Profile = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
    ) -> Profile:
        is_sole_super = await auth_service.is_platform_super_admin(session, current_user)
        if is_sole_super:
            return current_user

        user_email = (current_user.email or "").strip().lower()
        sole_admins = {e.strip().lower() for e in settings.super_admin_emails}
        if "super_admin" in target_roles and user_email in sole_admins:
            return current_user

        raise PermissionDeniedError(
            f"Platform administrative privilege required (allowed: {', '.join(sorted(target_roles))})"
        )

    return _platform_role_checker
