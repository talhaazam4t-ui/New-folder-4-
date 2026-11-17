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
from sqlalchemy import func, select
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


def normalize_industry(industry: Optional[str]) -> str:
    if not industry:
        return "Financing"
    cleaned = industry.strip()
    return INDUSTRY_ALIASES.get(cleaned.lower(), cleaned)


class BillingService:
    """Manages monetization, subscriptions, and financial invoices."""

    async def ensure_default_catalog(self, session: AsyncSession) -> None:
        """Populate default industry-aware services if the catalog table is completely empty."""
        count_res = await session.execute(select(func.count(Service.id)))
        if (count_res.scalar() or 0) > 0:
            return
        from scripts.seed_services import DEFAULT_SERVICES

        for item in DEFAULT_SERVICES:
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

        # Determine payment amount from outstanding invoice if not explicitly passed
        amount = request.amount
        if not amount:
            inv_res = await session.execute(
                select(Invoice)
                .where(Invoice.tenant_id == tenant_id, Invoice.status != "paid")
                .order_by(Invoice.created_at.desc())
            )
            inv = inv_res.scalar_one_or_none()
            amount = float(inv.total) if inv else 249.0

        payment = Payment(
            tenant_id=tenant_id,
            amount=amount,
            currency="USD",
            payment_method="bank_transfer",
            provider_reference=request.transaction_reference,
            status="pending_verification",
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
        curr_settings["payment_approved_at"] = now.isoformat()
        if notes:
            curr_settings["payment_approval_notes"] = notes
        tenant.settings = curr_settings

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


billing_service = BillingService()
