"""External Provider Circuit Breaker Registry (Phase 1 Resilience Engine).

Protects all external API integrations against cascading failures:
- Free LLM Providers: `groq`, `gemini`, `openrouter`
- Paid LLM Fallback: `deepseek`
- Voice & Telephony: `retell`, `telnyx`

When a provider hits `max_failures` consecutive errors (HTTP 429, 5xx, timeout),
its circuit transitions to `OPEN` for `cooldown_seconds`, allowing the router to
immediately fail over to the next provider in the Free-First cascade without latency.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from app.config import settings
from app.core.logging import logger
from pydantic import BaseModel


class ProviderCircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class ProviderHealthRecord(BaseModel):
    provider: str
    tier_category: str  # free_llm | paid_llm | voice_pstn
    state: ProviderCircuitState = ProviderCircuitState.CLOSED
    consecutive_failures: int = 0
    total_calls: int = 0
    total_failures: int = 0
    last_error: Optional[str] = None
    tripped_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None


PROVIDER_SPECS: Dict[str, str] = {
    "groq": "free_llm",
    "gemini": "free_llm",
    "openrouter": "free_llm",
    "deepseek": "paid_llm",
    "retell": "voice_pstn",
    "telnyx": "voice_pstn",
}


class ProviderCircuitBreakerRegistry:
    """Manages per-provider circuit breaker state across LLM and Voice providers."""

    def __init__(self) -> None:
        self._providers: Dict[str, ProviderHealthRecord] = {
            name: ProviderHealthRecord(provider=name, tier_category=cat)
            for name, cat in PROVIDER_SPECS.items()
        }

    def get_record(self, provider: str) -> ProviderHealthRecord:
        key = provider.strip().lower()
        rec = self._providers.get(key)
        if not rec:
            rec = ProviderHealthRecord(provider=key, tier_category="external")
            self._providers[key] = rec

        if rec.state == ProviderCircuitState.OPEN and rec.tripped_at:
            elapsed = (datetime.now(timezone.utc) - rec.tripped_at).total_seconds()
            if elapsed >= settings.circuit_breaker_cooldown_seconds:
                rec.state = ProviderCircuitState.HALF_OPEN
        return rec

    def allow_request(self, provider: str) -> bool:
        """Return True if the external provider circuit is CLOSED or HALF_OPEN."""
        rec = self.get_record(provider)
        return rec.state != ProviderCircuitState.OPEN

    def record_success(self, provider: str) -> ProviderHealthRecord:
        rec = self.get_record(provider)
        rec.total_calls += 1
        rec.consecutive_failures = 0
        rec.last_error = None
        rec.last_success_at = datetime.now(timezone.utc)
        if rec.state != ProviderCircuitState.CLOSED:
            logger.info("Provider circuit recovered -> CLOSED", provider=rec.provider)
            rec.state = ProviderCircuitState.CLOSED
            rec.tripped_at = None
        return rec

    def record_failure(self, provider: str, error_detail: str) -> ProviderHealthRecord:
        rec = self.get_record(provider)
        rec.total_calls += 1
        rec.total_failures += 1
        rec.consecutive_failures += 1
        rec.last_error = str(error_detail)[:240]

        max_fail = max(1, int(settings.circuit_breaker_max_failures or 3))
        if rec.consecutive_failures >= max_fail:
            rec.state = ProviderCircuitState.OPEN
            rec.tripped_at = datetime.now(timezone.utc)
            logger.warning(
                "External provider circuit TRIPPED -> OPEN (failing over to next provider)",
                provider=rec.provider,
                consecutive_failures=rec.consecutive_failures,
                last_error=rec.last_error,
            )
        return rec

    def reset_provider(self, provider: Optional[str] = None) -> Dict[str, Any]:
        if provider:
            rec = self.get_record(provider)
            rec.state = ProviderCircuitState.CLOSED
            rec.consecutive_failures = 0
            rec.tripped_at = None
            rec.last_error = None
        else:
            for rec in self._providers.values():
                rec.state = ProviderCircuitState.CLOSED
                rec.consecutive_failures = 0
                rec.tripped_at = None
                rec.last_error = None
        return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        return {
            name: {
                "provider": rec.provider,
                "tier_category": rec.tier_category,
                "state": rec.state.value,
                "consecutive_failures": rec.consecutive_failures,
                "total_calls": rec.total_calls,
                "total_failures": rec.total_failures,
                "last_error": rec.last_error,
                "tripped_at": rec.tripped_at.isoformat() if rec.tripped_at else None,
                "last_success_at": rec.last_success_at.isoformat() if rec.last_success_at else None,
            }
            for name, rec in sorted(self._providers.items())
        }


provider_circuit_breaker = ProviderCircuitBreakerRegistry()
