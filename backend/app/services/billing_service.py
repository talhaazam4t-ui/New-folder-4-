"""Billing, Subscription, and Payment Reconciliation Service.

Implements:
1. Service Catalog Management.
2. Tenant Subscription Provisioning & Plan Upgrades.
3. Automated Invoice Generation.
4. Payment Recording & Reconciliation.
5. Service Access Authorization (`is_service_enabled_for_tenant`).
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.core.exceptions import ResourceNotFoundError, TaloxException
from app.core.logging import logger
from app.database.models.automation import AuditLog
from app.database.models.billing import Invoice, Payment
from app.database.models.service import Service, ServiceSubscription
from app.database.models.tenant import Tenant
from app.schemas.payment import (
    BankTransferNotifyRequest,
    PaymentCreateRequest,
    PaymentResponse,
)
from app.schemas.service import (
    ServiceCreateRequest,
    ServiceUpdateRequest,
    SubscriptionCreateRequest,
    SubscriptionResponse,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

INDUSTRY_ALIASES = {
    # Core verticals
    "financing": "Financing",
    "finance": "Financing",
    "professional financial services": "Financing",
    "banking": "Financing",
    "accounting & cpa": "Financing",
    "insurance": "Financing",
    "wealth management": "Financing",
    "clinics / hospitals": "Clinics / Hospitals",
    "clinics": "Clinics / Hospitals",
    "hospitals": "Clinics / Hospitals",
    "healthcare": "Clinics / Hospitals",
    "healthcare & medical clinics": "Clinics / Hospitals",
    "dental clinics": "Clinics / Hospitals",
    "cosmetic & aesthetic surgery": "Clinics / Hospitals",
    "pharmacy & lab diagnostics": "Clinics / Hospitals",
    "physiotherapy & rehabilitation": "Clinics / Hospitals",
    "mental health & therapy": "Clinics / Hospitals",
    "veterinary clinics": "Clinics / Hospitals",
    "real estate / property": "Real Estate / Property",
    "real estate": "Real Estate / Property",
    "real estate & property management": "Real Estate / Property",
    "property": "Real Estate / Property",
    "commercial real estate": "Real Estate / Property",
    "residential property brokerage": "Real Estate / Property",
    "property management & leasing": "Real Estate / Property",
    "architecture & construction": "Real Estate / Property",
    "interior design": "Real Estate / Property",
    "e-commerce": "E-Commerce",
    "ecommerce": "E-Commerce",
    "retail": "E-Commerce",
    "retail & e-commerce": "E-Commerce",
    "fashion & apparel": "E-Commerce",
    "electronics & gadgets": "E-Commerce",
    "beauty & skincare": "E-Commerce",
    "food & beverage / d2c": "E-Commerce",
    "wholesale & distribution": "E-Commerce",
    # Additional expanded service industries
    "legal services & law firms": "Financing",
    "automotive dealerships & repair": "Real Estate / Property",
    "hospitality & hotels": "Real Estate / Property",
    "fitness & gym centers": "Clinics / Hospitals",
    "education & online academies": "Financing",
    "logistics & freight forwarding": "E-Commerce",
}

EXPANDED_INDUSTRIES = [
    # Core verticals
    "Clinics / Hospitals",
    "Financing",
    "Real Estate / Property",
    "E-Commerce",
    # Sub-specialties and extended industries
    "Dental Clinics",
    "Cosmetic & Aesthetic Surgery",
    "Pharmacy & Lab Diagnostics",
    "Physiotherapy & Rehabilitation",
    "Mental Health & Therapy",
    "Veterinary Clinics",
    "Accounting & CPA",
    "Insurance",
    "Wealth Management",
    "Legal Services & Law Firms",
    "Commercial Real Estate",
    "Residential Property Brokerage",
    "Property Management & Leasing",
    "Architecture & Construction",
    "Fashion & Apparel",
    "Electronics & Gadgets",
    "Beauty & Skincare",
    "Food & Beverage / D2C",
    "Automotive Dealerships & Repair",
    "Hospitality & Hotels",
    "Fitness & Gym Centers",
    "Education & Online Academies",
    "Logistics & Freight Forwarding",
]


COMPANY_BANK_DETAILS = {
    "bank_name": "Faysal Bank",
    "account_name": "Talha Azam",
    "account_number": "3398701000005292",
    "iban": "PK97FAYS3398701000005292",
}


def get_payment_rails_info() -> Dict[str, Any]:
    """Return client-safe local (Faysal Bank/PayFast/Safepay PKR) and international (Payoneer/Stripe USD) rails."""
    from app.services.wallet_service import CREDIT_PACKS, TRIAL_DURATION_DAYS, TRIAL_GRANT_CREDITS

    payoneer_email = (settings.payoneer_account_email or "").strip()
    payoneer_details = (settings.payoneer_receiving_details or "").strip()
    payoneer_active = bool(payoneer_email and payoneer_email.lower() != "mock")
    stripe_live = bool((settings.stripe_secret_key or "").strip().startswith("sk_"))
    payfast_live = bool((settings.payfast_merchant_id or "").strip() and (settings.payfast_secured_key or "").strip())
    safepay_live = bool((settings.safepay_api_key or "").strip())

    return {
        "bank_transfer": COMPANY_BANK_DETAILS,
        "payoneer": {
            "enabled": payoneer_active,
            "status": "active" if payoneer_active else "approval_pending",
            "account_email": payoneer_email if payoneer_active else "Pending Payoneer Approval",
            "receiving_details": (
                payoneer_details
                or (
                    f"Send international USD subscription/retainer payments via Payoneer to {payoneer_email}, then submit your Transaction Reference ID."
                    if payoneer_active
                    else "Your Payoneer USD receiving account is currently pending verification. Once approved, set PAYONEER_ACCOUNT_EMAIL & PAYONEER_RECEIVING_DETAILS in Render to display it automatically."
                )
            ),
            "currency": "USD",
        },
        "gateways": {
            "payfast": {
                "provider": "payfast",
                "name": "PayFast Pakistan (Cards / JazzCash / Easypaisa / Bank)",
                "currency": "PKR",
                "status": "live" if payfast_live else "sandbox",
                "enabled": payfast_live,
            },
            "safepay": {
                "provider": "safepay",
                "name": "Safepay Pakistan (PKR / International Cards)",
                "currency": "PKR",
                "status": "live" if safepay_live else "sandbox",
                "enabled": safepay_live,
            },
            "stripe": {
                "provider": "stripe",
                "name": "Stripe International (USD Cards / Apple Pay)",
                "currency": "USD",
                "status": "live" if stripe_live else "sandbox",
                "enabled": stripe_live,
            },
            "payoneer": {
                "provider": "payoneer",
                "name": "Payoneer Business (USD Receiving Account)",
                "currency": "USD",
                "status": "live" if payoneer_active else "approval_pending",
                "enabled": payoneer_active,
            },
            "bank_transfer": {
                "provider": "bank_transfer",
                "name": "Faysal Bank Direct Transfer (PKR)",
                "currency": "PKR",
                "status": "live",
                "enabled": True,
            },
        },
        "credit_packs": CREDIT_PACKS,
        "trial_offer": {
            "duration_days": TRIAL_DURATION_DAYS,
            "grant_credits": TRIAL_GRANT_CREDITS,
        },
    }


def normalize_industry(industry: Optional[str]) -> str:
    if not industry:
        return "Financing"
    cleaned = industry.strip()
    return INDUSTRY_ALIASES.get(cleaned.lower(), cleaned)


LEGACY_SERVICE_SLUGS = {
    "business-finance",
    "whatsapp-automation",
    "marketing-growth",
}


class BillingService:
    """Manages monetization, subscriptions, and financial invoices."""

    async def ensure_default_catalog(self, session: AsyncSession) -> None:
        """Populate and upgrade default industry-aware services in the catalog table."""
        try:
            from scripts.seed_services import DEFAULT_SERVICES
        except ImportError:
            import sys
            from pathlib import Path

            for parent_idx in (3, 2):
                candidate_root = Path(__file__).resolve().parents[parent_idx]
                if (candidate_root / "scripts" / "seed_services.py").is_file():
                    root_str = str(candidate_root)
                    if root_str not in sys.path:
                        sys.path.insert(0, root_str)
                    break
            from scripts.seed_services import DEFAULT_SERVICES

        res = await session.execute(select(Service))
        existing_by_slug = {srv.slug: srv for srv in res.scalars().all()}

        changed = False
        for item in DEFAULT_SERVICES:
            srv = existing_by_slug.get(item["slug"])
            if not srv:
                session.add(
                    Service(
                        name=item["name"],
                        slug=item["slug"],
                        category=item["category"],
                        description=item["description"],
                        configuration_schema=item["configuration_schema"],
                        active=True,
                    )
                )
                changed = True
            else:
                schema = srv.configuration_schema or {}
                needs_upgrade = any(
                    key not in schema
                    for key in ("packages", "industries", "industry_profiles")
                )
                if needs_upgrade:
                    srv.name = item["name"]
                    srv.category = item["category"]
                    srv.description = item["description"]
                    srv.configuration_schema = item["configuration_schema"]
                    changed = True

        if changed:
            await session.commit()

    async def list_services(
        self,
        session: AsyncSession,
        category: Optional[str] = None,
        industry: Optional[str] = None,
        active_only: bool = True,
        ensure_seeded: bool = False,
    ) -> List[Service]:
        """Fetch services from catalog with optional category and dynamic industry filtering."""
        if ensure_seeded:
            await self.ensure_default_catalog(session)

        query = select(Service)
        if active_only:
            query = query.where(Service.active == True)  # noqa: E712
        if category:
            query = query.where(Service.category == category)
        res = await session.execute(query.order_by(Service.name))
        services = [
            srv
            for srv in res.scalars().all()
            if not (
                srv.slug in LEGACY_SERVICE_SLUGS
                and (
                    not (srv.configuration_schema or {}).get("industries")
                    or not (srv.configuration_schema or {}).get("packages")
                )
            )
        ]

        CANONICAL_ORDER = {
            "business-financial-tracking": 1,
            "ai-marketing-growth": 2,
            "whatsapp-business-concierge": 3,
            "lead-crm-qualification": 4,
            "office-receptionist": 5,
            "multi-agent-orchestration": 6,
            "executive-analytics-compliance": 7,
        }
        services.sort(key=lambda s: (CANONICAL_ORDER.get((s.slug or "").lower(), 99), s.name))

        if industry:
            norm_ind = normalize_industry(industry)
            filtered: List[Service] = []
            for srv in services:
                schema = srv.configuration_schema or {}
                industries = schema.get("industries", [])
                if not industries or "All" in industries or norm_ind in industries or industry in industries:
                    filtered.append(srv)
            return filtered

        return services

    async def update_service(
        self,
        session: AsyncSession,
        service_id: uuid.UUID,
        request: ServiceUpdateRequest,
    ) -> Service:
        """Modify an existing service package, pricing, features, or availability (Owner only)."""
        res = await session.execute(select(Service).where(Service.id == service_id))
        service = res.scalar_one_or_none()
        if not service:
            raise ResourceNotFoundError("Service", str(service_id))

        if request.name is not None:
            service.name = request.name
        if request.category is not None:
            service.category = request.category
        if request.description is not None:
            service.description = request.description
        if request.configuration_schema is not None:
            merged = dict(service.configuration_schema or {})
            merged.update(request.configuration_schema)
            service.configuration_schema = merged
        if request.active is not None:
            service.active = request.active

        await session.commit()
        await session.refresh(service)
        logger.info("Service updated", service_id=str(service.id), slug=service.slug)
        return service

    async def create_service(
        self,
        session: AsyncSession,
        request: ServiceCreateRequest,
    ) -> Service:
        """Create a new service in the platform catalog (Admin only)."""
        check = await session.execute(select(Service).where(Service.slug == request.slug))
        if check.scalar_one_or_none():
            raise TaloxException(
                message=f"Service with handle '{request.slug}' already exists",
                code="SERVICE_SLUG_EXISTS",
                status_code=409,
            )

        service = Service(
            name=request.name,
            slug=request.slug,
            category=request.category,
            description=request.description,
            configuration_schema=request.configuration_schema or {},
            active=request.active,
        )
        session.add(service)
        await session.commit()
        await session.refresh(service)
        logger.info("Service created", slug=service.slug, service_id=str(service.id))
        return service

    async def subscribe_service(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        request: SubscriptionCreateRequest,
    ) -> SubscriptionResponse:
        """Subscribe a tenant to a service and generate an invoice."""
        # 1. Verify service exists
        s_query = select(Service).where(Service.id == request.service_id)
        s_res = await session.execute(s_query)
        service = s_res.scalar_one_or_none()
        if not service:
            raise ResourceNotFoundError("Service", str(request.service_id))

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=365 if request.billing_interval == "annual" else 30)

        # 2. Check existing subscription
        sub_query = select(ServiceSubscription).where(
            ServiceSubscription.tenant_id == tenant_id,
            ServiceSubscription.service_id == service.id,
        )
        sub_res = await session.execute(sub_query)
        subscription = sub_res.scalar_one_or_none()

        if subscription:
            # Upgrade or reactivate existing subscription
            subscription.plan_name = request.plan_name
            subscription.billing_interval = request.billing_interval
            subscription.price = request.price
            subscription.status = "active"
            subscription.started_at = now
            subscription.expires_at = expires_at
        else:
            subscription = ServiceSubscription(
                tenant_id=tenant_id,
                service_id=service.id,
                plan_name=request.plan_name,
                status="active",
                price=request.price,
                billing_interval=request.billing_interval,
                started_at=now,
                expires_at=expires_at,
            )
            session.add(subscription)

        await session.flush()

        # 3. Generate Invoice
        invoice_num = f"INV-{str(tenant_id)[:6].upper()}-{uuid.uuid4().hex[:6].upper()}"
        invoice_status = "paid" if request.price == 0 else "issued"

        invoice = Invoice(
            tenant_id=tenant_id,
            invoice_number=invoice_num,
            subtotal=request.price,
            tax=0.00,
            total=request.price,
            currency="USD",
            status=invoice_status,
            due_at=now + timedelta(days=7),
        )
        session.add(invoice)

        # 4. Audit Log
        audit = AuditLog(
            tenant_id=tenant_id,
            actor_type="user",
            action="service.subscribed",
            resource_type="service_subscription",
            resource_id=subscription.id,
            metadata_={"service": service.slug, "plan": request.plan_name, "price": request.price},
        )
        session.add(audit)
        await session.commit()
        await session.refresh(subscription)

        logger.info(
            "Service subscription activated",
            tenant_id=str(tenant_id),
            service=service.slug,
            price=request.price,
        )

        return SubscriptionResponse(
            id=subscription.id,
            tenant_id=subscription.tenant_id,
            service_id=subscription.service_id,
            service_name=service.name,
            service_slug=service.slug,
            plan_name=subscription.plan_name,
            status=subscription.status,
            price=float(subscription.price),
            billing_interval=subscription.billing_interval,
            started_at=subscription.started_at,
            expires_at=subscription.expires_at,
        )

    async def cancel_subscription(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        subscription_id: uuid.UUID,
    ) -> bool:
        """Cancel an active tenant subscription."""
        query = select(ServiceSubscription).where(
            ServiceSubscription.id == subscription_id,
            ServiceSubscription.tenant_id == tenant_id,
        )
        res = await session.execute(query)
        subscription = res.scalar_one_or_none()
        if not subscription:
            raise ResourceNotFoundError("Subscription", str(subscription_id))

        subscription.status = "canceled"
        await session.commit()
        logger.info("Subscription canceled", tenant_id=str(tenant_id), sub_id=str(subscription_id))
        return True

    async def record_payment(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        request: PaymentCreateRequest,
    ) -> PaymentResponse:
        """Record and reconcile a client payment with idempotency protection and approval workflows."""
        # 1. Idempotency Check: Return existing record if provider_reference was already recorded
        if request.provider_reference:
            existing_q = select(Payment).where(
                Payment.tenant_id == tenant_id,
                Payment.provider_reference == request.provider_reference,
            )
            existing_res = await session.execute(existing_q)
            existing_payment = existing_res.scalar_one_or_none()
            if existing_payment:
                logger.info(
                    "Idempotent payment returned without duplicate record creation",
                    tenant_id=str(tenant_id),
                    reference=request.provider_reference,
                )
                return PaymentResponse(
                    id=existing_payment.id,
                    tenant_id=existing_payment.tenant_id,
                    subscription_id=existing_payment.subscription_id,
                    amount=float(existing_payment.amount),
                    currency=existing_payment.currency,
                    payment_method=existing_payment.payment_method,
                    provider_reference=existing_payment.provider_reference,
                    status=existing_payment.status,
                    paid_at=existing_payment.paid_at,
                    created_at=existing_payment.created_at,
                )

        now = datetime.now(timezone.utc)
        # Manual payments (bank transfer) require Super Admin verification before activation
        is_manual = request.payment_method.lower() in ("bank_transfer", "manual", "offline")
        payment_status = "pending_confirmation" if is_manual else "completed"
        paid_at = None if is_manual else now

        payment = Payment(
            tenant_id=tenant_id,
            subscription_id=request.subscription_id,
            amount=request.amount,
            currency=request.currency,
            payment_method=request.payment_method,
            provider_reference=request.provider_reference or f"TXN-{uuid.uuid4().hex[:8].upper()}",
            status=payment_status,
            paid_at=paid_at,
        )
        session.add(payment)

        # If paying against an invoice, update invoice status
        if request.invoice_id:
            inv_query = select(Invoice).where(
                Invoice.id == request.invoice_id,
                Invoice.tenant_id == tenant_id,
            )
            inv_res = await session.execute(inv_query)
            invoice = inv_res.scalar_one_or_none()
            if invoice:
                invoice.status = "paid" if payment_status == "completed" else "payment_pending"

        await session.commit()
        await session.refresh(payment)

        logger.info(
            "Payment recorded",
            tenant_id=str(tenant_id),
            amount=request.amount,
            status=payment_status,
            reference=payment.provider_reference,
        )

        return PaymentResponse(
            id=payment.id,
            tenant_id=payment.tenant_id,
            subscription_id=payment.subscription_id,
            amount=float(payment.amount),
            currency=payment.currency,
            payment_method=payment.payment_method,
            provider_reference=payment.provider_reference,
            status=payment.status,
            paid_at=payment.paid_at,
            created_at=payment.created_at,
        )

    async def confirm_payment(
        self,
        session: AsyncSession,
        payment_id: uuid.UUID,
    ) -> PaymentResponse:
        """Super Admin manual confirmation of payment receipt.

        Transitions payment status to 'completed', settles linked invoices,
        and activates tenant workspace if currently pending approval.
        """
        payment_q = select(Payment).where(Payment.id == payment_id)
        payment_res = await session.execute(payment_q)
        payment = payment_res.scalar_one_or_none()
        if not payment:
            raise ResourceNotFoundError("Payment", str(payment_id))

        now = datetime.now(timezone.utc)
        payment.status = "completed"
        payment.paid_at = now

        # Activate linked subscription if present
        if payment.subscription_id:
            sub_q = select(ServiceSubscription).where(ServiceSubscription.id == payment.subscription_id)
            sub_res = await session.execute(sub_q)
            sub = sub_res.scalar_one_or_none()
            if sub:
                sub.status = "active"

        # Mark any pending invoices for this tenant as paid
        inv_q = select(Invoice).where(
            Invoice.tenant_id == payment.tenant_id,
            Invoice.status.in_(["issued", "payment_pending"]),
        )
        inv_res = await session.execute(inv_q)
        for inv in inv_res.scalars().all():
            inv.status = "paid"

        # Activate tenant workspace if pending approval / unpaid
        tenant_q = select(Tenant).where(Tenant.id == payment.tenant_id)
        tenant_res = await session.execute(tenant_q)
        tenant = tenant_res.scalar_one_or_none()
        if tenant:
            curr_settings = dict(tenant.settings or {})
            curr_settings["payment_approved"] = True
            curr_settings["automation_approved_by_owner"] = True
            curr_settings["trial_active"] = False
            curr_settings["trial_expired"] = False
            curr_settings["payment_approved_at"] = now.isoformat()
            tenant.settings = curr_settings
            if tenant.status in ("pending_approval", "unpaid"):
                tenant.status = "active"

        await session.commit()
        await session.refresh(payment)

        from app.services.wallet_service import PLAN_ACTIVATION_BONUS_CREDITS, wallet_service

        await wallet_service.credit_wallet(
            session=session,
            tenant_id=payment.tenant_id,
            credits=PLAN_ACTIVATION_BONUS_CREDITS,
            category="plan_grant",
            description="Plan activation prepaid credit grant",
            entry_type="plan_grant",
            reference_id=f"payment_confirm:{payment.id}",
        )

        logger.info(
            "Payment manually confirmed by Super Admin",
            payment_id=str(payment_id),
            tenant_id=str(payment.tenant_id),
            amount=float(payment.amount),
        )

        return PaymentResponse(
            id=payment.id,
            tenant_id=payment.tenant_id,
            subscription_id=payment.subscription_id,
            amount=float(payment.amount),
            currency=payment.currency,
            payment_method=payment.payment_method,
            provider_reference=payment.provider_reference,
            status=payment.status,
            paid_at=payment.paid_at,
            created_at=payment.created_at,
        )

    async def get_tenant_subscriptions(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> List[SubscriptionResponse]:
        """Fetch all subscriptions for a tenant."""
        query = (
            select(ServiceSubscription, Service.name, Service.slug)
            .join(Service, ServiceSubscription.service_id == Service.id)
            .where(ServiceSubscription.tenant_id == tenant_id)
        )
        res = await session.execute(query)
        rows = res.all()

        return [
            SubscriptionResponse(
                id=sub.id,
                tenant_id=sub.tenant_id,
                service_id=sub.service_id,
                service_name=s_name,
                service_slug=s_slug,
                plan_name=sub.plan_name,
                status=sub.status,
                price=float(sub.price),
                billing_interval=sub.billing_interval,
                started_at=sub.started_at,
                expires_at=sub.expires_at,
            )
            for sub, s_name, s_slug in rows
        ]

    async def get_tenant_invoices(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> List[Invoice]:
        """Fetch all invoices for a tenant."""
        query = (
            select(Invoice)
            .where(Invoice.tenant_id == tenant_id)
            .order_by(Invoice.created_at.desc())
        )
        res = await session.execute(query)
        return list(res.scalars().all())

    async def is_service_enabled_for_tenant(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        service_slug: str,
    ) -> bool:
        """Enforce subscription access check for specific service categories."""
        query = (
            select(ServiceSubscription)
            .join(Service, ServiceSubscription.service_id == Service.id)
            .where(
                ServiceSubscription.tenant_id == tenant_id,
                Service.slug == service_slug,
                ServiceSubscription.status == "active",
            )
        )
        res = await session.execute(query)
        subscription = res.scalar_one_or_none()
        if not subscription:
            return False
        if subscription.expires_at is not None:
            expires_at = subscription.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                return False
        return True


    async def record_bank_transfer_notification(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        request: BankTransferNotifyRequest,
    ) -> Dict[str, Any]:
        """Record a client-submitted bank transfer receipt / reference for admin verification."""
        t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = t_res.scalar_one_or_none()
        if not tenant:
            raise ResourceNotFoundError("Tenant", str(tenant_id))

        now = datetime.now(timezone.utc)
        curr_settings = dict(tenant.settings or {})
        curr_settings["payment_notified"] = True
        curr_settings["payment_reference"] = request.transaction_reference
        curr_settings["payment_notes"] = request.notes
        curr_settings["payment_notified_at"] = now.isoformat()
        tenant.settings = curr_settings

        # Determine payment amount from outstanding invoices if not explicitly passed
        amount = request.amount
        if not amount:
            inv_res = await session.execute(
                select(Invoice)
                .where(Invoice.tenant_id == tenant_id, Invoice.status != "paid")
                .order_by(Invoice.created_at.desc())
            )
            unpaid_invoices = inv_res.scalars().all()
            amount = round(sum(float(i.total) for i in unpaid_invoices), 2) if unpaid_invoices else 249.0

        payment = Payment(
            tenant_id=tenant_id,
            amount=amount,
            currency="USD",
            payment_method="bank_transfer",
            provider_reference=request.transaction_reference,
            status="pending",
            paid_at=None,
        )
        session.add(payment)

        audit = AuditLog(
            tenant_id=tenant_id,
            actor_type="user",
            action="payment.bank_transfer_submitted",
            resource_type="payment",
            resource_id=payment.id,
            metadata_={
                "transaction_reference": request.transaction_reference,
                "amount": amount,
                "bank": COMPANY_BANK_DETAILS["bank_name"],
                "account_name": COMPANY_BANK_DETAILS["account_name"],
                "notes": request.notes,
            },
        )
        session.add(audit)
        await session.commit()
        await session.refresh(payment)

        return {
            "success": True,
            "payment_id": str(payment.id),
            "status": "pending_verification",
            "transaction_reference": request.transaction_reference,
            "amount": float(payment.amount),
            "bank_details": COMPANY_BANK_DETAILS,
            "message": "Bank transfer reference recorded. Platform Admin has been notified for manual verification.",
        }

    async def approve_tenant_payment(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        admin_user_id: Optional[uuid.UUID] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Admin approves verified bank transfer, unlocks managed AI services, and marks subscriptions active."""
        t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = t_res.scalar_one_or_none()
        if not tenant:
            raise ResourceNotFoundError("Tenant", str(tenant_id))

        now = datetime.now(timezone.utc)
        curr_settings = dict(tenant.settings or {})
        curr_settings["payment_approved"] = True
        curr_settings["automation_approved_by_owner"] = True
        curr_settings["trial_active"] = False
        curr_settings["trial_expired"] = False
        curr_settings["payment_approved_at"] = now.isoformat()
        if notes:
            curr_settings["payment_approval_notes"] = notes
        tenant.settings = curr_settings
        if tenant.status in ("pending_approval", "unpaid"):
            tenant.status = "active"

        # Reconcile all pending payments
        pay_res = await session.execute(
            select(Payment).where(
                Payment.tenant_id == tenant_id,
                Payment.status.in_(["pending_verification", "pending"]),
            )
        )
        for payment in pay_res.scalars().all():
            payment.status = "completed"
            payment.paid_at = now

        # Reconcile all outstanding invoices
        inv_res = await session.execute(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id,
                Invoice.status != "paid",
            )
        )
        for invoice in inv_res.scalars().all():
            invoice.status = "paid"

        # Activate all service subscriptions
        sub_res = await session.execute(
            select(ServiceSubscription).where(
                ServiceSubscription.tenant_id == tenant_id,
            )
        )
        for sub in sub_res.scalars().all():
            sub.status = "active"

        audit = AuditLog(
            tenant_id=tenant_id,
            actor_id=admin_user_id,
            actor_type="admin",
            action="admin.payment.approved",
            resource_type="tenant",
            resource_id=tenant_id,
            metadata_={"approved_at": now.isoformat(), "notes": notes},
        )
        session.add(audit)
        await session.commit()

        from app.services.wallet_service import PLAN_ACTIVATION_BONUS_CREDITS, wallet_service

        await wallet_service.credit_wallet(
            session=session,
            tenant_id=tenant_id,
            credits=PLAN_ACTIVATION_BONUS_CREDITS,
            category="plan_grant",
            description="Subscription payment verified — starter prepaid credits added",
            entry_type="plan_grant",
            reference_id=f"admin_approve_plan:{tenant_id}:{now.strftime('%Y%m%d')}",
        )

        logger.info(
            "Tenant payment approved and services activated",
            tenant_id=str(tenant_id),
            admin_id=str(admin_user_id),
        )

        return {
            "success": True,
            "tenant_id": str(tenant_id),
            "payment_approved": True,
            "automation_active": True,
            "message": "Payment verified and approved. Client AI services are now activated.",
        }

    async def reconcile_verified_payment(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        provider: str,
        provider_reference: str,
        amount: float,
        currency: str = "USD",
        purpose: str = "subscription",
        credits_to_grant: Optional[float] = None,
        invoice_id: Optional[uuid.UUID] = None,
        subscription_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Idempotently verify/complete a gateway payment and provision workspace plan & credits."""
        t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = t_res.scalar_one_or_none()
        if not tenant:
            raise ResourceNotFoundError("Tenant", str(tenant_id))

        now = datetime.now(timezone.utc)
        pay_res = await session.execute(
            select(Payment).where(
                Payment.tenant_id == tenant_id,
                Payment.provider_reference == provider_reference,
            )
        )
        payment = pay_res.scalar_one_or_none()
        if payment and payment.status == "completed":
            return {
                "reconciled": False,
                "idempotent": True,
                "payment_id": str(payment.id),
                "message": "Webhook event already processed",
            }

        if payment:
            payment.status = "completed"
            payment.paid_at = now
            if amount > 0:
                payment.amount = amount
            payment.currency = currency.upper()[:3]
            if invoice_id is None and payment.subscription_id and subscription_id is None:
                subscription_id = payment.subscription_id
        else:
            payment = Payment(
                tenant_id=tenant_id,
                subscription_id=subscription_id,
                amount=amount,
                currency=currency.upper()[:3],
                payment_method=provider.lower(),
                provider_reference=provider_reference,
                status="completed",
                paid_at=now,
            )
            session.add(payment)

        if invoice_id:
            inv_res = await session.execute(
                select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
            )
            invoice = inv_res.scalar_one_or_none()
            if invoice:
                invoice.status = "paid"

        if purpose != "wallet_topup":
            if subscription_id:
                sub_res = await session.execute(
                    select(ServiceSubscription).where(
                        ServiceSubscription.id == subscription_id,
                        ServiceSubscription.tenant_id == tenant_id,
                    )
                )
                sub = sub_res.scalar_one_or_none()
                if sub:
                    sub.status = "active"
            else:
                sub_res = await session.execute(
                    select(ServiceSubscription).where(ServiceSubscription.tenant_id == tenant_id)
                )
                for sub in sub_res.scalars().all():
                    if sub.status != "canceled":
                        sub.status = "active"

            if not invoice_id:
                open_inv_res = await session.execute(
                    select(Invoice).where(
                        Invoice.tenant_id == tenant_id,
                        Invoice.status.in_(["issued", "payment_pending"]),
                    )
                )
                for inv in open_inv_res.scalars().all():
                    inv.status = "paid"

        curr_settings = dict(tenant.settings or {})
        curr_settings["payment_approved"] = True
        curr_settings["automation_approved_by_owner"] = True
        curr_settings["trial_active"] = False
        curr_settings["trial_expired"] = False
        curr_settings["payment_approved_at"] = now.isoformat()
        curr_settings["last_payment_provider"] = provider.lower()
        curr_settings["last_payment_reference"] = provider_reference
        tenant.settings = curr_settings
        if tenant.status in ("pending_approval", "unpaid"):
            tenant.status = "active"

        await session.flush()
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_type="system",
                action="payment.webhook_reconciled",
                resource_type="payment",
                resource_id=payment.id,
                metadata_={
                    "provider": provider.lower(),
                    "provider_reference": provider_reference,
                    "amount": float(payment.amount),
                    "currency": payment.currency,
                    "purpose": purpose,
                },
            )
        )
        await session.commit()
        await session.refresh(payment)

        from app.services.wallet_service import PLAN_ACTIVATION_BONUS_CREDITS, wallet_service

        if purpose == "wallet_topup":
            grant_credits = float(credits_to_grant or max(100.0, round(float(amount) * 10.0, 2)))
            entry_type = "credit"
            cat = "wallet_topup"
            desc = f"{provider.title()} prepaid credit top-up ({provider_reference})"
        else:
            grant_credits = float(credits_to_grant or PLAN_ACTIVATION_BONUS_CREDITS)
            entry_type = "plan_grant"
            cat = "plan_grant"
            desc = f"{provider.title()} subscription activation credit grant ({provider_reference})"

        wallet_res = await wallet_service.credit_wallet(
            session=session,
            tenant_id=tenant_id,
            credits=grant_credits,
            category=cat,
            description=desc,
            entry_type=entry_type,
            reference_id=f"payment_webhook:{provider_reference}",
            metadata={"provider": provider.lower(), "payment_id": str(payment.id)},
            enable_auto_pause=True if purpose == "wallet_topup" else None,
        )

        from app.services.notification_service import notification_service

        await notification_service.send_notification(
            session=session,
            tenant_id=tenant_id,
            title=f"{provider.title()} Payment Verified (+{grant_credits:.0f} Credits)",
            message=f"Payment {provider_reference} ({payment.amount:.2f} {payment.currency}) verified. Your workspace and {grant_credits:.0f} credits are ready.",
            channel="in_app",
        )

        return {
            "reconciled": True,
            "idempotent": False,
            "payment_id": str(payment.id),
            "credits_granted": grant_credits,
            "wallet": wallet_res["wallet"],
            "message": "Webhook verified and payment provisioned",
        }

    async def execute_approved_refund(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        payment_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Complete a refund strictly after Human-in-the-Loop ApprovalManager authorization."""
        res = await session.execute(
            select(Payment).where(Payment.id == payment_id, Payment.tenant_id == tenant_id)
        )
        payment = res.scalar_one_or_none()
        if not payment:
            raise ResourceNotFoundError("Payment", str(payment_id))
        if payment.status == "refunded":
            return {"payment_id": str(payment.id), "status": "refunded", "idempotent": True}

        payment.status = "refunded"
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=reviewer_id,
                actor_type="user",
                action="payment.refunded_approved",
                resource_type="payment",
                resource_id=payment.id,
                metadata_={
                    "amount": float(payment.amount),
                    "currency": payment.currency,
                    "reason": reason,
                },
            )
        )
        await session.commit()

        from app.services.notification_service import notification_service

        await notification_service.send_notification(
            session=session,
            tenant_id=tenant_id,
            title="Refund Request Approved",
            message=f"Payment {payment.provider_reference} ({float(payment.amount):.2f} {payment.currency}) has been marked refunded after human review.",
            channel="in_app",
        )

        return {"payment_id": str(payment.id), "status": "refunded", "idempotent": False}


billing_service = BillingService()
