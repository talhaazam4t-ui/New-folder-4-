"""SQLAlchemy Model for Automated Website Audits & Playwright Scraper."""

import uuid
from typing import Optional

from app.database.models.base import Base, TimestampMixin
from app.database.models.tenant import GUID
from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class WebsiteAudit(Base, TimestampMixin):
    """Stores full website scraping, SEO metadata, performance metrics, and intercepted network calls per tenant."""

    __tablename__ = "website_audits"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    audit_scores_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    pitch_proposal_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    proof_recording_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # pending | completed | timeout | blocked | failed

    __table_args__ = (
        Index("idx_website_audits_tenant_status", "tenant_id", "status"),
        Index("idx_website_audits_target_url", "tenant_id", "target_url"),
    )
