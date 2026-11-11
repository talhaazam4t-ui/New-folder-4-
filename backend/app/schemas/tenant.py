"""Pydantic Schemas for Tenant Management & Cascading Account Purge.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    industry: str = Field(min_length=2, max_length=100)
    settings: Optional[Dict[str, Any]] = None


class TenantUpdateRequest(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    industry: str
    status: str
    settings: Dict[str, Any]
    created_at: datetime
    role: Optional[str] = None


class TenantMemberInviteRequest(BaseModel):
    email: str
    role: str = Field(pattern=r"^(admin|manager|staff|viewer)$")


class TenantMemberResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    status: str
    created_at: datetime
    email: Optional[str] = None
    full_name: Optional[str] = None


class TenantPurgeRequest(BaseModel):
    confirmation_slug: str = Field(description="Must match the tenant slug to confirm permanent deletion")
    reason: Optional[str] = None
