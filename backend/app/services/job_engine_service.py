"""Native Python Asyncio Delayed Job, Retry & Dead-Letter Queue Engine (Zero n8n).

Handles DB-backed delayed jobs (`public.scheduled_jobs`) with:
1. Idempotency deduplication (`idempotency_key`).
2. Exponential backoff retries (`30s * 2**(attempt-1)`) up to `max_attempts`.
3. Dead-letter quarantine (`dead_letter`) + audit logs when retries are exhausted.
4. Optional Upstash/Redis awareness (`REDIS_URL`) while remaining 100% reliable on Postgres/SQLite alone.
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx
from app.config import settings
from app.core.exceptions import ResourceNotFoundError, TaloxException
from app.core.logging import logger
from app.database.models.automation import AuditLog, ScheduledJob
from app.services.notification_service import notification_service
from app.services.wallet_service import _ensure_utc, wallet_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

JobHandler = Callable[[AsyncSession, ScheduledJob], Awaitable[Any]]


class JobEngineService:
    """In-house Python asyncio scheduled job queue with exponential backoff and DLQ."""

    def __init__(self) -> None:
        self._handlers: Dict[str, JobHandler] = {}
        self._register_builtin_handlers()

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        self._handlers[job_type.strip()] = handler

    def _register_builtin_handlers(self) -> None:
        self.register_handler("expire_trials", self._handle_expire_trials)
        self.register_handler("low_balance_alert", self._handle_low_balance_alert)
        self.register_handler("post_payment_provision", self._handle_post_payment_provision)
        self.register_handler("outreach_autopilot_run", self._handle_outreach_autopilot_run)
        self.register_handler("webhook_dispatch", self._handle_webhook_dispatch)

    async def _handle_expire_trials(self, session: AsyncSession, job: ScheduledJob) -> Any:
        return await wallet_service.expire_elapsed_trials(session)

    async def _handle_low_balance_alert(self, session: AsyncSession, job: ScheduledJob) -> Any:
        if not job.tenant_id:
            return {"skipped": "missing_tenant_id"}
        payload = dict(job.payload or {})
        title = str(payload.get("title") or "Low Credit Balance Alert")
        message = str(payload.get("message") or "Your workspace prepaid credits are running low.")
        return await notification_service.send_notification(
            session=session,
            tenant_id=job.tenant_id,
            title=title,
            message=message,
            channel="in_app",
        )

    async def _handle_post_payment_provision(self, session: AsyncSession, job: ScheduledJob) -> Any:
        if not job.tenant_id:
            return {"skipped": "missing_tenant_id"}
        payload = dict(job.payload or {})
        msg = str(
            payload.get("message")
            or "Payment verified and workspace subscriptions + prepaid credits have been activated."
        )
        return await notification_service.send_notification(
            session=session,
            tenant_id=job.tenant_id,
            title=str(payload.get("title") or "Payment Confirmed — Workspace Active"),
            message=msg,
            channel="in_app",
        )

    async def _handle_outreach_autopilot_run(self, session: AsyncSession, job: ScheduledJob) -> Any:
        if not job.tenant_id:
            raise ValueError("outreach_autopilot_run job requires tenant_id")
        from app.services.outreach_autopilot_service import outreach_autopilot_service

        payload = dict(job.payload or {})
        return await outreach_autopilot_service.run_autopilot_cycle(
            session=session,
            tenant_id=job.tenant_id,
            niche_override=payload.get("niche"),
            city_override=payload.get("city"),
            limit_override=payload.get("limit"),
        )

    async def _handle_webhook_dispatch(self, session: AsyncSession, job: ScheduledJob) -> Any:
        from app.services.outreach_autopilot_service import _is_safe_public_url

        payload = dict(job.payload or {})
        raw_url = str(payload.get("url") or "").strip()
        safe_url = _is_safe_public_url(raw_url)
        if not safe_url:
            raise ValueError(f"Unsafe or invalid webhook URL blocked: {raw_url}")

        body_bytes = json.dumps(payload.get("body") or {}, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "TaloxTech-Webhook/2.0"}
        signing_secret = str(payload.get("signing_secret") or "").strip()
        if signing_secret:
            sig = hmac.new(signing_secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
            headers["X-Talox-Signature"] = sig

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(safe_url, content=body_bytes, headers=headers)
            if resp.status_code >= 400:
                raise RuntimeError(f"Outbound webhook returned HTTP {resp.status_code}")
            return {"status_code": resp.status_code, "url": safe_url}

    def get_engine_status(self) -> Dict[str, Any]:
        return {
            "engine": "python_asyncio_native",
            "mode": "postgres_asyncio",
            "redis_configured": bool((settings.redis_url or "").strip()),
            "registered_handlers": sorted(self._handlers.keys()),
        }

    def _serialize_job(self, job: ScheduledJob) -> Dict[str, Any]:
        return {
            "id": str(job.id),
            "tenant_id": str(job.tenant_id) if job.tenant_id else None,
            "job_type": job.job_type,
            "payload": job.payload or {},
            "status": job.status,
            "attempts": job.attempts,
            "max_attempts": job.max_attempts,
            "run_at": job.run_at.isoformat() if job.run_at else None,
            "last_error": job.last_error,
            "idempotency_key": job.idempotency_key,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        }

    async def enqueue_job(
        self,
        session: AsyncSession,
        job_type: str,
        payload: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[uuid.UUID] = None,
        delay_seconds: int = 0,
        run_at: Optional[datetime] = None,
        max_attempts: int = 3,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if idempotency_key:
            dup_res = await session.execute(
                select(ScheduledJob).where(ScheduledJob.idempotency_key == idempotency_key)
            )
            existing = dup_res.scalar_one_or_none()
            if existing:
                data = self._serialize_job(existing)
                data["idempotent"] = True
                return data

        now_utc = datetime.now(timezone.utc)
        target_run_at = _ensure_utc(run_at) if run_at else (now_utc + timedelta(seconds=max(0, int(delay_seconds))))

        job = ScheduledJob(
            tenant_id=tenant_id,
            job_type=job_type.strip(),
            payload=dict(payload or {}),
            status="queued",
            attempts=0,
            max_attempts=max(1, min(int(max_attempts), 10)),
            run_at=target_run_at,
            idempotency_key=idempotency_key,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        data = self._serialize_job(job)
        data["idempotent"] = False
        return data

    async def process_due_jobs(
        self,
        session: AsyncSession,
        batch_size: int = 20,
    ) -> Dict[str, Any]:
        """Execute queued jobs whose `run_at` has elapsed, applying exponential backoff or DLQ."""
        now_utc = datetime.now(timezone.utc)
        res = await session.execute(
            select(ScheduledJob)
            .where(ScheduledJob.status == "queued")
            .order_by(ScheduledJob.run_at.asc())
            .limit(max(batch_size * 2, 40))
        )
        candidates = res.scalars().all()

        due_jobs: List[ScheduledJob] = []
        for candidate in candidates:
            due_at = _ensure_utc(candidate.run_at)
            if due_at is not None and due_at <= now_utc:
                due_jobs.append(candidate)
            if len(due_jobs) >= batch_size:
                break

        completed = 0
        retried = 0
        dead_lettered = 0

        for job in due_jobs:
            handler = self._handlers.get(job.job_type)
            job.status = "running"
            job.attempts = int(job.attempts or 0) + 1
            await session.flush()

            try:
                if not handler:
                    raise KeyError(f"No handler registered for job_type '{job.job_type}'")
                await handler(session, job)
                job.status = "completed"
                job.last_error = None
                job.completed_at = datetime.now(timezone.utc)
                completed += 1
            except Exception as exc:
                err_msg = str(exc)[:1000]
                job.last_error = err_msg
                if job.attempts < int(job.max_attempts or 3):
                    backoff_seconds = 30 * (2 ** max(0, job.attempts - 1))
                    job.status = "queued"
                    job.run_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
                    retried += 1
                else:
                    job.status = "dead_letter"
                    job.completed_at = datetime.now(timezone.utc)
                    dead_lettered += 1
                    session.add(
                        AuditLog(
                            tenant_id=job.tenant_id,
                            actor_type="system",
                            action="scheduled_job.dead_lettered",
                            resource_type="scheduled_job",
                            resource_id=job.id,
                            metadata_={
                                "job_type": job.job_type,
                                "attempts": job.attempts,
                                "error": err_msg,
                            },
                        )
                    )
                logger.warning(
                    "Scheduled job execution error",
                    job_id=str(job.id),
                    job_type=job.job_type,
                    attempts=job.attempts,
                    status=job.status,
                    error=err_msg,
                )

            await session.commit()

        return {
            "checked": len(due_jobs),
            "completed": completed,
            "retried": retried,
            "dead_lettered": dead_lettered,
        }

    async def list_jobs(
        self,
        session: AsyncSession,
        tenant_id: Optional[uuid.UUID] = None,
        status_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query = select(ScheduledJob)
        if tenant_id is not None:
            query = query.where(ScheduledJob.tenant_id == tenant_id)
        if status_filter:
            query = query.where(ScheduledJob.status == status_filter)
        query = query.order_by(ScheduledJob.created_at.desc()).limit(limit)
        res = await session.execute(query)
        return [self._serialize_job(j) for j in res.scalars().all()]

    async def retry_job(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        tenant_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        query = select(ScheduledJob).where(ScheduledJob.id == job_id)
        if tenant_id is not None:
            query = query.where(ScheduledJob.tenant_id == tenant_id)
        res = await session.execute(query)
        job = res.scalar_one_or_none()
        if not job:
            raise ResourceNotFoundError("ScheduledJob", str(job_id))
        if job.status not in ("dead_letter", "failed", "cancelled"):
            raise TaloxException(
                message=f"Job '{job_id}' cannot be retried from status '{job.status}'.",
                code="INVALID_JOB_STATUS",
                status_code=400,
            )

        job.status = "queued"
        job.attempts = 0
        job.last_error = None
        job.completed_at = None
        job.run_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(job)
        return self._serialize_job(job)


job_engine_service = JobEngineService()
