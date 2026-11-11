"""Automation Budget Manager & Circuit Breaker (Cost Protection Engine).

Protects against:
1. Runaway API spend / budget exhaustion.
2. Rapid failure loops (e.g. agent retry storms).
3. Breached tenant daily token quotas.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional

from app.config import settings
from app.core.exceptions import BudgetExceededError, CircuitBreakerTrippedError
from app.core.logging import logger
from pydantic import BaseModel


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operation: requests allowed
    OPEN = "OPEN"            # Tripped: requests blocked to protect budget
    HALF_OPEN = "HALF_OPEN"  # Testing recovery after cooldown


class TenantBudgetRecord(BaseModel):
    tenant_id: str
    daily_token_limit: int
    tokens_used_today: int = 0
    estimated_cost_today: float = 0.0
    consecutive_failures: int = 0
    circuit_state: CircuitState = CircuitState.CLOSED
    tripped_at: Optional[datetime] = None
    suspended: bool = False
    last_reset: datetime = datetime.now(timezone.utc)


class BudgetManager:
    """In-memory circuit breaker and budget tracking controller.

    In production, this state is synchronized with Supabase PostgreSQL
    or Redis, with in-memory caching for zero-latency execution checks.
    """

    def __init__(self):
        self._tenants: Dict[str, TenantBudgetRecord] = {}

    def get_or_create_record(self, tenant_id: str) -> TenantBudgetRecord:
        """Fetch or initialize tenant budget record with system defaults."""
        now = datetime.now(timezone.utc)
        record = self._tenants.get(tenant_id)
        if not record:
            record = TenantBudgetRecord(
                tenant_id=tenant_id,
                daily_token_limit=settings.default_tenant_daily_token_budget,
                last_reset=now,
            )
            self._tenants[tenant_id] = record
            return record

        # Check for 24-hour daily token reset
        if (now - record.last_reset).total_seconds() >= 86400:
            record.tokens_used_today = 0
            record.estimated_cost_today = 0.0
            record.last_reset = now

        # Check circuit breaker cooldown
        if record.circuit_state == CircuitState.OPEN and record.tripped_at:
            elapsed = (now - record.tripped_at).total_seconds()
            if elapsed >= settings.circuit_breaker_cooldown_seconds:
                logger.info(
                    "Circuit breaker cooldown elapsed, transitioning to HALF_OPEN",
                    tenant_id=tenant_id,
                    elapsed_seconds=elapsed,
                )
                record.circuit_state = CircuitState.HALF_OPEN

        return record

    def check_execution_eligibility(
        self,
        tenant_id: str,
        estimated_tokens: int = 1000
    ) -> None:
        """Pre-execution validation: validates circuit state and remaining token quota.

        Raises:
            CircuitBreakerTrippedError: If the circuit is OPEN or tenant is suspended.
            BudgetExceededError: If remaining token budget is insufficient.
        """
        record = self.get_or_create_record(tenant_id)

        if record.suspended:
            raise CircuitBreakerTrippedError(
                f"Tenant '{tenant_id}' is suspended due to automated cost-protection policy"
            )

        if record.circuit_state == CircuitState.OPEN:
            raise CircuitBreakerTrippedError(
                f"Circuit breaker is OPEN for tenant '{tenant_id}'. Consecutive failure limit reached."
            )

        if (record.tokens_used_today + estimated_tokens) > record.daily_token_limit:
            raise BudgetExceededError(
                f"Daily token quota exceeded for tenant '{tenant_id}'. "
                f"Used: {record.tokens_used_today}, Limit: {record.daily_token_limit}"
            )

    def record_success(
        self,
        tenant_id: str,
        tokens_used: int,
        estimated_cost: float
    ) -> None:
        """Record successful execution, add token usage, and reset consecutive failures."""
        record = self.get_or_create_record(tenant_id)
        record.tokens_used_today += tokens_used
        record.estimated_cost_today += estimated_cost
        record.consecutive_failures = 0

        if record.circuit_state == CircuitState.HALF_OPEN:
            logger.info("Half-open test succeeded: Closing circuit breaker", tenant_id=tenant_id)
            record.circuit_state = CircuitState.CLOSED
            record.tripped_at = None

    def record_failure(self, tenant_id: str, error_message: str) -> None:
        """Record execution failure, increment failure counter, and trip circuit if threshold reached."""
        record = self.get_or_create_record(tenant_id)
        record.consecutive_failures += 1
        now = datetime.now(timezone.utc)

        logger.warning(
            "Agent execution failed",
            tenant_id=tenant_id,
            consecutive_failures=record.consecutive_failures,
            threshold=settings.circuit_breaker_max_failures,
            error=error_message,
        )

        if record.consecutive_failures >= settings.circuit_breaker_max_failures:
            record.circuit_state = CircuitState.OPEN
            record.tripped_at = now
            logger.error(
                "CIRCUIT BREAKER TRIPPED: Suspending automated executions for tenant",
                tenant_id=tenant_id,
                consecutive_failures=record.consecutive_failures,
                cooldown_seconds=settings.circuit_breaker_cooldown_seconds,
            )

    def admin_reset_circuit(self, tenant_id: str) -> None:
        """Manual admin override to reset circuit and clear consecutive failures."""
        record = self.get_or_create_record(tenant_id)
        record.circuit_state = CircuitState.CLOSED
        record.consecutive_failures = 0
        record.tripped_at = None
        record.suspended = False
        logger.info("Admin reset circuit breaker for tenant", tenant_id=tenant_id)


# Global singleton instance
budget_manager = BudgetManager()
