"""Task Dispatcher for Custom Python Automation Runtime.

Creates, queues, lists, and dispatches tenant tasks to `TaskExecutor`.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from app.automation.approval_manager import approval_manager
from app.automation.event_bus import event_bus
from app.automation.executor import task_executor
from app.core.exceptions import ResourceNotFoundError
from app.database.models.agent import AgentTask
from app.schemas.approval import ApprovalCreateRequest
from app.schemas.task import TaskCreateRequest, TaskResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TaskDispatcher:
    """Routes incoming automation tasks (`manual`, `scheduled`, `event`, `webhook`, `agent`)."""

    async def dispatch_task(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        request: TaskCreateRequest,
    ) -> TaskResponse:
        """Create a task record, check approval requirements, and optionally execute immediately."""
        now = datetime.now(timezone.utc)
        needs_approval = approval_manager.is_sensitive_action(request.task_type, request.input)

        initial_status = "awaiting_approval" if needs_approval else ("queued" if request.execute_immediately else "pending")

        task = AgentTask(
            tenant_id=tenant_id,
            agent_id=request.agent_id,
            task_type=request.task_type,
            input_=request.input,
            status=initial_status,
            priority=request.priority,
            attempts=0,
            scheduled_at=request.scheduled_at or now,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)

        await event_bus.publish(
            event_type="task.created",
            tenant_id=str(tenant_id),
            payload={"task_id": str(task.id), "task_type": task.task_type, "status": task.status},
        )

        if needs_approval:
            await approval_manager.request_approval(
                session=session,
                tenant_id=tenant_id,
                request=ApprovalCreateRequest(
                    task_id=task.id,
                    action_type=task.task_type,
                    proposed_action=request.input,
                    requested_by="task_dispatcher",
                ),
            )
            return task_executor._to_response(task)

        if request.execute_immediately:
            return await task_executor.execute_task(session, tenant_id, task.id)

        return task_executor._to_response(task)

    async def list_tasks(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        status_filter: Optional[str] = None,
        limit: int = 100,
    ) -> List[TaskResponse]:
        """List tasks scoped strictly to the authenticated tenant."""
        query = select(AgentTask).where(AgentTask.tenant_id == tenant_id)
        if status_filter:
            query = query.where(AgentTask.status == status_filter)
        query = query.order_by(AgentTask.created_at.desc()).limit(limit)
        res = await session.execute(query)
        return [task_executor._to_response(t) for t in res.scalars().all()]

    async def get_task(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> TaskResponse:
        """Retrieve a single task scoped to the tenant."""
        res = await session.execute(
            select(AgentTask).where(
                AgentTask.id == task_id,
                AgentTask.tenant_id == tenant_id,
            )
        )
        task = res.scalar_one_or_none()
        if not task:
            raise ResourceNotFoundError("AgentTask", str(task_id))
        return task_executor._to_response(task)


task_dispatcher = TaskDispatcher()
