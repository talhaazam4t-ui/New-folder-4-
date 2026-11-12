"""Tenant-Scoped Generic Repository Pattern (`backend/app/database/repositories/`).

Guarantees that all repository queries automatically include `tenant_id == context.tenant_id`
to prevent accidental cross-tenant data leakage at the data-access layer.
"""

import uuid
from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ModelType = TypeVar("ModelType")


class TenantScopedRepository(Generic[ModelType]):
    """Generic async repository enforcing strict `tenant_id` filtering on every query."""

    def __init__(self, model: Type[ModelType]):
        self.model = model

    async def list_by_tenant(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ModelType]:
        query = (
            select(self.model)
            .where(getattr(self.model, "tenant_id") == tenant_id)
            .limit(limit)
            .offset(offset)
        )
        res = await session.execute(query)
        return list(res.scalars().all())

    async def get_by_id_for_tenant(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        record_id: uuid.UUID,
    ) -> Optional[ModelType]:
        query = select(self.model).where(
            getattr(self.model, "id") == record_id,
            getattr(self.model, "tenant_id") == tenant_id,
        )
        res = await session.execute(query)
        return res.scalar_one_or_none()
