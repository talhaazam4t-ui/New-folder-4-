"""Central Custom Python Automation Runtime.

Coordinates `event_bus`, `task_dispatcher`, `task_executor`, `approval_manager`,
`budget_manager`, and `automation_scheduler` as a cohesive, zero-n8n Python automation engine.
"""

import uuid
from typing import Any, Dict, Optional

from app.automation.approval_manager import approval_manager
from app.automation.budget_manager import budget_manager
from app.automation.dispatcher import task_dispatcher
from app.automation.event_bus import event_bus
from app.automation.executor import task_executor
from app.automation.retry import dead_letter_queue
from app.automation.scheduler import automation_scheduler
from app.schemas.approval import ApprovalResponse
from app.schemas.task import TaskCreateRequest, TaskResponse
from sqlalchemy.ext.asyncio import AsyncSession


class AutomationRuntime:
    """High-level facade for the Talox Tech Stream custom Python automation engine."""

    def __init__(self):
        self.event_bus = event_bus
        self.dispatcher = task_dispatcher
        self.executor = task_executor
        self.approvals = approval_manager
        self.budgets = budget_manager
        self.scheduler = automation_scheduler
        self.dlq = dead_letter_queue

    async def submit_task(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        request: TaskCreateRequest,
    ) -> TaskResponse:
        """Submit a task through the dispatcher."""
        return await self.dispatcher.dispatch_task(session, tenant_id, request)

    async def approve_and_resume(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        approval_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Approve a pending action and immediately resume its linked task if present."""
        approval_resp: ApprovalResponse = await self.approvals.resolve_approval(
            session=session,
            tenant_id=tenant_id,
            approval_id=approval_id,
            reviewer_id=reviewer_id,
            approved=True,
            reason=reason,
        )
        task_resp: Optional[TaskResponse] = None
        if approval_resp.task_id:
            task_resp = await self.executor.execute_task(
                session=session,
                tenant_id=tenant_id,
                task_id=approval_resp.task_id,
            )
        return {
            "approval": approval_resp,
            "task": task_resp,
        }


automation_runtime = AutomationRuntime()
