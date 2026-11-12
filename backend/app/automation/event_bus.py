"""Async In-Process Event Bus for Custom Python Automation.

Supports publishing domain events (e.g. `task.created`, `approval.requested`,
`whatsapp.message_received`, `payment.completed`) and registering async subscribers
without external message broker dependencies on a Free-Tier VPS.
"""

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.core.logging import logger
from pydantic import BaseModel, Field

EventHandler = Callable[["AutomationEvent"], Awaitable[None]]


class AutomationEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    tenant_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    """Lightweight async event bus with bounded event history for observability."""

    def __init__(self, max_history: int = 200):
        self._subscribers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._history: List[AutomationEvent] = []
        self._max_history = max_history

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register an async coroutine callback for a specific event type."""
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)

    async def publish(
        self,
        event_type: str,
        tenant_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> AutomationEvent:
        """Publish an event to all registered subscribers and record in bounded history."""
        event = AutomationEvent(
            event_type=event_type,
            tenant_id=tenant_id,
            payload=payload or {},
        )
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        handlers = list(self._subscribers.get(event_type, [])) + list(self._subscribers.get("*", []))
        for handler in handlers:
            try:
                await handler(event)
            except Exception as exc:
                logger.error(
                    "EventBus subscriber error",
                    event_type=event_type,
                    tenant_id=tenant_id,
                    error=str(exc),
                )

        return event

    def get_recent_events(self, tenant_id: Optional[str] = None, limit: int = 50) -> List[AutomationEvent]:
        """Return recent published events, optionally filtered by tenant_id."""
        events = self._history
        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]
        return list(reversed(events[-limit:]))


event_bus = EventBus()
