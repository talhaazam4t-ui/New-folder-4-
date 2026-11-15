"""SQLAlchemy Models for Business Financial & Rent Tracking.
"""

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from app.database.models.base import Base, TimestampMixin
from app.database.models.tenant import GUID
from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column


class FinancialAccount(Base, TimestampMixin):
    __tablename__ = "financial_accounts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    current_balance: Mapped[float] = mapped_column(Numeric(14, 2), default=0.00, nullable=False)


class FinancialTransaction(Base, TimestampMixin):
    __tablename__ = "financial_transactions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("financial_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # income, expense, rent
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="paid", nullable=False)  # paid, pending, overdue
    transaction_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    counterparty_name: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    receipt_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class RentSchedule(Base, TimestampMixin):
    __tablename__ = "rent_schedules"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    property_unit: Mapped[str] = mapped_column(String(255), nullable=False)
    lessee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    lessee_whatsapp: Mapped[str] = mapped_column(String(50), nullable=False)
    monthly_rent: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="PKR", nullable=False)
    billing_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    auto_remind_whatsapp: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active, vacant


class FinancialAuditLog(Base):
    __tablename__ = "financial_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    diff_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
