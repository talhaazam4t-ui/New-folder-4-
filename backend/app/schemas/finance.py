"""Pydantic Schemas for Business Financial & Rent Tracking.
"""

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

TransactionType = Literal["income", "expense", "rent"]
TransactionStatus = Literal["paid", "pending", "overdue"]
RentStatus = Literal["active", "vacant"]


# --- Account Schemas ---
class FinancialAccountCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100, description="e.g. Bank, Cash, NayaPay, Stripe")
    currency: str = Field(default="USD", min_length=3, max_length=10)
    current_balance: float = Field(default=0.00, description="Initial starting balance")


class FinancialAccountResponse(BaseModel):
    id: uuid.UUID
    tenant_id: str
    name: str
    currency: str
    current_balance: float
    created_at: datetime
    updated_at: datetime


# --- Transaction Schemas ---
class FinancialTransactionCreateRequest(BaseModel):
    account_id: Optional[uuid.UUID] = None
    type: TransactionType
    category: str = Field(min_length=2, max_length=100, description="e.g. Client Retainer, Property Rent, Software, Payroll, Utilities")
    amount: float = Field(gt=0, description="Amount must be positive")
    currency: str = Field(default="USD", min_length=3, max_length=10)
    status: TransactionStatus = "paid"
    transaction_date: Optional[date] = None
    due_date: Optional[date] = None
    counterparty_name: str = Field(min_length=2, max_length=255, description="Tenant / Vendor / Client")
    notes: Optional[str] = Field(default=None, max_length=1000)
    receipt_url: Optional[str] = Field(default=None, max_length=500)


class FinancialTransactionUpdateRequest(BaseModel):
    account_id: Optional[uuid.UUID] = None
    status: Optional[TransactionStatus] = None
    category: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)
    counterparty_name: Optional[str] = None
    notes: Optional[str] = None
    due_date: Optional[date] = None


class FinancialTransactionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: str
    account_id: Optional[uuid.UUID] = None
    type: str
    category: str
    amount: float
    currency: str
    status: str
    transaction_date: date
    due_date: Optional[date] = None
    counterparty_name: str
    notes: Optional[str] = None
    receipt_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# --- Rent Schedule Schemas ---
class RentScheduleCreateRequest(BaseModel):
    property_unit: str = Field(min_length=2, max_length=255, description="Unit / Property Name")
    lessee_name: str = Field(min_length=2, max_length=255, description="Tenant/Lessee Name")
    lessee_whatsapp: str = Field(min_length=5, max_length=50, description="WhatsApp Number e.g. +923238300330")
    monthly_rent: float = Field(gt=0, description="Monthly rent amount")
    currency: str = Field(default="PKR", min_length=3, max_length=10)
    billing_day: int = Field(default=1, ge=1, le=31, description="Day of month when rent is billed")
    auto_remind_whatsapp: bool = True
    status: RentStatus = "active"


class RentScheduleUpdateRequest(BaseModel):
    property_unit: Optional[str] = None
    lessee_name: Optional[str] = None
    lessee_whatsapp: Optional[str] = None
    monthly_rent: Optional[float] = Field(default=None, gt=0)
    currency: Optional[str] = None
    billing_day: Optional[int] = Field(default=None, ge=1, le=31)
    auto_remind_whatsapp: Optional[bool] = None
    status: Optional[RentStatus] = None


class RentScheduleResponse(BaseModel):
    id: uuid.UUID
    tenant_id: str
    property_unit: str
    lessee_name: str
    lessee_whatsapp: str
    monthly_rent: float
    currency: str
    billing_day: int
    auto_remind_whatsapp: bool
    status: str
    created_at: datetime
    updated_at: datetime


# --- KPI Summary & Charts ---
class MonthlyChartPoint(BaseModel):
    month: str
    income: float
    expense: float
    net: float


class FinancialSummaryResponse(BaseModel):
    total_cash_balance: float
    monthly_revenue: float
    monthly_expenses: float
    net_cash_flow: float
    accounts_receivable: float
    monthly_burn_rate: float
    pending_rent_count: int
    overdue_rent_count: int
    currency: str
    currency_balances: Dict[str, float]
    monthly_chart: List[MonthlyChartPoint]


# --- Audit Logs ---
class FinancialAuditLogResponse(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    tenant_id: str
    action: str
    diff_json: Dict[str, Any]
    timestamp: datetime


# --- WhatsApp Automation ---
class WhatsAppReminderResult(BaseModel):
    schedule_id: Optional[str] = None
    transaction_id: Optional[str] = None
    lessee_name: str
    phone: str
    amount: float
    currency: str
    status: str
    due_date: Optional[str] = None
    message_id: Optional[str] = None
    detail: str


class WhatsAppReminderSummaryResponse(BaseModel):
    total_scanned: int
    reminders_dispatched: int
    results: List[WhatsAppReminderResult]
