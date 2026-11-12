"""Payments, Invoices, and Payment Rails API Endpoints.
"""

import uuid
from typing import List

from app.config import settings
from app.database.supabase import get_db
from app.dependencies import get_current_tenant
from app.integrations.payment.base import get_payment_provider
from app.schemas.payment import (
    InvoiceResponse,
    PaymentCreateRequest,
    PaymentResponse,
)
from app.services.billing_service import billing_service
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/payments", tags=["Billing & Payments"])


@router.get("", response_model=List[PaymentResponse])
async def list_payments(
    context=Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve payment transaction records for the active tenant."""
    from app.database.models.billing import Payment
    from sqlalchemy import select
    query = select(Payment).where(Payment.tenant_id == context.tenant_id).order_by(Payment.created_at.desc())
    res = await session.execute(query)
    payments = res.scalars().all()
    return [
        PaymentResponse(
            id=p.id,
            tenant_id=p.tenant_id,
            subscription_id=p.subscription_id,
            amount=float(p.amount),
            currency=p.currency,
            payment_method=p.payment_method,
            provider_reference=p.provider_reference,
            status=p.status,
            paid_at=p.paid_at,
            created_at=p.created_at,
        )
        for p in payments
    ]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PaymentResponse)
async def record_payment(
    request: PaymentCreateRequest,
    context=Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """Record and reconcile a payment transaction for the tenant."""
    return await billing_service.record_payment(session, context.tenant_id, request)


@router.get("/invoices", response_model=List[InvoiceResponse])
async def list_invoices(
    context=Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve billing invoices issued for the active tenant."""
    invoices = await billing_service.get_tenant_invoices(session, context.tenant_id)
    return [
        InvoiceResponse(
            id=inv.id,
            tenant_id=inv.tenant_id,
            invoice_number=inv.invoice_number,
            subtotal=float(inv.subtotal),
            tax=float(inv.tax),
            total=float(inv.total),
            currency=inv.currency,
            status=inv.status,
            due_at=inv.due_at,
            created_at=inv.created_at,
        )
        for inv in invoices
    ]


@router.post("/invoices/{invoice_id}/pay", response_model=PaymentResponse)
async def pay_invoice(
    invoice_id: uuid.UUID,
    context=Depends(get_current_tenant),
    session: AsyncSession = Depends(get_db),
):
    """Settle an outstanding invoice for the tenant."""
    # Fetch invoice
    from app.database.models.billing import Invoice
    from sqlalchemy import select
    q = select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == context.tenant_id)
    res = await session.execute(q)
    invoice = res.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    pay_req = PaymentCreateRequest(
        amount=float(invoice.total),
        currency=invoice.currency,
        payment_method="bank_transfer",
        invoice_id=invoice.id,
    )
    return await billing_service.record_payment(session, context.tenant_id, pay_req)


@router.post("/intent")
async def create_payment_intent(
    amount: float,
    currency: str = "USD",
    context=Depends(get_current_tenant),
):
    """Generate deposit instructions or checkout intent through the configured payment provider."""
    provider = get_payment_provider(settings.payment_provider)
    result = await provider.create_payment_intent(
        tenant_id=str(context.tenant_id),
        amount=amount,
        currency=currency,
    )
    return {"success": True, "data": result.model_dump()}


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
):
    """Cryptographically verified payment gateway webhook."""
    provider = get_payment_provider(settings.payment_provider)
    body = await request.body()
    if not provider.verify_webhook_signature(body, stripe_signature or ""):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    return {"success": True, "message": "Webhook verified and processed"}
