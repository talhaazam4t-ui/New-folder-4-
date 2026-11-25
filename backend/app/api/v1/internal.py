"""Internal Native Python Asyncio Cron Tick & Scheduled Job Queue API Endpoints.

Provides:
1. Secret-protected `POST /api/v1/internal/cron/tick` so external free schedulers (or Supabase pg_cron)
   can reliably fire due delayed jobs, pending agent tasks, stale approvals, trial expirations,
   and daily outreach autopilot even on sleeping Render Free containers.
2. Tenant-scoped job inspection (`GET /api/v1/internal/jobs`) and manual retry (`POST /api/v1/internal/jobs/{job_id}/retry`).
"""

import hashlib
import hmac
import uuid
from typing import Any, Dict, Optional

from app.automation.workers.task_worker import background_task_worker
from app.config import settings
from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.services.call_intelligence_service import call_intelligence_service
from app.services.job_engine_service import job_engine_service
from app.services.outreach_autopilot_service import outreach_autopilot_service
from app.services.wallet_service import wallet_service
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/internal", tags=["Internal Scheduler & Job Engine"])


def _expected_cron_secret() -> str:
    configured = (settings.cron_secret or "").strip()
    if configured:
        return configured
    return hashlib.sha256(f"cron:{settings.app_secret_key}".encode("utf-8")).hexdigest()[:32]


def _verify_cron_secret(x_cron_secret: Optional[str]) -> None:
    expected = _expected_cron_secret()
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret.strip(), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Cron-Secret header",
        )


class EnqueueJobRequest(BaseModel):
    job_type: str = Field(min_length=2, max_length=120)
    payload: Dict[str, Any] = Field(default_factory=dict)
    delay_seconds: int = Field(default=0, ge=0, le=2592000)
    max_attempts: int = Field(default=3, ge=1, le=10)
    idempotency_key: Optional[str] = Field(default=None, max_length=255)


@router.post("/cron/tick")
async def trigger_internal_cron_tick(
    x_cron_secret: Optional[str] = Header(None, alias="X-Cron-Secret"),
    session: AsyncSession = Depends(get_db),
):
    """Execute one reliable sweep across native Python delayed jobs, queues, trials, and autopilot."""
    _verify_cron_secret(x_cron_secret)

    due_jobs_res = await job_engine_service.process_due_jobs(session, batch_size=25)
    pending_tasks_res = await background_task_worker.process_pending_queue(session, batch_size=15)
    expired_approvals_count = await background_task_worker.expire_stale_approvals(session)
    expired_trials_res = await wallet_service.expire_elapsed_trials(session)
    autopilot_res = await outreach_autopilot_service.run_scheduled_autopilot_tick(session)
    weekly_roi_res = await call_intelligence_service.run_monday_weekly_roi_tick(session)

    return {
        "success": True,
        "data": {
            "engine": job_engine_service.get_engine_status(),
            "scheduled_jobs": due_jobs_res,
            "agent_tasks": pending_tasks_res,
            "expired_approvals": expired_approvals_count,
            "trial_expiration": expired_trials_res,
            "outreach_autopilot": autopilot_res,
            "weekly_roi": weekly_roi_res,
        },
        "message": "Native asyncio scheduler tick completed cleanly",
    }


@router.get("/jobs")
async def list_tenant_scheduled_jobs(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """Inspect delayed scheduled jobs strictly scoped to the active tenant."""
    jobs = await job_engine_service.list_jobs(
        session=session,
        tenant_id=context.tenant_id,
        status_filter=status_filter,
        limit=limit,
    )
    return {
        "success": True,
        "data": {
            "engine": job_engine_service.get_engine_status(),
            "jobs": jobs,
        },
    }


@router.post("/jobs/enqueue", status_code=status.HTTP_201_CREATED)
async def enqueue_tenant_scheduled_job(
    request: EnqueueJobRequest,
    context: TenantContext = Depends(require_permission("agents.execute")),
    session: AsyncSession = Depends(get_db),
):
    """Queue a delayed Python asyncio job for the active tenant."""
    allowed_client_jobs = {
        "outreach_autopilot_run",
        "low_balance_alert",
        "post_payment_provision",
        "webhook_dispatch",
    }
    if request.job_type.strip() not in allowed_client_jobs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported tenant job_type '{request.job_type}'",
        )
    job = await job_engine_service.enqueue_job(
        session=session,
        job_type=request.job_type,
        payload=request.payload,
        tenant_id=context.tenant_id,
        delay_seconds=request.delay_seconds,
        max_attempts=request.max_attempts,
        idempotency_key=request.idempotency_key,
    )
    return {"success": True, "data": job}


@router.post("/jobs/{job_id}/retry")
async def retry_tenant_scheduled_job(
    job_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("agents.execute")),
    session: AsyncSession = Depends(get_db),
):
    """Re-queue a failed or dead-letter scheduled job belonging to the tenant."""
    job = await job_engine_service.retry_job(
        session=session,
        job_id=job_id,
        tenant_id=context.tenant_id,
    )
    return {"success": True, "data": job, "message": "Scheduled job re-queued"}
