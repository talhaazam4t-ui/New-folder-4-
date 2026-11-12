"""Business Tracking Engine API Endpoints.

Implements all 10 required endpoints under /api/v1/business with strict
authentication, tenant isolation, RBAC permission verification, and audit logging.
"""

import uuid
from typing import List, Optional

from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.schemas.business import (
    BusinessImportRequest,
    BusinessRecordCreateRequest,
    BusinessRecordResponse,
    BusinessRecordUpdateRequest,
    BusinessSummaryResponse,
    CustomMetricCreateRequest,
    CustomMetricResponse,
)
from app.services.business_service import business_service
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/business", tags=["Business Tracking Engine"])


@router.post("/records", status_code=status.HTTP_201_CREATED, response_model=BusinessRecordResponse)
async def create_business_record(
    request: BusinessRecordCreateRequest,
    context: TenantContext = Depends(require_permission("business.records.create")),
    session: AsyncSession = Depends(get_db),
):
    """Add an income, expense, rent, payment_received, outstanding, or adjustment record."""
    return await business_service.create_record(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        request=request,
    )


@router.get("/records", response_model=List[BusinessRecordResponse])
async def list_business_records(
    record_type: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    context: TenantContext = Depends(require_permission("business.records.read")),
    session: AsyncSession = Depends(get_db),
):
    """List tenant financial records with optional type and source filtering."""
    return await business_service.list_records(
        session=session,
        tenant_id=context.tenant_id,
        record_type=record_type,
        source=source,
        limit=limit,
        offset=offset,
    )


@router.get("/records/{record_id}", response_model=BusinessRecordResponse)
async def get_business_record(
    record_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("business.records.read")),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve a single financial record by ID (enforcing tenant isolation)."""
    return await business_service.get_record(
        session=session,
        tenant_id=context.tenant_id,
        record_id=record_id,
    )


@router.patch("/records/{record_id}", response_model=BusinessRecordResponse)
async def update_business_record(
    record_id: uuid.UUID,
    request: BusinessRecordUpdateRequest,
    context: TenantContext = Depends(require_permission("business.records.update")),
    session: AsyncSession = Depends(get_db),
):
    """Update a financial record while preserving original values and audit history."""
    return await business_service.update_record(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        record_id=record_id,
        request=request,
    )


@router.delete("/records/{record_id}")
async def delete_business_record(
    record_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("business.records.delete")),
    session: AsyncSession = Depends(get_db),
):
    """Delete a financial record (Owner permission required) and record audit trail."""
    await business_service.delete_record(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        record_id=record_id,
    )
    return {"success": True, "message": "Financial record deleted and audited"}


@router.get("/summary", response_model=BusinessSummaryResponse)
async def get_business_summary(
    context: TenantContext = Depends(require_permission("business.records.read")),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve reconciled financial summary for the tenant."""
    return await business_service.get_summary(
        session=session,
        tenant_id=context.tenant_id,
    )


@router.get("/metrics", response_model=List[CustomMetricResponse])
async def list_custom_metrics(
    context: TenantContext = Depends(require_permission("business.metrics.read")),
    session: AsyncSession = Depends(get_db),
):
    """List custom numerical business metrics for the tenant."""
    return await business_service.list_custom_metrics(
        session=session,
        tenant_id=context.tenant_id,
    )


@router.post("/custom-metrics", status_code=status.HTTP_201_CREATED, response_model=CustomMetricResponse)
async def create_custom_metric(
    request: CustomMetricCreateRequest,
    context: TenantContext = Depends(require_permission("business.records.create")),
    session: AsyncSession = Depends(get_db),
):
    """Create a custom numerical metric for business tracking."""
    return await business_service.create_custom_metric(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        request=request,
    )


@router.post("/import", status_code=status.HTTP_201_CREATED, response_model=List[BusinessRecordResponse])
async def import_business_records(
    request: BusinessImportRequest,
    context: TenantContext = Depends(require_permission("business.records.create")),
    session: AsyncSession = Depends(get_db),
):
    """Batch import multiple financial records into the tenant ledger."""
    return await business_service.import_records(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        request=request,
    )


@router.get("/reports")
async def export_business_report(
    context: TenantContext = Depends(require_permission("business.records.read")),
    session: AsyncSession = Depends(get_db),
):
    """Generate and export financial summary and CSV ledger report."""
    report = await business_service.generate_report(
        session=session,
        tenant_id=context.tenant_id,
    )
    return {"success": True, "data": report, "message": "Financial report generated"}
