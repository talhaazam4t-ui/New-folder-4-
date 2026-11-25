"""SQLAlchemy Models for Phase 4 Built-In Multi-Service Upsells:
- `social_comment_rules` & `social_dm_logs` (Native IG & FB Comment-to-DM)
- `review_requests` (Smart Google Review Booster 1-5 star routing)
- `document_extractions` (WhatsApp & Upload Gemini Flash Vision OCR)
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from app.database.models.base import Base, TimestampMixin
from app.database.models.tenant import GUID
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class SocialCommentRule(Base, TimestampMixin):
    __tablename__ = "social_comment_rules"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(24), default="both", nullable=False)  # instagram | facebook | both
    keyword: Mapped[str] = mapped_column(String(120), nullable=False)  # "*" for all comments
    post_id: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    dm_template: Mapped[str] = mapped_column(Text, nullable=False)
    reply_comment_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    booking_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class SocialDmLog(Base):
    __tablename__ = "social_dm_logs"
    __table_args__ = (
        Index("idx_social_dm_logs_tenant_comment_lookup", "tenant_id", "external_comment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("social_comment_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(24), nullable=False)  # instagram | facebook
    post_id: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    external_comment_id: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    commenter_id: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    commenter_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    matched_keyword: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    dm_text: Mapped[str] = mapped_column(Text, nullable=False)
    booking_link: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="sandbox_sent", nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ReviewRequest(Base, TimestampMixin):
    __tablename__ = "review_requests"
    __table_args__ = (
        Index("idx_review_requests_tenant_phone_lookup", "tenant_id", "customer_phone"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    call_log_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("receptionist_call_logs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    customer_phone: Mapped[str] = mapped_column(String(60), nullable=False)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="sent", nullable=False
    )  # sent | rated_positive | rated_negative | feedback_submitted
    routing_target: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )  # google_business | internal_feedback
    google_review_url: Mapped[Optional[str]] = mapped_column(String(800), nullable=True)
    private_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback_token: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("omnichannel_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approval_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("approvals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_channel: Mapped[str] = mapped_column(String(40), default="whatsapp", nullable=False)
    document_type: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False)
    mime_type: Mapped[str] = mapped_column(String(80), default="image/jpeg", nullable=False)
    sender_phone: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    sender_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    media_id: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    extracted_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    raw_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(4, 2), default=0.85, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="extracted", nullable=False
    )  # extracted | pending_approval | synced_crm
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
