"""Payments, Invoices, and Payment Rails API Endpoints.
"""

import json
import uuid
from typing import List, Optional

from app.config import settings
from app.core.logging import logger
from app.core.tenant_context import TenantContext
from app.database.models.billing import Invoice, Payment
from app.database.models.service import ServiceSubscription
from app.database.models.tenant import Tenant
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.integrations.payment.base import get_payment_provider
from app.schemas.payment import (
    InvoiceResponse,
    PaymentCreateRequest,
    PaymentResponse,
)
from app.services.billing_service import billing_service
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/payments", tags=["Billing & Payments"])


@router.get("", response_model=List[PaymentResponse])
async def list_payments(
    context: TenantContext = Depends(require_permission("payments.read")),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve payment transaction records for the active tenant."""
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
    context: TenantContext = Depends(require_permission("payments.create")),
    session: AsyncSession = Depends(get_db),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """Record and reconcile a payment transaction for the tenant with idempotency protection."""
    if idempotency_key and not request.provider_reference:
        request.provider_reference = idempotency_key
    return await billing_service.record_payment(session, context.tenant_id, request)


@router.get("/invoices", response_model=List[InvoiceResponse])
async def list_invoices(
    context: TenantContext = Depends(require_permission("payments.read")),
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
    context: TenantContext = Depends(require_permission("payments.create")),
    session: AsyncSession = Depends(get_db),
):
    """Settle an outstanding invoice for the tenant."""
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
    context: TenantContext = Depends(require_permission("payments.create")),
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
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
    session: AsyncSession = Depends(get_db),
):
    """Cryptographically verified payment gateway webhook with idempotent DB reconciliation."""
    if settings.payment_provider.lower() == "manual":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Automated webhooks are disabled when PAYMENT_PROVIDER is set to manual",
        )

    provider = get_payment_provider(settings.payment_provider)
    body = await request.body()
    if not provider.verify_webhook_signature(body, stripe_signature or ""):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed webhook JSON payload")

    event_type = str(payload.get("type") or payload.get("event") or "").strip()
    data_obj = (payload.get("data") or {}).get("object") or {}
    metadata = data_obj.get("metadata") or payload.get("metadata") or {}

    reconciled = False
    payment_id: Optional[str] = None

    if event_type in ("checkout.session.completed", "payment_intent.succeeded", "invoice.paid"):
        tenant_id_raw = metadata.get("tenant_id")
        if tenant_id_raw:
            try:
                tenant_uuid = uuid.UUID(str(tenant_id_raw))
            except ValueError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant_id in webhook metadata")

            tenant_res = await session.execute(select(Tenant).where(Tenant.id == tenant_uuid))
            tenant = tenant_res.scalar_one_or_none()
            if not tenant:
                logger.warning("Payment webhook tenant not found", tenant_id=str(tenant_uuid), event_type=event_type)
                return {"success": True, "reconciled": False, "message": "Webhook verified; tenant not found"}

            provider_ref = str(
                data_obj.get("payment_intent")
                or data_obj.get("id")
                or payload.get("id")
                or f"stripe_{uuid.uuid4().hex[:12]}"
            )

            existing_res = await session.execute(
                select(Payment).where(
                    Payment.tenant_id == tenant_uuid,
                    Payment.provider_reference == provider_ref,
                )
            )
            existing_payment = existing_res.scalar_one_or_none()
            if existing_payment:
                return {
                    "success": True,
                    "reconciled": False,
                    "idempotent": True,
                    "payment_id": str(existing_payment.id),
                    "message": "Webhook event already processed",
                }

            raw_amount = metadata.get("amount")
            if raw_amount is not None:
                amount = float(raw_amount)
            else:
                cents = (
                    data_obj.get("amount_total")
                    or data_obj.get("amount_received")
                    or data_obj.get("amount_paid")
                    or data_obj.get("amount")
                    or 0
                )
                amount = float(cents) / 100.0

            invoice_uuid: Optional[uuid.UUID] = None
            if metadata.get("invoice_id"):
                try:
                    invoice_uuid = uuid.UUID(str(metadata["invoice_id"]))
                except ValueError:
                    invoice_uuid = None

            sub_uuid: Optional[uuid.UUID] = None
            if metadata.get("subscription_id"):
                try:
                    sub_uuid = uuid.UUID(str(metadata["subscription_id"]))
                except ValueError:
                    sub_uuid = None

            currency = str(data_obj.get("currency") or metadata.get("currency") or "USD").upper()[:3]
            if amount > 0:
                recorded = await billing_service.record_payment(
                    session,
                    tenant_uuid,
                    PaymentCreateRequest(
                        amount=amount,
                        currency=currency,
                        payment_method=settings.payment_provider.lower(),
                        provider_reference=provider_ref,
                        subscription_id=sub_uuid,
                        invoice_id=invoice_uuid,
                    ),
                )
                payment_id = str(recorded.id)
                reconciled = True

                if sub_uuid:
                    sub_res = await session.execute(
                        select(ServiceSubscription).where(
                            ServiceSubscription.id == sub_uuid,
                            ServiceSubscription.tenant_id == tenant_uuid,
                        )
                    )
                    sub = sub_res.scalar_one_or_none()
                    if sub:
                        sub.status = "active"

                if tenant.status in ("pending_approval", "unpaid"):
                    tenant.status = "active"

                await session.commit()

    return {
        "success": True,
        "reconciled": reconciled,
        "payment_id": payment_id,
        "message": "Webhook verified and processed",
    }
