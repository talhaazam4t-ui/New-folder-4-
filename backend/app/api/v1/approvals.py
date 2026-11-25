"""Human-in-the-Loop Approvals API Endpoints (Section 10.2 & 13.8).

Allows authorized reviewers (`approvals.review` permission — Owner/Admin) to inspect,
approve, or reject sensitive actions queued by agents or automation services.
"""

import uuid
from typing import List, Optional

from app.automation.runtime import automation_runtime
from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.schemas.approval import (
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ApprovalResponse,
)
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/approvals", tags=["Human Approvals"])


@router.get("", response_model=List[ApprovalResponse])
async def list_tenant_approvals(
    status_filter: Optional[str] = Query(None, alias="status"),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """List pending and resolved human approval requests for the tenant."""
    return await automation_runtime.approvals.list_approvals(
        session=session,
        tenant_id=context.tenant_id,
        status_filter=status_filter,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ApprovalResponse)
async def create_approval_request(
    request: ApprovalCreateRequest,
    context: TenantContext = Depends(require_permission("agents.execute")),
    session: AsyncSession = Depends(get_db),
):
    """Explicitly create a human approval request for a sensitive action."""
    return await automation_runtime.approvals.request_approval(
        session=session,
        tenant_id=context.tenant_id,
        request=request,
    )


@router.post("/{approval_id}/approve")
async def approve_pending_action(
    approval_id: uuid.UUID,
    request: ApprovalDecisionRequest,
    context: TenantContext = Depends(require_permission("approvals.review")),
    session: AsyncSession = Depends(get_db),
):
    """Approve a pending sensitive action and automatically resume its linked task."""
    result = await automation_runtime.approve_and_resume(
        session=session,
        tenant_id=context.tenant_id,
        approval_id=approval_id,
        reviewer_id=context.user_id,
        reason=request.reason,
    )
    return {
        "success": True,
        "data": {
            "approval": result["approval"].model_dump(mode="json"),
            "task": result["task"].model_dump(mode="json") if result["task"] else None,
            "refund": result.get("refund"),
        },
        "message": "Action approved and resumed",
    }


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
async def reject_pending_action(
    approval_id: uuid.UUID,
    request: ApprovalDecisionRequest,
    context: TenantContext = Depends(require_permission("approvals.review")),
    session: AsyncSession = Depends(get_db),
):
    """Reject a pending sensitive action and cancel its linked task."""
    return await automation_runtime.approvals.resolve_approval(
        session=session,
        tenant_id=context.tenant_id,
        approval_id=approval_id,
        reviewer_id=context.user_id,
        approved=False,
        reason=request.reason,
    )
