"""Human-in-the-Loop Approval Manager (Section 10.2 & Non-Negotiable Rule #9).

Sensitive or financially consequential actions MUST NEVER execute autonomously.
They are intercepted and held in `awaiting_approval` until a human with
`approvals.review` permission explicitly approves or rejects the request.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from app.automation.event_bus import event_bus
from app.core.exceptions import ResourceNotFoundError, TaloxException
from app.core.logging import logger
from app.database.models.agent import AgentTask
from app.database.models.automation import Approval, AuditLog
from app.schemas.approval import ApprovalCreateRequest, ApprovalResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Non-negotiable list of action/task types requiring human approval (Section 10.2)
SENSITIVE_ACTION_TYPES: Set[str] = {
    "send_bulk_whatsapp",
    "publish_marketing_campaign",
    "modify_financial_record",
    "external_payment",
    "delete_records",
    "high_cost_ai_task",
    "refund_payment",
}


class ApprovalManager:
    """Manages human approval creation, verification, expiration, and resolution."""

    def is_sensitive_action(self, task_type: str, input_payload: Optional[Dict[str, Any]] = None) -> bool:
        """Determine whether a task or action requires human-in-the-loop approval."""
        if task_type in SENSITIVE_ACTION_TYPES:
            return True
        payload = input_payload or {}
        if payload.get("requires_approval") is True:
            return True
        if float(payload.get("estimated_cost_usd", 0.0)) >= 5.0:
            return True
        return False

    def _to_response(self, approval: Approval) -> ApprovalResponse:
        return ApprovalResponse(
            id=approval.id,
            tenant_id=approval.tenant_id,
            task_id=approval.task_id,
            action_type=approval.action_type,
            proposed_action=approval.proposed_action or {},
            status=approval.status,
            requested_by=approval.requested_by,
            reviewed_by=approval.reviewed_by,
            reviewed_at=approval.reviewed_at,
            expires_at=approval.expires_at,
            created_at=approval.created_at,
        )

    async def request_approval(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        request: ApprovalCreateRequest,
    ) -> ApprovalResponse:
        """Create a pending human approval request and publish an event."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=request.expires_in_hours)

        approval = Approval(
            tenant_id=tenant_id,
            task_id=request.task_id,
            action_type=request.action_type,
            proposed_action=request.proposed_action,
            status="pending",
            requested_by=request.requested_by,
            expires_at=expires_at,
        )
        session.add(approval)
        await session.flush()

        audit = AuditLog(
            tenant_id=tenant_id,
            actor_id=None,
            actor_type="system",
            action="approval.requested",
            resource_type="approval",
            resource_id=approval.id,
            metadata_={
                "action_type": request.action_type,
                "task_id": str(request.task_id) if request.task_id else None,
            },
        )
        session.add(audit)
        await session.commit()
        await session.refresh(approval)

        await event_bus.publish(
            event_type="approval.requested",
            tenant_id=str(tenant_id),
            payload={
                "approval_id": str(approval.id),
                "task_id": str(approval.task_id) if approval.task_id else None,
                "action_type": approval.action_type,
            },
        )

        logger.info(
            "Human approval requested for sensitive action",
            tenant_id=str(tenant_id),
            approval_id=str(approval.id),
            action_type=request.action_type,
        )
        return self._to_response(approval)

    async def list_approvals(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        status_filter: Optional[str] = None,
    ) -> List[ApprovalResponse]:
        """List human approval requests for a tenant."""
        query = select(Approval).where(Approval.tenant_id == tenant_id)
        if status_filter:
            query = query.where(Approval.status == status_filter)
        query = query.order_by(Approval.created_at.desc())
        res = await session.execute(query)
        return [self._to_response(a) for a in res.scalars().all()]

    async def resolve_approval(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        approval_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        approved: bool,
        reason: Optional[str] = None,
    ) -> ApprovalResponse:
        """Approve or reject a pending approval request and update linked task status."""
        query = select(Approval).where(
            Approval.id == approval_id,
            Approval.tenant_id == tenant_id,
        )
        res = await session.execute(query)
        approval = res.scalar_one_or_none()
        if not approval:
            raise ResourceNotFoundError("Approval", str(approval_id))

        if approval.status != "pending":
            raise TaloxException(
                message=f"Approval '{approval_id}' is already resolved with status '{approval.status}'",
                code="APPROVAL_ALREADY_RESOLVED",
                status_code=400,
            )

        now = datetime.now(timezone.utc)
        expires_at = approval.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if now > expires_at:
            approval.status = "expired"
            await session.commit()
            raise TaloxException(
                message="Approval request has expired",
                code="APPROVAL_EXPIRED",
                status_code=400,
            )

        approval.status = "approved" if approved else "rejected"
        approval.reviewed_by = reviewer_id
        approval.reviewed_at = now

        # If linked to an AgentTask, update its status
        if approval.task_id:
            t_res = await session.execute(
                select(AgentTask).where(
                    AgentTask.id == approval.task_id,
                    AgentTask.tenant_id == tenant_id,
                )
            )
            task = t_res.scalar_one_or_none()
            if task:
                if approved:
                    task.status = "queued"
                else:
                    task.status = "cancelled"
                    task.completed_at = now
                    task.output = {"cancelled_reason": reason or "Rejected by human reviewer"}

        audit = AuditLog(
            tenant_id=tenant_id,
            actor_id=reviewer_id,
            actor_type="user",
            action=f"approval.{approval.status}",
            resource_type="approval",
            resource_id=approval.id,
            metadata_={
                "reason": reason,
                "task_id": str(approval.task_id) if approval.task_id else None,
            },
        )
        session.add(audit)
        await session.commit()
        await session.refresh(approval)

        await event_bus.publish(
            event_type=f"approval.{approval.status}",
            tenant_id=str(tenant_id),
            payload={
                "approval_id": str(approval.id),
                "task_id": str(approval.task_id) if approval.task_id else None,
            },
        )

        return self._to_response(approval)


approval_manager = ApprovalManager()
