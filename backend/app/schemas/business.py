"""Pydantic Schemas for Business Tracking Engine and Financial Records.
"""

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

RecordType = Literal[
    "income",
    "expense",
    "rent",
    "payment_received",
    "outstanding",
    "adjustment",
]

RecordSource = Literal[
    "manual",
    "whatsapp",
    "integration",
    "agent",
]


class BusinessRecordCreateRequest(BaseModel):
    record_type: RecordType
    title: str = Field(min_length=2, max_length=255)
    amount: float = Field(gt=0, description="Transaction amount must be strictly positive")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    description: Optional[str] = Field(default=None, max_length=1000)
    source: RecordSource = "manual"
    reference_id: Optional[str] = None
    recorded_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class BusinessRecordUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=255)
    amount: Optional[float] = Field(default=None, gt=0)
    description: Optional[str] = Field(default=None, max_length=1000)
    record_type: Optional[RecordType] = None
    reason: str = Field(min_length=3, max_length=500, description="Audit reason for modifying financial record")
    actor_type: Literal["user", "agent"] = "user"


class BusinessRecordResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    record_type: str
    title: str
    amount: float
    currency: str
    description: Optional[str] = None
    source: str
    reference_id: Optional[str] = None
    recorded_by: Optional[uuid.UUID] = None
    recorded_at: datetime
    metadata: Dict[str, Any]
    created_at: datetime


class BusinessSummaryResponse(BaseModel):
    tenant_id: uuid.UUID
    total_income: float
    total_rent: float
    total_payments_received: float
    total_expenses: float
    total_outstanding: float
    total_adjustments: float
    gross_inflow: float
    net_cashflow: float
    record_count: int


class CustomMetricCreateRequest(BaseModel):
    metric_name: str = Field(min_length=2, max_length=100)
    metric_value: float
    period_start: date = Field(default_factory=date.today)
    period_end: date = Field(default_factory=date.today)
    metadata: Optional[Dict[str, Any]] = None


class CustomMetricResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    metric_name: str
    metric_value: float
    period_start: date
    period_end: date
    metadata: Dict[str, Any]
    created_at: datetime


class BusinessImportRequest(BaseModel):
    records: List[BusinessRecordCreateRequest] = Field(min_length=1, max_length=500)
