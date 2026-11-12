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
from app.schemas.payment import PaymentCreateRequest, PaymentResponse
from app.schemas.service import (
    ServiceCreateRequest,
    SubscriptionCreateRequest,
    SubscriptionResponse,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class BillingService:
    """Manages monetization, subscriptions, and financial invoices."""

    async def list_services(
        self,
        session: AsyncSession,
        category: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Service]:
        """Fetch all services from catalog."""
        query = select(Service)
        if active_only:
            query = query.where(Service.active == True)  # noqa: E712
        if category:
            query = query.where(Service.category == category)
        res = await session.execute(query.order_by(Service.name))
        return list(res.scalars().all())

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
        """Record and reconcile a client payment."""
        now = datetime.now(timezone.utc)

        payment = Payment(
            tenant_id=tenant_id,
            subscription_id=request.subscription_id,
            amount=request.amount,
            currency=request.currency,
            payment_method=request.payment_method,
            provider_reference=request.provider_reference or f"TXN-{uuid.uuid4().hex[:8].upper()}",
            status="completed",
            paid_at=now,
        )
        session.add(payment)

        # If paying against an invoice, mark invoice paid
        if request.invoice_id:
            inv_query = select(Invoice).where(
                Invoice.id == request.invoice_id,
                Invoice.tenant_id == tenant_id,
            )
            inv_res = await session.execute(inv_query)
            invoice = inv_res.scalar_one_or_none()
            if invoice:
                invoice.status = "paid"

        await session.commit()
        await session.refresh(payment)

        logger.info(
            "Payment recorded and settled",
            tenant_id=str(tenant_id),
            amount=request.amount,
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
