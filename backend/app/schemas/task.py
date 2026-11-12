"""Pydantic Schemas for Custom Python Automation Tasks and Executions.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

TaskStatus = Literal[
    "pending",
    "queued",
    "running",
    "awaiting_approval",
    "completed",
    "failed",
    "cancelled",
]


class TaskCreateRequest(BaseModel):
    task_type: str = Field(min_length=2, max_length=100)
    input: Dict[str, Any] = Field(default_factory=dict)
    agent_id: Optional[uuid.UUID] = None
    priority: int = Field(default=5, ge=1, le=10)
    scheduled_at: Optional[datetime] = None
    execute_immediately: bool = True


class TaskResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    agent_id: Optional[uuid.UUID] = None
    task_type: str
    input: Dict[str, Any]
    output: Optional[Dict[str, Any]] = None
    status: str
    priority: int
    attempts: int
    scheduled_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class TaskExecutionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    task_id: uuid.UUID
    agent_id: Optional[uuid.UUID] = None
    status: str
    tokens_used: int
    estimated_cost: float
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime
