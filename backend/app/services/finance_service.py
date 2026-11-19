"""Business Financial & Rent Tracking Domain Service.

Handles:
1. Multi-currency financial accounts & automatic atomic ledger balance reconciliation.
2. Income, expense, and rent tracking with status transitions (paid, pending, overdue).
3. Real estate rent schedules with WhatsApp automated reminder dispatching.
4. Comprehensive KPI summaries, burn rate, cash flow, and CSV exports.
5. Strict tenant isolation, immutable audit logging, and module subscription checks.
"""

import csv
import io
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Union

from app.core.exceptions import ResourceNotFoundError
from app.database.models.finance import (
    FinancialAccount,
    FinancialAuditLog,
    FinancialTransaction,
    RentSchedule,
)
from app.database.models.service import Service, ServiceSubscription
from app.integrations.whatsapp.client import WhatsAppCloudClient
from app.schemas.finance import (
    FinancialAccountCreateRequest,
    FinancialAccountResponse,
    FinancialSummaryResponse,
    FinancialTransactionCreateRequest,
    FinancialTransactionResponse,
    FinancialTransactionUpdateRequest,
    MonthlyChartPoint,
    RentScheduleCreateRequest,
    RentScheduleResponse,
    RentScheduleUpdateRequest,
    WhatsAppReminderResult,
    WhatsAppReminderSummaryResponse,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

FINANCE_SERVICE_SLUGS = ("business-financial-tracking", "business-finance")


class FinanceService:
    """Dedicated domain service for multi-tenant financial accounts and rent tracking."""

    def __init__(self):
        self.wa_client = WhatsAppCloudClient()

    @staticmethod
    def _coerce_tenant_id(tenant_id: Union[uuid.UUID, str]) -> uuid.UUID:
        if isinstance(tenant_id, uuid.UUID):
            return tenant_id
        return uuid.UUID(str(tenant_id))

    # --- Module Active Check ---
    async def is_module_active(self, session: AsyncSession, tenant_id: Union[uuid.UUID, str]) -> bool:
        """Check if tenant has an active finance subscription and the catalog module is enabled."""
        tenant_uuid = self._coerce_tenant_id(tenant_id)

        # 1. Global Service Catalog Toggle from Admin Operations Console
        srv_q = select(Service).where(Service.slug.in_(FINANCE_SERVICE_SLUGS))
        services = list((await session.execute(srv_q)).scalars().all())
        if not services:
            return False

        # If canonical slug exists, respect its active toggle; otherwise check any matching active service
        canonical_srv = next((s for s in services if s.slug == "business-financial-tracking"), None)
        if canonical_srv is not None and not canonical_srv.active:
            return False
        if not any(s.active for s in services):
            return False

        # 2. Tenant-Specific Active Service Subscription Check
        sub_q = (
            select(ServiceSubscription)
            .join(Service, ServiceSubscription.service_id == Service.id)
            .where(
                ServiceSubscription.tenant_id == tenant_uuid,
                Service.slug.in_(FINANCE_SERVICE_SLUGS),
                Service.active == True,  # noqa: E712
                ServiceSubscription.status.in_(("active", "trialing")),
            )
        )
        res = await session.execute(sub_q)
        return res.scalars().first() is not None

    # --- Accounts ---
    async def create_account(
        self,
        session: AsyncSession,
        tenant_id: Union[uuid.UUID, str],
        user_id: Optional[uuid.UUID],
        request: FinancialAccountCreateRequest,
    ) -> FinancialAccountResponse:
        """Create a new financial account (Bank, Cash, NayaPay, Stripe) and audit."""
        tenant_uuid = self._coerce_tenant_id(tenant_id)
        account = FinancialAccount(
            id=uuid.uuid4(),
            tenant_id=tenant_uuid,
            name=request.name.strip(),
            currency=request.currency.upper(),
            current_balance=float(request.current_balance),
        )
        session.add(account)

        audit = FinancialAuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            tenant_id=tenant_uuid,
            action="CREATE_ACCOUNT",
            diff_json={
                "account_id": str(account.id),
                "name": account.name,
                "currency": account.currency,
                "initial_balance": float(account.current_balance),
            },
        )
        session.add(audit)
        await session.commit()
        await session.refresh(account)

        return FinancialAccountResponse(
            id=account.id,
            tenant_id=str(account.tenant_id),
            name=account.name,
            currency=account.currency,
            current_balance=float(account.current_balance),
            created_at=account.created_at,
            updated_at=account.updated_at,
        )

    async def list_accounts(
        self,
        session: AsyncSession,
        tenant_id: Union[uuid.UUID, str],
    ) -> List[FinancialAccountResponse]:
        """List all financial accounts for a tenant."""
        tenant_uuid = self._coerce_tenant_id(tenant_id)
        query = select(FinancialAccount).where(FinancialAccount.tenant_id == tenant_uuid).order_by(FinancialAccount.name)
        res = await session.execute(query)
        rows = res.scalars().all()
        return [
            FinancialAccountResponse(
                id=a.id,
                tenant_id=str(a.tenant_id),
                name=a.name,
                currency=a.currency,
                current_balance=float(a.current_balance),
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
            for a in rows
        ]

    # --- Transactions & Ledger Reconciliation ---
    async def create_transaction(
        self,
        session: AsyncSession,
        tenant_id: Union[uuid.UUID, str],
        user_id: Optional[uuid.UUID],
        request: FinancialTransactionCreateRequest,
    ) -> FinancialTransactionResponse:
        """Log a new transaction and atomically reconcile current_balance if paid."""
        tenant_uuid = self._coerce_tenant_id(tenant_id)
        tx_date = request.transaction_date or date.today()
        tx = FinancialTransaction(
            id=uuid.uuid4(),
            tenant_id=tenant_uuid,
            account_id=request.account_id,
            type=request.type,
            category=request.category.strip(),
            amount=float(request.amount),
            currency=request.currency.upper(),
            status=request.status,
            transaction_date=tx_date,
            due_date=request.due_date,
            counterparty_name=request.counterparty_name.strip(),
            notes=request.notes,
            receipt_url=request.receipt_url,
        )
        session.add(tx)

        # Atomic balance update if linked to an account and status is paid
        if request.account_id and request.status == "paid":
            acc_query = (
                select(FinancialAccount)
                .where(
                    FinancialAccount.id == request.account_id,
                    FinancialAccount.tenant_id == tenant_uuid,
                )
                .with_for_update()
            )
            acc_res = await session.execute(acc_query)
            account = acc_res.scalar_one_or_none()
            if account:
                if request.type in ("income", "rent"):
                    account.current_balance = float(account.current_balance) + float(request.amount)
                elif request.type == "expense":
                    account.current_balance = float(account.current_balance) - float(request.amount)

        audit = FinancialAuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            tenant_id=tenant_uuid,
            action="CREATE_TRANSACTION",
            diff_json={
                "transaction_id": str(tx.id),
                "type": tx.type,
                "amount": float(tx.amount),
                "currency": tx.currency,
                "status": tx.status,
                "account_id": str(tx.account_id) if tx.account_id else None,
                "counterparty": tx.counterparty_name,
            },
        )
        session.add(audit)
        await session.commit()
        await session.refresh(tx)

        return self._to_tx_response(tx)

    async def update_transaction(
        self,
        session: AsyncSession,
        tenant_id: Union[uuid.UUID, str],
        user_id: Optional[uuid.UUID],
        transaction_id: uuid.UUID,
        request: FinancialTransactionUpdateRequest,
    ) -> FinancialTransactionResponse:
        """Update transaction (e.g. mark as paid) and atomically adjust ledger balance."""
        tenant_uuid = self._coerce_tenant_id(tenant_id)
        query = (
            select(FinancialTransaction)
            .where(
                FinancialTransaction.id == transaction_id,
                FinancialTransaction.tenant_id == tenant_uuid,
            )
            .with_for_update()
        )
        res = await session.execute(query)
        tx = res.scalar_one_or_none()
        if not tx:
            raise ResourceNotFoundError("FinancialTransaction", str(transaction_id))

        old_status = tx.status
        old_amount = float(tx.amount)
        new_status = request.status or old_status
        new_amount = float(request.amount) if request.amount is not None else old_amount
        target_account_id = request.account_id or tx.account_id

        # Reconcile balance transitions
        if target_account_id:
            acc_query = (
                select(FinancialAccount)
                .where(
                    FinancialAccount.id == target_account_id,
                    FinancialAccount.tenant_id == tenant_uuid,
                )
                .with_for_update()
            )
            acc_res = await session.execute(acc_query)
            account = acc_res.scalar_one_or_none()

            if account:
                bal = float(account.current_balance)
                # If transaction was already paid, reverse old amount effect
                if old_status == "paid":
                    if tx.type in ("income", "rent"):
                        bal -= old_amount
                    elif tx.type == "expense":
                        bal += old_amount

                # If new status is paid, apply new amount effect
                if new_status == "paid":
                    if tx.type in ("income", "rent"):
                        bal += new_amount
                    elif tx.type == "expense":
                        bal -= new_amount
                account.current_balance = bal

        # Apply fields
        if request.status:
            tx.status = request.status
        if request.amount is not None:
            tx.amount = request.amount
        if request.category:
            tx.category = request.category
        if request.counterparty_name:
            tx.counterparty_name = request.counterparty_name
        if request.notes is not None:
            tx.notes = request.notes
        if request.due_date is not None:
            tx.due_date = request.due_date
        if request.account_id is not None:
            tx.account_id = request.account_id

        audit = FinancialAuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            tenant_id=tenant_uuid,
            action="UPDATE_TRANSACTION",
            diff_json={
                "transaction_id": str(tx.id),
                "old_status": old_status,
                "new_status": tx.status,
                "old_amount": float(old_amount),
                "new_amount": float(tx.amount),
            },
        )
        session.add(audit)
        await session.commit()
        await session.refresh(tx)

        return self._to_tx_response(tx)

    async def list_transactions(
        self,
        session: AsyncSession,
        tenant_id: Union[uuid.UUID, str],
        type_: Optional[str] = None,
        status_: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[FinancialTransactionResponse]:
        """List tenant transactions with multi-criteria filtering."""
        tenant_uuid = self._coerce_tenant_id(tenant_id)
        query = select(FinancialTransaction).where(FinancialTransaction.tenant_id == tenant_uuid)

        if type_:
            query = query.where(FinancialTransaction.type == type_)
        if status_:
            query = query.where(FinancialTransaction.status == status_)
        if start_date:
            query = query.where(FinancialTransaction.transaction_date >= start_date)
        if end_date:
            query = query.where(FinancialTransaction.transaction_date <= end_date)

        query = query.order_by(FinancialTransaction.transaction_date.desc(), FinancialTransaction.created_at.desc()).offset(offset).limit(limit)
        res = await session.execute(query)
        rows = res.scalars().all()
        return [self._to_tx_response(tx) for tx in rows]

    # --- Rent Schedules ---
    async def create_rent_schedule(
        self,
        session: AsyncSession,
        tenant_id: Union[uuid.UUID, str],
        user_id: Optional[uuid.UUID],
        request: RentScheduleCreateRequest,
    ) -> RentScheduleResponse:
        """Create a recurring property rent schedule for a client lessee."""
        tenant_uuid = self._coerce_tenant_id(tenant_id)
        schedule = RentSchedule(
            id=uuid.uuid4(),
            tenant_id=tenant_uuid,
            property_unit=request.property_unit.strip(),
            lessee_name=request.lessee_name.strip(),
            lessee_whatsapp=request.lessee_whatsapp.strip(),
            monthly_rent=float(request.monthly_rent),
            currency=request.currency.upper(),
            billing_day=request.billing_day,
            auto_remind_whatsapp=request.auto_remind_whatsapp,
            status=request.status,
        )
        session.add(schedule)

        audit = FinancialAuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            tenant_id=tenant_uuid,
            action="CREATE_RENT_SCHEDULE",
            diff_json={
                "schedule_id": str(schedule.id),
                "property_unit": schedule.property_unit,
                "lessee_name": schedule.lessee_name,
                "monthly_rent": float(schedule.monthly_rent),
            },
        )
        session.add(audit)
        await session.commit()
        await session.refresh(schedule)

        return self._to_schedule_response(schedule)

    async def list_rent_schedules(
        self,
        session: AsyncSession,
        tenant_id: Union[uuid.UUID, str],
        status_: Optional[str] = None,
    ) -> List[RentScheduleResponse]:
        """List rent schedules for tenant properties."""
        tenant_uuid = self._coerce_tenant_id(tenant_id)
        query = select(RentSchedule).where(RentSchedule.tenant_id == tenant_uuid)
        if status_:
            query = query.where(RentSchedule.status == status_)
        query = query.order_by(RentSchedule.property_unit)
        res = await session.execute(query)
        rows = res.scalars().all()
        return [self._to_schedule_response(s) for s in rows]

    async def update_rent_schedule(
        self,
        session: AsyncSession,
        tenant_id: Union[uuid.UUID, str],
        user_id: Optional[uuid.UUID],
        schedule_id: uuid.UUID,
        request: RentScheduleUpdateRequest,
    ) -> RentScheduleResponse:
        """Update property unit rent schedule parameters."""
        tenant_uuid = self._coerce_tenant_id(tenant_id)
        query = select(RentSchedule).where(
            RentSchedule.id == schedule_id,
            RentSchedule.tenant_id == tenant_uuid,
        )
        res = await session.execute(query)
        schedule = res.scalar_one_or_none()
        if not schedule:
            raise ResourceNotFoundError("RentSchedule", str(schedule_id))

        if request.property_unit is not None:
            schedule.property_unit = request.property_unit
        if request.lessee_name is not None:
            schedule.lessee_name = request.lessee_name
        if request.lessee_whatsapp is not None:
            schedule.lessee_whatsapp = request.lessee_whatsapp
        if request.monthly_rent is not None:
            schedule.monthly_rent = request.monthly_rent
        if request.currency is not None:
            schedule.currency = request.currency.upper()
        if request.billing_day is not None:
            schedule.billing_day = request.billing_day
        if request.auto_remind_whatsapp is not None:
            schedule.auto_remind_whatsapp = request.auto_remind_whatsapp
        if request.status is not None:
            schedule.status = request.status

        session.add(schedule)
        await session.commit()
        await session.refresh(schedule)
        return self._to_schedule_response(schedule)

    # --- KPI Summary & Interactive Chart Breakdown ---
    async def get_summary(
        self,
        session: AsyncSession,
        tenant_id: Union[uuid.UUID, str],
        target_currency: str = "USD",
    ) -> FinancialSummaryResponse:
        """Calculate real-time KPIs: Cash Balance, Revenue, Expenses, Burn Rate, and Chart Data."""
        tenant_uuid = self._coerce_tenant_id(tenant_id)

        # 1. Accounts Total Balance & per-currency balances
        accounts_query = select(FinancialAccount).where(FinancialAccount.tenant_id == tenant_uuid)
        acc_res = await session.execute(accounts_query)
        accounts = acc_res.scalars().all()

        currency_balances: Dict[str, float] = {}
        total_balance = 0.0
        for acc in accounts:
            curr = acc.currency.upper()
            bal = float(acc.current_balance)
            currency_balances[curr] = currency_balances.get(curr, 0.0) + bal
            total_balance += bal

        # 2. Date ranges
        now = datetime.now(timezone.utc)
        thirty_days_ago = now.date() - timedelta(days=30)

        # 3. Monthly Revenue (paid income + paid rent in last 30 days)
        rev_query = select(func.coalesce(func.sum(FinancialTransaction.amount), 0.0)).where(
            FinancialTransaction.tenant_id == tenant_uuid,
            FinancialTransaction.status == "paid",
            FinancialTransaction.type.in_(["income", "rent"]),
            FinancialTransaction.transaction_date >= thirty_days_ago,
        )
        monthly_revenue = float((await session.execute(rev_query)).scalar() or 0.0)

        # 4. Monthly Expenses
        exp_query = select(func.coalesce(func.sum(FinancialTransaction.amount), 0.0)).where(
            FinancialTransaction.tenant_id == tenant_uuid,
            FinancialTransaction.status == "paid",
            FinancialTransaction.type == "expense",
            FinancialTransaction.transaction_date >= thirty_days_ago,
        )
        monthly_expenses = float((await session.execute(exp_query)).scalar() or 0.0)

        # 5. Accounts Receivable (pending/overdue rent and invoices)
        ar_query = select(func.coalesce(func.sum(FinancialTransaction.amount), 0.0)).where(
            FinancialTransaction.tenant_id == tenant_uuid,
            FinancialTransaction.status.in_(["pending", "overdue"]),
            FinancialTransaction.type.in_(["income", "rent"]),
        )
        accounts_receivable = float((await session.execute(ar_query)).scalar() or 0.0)

        # 6. Rent counts
        pending_count_q = select(func.count(FinancialTransaction.id)).where(
            FinancialTransaction.tenant_id == tenant_uuid,
            FinancialTransaction.type == "rent",
            FinancialTransaction.status == "pending",
        )
        pending_rent_count = int((await session.execute(pending_count_q)).scalar() or 0)

        overdue_count_q = select(func.count(FinancialTransaction.id)).where(
            FinancialTransaction.tenant_id == tenant_uuid,
            FinancialTransaction.type == "rent",
            FinancialTransaction.status == "overdue",
        )
        overdue_rent_count = int((await session.execute(overdue_count_q)).scalar() or 0)

        # 7. Monthly Chart (Last 6 months breakdown)
        chart_points: List[MonthlyChartPoint] = []
        for i in range(5, -1, -1):
            m_date = (now - timedelta(days=i * 30)).date()
            m_start = date(m_date.year, m_date.month, 1)
            # month end
            if m_date.month == 12:
                m_end = date(m_date.year + 1, 1, 1) - timedelta(days=1)
            else:
                m_end = date(m_date.year, m_date.month + 1, 1) - timedelta(days=1)

            inc_q = select(func.coalesce(func.sum(FinancialTransaction.amount), 0.0)).where(
                FinancialTransaction.tenant_id == tenant_uuid,
                FinancialTransaction.status == "paid",
                FinancialTransaction.type.in_(["income", "rent"]),
                FinancialTransaction.transaction_date >= m_start,
                FinancialTransaction.transaction_date <= m_end,
            )
            m_inc = float((await session.execute(inc_q)).scalar() or 0.0)

            exp_m_q = select(func.coalesce(func.sum(FinancialTransaction.amount), 0.0)).where(
                FinancialTransaction.tenant_id == tenant_uuid,
                FinancialTransaction.status == "paid",
                FinancialTransaction.type == "expense",
                FinancialTransaction.transaction_date >= m_start,
                FinancialTransaction.transaction_date <= m_end,
            )
            m_exp = float((await session.execute(exp_m_q)).scalar() or 0.0)

            chart_points.append(
                MonthlyChartPoint(
                    month=m_start.strftime("%b %Y"),
                    income=m_inc,
                    expense=m_exp,
                    net=m_inc - m_exp,
                )
            )

        return FinancialSummaryResponse(
            total_cash_balance=total_balance,
            monthly_revenue=monthly_revenue,
            monthly_expenses=monthly_expenses,
            net_cash_flow=monthly_revenue - monthly_expenses,
            accounts_receivable=accounts_receivable,
            monthly_burn_rate=monthly_expenses,
            pending_rent_count=pending_rent_count,
            overdue_rent_count=overdue_rent_count,
            currency=target_currency,
            currency_balances=currency_balances,
            monthly_chart=chart_points,
        )

    # --- Automated WhatsApp Reminders ---
    async def dispatch_rent_reminders(
        self,
        session: AsyncSession,
        tenant_id: Union[uuid.UUID, str],
        user_id: Optional[uuid.UUID] = None,
    ) -> WhatsAppReminderSummaryResponse:
        """Scan rent schedules and overdue transactions, dispatching automated WhatsApp reminders."""
        tenant_uuid = self._coerce_tenant_id(tenant_id)
        today = date.today()
        results: List[WhatsAppReminderResult] = []

        # 1. Scan active rent schedules with auto_remind_whatsapp enabled
        schedules_q = select(RentSchedule).where(
            RentSchedule.tenant_id == tenant_uuid,
            RentSchedule.status == "active",
            RentSchedule.auto_remind_whatsapp == True,  # noqa: E712
        )
        schedules = (await session.execute(schedules_q)).scalars().all()

        for s in schedules:
            try:
                current_due = date(today.year, today.month, min(s.billing_day, 28))
            except ValueError:
                current_due = date(today.year, today.month, 28)

            days_diff = (current_due - today).days

            if -5 <= days_diff <= 3:
                msg = (
                    f"Assalam o Alaikum {s.lessee_name},\n\n"
                    f"This is an automated reminder regarding the upcoming rent for *{s.property_unit}*.\n"
                    f"• Amount Due: *{s.currency} {s.monthly_rent:,.2f}*\n"
                    f"• Due Date: *{current_due.strftime('%d %B %Y')}*\n\n"
                    f"Please submit payment via bank transfer or Cash and share the receipt.\n"
                    f"— Platform Finance Team (Teloxtech)"
                )
                wa_res = await self.wa_client.send_text_message(
                    tenant_id=str(tenant_uuid),
                    to_phone=s.lessee_whatsapp,
                    message_body=msg,
                )

                audit = FinancialAuditLog(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    tenant_id=tenant_uuid,
                    action="WHATSAPP_RENT_REMINDER_SENT",
                    diff_json={
                        "schedule_id": str(s.id),
                        "lessee": s.lessee_name,
                        "phone": s.lessee_whatsapp,
                        "due_date": str(current_due),
                        "message_id": wa_res.get("message_id"),
                    },
                )
                session.add(audit)

                results.append(
                    WhatsAppReminderResult(
                        schedule_id=str(s.id),
                        lessee_name=s.lessee_name,
                        phone=s.lessee_whatsapp,
                        amount=float(s.monthly_rent),
                        currency=s.currency,
                        status="reminder_dispatched",
                        due_date=str(current_due),
                        message_id=wa_res.get("message_id"),
                        detail=f"Dispatched reminder for billing date {current_due}",
                    )
                )

        # 2. Also scan any pending/overdue rent transactions
        tx_q = select(FinancialTransaction).where(
            FinancialTransaction.tenant_id == tenant_uuid,
            FinancialTransaction.type == "rent",
            FinancialTransaction.status.in_(["pending", "overdue"]),
        )
        tx_rows = (await session.execute(tx_q)).scalars().all()
        for t in tx_rows:
            if t.due_date:
                results.append(
                    WhatsAppReminderResult(
                        transaction_id=str(t.id),
                        lessee_name=t.counterparty_name,
                        phone="Tenant Profile Phone",
                        amount=float(t.amount),
                        currency=t.currency,
                        status=t.status,
                        due_date=str(t.due_date),
                        detail=f"Flagged pending transaction {t.id} for manual follow-up",
                    )
                )

        await session.commit()
        return WhatsAppReminderSummaryResponse(
            total_scanned=len(schedules) + len(tx_rows),
            reminders_dispatched=len([r for r in results if r.status == "reminder_dispatched"]),
            results=results,
        )

    # --- CSV Export ---
    async def export_csv(
        self,
        session: AsyncSession,
        tenant_id: Union[uuid.UUID, str],
    ) -> str:
        """Generate CSV export of the financial ledger."""
        transactions = await self.list_transactions(session, tenant_id, limit=5000)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Transaction ID",
            "Date",
            "Type",
            "Category",
            "Amount",
            "Currency",
            "Status",
            "Counterparty",
            "Account ID",
            "Due Date",
            "Notes",
            "Receipt URL",
        ])

        for tx in transactions:
            writer.writerow([
                str(tx.id),
                tx.transaction_date.isoformat(),
                tx.type,
                tx.category,
                f"{tx.amount:.2f}",
                tx.currency,
                tx.status,
                tx.counterparty_name,
                str(tx.account_id) if tx.account_id else "",
                tx.due_date.isoformat() if tx.due_date else "",
                tx.notes or "",
                tx.receipt_url or "",
            ])

        return output.getvalue()

    def _to_tx_response(self, tx: FinancialTransaction) -> FinancialTransactionResponse:
        return FinancialTransactionResponse(
            id=tx.id,
            tenant_id=str(tx.tenant_id),
            account_id=tx.account_id,
            type=tx.type,
            category=tx.category,
            amount=float(tx.amount),
            currency=tx.currency,
            status=tx.status,
            transaction_date=tx.transaction_date,
            due_date=tx.due_date,
            counterparty_name=tx.counterparty_name,
            notes=tx.notes,
            receipt_url=tx.receipt_url,
            created_at=tx.created_at,
            updated_at=tx.updated_at,
        )

    def _to_schedule_response(self, s: RentSchedule) -> RentScheduleResponse:
        return RentScheduleResponse(
            id=s.id,
            tenant_id=str(s.tenant_id),
            property_unit=s.property_unit,
            lessee_name=s.lessee_name,
            lessee_whatsapp=s.lessee_whatsapp,
            monthly_rent=float(s.monthly_rent),
            currency=s.currency,
            billing_day=s.billing_day,
            auto_remind_whatsapp=s.auto_remind_whatsapp,
            status=s.status,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )


finance_service = FinanceService()
