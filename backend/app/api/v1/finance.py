"""Business Financial & Rent Tracking API Router.

Implements production endpoints under /api/v1/finance:
1. Multi-currency accounts & atomic ledger balance reconciliation.
2. Income, expense, and rent transactions with status toggles (paid, pending, overdue).
3. Real estate rent schedules with WhatsApp automated reminder dispatching.
4. Real-time KPI summaries, monthly burn rate, and CSV report export.
5. Strict tenant isolation, RBAC permissions, and Operations Console module gating.
"""

import uuid
from datetime import date
from typing import List, Optional

from app.core.exceptions import PermissionDeniedError
from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.schemas.finance import (
    FinancialAccountCreateRequest,
    FinancialAccountResponse,
    FinancialSummaryResponse,
    FinancialTransactionCreateRequest,
    FinancialTransactionResponse,
    FinancialTransactionUpdateRequest,
    RentScheduleCreateRequest,
    RentScheduleResponse,
    RentScheduleUpdateRequest,
    WhatsAppReminderSummaryResponse,
)
from app.services.finance_service import finance_service
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/finance", tags=["Business Financial & Rent Tracking"])


def verify_finance_module_permission(permission_name: str):
    """Dependency factory ensuring RBAC permission AND active Business Financial Tracking module."""
    async def _checker(
        context: TenantContext = Depends(require_permission(permission_name)),
        session: AsyncSession = Depends(get_db),
    ) -> TenantContext:
        is_active = await finance_service.is_module_active(session, context.tenant_id)
        if not is_active:
            raise PermissionDeniedError(
                "The Business Financial Tracking & Ledger module is disabled or not subscribed for this tenant. "
                "Please subscribe or contact the Super Administrator to activate this service."
            )
        return context

    return _checker


verify_finance_module_active = verify_finance_module_permission("business.records.read")


# --- Module Status ---
@router.get("/status")
async def get_finance_module_status(
    context: TenantContext = Depends(require_permission("business.records.read")),
    session: AsyncSession = Depends(get_db),
):
    """Check whether the Business Financial Tracking module is active for the tenant."""
    active = await finance_service.is_module_active(session, context.tenant_id)
    return {
        "success": True,
        "data": {
            "tenant_id": str(context.tenant_id),
            "service": "business-financial-tracking",
            "active": active,
            "status": "ACTIVE" if active else "DISABLED",
        },
    }


# --- Accounts ---
@router.get("/accounts", response_model=List[FinancialAccountResponse])
async def list_financial_accounts(
    context: TenantContext = Depends(verify_finance_module_active),
    session: AsyncSession = Depends(get_db),
):
    """List all financial accounts (Bank, Cash, NayaPay, Stripe) for the active tenant."""
    return await finance_service.list_accounts(
        session=session,
        tenant_id=context.tenant_id,
    )


@router.post("/accounts", status_code=status.HTTP_201_CREATED, response_model=FinancialAccountResponse)
async def create_financial_account(
    request: FinancialAccountCreateRequest,
    context: TenantContext = Depends(verify_finance_module_permission("business.records.create")),
    session: AsyncSession = Depends(get_db),
):
    """Create a new financial account and audit initial balance."""
    return await finance_service.create_account(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        request=request,
    )


# --- Transactions & Ledger ---
@router.get("/transactions", response_model=List[FinancialTransactionResponse])
async def list_financial_transactions(
    type: Optional[str] = Query(None, description="Filter by type: income, expense, rent"),
    status: Optional[str] = Query(None, description="Filter by status: paid, pending, overdue"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    context: TenantContext = Depends(verify_finance_module_active),
    session: AsyncSession = Depends(get_db),
):
    """List tenant transactions with multi-criteria filtering."""
    return await finance_service.list_transactions(
        session=session,
        tenant_id=context.tenant_id,
        type_=type,
        status_=status,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


@router.post("/transactions", status_code=status.HTTP_201_CREATED, response_model=FinancialTransactionResponse)
async def create_financial_transaction(
    request: FinancialTransactionCreateRequest,
    context: TenantContext = Depends(verify_finance_module_permission("business.records.create")),
    session: AsyncSession = Depends(get_db),
):
    """Log an income, expense, or rent payment with atomic account balance reconciliation."""
    return await finance_service.create_transaction(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        request=request,
    )


@router.patch("/transactions/{transaction_id}", response_model=FinancialTransactionResponse)
async def update_financial_transaction(
    transaction_id: uuid.UUID,
    request: FinancialTransactionUpdateRequest,
    context: TenantContext = Depends(verify_finance_module_permission("business.records.update")),
    session: AsyncSession = Depends(get_db),
):
    """Update a transaction (e.g. Mark as Paid) and reconcile ledger balances atomically."""
    return await finance_service.update_transaction(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        transaction_id=transaction_id,
        request=request,
    )


# --- Rent Schedules (Real Estate / Property) ---
@router.get("/rent-schedules", response_model=List[RentScheduleResponse])
async def list_rent_schedules(
    status: Optional[str] = Query(None, description="Filter by status: active, vacant"),
    context: TenantContext = Depends(verify_finance_module_active),
    session: AsyncSession = Depends(get_db),
):
    """List all recurring property rent schedules for the tenant."""
    return await finance_service.list_rent_schedules(
        session=session,
        tenant_id=context.tenant_id,
        status_=status,
    )


@router.post("/rent-schedules", status_code=status.HTTP_201_CREATED, response_model=RentScheduleResponse)
async def create_rent_schedule(
    request: RentScheduleCreateRequest,
    context: TenantContext = Depends(verify_finance_module_permission("business.records.create")),
    session: AsyncSession = Depends(get_db),
):
    """Create a recurring rent schedule for a property unit and lessee."""
    return await finance_service.create_rent_schedule(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        request=request,
    )


@router.patch("/rent-schedules/{schedule_id}", response_model=RentScheduleResponse)
async def update_rent_schedule(
    schedule_id: uuid.UUID,
    request: RentScheduleUpdateRequest,
    context: TenantContext = Depends(verify_finance_module_permission("business.records.update")),
    session: AsyncSession = Depends(get_db),
):
    """Update property unit rent schedule parameters or status (active/vacant)."""
    return await finance_service.update_rent_schedule(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        schedule_id=schedule_id,
        request=request,
    )


# --- KPI Summary & Charts ---
@router.get("/summary", response_model=FinancialSummaryResponse)
async def get_financial_summary(
    currency: str = Query("USD", description="Target currency for summary calculations"),
    context: TenantContext = Depends(verify_finance_module_active),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve real-time financial KPIs: Cash Balance, Revenue, Expenses, Burn Rate, and Chart Data."""
    return await finance_service.get_summary(
        session=session,
        tenant_id=context.tenant_id,
        target_currency=currency,
    )


# --- WhatsApp Automation Reminders ---
@router.post("/whatsapp/reminders", response_model=WhatsAppReminderSummaryResponse)
async def trigger_whatsapp_rent_reminders(
    context: TenantContext = Depends(verify_finance_module_permission("business.records.create")),
    session: AsyncSession = Depends(get_db),
):
    """Scan rent schedules and dispatch automated WhatsApp reminders 3 days before due date."""
    return await finance_service.dispatch_rent_reminders(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
    )


# --- CSV Report Export ---
@router.get("/export/csv")
async def export_financial_csv(
    context: TenantContext = Depends(verify_finance_module_active),
    session: AsyncSession = Depends(get_db),
):
    """Download the complete financial transaction ledger as a CSV reconciliation report."""
    csv_content = await finance_service.export_csv(
        session=session,
        tenant_id=context.tenant_id,
    )
    filename = f"financial_ledger_{context.tenant_id}_{date.today().isoformat()}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
