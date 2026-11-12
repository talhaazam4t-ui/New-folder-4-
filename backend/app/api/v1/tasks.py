"""Automation Tasks API Endpoints.

Provides tenant-isolated endpoints to submit, list, inspect, and execute custom Python tasks.
"""

import uuid
from typing import List, Optional

from app.automation.runtime import automation_runtime
from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.schemas.task import TaskCreateRequest, TaskResponse
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/tasks", tags=["Automation Tasks"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TaskResponse)
async def create_and_dispatch_task(
    request: TaskCreateRequest,
    context: TenantContext = Depends(require_permission("agents.execute")),
    session: AsyncSession = Depends(get_db),
):
    """Submit an automation or agent task through the custom Python runtime."""
    return await automation_runtime.submit_task(
        session=session,
        tenant_id=context.tenant_id,
        request=request,
    )


@router.get("", response_model=List[TaskResponse])
async def list_tenant_tasks(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """List automation tasks belonging to the authenticated tenant."""
    return await automation_runtime.dispatcher.list_tasks(
        session=session,
        tenant_id=context.tenant_id,
        status_filter=status_filter,
        limit=limit,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_tenant_task(
    task_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve details of a single automation task."""
    return await automation_runtime.dispatcher.get_task(
        session=session,
        tenant_id=context.tenant_id,
        task_id=task_id,
    )


@router.post("/{task_id}/execute", response_model=TaskResponse)
async def execute_pending_task(
    task_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("agents.execute")),
    session: AsyncSession = Depends(get_db),
):
    """Trigger execution of a pending or approved automation task."""
    return await automation_runtime.executor.execute_task(
        session=session,
        tenant_id=context.tenant_id,
        task_id=task_id,
    )
