"""SQLAlchemy ORM Models for TALOX International Lead Hunting, Demo, Follow-up & Control Panel."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from app.database.models.base import Base, TimestampMixin
from app.database.models.tenant import GUID
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class HunterLead(Base, TimestampMixin):
    __tablename__ = "hunter_leads"
    __table_args__ = (
        Index("idx_hunter_leads_tenant_score_orm", "tenant_id", "interest_score"),
        Index("idx_hunter_leads_tenant_stage_orm", "tenant_id", "pipeline_stage"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    google_place_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    owner_title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    favicon_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    services: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    working_hours: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pricing_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0.0, nullable=False)
    total_reviews: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    has_ai: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    pain_points: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    interest_score: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    lead_source: Mapped[str] = mapped_column(String(32), default="google_places", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    pipeline_stage: Mapped[str] = mapped_column(String(48), default="new_lead", nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), default="America/New_York", nullable=False)
    deal_value_usd: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0, nullable=False)
    human_needed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    do_not_disturb: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_contact_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_followup_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    call_result: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class HunterDemo(Base, TimestampMixin):
    __tablename__ = "hunter_demos"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("hunter_leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email_subject: Mapped[str] = mapped_column(String(300), nullable=False)
    email_copy: Mapped[str] = mapped_column(Text, nullable=False)
    whatsapp_copy: Mapped[str] = mapped_column(Text, nullable=False)
    voice_script: Mapped[str] = mapped_column(Text, nullable=False)
    chat_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    business_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_channels: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


class HunterFollowup(Base):
    __tablename__ = "hunter_followups"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("hunter_leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    demo_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("hunter_demos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    followup_number: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(String(24), default="email", nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(36), default="scheduled", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class HunterConversation(Base):
    __tablename__ = "hunter_conversations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("hunter_leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    channel: Mapped[str] = mapped_column(String(24), default="email", nullable=False)
    intent_detected: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class HunterModuleSetting(Base):
    __tablename__ = "hunter_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "module_name", name="uq_hunter_settings_tenant_module_orm"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    module_name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_on: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    budget_mode: Mapped[str] = mapped_column(String(32), default="custom", nullable=False)
    daily_limit: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    used_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    usage_date: Mapped[str] = mapped_column(
        String(16),
        default=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
