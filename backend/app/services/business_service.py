"""Business Tracking Engine Service.

Provides:
1. Immutable financial ledger tracking (Income, Expense, Rent, Outstanding, Payment Received, Adjustment).
2. Auditable correction history preserving original transaction values.
3. Strict prohibition of silent AI modification of confirmed financial transactions.
4. Custom numerical business metrics, batch imports, and exportable financial reports.
"""

import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.core.logging import logger
from app.database.models.automation import AuditLog
from app.database.models.business import BusinessMetric, BusinessRecord
from app.schemas.business import (
    BusinessImportRequest,
    BusinessRecordCreateRequest,
    BusinessRecordResponse,
    BusinessRecordUpdateRequest,
    BusinessSummaryResponse,
    CustomMetricCreateRequest,
    CustomMetricResponse,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class BusinessService:
    """Dedicated domain service for tenant financial tracking and business metrics."""

    def _to_record_response(self, record: BusinessRecord) -> BusinessRecordResponse:
        return BusinessRecordResponse(
            id=record.id,
            tenant_id=record.tenant_id,
            record_type=record.record_type,
            title=record.title,
            amount=float(record.amount),
            currency=record.currency,
            description=record.description,
            source=record.source,
            reference_id=record.reference_id,
            recorded_by=record.recorded_by,
            recorded_at=record.recorded_at,
            metadata=record.metadata_ or {},
            created_at=record.created_at,
        )

    async def create_record(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        request: BusinessRecordCreateRequest,
    ) -> BusinessRecordResponse:
        """Create a new financial business record and log audit trail."""
        now = datetime.now(timezone.utc)
        initial_meta = dict(request.metadata or {})
        initial_meta["original_amount"] = request.amount
        initial_meta["original_type"] = request.record_type
        initial_meta["revision_history"] = []

        record = BusinessRecord(
            tenant_id=tenant_id,
            record_type=request.record_type,
            title=request.title,
            amount=request.amount,
            currency=request.currency.upper(),
            description=request.description,
            source=request.source,
            reference_id=request.reference_id,
            recorded_by=user_id,
            recorded_at=request.recorded_at or now,
            metadata_=initial_meta,
        )
        session.add(record)
        await session.flush()

        audit = AuditLog(
            tenant_id=tenant_id,
            actor_id=user_id,
            actor_type="user" if request.source != "agent" else "agent",
            action="business.record.created",
            resource_type="business_record",
            resource_id=record.id,
            metadata_={
                "record_type": record.record_type,
                "amount": float(record.amount),
                "currency": record.currency,
                "source": record.source,
            },
        )
        session.add(audit)
        await session.commit()
        await session.refresh(record)

        logger.info(
            "Business record created",
            tenant_id=str(tenant_id),
            record_id=str(record.id),
            record_type=record.record_type,
            amount=float(record.amount),
        )
        return self._to_record_response(record)

    async def list_records(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        record_type: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[BusinessRecordResponse]:
        """List business records strictly isolated to the authenticated tenant."""
        query = select(BusinessRecord).where(BusinessRecord.tenant_id == tenant_id)
        if record_type:
            query = query.where(BusinessRecord.record_type == record_type)
        if source:
            query = query.where(BusinessRecord.source == source)

        query = query.order_by(BusinessRecord.recorded_at.desc()).limit(limit).offset(offset)
        res = await session.execute(query)
        records = res.scalars().all()
        return [self._to_record_response(r) for r in records]

    async def get_record(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        record_id: uuid.UUID,
    ) -> BusinessRecordResponse:
        """Retrieve a single business record scoped to the tenant."""
        query = select(BusinessRecord).where(
            BusinessRecord.id == record_id,
            BusinessRecord.tenant_id == tenant_id,
        )
        res = await session.execute(query)
        record = res.scalar_one_or_none()
        if not record:
            raise ResourceNotFoundError("BusinessRecord", str(record_id))
        return self._to_record_response(record)

    async def update_record(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        record_id: uuid.UUID,
        request: BusinessRecordUpdateRequest,
    ) -> BusinessRecordResponse:
        """Update a financial record while preserving original values and audit history.

        Non-negotiable restriction: AI agents cannot silently alter confirmed financial records.
        """
        if request.actor_type == "agent":
            raise PermissionDeniedError(
                "AI agents are strictly prohibited from altering confirmed financial transactions."
            )

        query = select(BusinessRecord).where(
            BusinessRecord.id == record_id,
            BusinessRecord.tenant_id == tenant_id,
        )
        res = await session.execute(query)
        record = res.scalar_one_or_none()
        if not record:
            raise ResourceNotFoundError("BusinessRecord", str(record_id))

        # Snapshot previous state into revision history
        current_meta = dict(record.metadata_ or {})
        history = list(current_meta.get("revision_history", []))
        revision_entry = {
            "modified_at": datetime.now(timezone.utc).isoformat(),
            "modified_by": str(user_id),
            "reason": request.reason,
            "previous_title": record.title,
            "previous_amount": float(record.amount),
            "previous_type": record.record_type,
            "previous_description": record.description,
        }
        history.append(revision_entry)
        current_meta["revision_history"] = history

        if request.title is not None:
            record.title = request.title
        if request.amount is not None:
            record.amount = request.amount
        if request.description is not None:
            record.description = request.description
        if request.record_type is not None:
            record.record_type = request.record_type

        record.metadata_ = current_meta

        audit = AuditLog(
            tenant_id=tenant_id,
            actor_id=user_id,
            actor_type="user",
            action="business.record.updated",
            resource_type="business_record",
            resource_id=record.id,
            metadata_={
                "reason": request.reason,
                "revision": revision_entry,
                "new_amount": float(record.amount),
            },
        )
        session.add(audit)
        await session.commit()
        await session.refresh(record)

        logger.info(
            "Business record updated with audit trail",
            tenant_id=str(tenant_id),
            record_id=str(record.id),
            reason=request.reason,
        )
        return self._to_record_response(record)

    async def delete_record(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        record_id: uuid.UUID,
    ) -> bool:
        """Delete a financial record (Requires Owner permission) and write audit entry."""
        query = select(BusinessRecord).where(
            BusinessRecord.id == record_id,
            BusinessRecord.tenant_id == tenant_id,
        )
        res = await session.execute(query)
        record = res.scalar_one_or_none()
        if not record:
            raise ResourceNotFoundError("BusinessRecord", str(record_id))

        audit = AuditLog(
            tenant_id=tenant_id,
            actor_id=user_id,
            actor_type="user",
            action="business.record.deleted",
            resource_type="business_record",
            resource_id=record.id,
            metadata_={
                "deleted_title": record.title,
                "deleted_amount": float(record.amount),
                "deleted_type": record.record_type,
            },
        )
        session.add(audit)
        await session.delete(record)
        await session.commit()
        return True

    async def get_summary(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> BusinessSummaryResponse:
        """Compute reconciled financial summary across all tenant business records."""
        query = select(BusinessRecord).where(BusinessRecord.tenant_id == tenant_id)
        res = await session.execute(query)
        records = res.scalars().all()

        total_income = sum(float(r.amount) for r in records if r.record_type == "income")
        total_rent = sum(float(r.amount) for r in records if r.record_type == "rent")
        total_received = sum(float(r.amount) for r in records if r.record_type == "payment_received")
        total_expenses = sum(float(r.amount) for r in records if r.record_type == "expense")
        total_outstanding = sum(float(r.amount) for r in records if r.record_type == "outstanding")
        total_adjustments = sum(float(r.amount) for r in records if r.record_type == "adjustment")

        gross_inflow = total_income + total_rent + total_received
        net_cashflow = gross_inflow - total_expenses + total_adjustments

        return BusinessSummaryResponse(
            tenant_id=tenant_id,
            total_income=round(total_income, 2),
            total_rent=round(total_rent, 2),
            total_payments_received=round(total_received, 2),
            total_expenses=round(total_expenses, 2),
            total_outstanding=round(total_outstanding, 2),
            total_adjustments=round(total_adjustments, 2),
            gross_inflow=round(gross_inflow, 2),
            net_cashflow=round(net_cashflow, 2),
            record_count=len(records),
        )

    async def create_custom_metric(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        request: CustomMetricCreateRequest,
    ) -> CustomMetricResponse:
        """Record a custom numerical business metric for the tenant."""
        metric = BusinessMetric(
            tenant_id=tenant_id,
            metric_name=request.metric_name,
            metric_value=request.metric_value,
            period_start=request.period_start,
            period_end=request.period_end,
            metadata_=request.metadata or {},
        )
        session.add(metric)
        await session.flush()

        audit = AuditLog(
            tenant_id=tenant_id,
            actor_id=user_id,
            actor_type="user",
            action="business.metric.created",
            resource_type="business_metric",
            resource_id=metric.id,
            metadata_={"metric_name": metric.metric_name, "value": float(metric.metric_value)},
        )
        session.add(audit)
        await session.commit()
        await session.refresh(metric)

        return CustomMetricResponse(
            id=metric.id,
            tenant_id=metric.tenant_id,
            metric_name=metric.metric_name,
            metric_value=float(metric.metric_value),
            period_start=metric.period_start,
            period_end=metric.period_end,
            metadata=metric.metadata_ or {},
            created_at=metric.created_at,
        )

    async def list_custom_metrics(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> List[CustomMetricResponse]:
        """List all custom numerical metrics for the tenant."""
        query = (
            select(BusinessMetric)
            .where(BusinessMetric.tenant_id == tenant_id)
            .order_by(BusinessMetric.created_at.desc())
        )
        res = await session.execute(query)
        metrics = res.scalars().all()
        return [
            CustomMetricResponse(
                id=m.id,
                tenant_id=m.tenant_id,
                metric_name=m.metric_name,
                metric_value=float(m.metric_value),
                period_start=m.period_start,
                period_end=m.period_end,
                metadata=m.metadata_ or {},
                created_at=m.created_at,
            )
            for m in metrics
        ]

    async def import_records(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        request: BusinessImportRequest,
    ) -> List[BusinessRecordResponse]:
        """Batch import multiple business records with transactional audit logging."""
        created_responses: List[BusinessRecordResponse] = []
        for item in request.records:
            resp = await self.create_record(session, tenant_id, user_id, item)
            created_responses.append(resp)
        return created_responses

    async def generate_report(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Generate an exportable financial report including summary and CSV payload."""
        summary = await self.get_summary(session, tenant_id)
        records = await self.list_records(session, tenant_id, limit=500)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Date", "Type", "Title", "Amount", "Currency", "Source", "Reference"])
        for r in records:
            writer.writerow([
                str(r.id),
                r.recorded_at.isoformat(),
                r.record_type,
                r.title,
                f"{r.amount:.2f}",
                r.currency,
                r.source,
                r.reference_id or "",
            ])

        return {
            "summary": summary.model_dump(mode="json"),
            "csv_content": output.getvalue(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


business_service = BusinessService()
