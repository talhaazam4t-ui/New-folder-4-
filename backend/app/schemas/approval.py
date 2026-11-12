"""Pydantic Schemas for Human-in-the-Loop Approval Workflows.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

ApprovalStatus = Literal["pending", "approved", "rejected", "expired"]


class ApprovalCreateRequest(BaseModel):
    task_id: Optional[uuid.UUID] = None
    action_type: str = Field(min_length=2, max_length=100)
    proposed_action: Dict[str, Any]
    requested_by: str = Field(default="automation_engine", max_length=100)
    expires_in_hours: int = Field(default=24, ge=1, le=168)


class ApprovalDecisionRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    task_id: Optional[uuid.UUID] = None
    action_type: str
    proposed_action: Dict[str, Any]
    status: str
    requested_by: str
    reviewed_by: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    expires_at: datetime
    created_at: datetime
