"""Exponential Backoff Retry Policy & Dead-Letter Logging for Custom Python Automation.
"""

from typing import Any, Awaitable, Callable, Dict, List

from app.core.exceptions import (
    ApprovalRequiredError,
    BudgetExceededError,
    CircuitBreakerTrippedError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.core.logging import logger
from tenacity import (
    AsyncRetrying,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Non-retryable exceptions that should fail fast without consuming retries
NON_RETRYABLE_EXCEPTIONS = (
    ApprovalRequiredError,
    BudgetExceededError,
    CircuitBreakerTrippedError,
    PermissionDeniedError,
    ResourceNotFoundError,
)


class DeadLetterQueue:
    """In-memory bounded Dead-Letter Queue (DLQ) for failed automation tasks after retry exhaustion."""

    def __init__(self, max_items: int = 200):
        self._entries: List[Dict[str, Any]] = []
        self._max_items = max_items

    def record_dead_letter(
        self,
        tenant_id: str,
        task_id: str,
        task_type: str,
        attempts: int,
        error_message: str,
    ) -> None:
        entry = {
            "tenant_id": tenant_id,
            "task_id": task_id,
            "task_type": task_type,
            "attempts": attempts,
            "error_message": error_message,
        }
        self._entries.append(entry)
        if len(self._entries) > self._max_items:
            self._entries.pop(0)
        logger.error(
            "Task moved to Dead-Letter Queue after exhausting retries",
            **entry,
        )

    def list_entries(self, tenant_id: str | None = None) -> List[Dict[str, Any]]:
        if tenant_id:
            return [e for e in self._entries if e["tenant_id"] == tenant_id]
        return list(self._entries)


dead_letter_queue = DeadLetterQueue()


async def execute_with_retry(
    func: Callable[[], Awaitable[Any]],
    max_attempts: int = 3,
    min_wait_seconds: float = 0.05,
    max_wait_seconds: float = 1.0,
) -> tuple[Any, int]:
    """Execute an async callable with exponential backoff retry for transient errors.

    Returns:
        Tuple of (result, attempt_count).
    """
    attempt_count = 0
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=min_wait_seconds, min=min_wait_seconds, max=max_wait_seconds),
        retry=retry_if_not_exception_type(NON_RETRYABLE_EXCEPTIONS),
        reraise=True,
    ):
        with attempt:
            attempt_count = attempt.retry_state.attempt_number
            result = await func()
            return result, attempt_count
    raise RuntimeError("Unreachable retry state")
