"""Pydantic Schemas for Invoices, Payments, and Billing Reconciliation.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PaymentCreateRequest(BaseModel):
    amount: float = Field(gt=0.0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    payment_method: str = Field(default="bank_transfer")
    provider_reference: Optional[str] = None
    subscription_id: Optional[uuid.UUID] = None
    invoice_id: Optional[uuid.UUID] = None


class BankTransferNotifyRequest(BaseModel):
    transaction_reference: str = Field(min_length=3, max_length=120)
    amount: Optional[float] = Field(default=None, gt=0.0)
    invoice_id: Optional[uuid.UUID] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class BankTransferApproveRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500)


class PaymentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    subscription_id: Optional[uuid.UUID] = None
    amount: float
    currency: str
    payment_method: str
    provider_reference: Optional[str] = None
    status: str
    paid_at: Optional[datetime] = None
    created_at: datetime


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    invoice_number: str
    subtotal: float
    tax: float
    total: float
    currency: str
    status: str
    due_at: datetime
    created_at: datetime
