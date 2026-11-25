"""SQLAlchemy Models for Payments, Invoices, Prepaid Credit Wallets, and Usage Ledger.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from app.database.models.base import Base, TimestampMixin
from app.database.models.tenant import GUID
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    subscription_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("service_subscriptions.id", ondelete="SET NULL"),
        nullable=True
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0.00, nullable=False)
    tax: Mapped[float] = mapped_column(Numeric(12, 2), default=0.00, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0.00, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="issued", nullable=False, index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TenantWallet(Base, TimestampMixin):
    __tablename__ = "tenant_wallets"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    balance_credits: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    reserved_credits: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    low_balance_threshold: Mapped[float] = mapped_column(Numeric(14, 2), default=25.00, nullable=False)
    auto_pause_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    low_balance_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lifetime_credited: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)
    lifetime_debited: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)


class UsageLedger(Base):
    __tablename__ = "usage_ledger"
    __table_args__ = (
        Index("uq_usage_ledger_tenant_ref", "tenant_id", "reference_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenant_wallets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_type: Mapped[str] = mapped_column(String(40), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    credits_delta: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    unit_count: Mapped[float] = mapped_column(Numeric(12, 2), default=1.00, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Numeric(12, 4), default=0.0000, nullable=False)
    reference_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), default="lemon_squeezy", nullable=False)
    provider_subscription_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    provider_customer_id: Mapped[str] = mapped_column(String(120), nullable=False)
    order_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    product_id: Mapped[str] = mapped_column(String(120), nullable=False)
    variant_id: Mapped[str] = mapped_column(String(120), nullable=False)
    product_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    variant_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tier: Mapped[str] = mapped_column(String(50), default="starter", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    card_brand: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    card_last_four: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    billing_anchor: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    renews_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    customer_portal_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    update_payment_method_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pause_resumes_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
