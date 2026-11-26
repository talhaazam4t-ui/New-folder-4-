"""SQLAlchemy ORM Model for Phase 1 Tiered Usage & Token Metering + Audit Log Immutability Guard."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.exceptions import TaloxException
from app.database.models.automation import AuditLog
from app.database.models.base import Base, TimestampMixin
from app.database.models.tenant import GUID
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column


class TenantTierQuota(Base, TimestampMixin):
    """Per-tenant subscription tier usage counters with 80% warning & 100% hard-lock state."""

    __tablename__ = "tenant_tier_quotas"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    tier: Mapped[str] = mapped_column(String(32), default="starter", nullable=False, index=True)
    period_month: Mapped[str] = mapped_column(
        String(16),
        default=lambda: datetime.now(timezone.utc).strftime("%Y-%m"),
        nullable=False,
    )
    tokens_limit: Mapped[int] = mapped_column(Integer, default=100000, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    api_calls_limit: Mapped[int] = mapped_column(Integer, default=2500, nullable=False)
    api_calls_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    voice_minutes_limit: Mapped[float] = mapped_column(Numeric(10, 2), default=60.00, nullable=False)
    voice_minutes_used: Mapped[float] = mapped_column(Numeric(10, 2), default=0.00, nullable=False)
    alert_80_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alert_80_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    hard_locked_100: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hard_locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


@event.listens_for(AuditLog, "before_update")
def _prevent_audit_log_update(mapper, connection, target):
    """Enforce immutable append-only audit logs at the ORM level across SQLite & PostgreSQL."""
    raise TaloxException(
        message="IMMUTABLE_AUDIT_LOG: Audit logs are append-only and cannot be modified.",
        code="IMMUTABLE_AUDIT_LOG",
        status_code=403,
    )


class AgentSkill(Base, TimestampMixin):
    """Database-driven skill registry ingested dynamically by the Central Orchestrator."""

    __tablename__ = "agent_skills"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    service_slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tool_schema: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    default_model_tier: Mapped[str] = mapped_column(String(32), default="fast_free", nullable=False)
    token_budget: Mapped[int] = mapped_column(Integer, default=1500, nullable=False)
    max_words: Mapped[int] = mapped_column(Integer, default=130, nullable=False)
    requires_hitl: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TenantEpisodicMemory(Base):
    """Per-tenant persistent episodic memory queried before agent actions."""

    __tablename__ = "tenant_episodic_memories"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    memory_type: Mapped[str] = mapped_column(String(64), default="interaction", nullable=False, index=True)
    skill_slug: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    context_key: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0.00, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

