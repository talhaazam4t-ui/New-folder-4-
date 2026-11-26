"""FastAPI Tiered Usage Metering Dependency & Governance Audit Helper (Phase 1)."""

import uuid
from typing import Any, Dict, Optional

from app.core.tenant_context import TenantContext
from app.database.models.automation import AuditLog
from app.database.supabase import get_db
from app.dependencies import get_current_tenant
from app.services.tier_quota_service import tier_quota_service
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def enforce_tier_quota_and_meter_api(
    request: Request,
    context: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
) -> TenantContext:
    """FastAPI dependency that blocks 100% hard-locked tenants with an upgrade prompt,
    meters 1 API call against the tenant's tier quota, and logs an immutable audit entry.
    """
    await tier_quota_service.assert_not_hard_locked(session, context.tenant_id)
    await tier_quota_service.record_usage(
        session=session,
        tenant_id=context.tenant_id,
        api_calls_delta=1,
        enforce_lock_before=True,
        actor_id=context.user_id,
    )
    session.add(
        AuditLog(
            tenant_id=context.tenant_id,
            actor_id=context.user_id,
            actor_type="user",
            action=f"api.{request.method.lower()}:{request.url.path}",
            resource_type="api_request",
            metadata_={
                "method": request.method,
                "path": request.url.path,
                "role": context.role,
            },
        )
    )
    await session.commit()
    return context


async def record_immutable_audit_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    action: str,
    resource_type: str,
    actor_id: Optional[uuid.UUID] = None,
    actor_type: str = "system",
    resource_id: Optional[uuid.UUID] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Append an immutable audit log entry for an agent decision, tool execution, or data access."""
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_=dict(metadata or {}),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry
