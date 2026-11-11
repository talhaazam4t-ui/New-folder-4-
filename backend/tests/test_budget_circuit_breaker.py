import pytest
from app.automation.budget_manager import BudgetManager, CircuitState
from app.core.exceptions import BudgetExceededError, CircuitBreakerTrippedError


def test_budget_manager_initial_eligibility():
    bm = BudgetManager()
    # Initial check should pass with 0 usage
    bm.check_execution_eligibility(tenant_id="t-1", estimated_tokens=1000)
    record = bm.get_or_create_record("t-1")
    assert record.circuit_state == CircuitState.CLOSED
    assert record.consecutive_failures == 0


def test_budget_manager_token_quota_exceeded():
    bm = BudgetManager()
    record = bm.get_or_create_record("t-quota")
    record.daily_token_limit = 5000
    record.tokens_used_today = 4500

    # Requesting 1000 tokens when only 500 left must raise BudgetExceededError
    with pytest.raises(BudgetExceededError):
        bm.check_execution_eligibility(tenant_id="t-quota", estimated_tokens=1000)


def test_circuit_breaker_tripping_on_consecutive_failures():
    bm = BudgetManager()
    tenant_id = "t-failures"

    # 1st failure
    bm.record_failure(tenant_id, "API timeout")
    assert bm.get_or_create_record(tenant_id).circuit_state == CircuitState.CLOSED

    # 2nd failure
    bm.record_failure(tenant_id, "Bad response")
    assert bm.get_or_create_record(tenant_id).circuit_state == CircuitState.CLOSED

    # 3rd consecutive failure -> trips circuit to OPEN
    bm.record_failure(tenant_id, "Gateway crash")
    assert bm.get_or_create_record(tenant_id).circuit_state == CircuitState.OPEN

    # Execution check must now throw CircuitBreakerTrippedError
    with pytest.raises(CircuitBreakerTrippedError):
        bm.check_execution_eligibility(tenant_id, estimated_tokens=100)

    # Admin reset clears the trip
    bm.admin_reset_circuit(tenant_id)
    assert bm.get_or_create_record(tenant_id).circuit_state == CircuitState.CLOSED
    bm.check_execution_eligibility(tenant_id, estimated_tokens=100)
