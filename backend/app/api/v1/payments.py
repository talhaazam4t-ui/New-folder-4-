"""Payments, Invoices, and Payment Rails API Endpoints.
"""

import json
import uuid
from typing import List, Optional

from app.automation.approval_manager import approval_manager
from app.config import settings
from app.core.exceptions import ResourceNotFoundError, TaloxException
from app.core.logging import logger
from app.core.tenant_context import TenantContext
from app.database.models.automation import Approval
from app.database.models.billing import Invoice, Payment
from app.database.models.service import ServiceSubscription
from app.database.models.tenant import Profile, Tenant
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.integrations.payment.base import get_payment_provider
from app.schemas.approval import ApprovalCreateRequest
from app.schemas.payment import (
    BankTransferNotifyRequest,
    CheckoutCreateRequest,
    InvoiceResponse,
    PaymentCreateRequest,
    PaymentResponse,
    RefundRequestCreate,
    WalletSettingsUpdateRequest,
)
from app.services.billing_service import (
    COMPANY_BANK_DETAILS,
    billing_service,
    get_payment_rails_info,
)
from app.services.wallet_service import get_credit_pack, wallet_service
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


@router.get("/bank-details")
async def get_company_bank_details():
    """Retrieve official company bank details for direct transfer payments."""
    return {"success": True, "data": COMPANY_BANK_DETAILS}


@router.get("/rails")
async def get_supported_payment_rails():
    """Retrieve Lemon Squeezy global checkout rails, PKR/USD gateways, and Faysal Bank transfer details."""
    return {"success": True, "data": get_payment_rails_info()}


@router.post("/bank-transfer/notify")
async def notify_bank_transfer(
    request: BankTransferNotifyRequest,
    context=Depends(require_permission("payments.create")),
    session: AsyncSession = Depends(get_db),
):
    """Client notifies platform of completed manual bank transfer."""
    return await billing_service.record_bank_transfer_notification(
        session, context.tenant_id, request
    )


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


@router.get("/wallet")
async def get_tenant_wallet_summary(
    limit: int = 50,
    context: TenantContext = Depends(require_permission("payments.read")),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve prepaid credit wallet balance, rates, packs, trial state, and usage ledger."""
    summary = await wallet_service.get_wallet_summary(session, context.tenant_id, ledger_limit=min(max(limit, 1), 100))
    return {"success": True, "data": summary}


@router.patch("/wallet/settings")
async def update_tenant_wallet_settings(
    request: WalletSettingsUpdateRequest,
    context: TenantContext = Depends(require_permission("payments.create")),
    session: AsyncSession = Depends(get_db),
):
    """Update low-balance alert threshold or auto-pause enforcement."""
    wallet = await wallet_service.update_wallet_settings(
        session=session,
        tenant_id=context.tenant_id,
        low_balance_threshold=request.low_balance_threshold,
        auto_pause_enabled=request.auto_pause_enabled,
    )
    return {"success": True, "data": wallet, "message": "Wallet settings updated"}


@router.post("/start-trial")
async def activate_free_trial(
    context: TenantContext = Depends(require_permission("payments.create")),
    session: AsyncSession = Depends(get_db),
):
    """Start a 7-Day Free Trial / Free Audit with 100 starter prepaid credits."""
    data = await wallet_service.start_free_trial(session, context.tenant_id, context.user_id)
    return {"success": True, "data": data, "message": "7-Day Free Trial activated with 100 credits"}


@router.get("/subscription")
async def get_lemon_squeezy_subscription(
    context: TenantContext = Depends(require_permission("payments.read")),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve the active Lemon Squeezy subscription state for the tenant."""
    sub = await billing_service.get_tenant_lemon_subscription(session, context.tenant_id)
    return {"success": True, "data": sub}


@router.post("/checkout")
async def create_multi_currency_checkout(
    request: CheckoutCreateRequest,
    context: TenantContext = Depends(require_permission("payments.create")),
    session: AsyncSession = Depends(get_db),
):
    """Initiate Lemon Squeezy (Global Cards/Subscriptions), PKR (PayFast/Safepay/Faysal Bank), or Stripe checkout."""
    provider_key = request.provider.strip().lower()
    if provider_key not in ("lemonsqueezy", "payfast", "safepay", "stripe", "bank_transfer", "manual"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported checkout provider '{request.provider}'",
        )

    purpose = request.purpose.strip().lower()
    if purpose not in ("subscription", "wallet_topup"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Checkout purpose must be 'subscription' or 'wallet_topup'",
        )

    default_curr = "PKR" if provider_key in ("payfast", "safepay", "bank_transfer", "manual", "lemonsqueezy") else "USD"
    currency = (request.currency or default_curr).upper()[:3]
    amount = float(request.amount or 0.0)
    credits_grant: Optional[float] = None
    description = request.description or "TaloxTech AI Automation Subscription"
    resolved_plan = (request.plan_name or "").strip().lower() or None

    if purpose == "wallet_topup":
        pack = get_credit_pack(request.pack_id)
        if pack:
            credits_grant = float(pack["credits"])
            amount = float(pack["amount_pkr"] if currency == "PKR" else pack["amount_usd"])
            description = pack["name"]
        elif amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide a valid pack_id or positive amount for wallet top-up",
            )
        else:
            credits_grant = round(amount * (0.04 if currency == "PKR" else 10.0), 2)
    else:
        if request.invoice_id:
            inv_res = await session.execute(
                select(Invoice).where(Invoice.id == request.invoice_id, Invoice.tenant_id == context.tenant_id)
            )
            inv = inv_res.scalar_one_or_none()
            if not inv:
                raise HTTPException(status_code=404, detail="Invoice not found")
            if amount <= 0:
                amount = float(inv.total)
            currency = (request.currency or inv.currency or default_curr).upper()[:3]
            description = f"Invoice {inv.invoice_number}"
        elif amount <= 0:
            subs_res = await session.execute(
                select(ServiceSubscription).where(ServiceSubscription.tenant_id == context.tenant_id)
            )
            subs = subs_res.scalars().all()
            if not resolved_plan and subs:
                resolved_plan = (subs[0].plan_name or "starter").strip().lower()
            usd_total = sum(float(s.price or 0.0) for s in subs if s.status != "canceled") or 99.0
            amount = round(usd_total * 278.0, 2) if currency == "PKR" else round(usd_total, 2)

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Checkout amount must be greater than zero")

    prof_res = await session.execute(select(Profile.email).where(Profile.id == context.user_id))
    user_email = prof_res.scalar_one_or_none()

    provider = get_payment_provider("manual" if provider_key == "bank_transfer" else provider_key)
    intent = await provider.create_payment_intent(
        tenant_id=str(context.tenant_id),
        amount=amount,
        currency=currency,
        metadata={
            "tenant_id": str(context.tenant_id),
            "user_id": str(context.user_id),
            "email": user_email,
            "plan_name": resolved_plan or "starter",
            "variant_id": request.variant_id,
            "purpose": purpose,
            "credits": credits_grant,
            "invoice_id": str(request.invoice_id) if request.invoice_id else None,
            "subscription_id": str(request.subscription_id) if request.subscription_id else None,
            "description": description,
        },
    )

    payment = Payment(
        tenant_id=context.tenant_id,
        subscription_id=request.subscription_id,
        amount=amount,
        currency=currency,
        payment_method=provider_key,
        provider_reference=intent.reference_id,
        status="pending",
        paid_at=None,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)

    return {
        "success": True,
        "data": {
            "payment_id": str(payment.id),
            "provider": provider_key,
            "purpose": purpose,
            "plan_name": resolved_plan or "starter",
            "reference_id": intent.reference_id,
            "amount": amount,
            "currency": currency,
            "credits_to_grant": credits_grant,
            "checkout_url": intent.checkout_url,
            "checkout_fields": intent.checkout_fields,
            "instructions": intent.instructions,
            "is_mock": intent.is_mock,
            "status": payment.status,
        },
        "message": "Checkout session initialized",
    }


async def process_lemonsqueezy_webhook_request(
    request: Request,
    x_signature: Optional[str],
    x_event_name: Optional[str],
    session: AsyncSession,
) -> dict:
    """Shared handler verifying Lemon Squeezy `X-Signature` HMAC-SHA256 and updating tenant subscriptions."""
    body = await request.body()
    provider = get_payment_provider("lemonsqueezy")
    if not provider.verify_webhook_signature(body, x_signature or ""):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Lemon Squeezy X-Signature header",
        )
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed Lemon Squeezy JSON payload")

    event_name = (x_event_name or str((payload.get("meta") or {}).get("event_name") or "")).strip().lower()
    result = await billing_service.handle_lemonsqueezy_webhook_event(
        session=session,
        event_name=event_name,
        payload=payload,
    )
    return {"success": True, **result}


@router.post("/webhooks/lemonsqueezy")
async def lemonsqueezy_v1_webhook(
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    x_event_name: Optional[str] = Header(None, alias="X-Event-Name"),
    session: AsyncSession = Depends(get_db),
):
    """Versioned Lemon Squeezy webhook endpoint (`/api/v1/payments/webhooks/lemonsqueezy`)."""
    return await process_lemonsqueezy_webhook_request(request, x_signature, x_event_name, session)


@router.post("/webhooks/{provider_name}")
async def multi_gateway_payment_webhook(
    provider_name: str,
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
    x_payfast_signature: Optional[str] = Header(None, alias="X-PayFast-Signature"),
    x_sfpy_signature: Optional[str] = Header(None, alias="X-SFPY-SIGNATURE"),
    x_webhook_signature: Optional[str] = Header(None, alias="X-Webhook-Signature"),
    session: AsyncSession = Depends(get_db),
):
    """Cryptographically verified webhook endpoint for PayFast, Safepay, and Stripe."""
    normalized = provider_name.strip().lower()
    if normalized not in ("payfast", "safepay", "stripe"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Automated webhooks are not supported for provider '{provider_name}'",
        )

    body = await request.body()
    sig_by_provider = {
        "stripe": stripe_signature or x_webhook_signature or "",
        "payfast": x_payfast_signature or x_webhook_signature or "",
        "safepay": x_sfpy_signature or x_webhook_signature or "",
    }
    provider = get_payment_provider(normalized)
    if not provider.verify_webhook_signature(body, sig_by_provider[normalized]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {normalized} webhook signature",
        )

    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed webhook JSON payload")

    data_obj = (payload.get("data") or {}).get("object") or (payload.get("data") or {})
    if not isinstance(data_obj, dict):
        data_obj = {}
    metadata = data_obj.get("metadata") or payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    event_type = str(
        payload.get("type")
        or payload.get("event")
        or payload.get("status")
        or payload.get("err_code")
        or "payment.succeeded"
    ).strip().lower()
    success_events = {
        "checkout.session.completed",
        "payment_intent.succeeded",
        "invoice.paid",
        "payment.succeeded",
        "payment.completed",
        "paid",
        "completed",
        "success",
        "000",
    }
    if event_type not in success_events:
        return {"success": True, "reconciled": False, "message": f"Ignored non-terminal event '{event_type}'"}

    provider_ref = str(
        payload.get("provider_reference")
        or data_obj.get("payment_intent")
        or data_obj.get("token")
        or payload.get("BASKET_ID")
        or payload.get("basket_id")
        or payload.get("transaction_id")
        or payload.get("reference_id")
        or data_obj.get("id")
        or payload.get("id")
        or ""
    ).strip()

    tenant_id_raw = metadata.get("tenant_id") or data_obj.get("tenant_id") or payload.get("tenant_id")
    pending_payment: Optional[Payment] = None
    if provider_ref:
        p_res = await session.execute(
            select(Payment).where(Payment.provider_reference == provider_ref).limit(1)
        )
        pending_payment = p_res.scalar_one_or_none()
        if pending_payment and not tenant_id_raw:
            tenant_id_raw = str(pending_payment.tenant_id)

    if not tenant_id_raw:
        return {"success": True, "reconciled": False, "message": "Webhook verified; no matching tenant reference"}

    try:
        tenant_uuid = uuid.UUID(str(tenant_id_raw))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant_id in webhook payload")

    if not provider_ref:
        provider_ref = f"{normalized}_{uuid.uuid4().hex[:12]}"

    raw_amount = (
        metadata.get("amount")
        or payload.get("TXNAMT")
        or payload.get("amount")
        or data_obj.get("amount")
    )
    if raw_amount is not None:
        amount = float(raw_amount)
    else:
        cents = (
            data_obj.get("amount_total")
            or data_obj.get("amount_received")
            or data_obj.get("amount_paid")
            or 0
        )
        amount = float(cents) / 100.0
    if amount <= 0 and pending_payment:
        amount = float(pending_payment.amount or 0.0)

    default_curr = "PKR" if normalized in ("payfast", "safepay") else "USD"
    currency = str(
        metadata.get("currency")
        or data_obj.get("currency")
        or payload.get("CURRENCY_CODE")
        or payload.get("currency")
        or (pending_payment.currency if pending_payment else default_curr)
    ).upper()[:3]

    purpose = str(metadata.get("purpose") or payload.get("purpose") or "subscription").lower()
    raw_credits = metadata.get("credits") or payload.get("credits")
    credits_grant = float(raw_credits) if raw_credits is not None else None

    invoice_uuid: Optional[uuid.UUID] = None
    if metadata.get("invoice_id") or payload.get("invoice_id"):
        try:
            invoice_uuid = uuid.UUID(str(metadata.get("invoice_id") or payload.get("invoice_id")))
        except ValueError:
            invoice_uuid = None

    sub_uuid: Optional[uuid.UUID] = None
    if metadata.get("subscription_id") or payload.get("subscription_id"):
        try:
            sub_uuid = uuid.UUID(str(metadata.get("subscription_id") or payload.get("subscription_id")))
        except ValueError:
            sub_uuid = None

    result = await billing_service.reconcile_verified_payment(
        session=session,
        tenant_id=tenant_uuid,
        provider=normalized,
        provider_reference=provider_ref,
        amount=amount,
        currency=currency,
        purpose=purpose,
        credits_to_grant=credits_grant,
        invoice_id=invoice_uuid,
        subscription_id=sub_uuid,
    )
    return {"success": True, **result}


@router.post("/{payment_id}/refund-request", status_code=status.HTTP_201_CREATED)
async def request_payment_refund(
    payment_id: uuid.UUID,
    request: RefundRequestCreate,
    context: TenantContext = Depends(require_permission("payments.create")),
    session: AsyncSession = Depends(get_db),
):
    """Queue a Human-in-the-Loop approval request before refunding any completed payment."""
    res = await session.execute(
        select(Payment).where(Payment.id == payment_id, Payment.tenant_id == context.tenant_id)
    )
    payment = res.scalar_one_or_none()
    if not payment:
        raise ResourceNotFoundError("Payment", str(payment_id))
    if payment.status != "completed":
        raise TaloxException(
            message=f"Only completed payments can be refunded (current status: '{payment.status}').",
            code="INVALID_REFUND_STATUS",
            status_code=400,
        )

    pending_res = await session.execute(
        select(Approval).where(
            Approval.tenant_id == context.tenant_id,
            Approval.action_type == "refund_payment",
            Approval.status == "pending",
        )
    )
    for app_row in pending_res.scalars().all():
        if str((app_row.proposed_action or {}).get("payment_id")) == str(payment_id):
            raise TaloxException(
                message="A refund approval request for this payment is already pending review.",
                code="REFUND_ALREADY_PENDING",
                status_code=409,
            )

    approval = await approval_manager.request_approval(
        session=session,
        tenant_id=context.tenant_id,
        request=ApprovalCreateRequest(
            action_type="refund_payment",
            proposed_action={
                "payment_id": str(payment.id),
                "amount": float(payment.amount),
                "currency": payment.currency,
                "payment_method": payment.payment_method,
                "provider_reference": payment.provider_reference,
                "reason": request.reason.strip(),
            },
            requested_by=str(context.user_id),
            expires_in_hours=72,
        ),
    )
    return {
        "success": True,
        "data": {
            "approval": approval.model_dump(mode="json"),
            "payment_status": payment.status,
        },
        "message": "Refund queued for Human-in-the-Loop admin approval",
    }
