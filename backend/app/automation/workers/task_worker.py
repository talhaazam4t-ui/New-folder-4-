"""Background Task Worker & Stale Approval Expiration Worker (Section 12).

Processes queued `AgentTask` records and expires stale pending `Approval` requests
that have exceeded `expires_at`.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from app.automation.executor import task_executor
from app.core.logging import logger
from app.database.models.agent import AgentTask
from app.database.models.automation import Approval
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class BackgroundTaskWorker:
    """Custom Python background worker for processing queued tasks and expiring stale approvals."""

    async def process_pending_queue(
        self,
        session: AsyncSession,
        batch_size: int = 10,
    ) -> Dict[str, Any]:
        """Poll `pending` or `queued` tasks due for execution and run them via `task_executor`."""
        now = datetime.now(timezone.utc)
        res = await session.execute(
            select(AgentTask)
            .where(
                AgentTask.status.in_(["pending", "queued"]),
                AgentTask.scheduled_at <= now,
            )
            .order_by(AgentTask.priority.desc(), AgentTask.scheduled_at.asc())
            .limit(batch_size)
        )
        tasks = res.scalars().all()
        processed = 0
        for task in tasks:
            await task_executor.execute_task(session, task.tenant_id, task.id)
            processed += 1

        return {"processed_tasks": processed}

    async def expire_stale_approvals(self, session: AsyncSession) -> int:
        """Transition pending approvals past `expires_at` to `expired` and cancel linked tasks."""
        now = datetime.now(timezone.utc)
        res = await session.execute(
            select(Approval).where(
                Approval.status == "pending",
                Approval.expires_at < now,
            )
        )
        expired_rows = res.scalars().all()
        count = 0
        for app_row in expired_rows:
            app_row.status = "expired"
            count += 1
            if app_row.task_id:
                t_res = await session.execute(
                    select(AgentTask).where(AgentTask.id == app_row.task_id)
                )
                task = t_res.scalar_one_or_none()
                if task and task.status == "awaiting_approval":
                    task.status = "cancelled"
                    task.completed_at = now
                    task.output = {"cancelled_reason": "Approval request expired"}

        if count > 0:
            await session.commit()
            logger.info("Expired stale pending approvals", expired_count=count)
        return count


background_task_worker = BackgroundTaskWorker()
