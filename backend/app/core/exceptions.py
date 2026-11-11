"""Custom Application Exceptions & Standardized Error Representations.
"""

from typing import Any, Optional


class TaloxException(Exception):
    """Base exception for all domain errors within Talox Tech Stream."""
    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = 500,
        details: Optional[Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class TenantIsolationError(TaloxException):
    """Raised when an operation attempts to breach tenant boundaries."""
    def __init__(self, message: str = "Access denied: cross-tenant operation prohibited"):
        super().__init__(
            message=message,
            code="TENANT_ISOLATION_VIOLATION",
            status_code=403
        )


class PermissionDeniedError(TaloxException):
    """Raised when an actor or agent lacks the required explicit permission."""
    def __init__(self, message: str = "Operation not permitted by policy"):
        super().__init__(
            message=message,
            code="PERMISSION_DENIED",
            status_code=403
        )


class BudgetExceededError(TaloxException):
    """Raised when a tenant or agent exceeds its token or financial quota."""
    def __init__(self, message: str = "Execution budget limit exceeded"):
        super().__init__(
            message=message,
            code="BUDGET_EXCEEDED",
            status_code=429
        )


class CircuitBreakerTrippedError(TaloxException):
    """Raised when the circuit breaker is OPEN due to repeated consecutive failures."""
    def __init__(self, message: str = "Circuit breaker OPEN: agent temporarily suspended to prevent runaway costs"):
        super().__init__(
            message=message,
            code="CIRCUIT_BREAKER_OPEN",
            status_code=503
        )


class ApprovalRequiredError(TaloxException):
    """Raised when an action requires explicit human approval before execution."""
    def __init__(self, message: str = "Human approval required before executing this sensitive action"):
        super().__init__(
            message=message,
            code="APPROVAL_REQUIRED",
            status_code=400
        )


class ResourceNotFoundError(TaloxException):
    """Raised when a requested resource does not exist within the tenant scope."""
    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"{resource_type} with ID '{resource_id}' not found",
            code="RESOURCE_NOT_FOUND",
            status_code=404
        )
