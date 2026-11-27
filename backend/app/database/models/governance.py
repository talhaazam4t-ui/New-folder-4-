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


class RepurposedContentBundle(Base, TimestampMixin):
    """Phase 3 Content Repurposing Agent output bundle (LinkedIn, Blog Summary, Newsletter)."""

    __tablename__ = "repurposed_content_bundles"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("marketing_campaigns.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_title: Mapped[str] = mapped_column(String(255), nullable=False)
    core_message: Mapped[str] = mapped_column(Text, nullable=False)
    linkedin_post: Mapped[str] = mapped_column(Text, nullable=False)
    blog_summary: Mapped[str] = mapped_column(Text, nullable=False)
    newsletter_draft: Mapped[str] = mapped_column(Text, nullable=False)
    qc_report: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending_hitl", nullable=False)
    approval_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("approvals.id", ondelete="SET NULL"),
        nullable=True,
    )


class FreelanceOrder(Base, TimestampMixin):
    """Phase 3 Automated Freelancing Pipeline order & HITL deliverable record."""

    __tablename__ = "freelance_orders"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_name: Mapped[str] = mapped_column(String(200), nullable=False)
    project_title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="seo_audit", nullable=False)
    budget_usd: Mapped[float] = mapped_column(Numeric(12, 2), default=250.00, nullable=False)
    requirements: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_workforce_agent: Mapped[str] = mapped_column(
        String(100), default="seo_auditor_agent", nullable=False
    )
    deliverable_draft: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qc_report: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(36), default="scanned", nullable=False, index=True)
    approval_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("approvals.id", ondelete="SET NULL"),
        nullable=True,
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ContractComplianceAudit(Base, TimestampMixin):
    """Phase 4 Automated Contract Compliance Agent SLA & milestone audit record."""

    __tablename__ = "contract_compliance_audits"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_title: Mapped[str] = mapped_column(String(255), nullable=False)
    counterparty: Mapped[str] = mapped_column(String(200), nullable=False)
    contract_text: Mapped[str] = mapped_column(Text, nullable=False)
    sla_terms: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    breach_flags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(24), default="low", nullable=False, index=True)
    milestone_status: Mapped[str] = mapped_column(String(48), default="on_track", nullable=False)
    ai_summary: Mapped[str] = mapped_column(Text, nullable=False)
    approval_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("approvals.id", ondelete="SET NULL"),
        nullable=True,
    )


class ClientKycOnboarding(Base, TimestampMixin):
    """Phase 4 Zero-Touch B2B Client KYC & Auto-Provisioning record."""

    __tablename__ = "client_kyc_onboardings"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    registration_number: Mapped[str] = mapped_column(String(120), nullable=False)
    tax_id: Mapped[str] = mapped_column(String(120), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(120), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_services: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    kyc_status: Mapped[str] = mapped_column(String(36), default="verified_provisioned", nullable=False)
    provisioned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class TenantWhitelabelConfig(Base, TimestampMixin):
    """Phase 5 Multi-Tenant White-Label branding, theme colors, custom domain, and reseller flags."""

    __tablename__ = "tenant_whitelabel_configs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    brand_name: Mapped[str] = mapped_column(String(255), default="Talox Tech Stream", nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    favicon_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(32), default="#2563EB", nullable=False)
    accent_color: Mapped[str] = mapped_column(String(32), default="#10B981", nullable=False)
    custom_domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True, index=True)
    support_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hide_powered_by: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    agency_reseller_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class TenantApiKey(Base, TimestampMixin):
    """Phase 5 Scoped Developer API Keys (SHA-256 hashed) for Metered API-as-a-Service."""

    __tablename__ = "tenant_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    scopes: Mapped[list] = mapped_column(
        JSON,
        default=lambda: ["agents:invoke", "leads:read", "finance:read", "compliance:audit"],
        nullable=False,
    )
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    total_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens_metered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)




