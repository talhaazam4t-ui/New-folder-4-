"""Bounded Task Executor for Custom Python Automation Runtime.

Enforces:
1. Pre-execution Budget & Circuit Breaker check (`budget_manager.check_execution_eligibility`).
2. Mandatory Human-in-the-Loop Approval interception (`approval_manager.is_sensitive_action`).
3. Exponential backoff retries (`execute_with_retry`) and Dead-Letter Queue recording.
4. Full execution telemetry (`AgentExecution` and `UsageRecord`).
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

from app.automation.approval_manager import approval_manager
from app.automation.budget_manager import budget_manager
from app.automation.event_bus import event_bus
from app.automation.retry import dead_letter_queue, execute_with_retry
from app.core.exceptions import ResourceNotFoundError
from app.core.logging import logger
from app.database.models.agent import AgentExecution, AgentTask
from app.database.models.automation import Approval, UsageRecord
from app.integrations.ai_providers.router import route_and_execute_ai_task
from app.schemas.approval import ApprovalCreateRequest
from app.schemas.task import TaskResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

TaskHandler = Callable[[uuid.UUID, Dict[str, Any]], Awaitable[Dict[str, Any]]]


class TaskExecutor:
    """Executes automation and agent tasks within strict permission, budget, and approval guardrails."""

    def __init__(self):
        self._custom_handlers: Dict[str, TaskHandler] = {}

    def register_handler(self, task_type: str, handler: TaskHandler) -> None:
        """Register a custom Python handler for a specific task type."""
        self._custom_handlers[task_type] = handler

    def _to_response(self, task: AgentTask) -> TaskResponse:
        return TaskResponse(
            id=task.id,
            tenant_id=task.tenant_id,
            agent_id=task.agent_id,
            task_type=task.task_type,
            input=task.input_ or {},
            output=task.output,
            status=task.status,
            priority=task.priority,
            attempts=task.attempts,
            scheduled_at=task.scheduled_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            created_at=task.created_at,
        )

    async def _has_approved_decision(self, session: AsyncSession, tenant_id: uuid.UUID, task_id: uuid.UUID) -> bool:
        """Check if a sensitive task has already received human approval."""
        res = await session.execute(
            select(Approval).where(
                Approval.tenant_id == tenant_id,
                Approval.task_id == task_id,
                Approval.status == "approved",
            )
        )
        return res.scalar_one_or_none() is not None

    async def _has_pending_approval(
        self, session: AsyncSession, tenant_id: uuid.UUID, task_id: uuid.UUID
    ) -> Optional[Approval]:
        res = await session.execute(
            select(Approval).where(
                Approval.tenant_id == tenant_id,
                Approval.task_id == task_id,
                Approval.status == "pending",
            )
        )
        return res.scalar_one_or_none()

    async def execute_task(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> TaskResponse:
        """Execute a task by ID after verifying budget, circuit state, and approval gates."""
        res = await session.execute(
            select(AgentTask).where(
                AgentTask.id == task_id,
                AgentTask.tenant_id == tenant_id,
            )
        )
        task = res.scalar_one_or_none()
        if not task:
            raise ResourceNotFoundError("AgentTask", str(task_id))

        # 1. Check Human Approval Gate for sensitive actions
        if approval_manager.is_sensitive_action(task.task_type, task.input_):
            is_approved = await self._has_approved_decision(session, tenant_id, task.id)
            if not is_approved:
                task.status = "awaiting_approval"
                await session.commit()
                existing_pending = await self._has_pending_approval(session, tenant_id, task.id)
                if not existing_pending:
                    await approval_manager.request_approval(
                        session=session,
                        tenant_id=tenant_id,
                        request=ApprovalCreateRequest(
                            task_id=task.id,
                            action_type=task.task_type,
                            proposed_action=task.input_ or {},
                            requested_by="task_executor",
                        ),
                    )
                await session.refresh(task)
                return self._to_response(task)

        # 2. Check Budget & Circuit Breaker eligibility
        estimated_tokens = int((task.input_ or {}).get("estimated_tokens", 500))
        budget_manager.check_execution_eligibility(str(tenant_id), estimated_tokens=estimated_tokens)

        # 3. Transition to running
        start_time = time.perf_counter()
        now = datetime.now(timezone.utc)
        task.status = "running"
        task.started_at = now
        await session.commit()

        async def _unit_of_work() -> Dict[str, Any]:
            payload = task.input_ or {}
            if payload.get("simulate_transient_failure") and task.attempts == 0:
                task.attempts += 1
                raise RuntimeError("Simulated transient upstream failure")

            if payload.get("simulate_permanent_failure"):
                raise RuntimeError("Simulated permanent upstream failure")

            if task.task_type in self._custom_handlers:
                return await self._custom_handlers[task.task_type](tenant_id, payload)

            prompt = str(payload.get("prompt") or f"Execute automation task: {task.task_type}")
            ai_res = await route_and_execute_ai_task(
                task_type=task.task_type,
                prompt=prompt,
                tenant_id=str(tenant_id),
            )
            return {
                "result": ai_res.content,
                "model": ai_res.model,
                "provider": "openrouter",
                "tokens_used": ai_res.total_tokens,
                "input_tokens": ai_res.tokens_prompt,
                "output_tokens": ai_res.tokens_completion,
                "estimated_cost_usd": ai_res.estimated_cost,
            }

        try:
            output_data, attempts = await execute_with_retry(_unit_of_work, max_attempts=3)
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            tokens_used = int(output_data.get("tokens_used", 150))
            input_tokens = int(output_data.get("input_tokens", 100))
            output_tokens = int(output_data.get("output_tokens", 50))
            estimated_cost = float(output_data.get("estimated_cost_usd", 0.0002))
            model_used = str(output_data.get("model", "google/gemini-flash-1.5"))
            provider_used = str(output_data.get("provider", "openrouter"))

            task.status = "completed"
            task.attempts = attempts
            task.output = output_data
            task.completed_at = datetime.now(timezone.utc)

            execution = AgentExecution(
                tenant_id=tenant_id,
                task_id=task.id,
                agent_id=task.agent_id,
                status="completed",
                tokens_used=tokens_used,
                estimated_cost=estimated_cost,
                duration_ms=duration_ms,
            )
            usage = UsageRecord(
                tenant_id=tenant_id,
                provider=provider_used,
                model=model_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=estimated_cost,
            )
            session.add(execution)
            session.add(usage)
            await session.commit()
            await session.refresh(task)

            budget_manager.record_success(
                tenant_id=str(tenant_id),
                tokens_used=tokens_used,
                estimated_cost=estimated_cost,
            )

            await event_bus.publish(
                event_type="task.completed",
                tenant_id=str(tenant_id),
                payload={"task_id": str(task.id), "task_type": task.task_type},
            )
            return self._to_response(task)

        except Exception as exc:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            error_msg = str(exc)
            task.status = "failed"
            task.attempts = max(task.attempts, 3)
            task.output = {"error": error_msg}
            task.completed_at = datetime.now(timezone.utc)

            execution = AgentExecution(
                tenant_id=tenant_id,
                task_id=task.id,
                agent_id=task.agent_id,
                status="failed",
                tokens_used=0,
                estimated_cost=0.0,
                duration_ms=duration_ms,
                error_message=error_msg[:1000],
            )
            session.add(execution)
            await session.commit()
            await session.refresh(task)

            budget_manager.record_failure(str(tenant_id), error_msg)
            dead_letter_queue.record_dead_letter(
                tenant_id=str(tenant_id),
                task_id=str(task.id),
                task_type=task.task_type,
                attempts=task.attempts,
                error_message=error_msg,
            )
            logger.error(
                "Task execution failed after retries",
                tenant_id=str(tenant_id),
                task_id=str(task.id),
                error=error_msg,
            )
            return self._to_response(task)


task_executor = TaskExecutor()
