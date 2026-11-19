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
from typing import List, Optional

from app.core.exceptions import ResourceNotFoundError, TaloxException
from app.core.logging import logger
from app.database.models.automation import AuditLog
from app.database.models.billing import Invoice, Payment
from app.database.models.service import Service, ServiceSubscription
from app.database.models.tenant import Tenant
from app.schemas.payment import PaymentCreateRequest, PaymentResponse
from app.schemas.service import (
    ServiceCreateRequest,
    ServiceUpdateRequest,
    SubscriptionCreateRequest,
    SubscriptionResponse,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

INDUSTRY_ALIASES = {
    "financing": "Financing",
    "finance": "Financing",
    "professional financial services": "Financing",
    "clinics / hospitals": "Clinics / Hospitals",
    "healthcare": "Clinics / Hospitals",
    "healthcare & medical clinics": "Clinics / Hospitals",
    "clinics": "Clinics / Hospitals",
    "hospitals": "Clinics / Hospitals",
    "real estate / property": "Real Estate / Property",
    "real estate": "Real Estate / Property",
    "real estate & property management": "Real Estate / Property",
    "property": "Real Estate / Property",
    "e-commerce": "E-Commerce",
    "ecommerce": "E-Commerce",
    "retail": "E-Commerce",
    "retail & e-commerce": "E-Commerce",
}


def normalize_industry(industry: Optional[str]) -> str:
    if not industry:
        return "Financing"
    cleaned = industry.strip()
    return INDUSTRY_ALIASES.get(cleaned.lower(), cleaned)


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
        services = list(res.scalars().all())

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
        if tenant and tenant.status in ("pending_approval", "unpaid"):
            tenant.status = "active"

        await session.commit()
        await session.refresh(payment)

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
        return res.scalar_one_or_none() is not None


billing_service = BillingService()
