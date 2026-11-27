"""Pydantic Schemas for Website Audits & Playwright Web Scraper."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class AuditRunRequest(BaseModel):
    """Payload to trigger an automated headless website audit."""

    target_url: str = Field(
        ...,
        description="Target website URL to scrape, render, and audit (e.g. https://example.com)",
        examples=["https://example.com"],
    )
    timeout_seconds: int = Field(
        default=30,
        ge=5,
        le=90,
        description="Navigation and network interception timeout in seconds",
    )
    extract_dom: bool = Field(
        default=True,
        description="Whether to extract and analyze the complete DOM structure and tags",
    )
    monitor_network: bool = Field(
        default=True,
        description="Whether to intercept and log all network requests and API calls",
    )

    @field_validator("target_url")
    @classmethod
    def validate_and_normalize_url(cls, v: str) -> str:
        clean = (v or "").strip()
        if not clean:
            raise ValueError("target_url cannot be empty")
        if not clean.startswith(("http://", "https://")):
            clean = f"https://{clean}"
        return clean


class AuditResponse(BaseModel):
    """Full representation of a completed or in-progress website audit."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    target_url: str
    status: str
    audit_scores_json: Dict[str, Any] = Field(default_factory=dict)
    pitch_proposal_json: Dict[str, Any] = Field(default_factory=dict)
    proof_recording_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AuditListResponse(BaseModel):
    """List of website audits for a tenant."""

    success: bool = True
    data: List[AuditResponse]
    total: int
