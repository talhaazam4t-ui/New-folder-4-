"""Pydantic Schemas for Service Marketplace and Subscriptions.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ServiceCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    category: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None
    configuration_schema: Optional[Dict[str, Any]] = None
    active: bool = True


class ServiceResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    category: str
    description: Optional[str] = None
    configuration_schema: Dict[str, Any]
    active: bool
    created_at: datetime


class SubscriptionCreateRequest(BaseModel):
    service_id: uuid.UUID
    plan_name: str = Field(default="standard")
    billing_interval: str = Field(default="monthly", pattern=r"^(monthly|annual|one_time)$")
    price: float = Field(ge=0.0)


class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    service_id: uuid.UUID
    service_name: Optional[str] = None
    service_slug: Optional[str] = None
    plan_name: str
    status: str
    price: float
    billing_interval: str
    started_at: datetime
    expires_at: Optional[datetime] = None
