"""Tenant Service — Multi-Tenant Lifecycle & Cascading Account Purge.

Implements:
1. Self-service Tenant Onboarding.
2. Multi-user Company Invitations & Role Assignments.
3. Strict Tenant Isolation Verification.
4. Cascading Account Deletion (GDPR "Right to be Forgotten").
"""

import uuid
from typing import List

from app.core.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    TaloxException,
    TenantIsolationError,
)
from app.core.logging import logger
from app.database.models.agent import AgentExecution, AgentTask, TenantAgent
from app.database.models.automation import (
    Approval,
    AuditLog,
    Integration,
    Notification,
    UsageRecord,
)
from app.database.models.billing import Invoice, Payment
from app.database.models.business import BusinessMetric, BusinessRecord
from app.database.models.marketing import Lead, MarketingCampaign, MarketingMetric
from app.database.models.service import ServiceSubscription
from app.database.models.tenant import Profile, Tenant, TenantMember
from app.schemas.tenant import (
    TenantCreateRequest,
    TenantMemberInviteRequest,
    TenantMemberResponse,
    TenantResponse,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


class TenantService:
    """Manages tenant workspaces and strict membership isolation."""

    async def create_tenant(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        request: TenantCreateRequest,
    ) -> TenantResponse:
        """Create a new tenant workspace and assign the creator as the Owner."""
        # 1. Check slug uniqueness
        query = select(Tenant).where(Tenant.slug == request.slug)
        existing = await session.execute(query)
        if existing.scalar_one_or_none():
            raise TaloxException(
                message=f"Company with handle '{request.slug}' already exists",
                code="SLUG_ALREADY_EXISTS",
                status_code=409,
            )

        # 2. Create Tenant record
        tenant = Tenant(
            name=request.name,
            slug=request.slug,
            industry=request.industry,
            status="pending_approval",
            settings=request.settings or {},
        )
        session.add(tenant)
        await session.flush()

        # 3. Create TenantMember with 'owner' role
        membership = TenantMember(
            tenant_id=tenant.id,
            user_id=user_id,
            role="owner",
            status="active",
        )
        session.add(membership)

        # 4. Record Audit Log
        audit = AuditLog(
            tenant_id=tenant.id,
            actor_id=user_id,
            actor_type="user",
            action="tenant.created",
            resource_type="tenant",
            resource_id=tenant.id,
            metadata_={"slug": tenant.slug, "industry": tenant.industry},
        )
        session.add(audit)
        await session.commit()
        await session.refresh(tenant)

        logger.info(
            "Tenant workspace created",
            tenant_id=str(tenant.id),
            slug=tenant.slug,
            owner_user_id=str(user_id),
        )

        return TenantResponse(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            industry=tenant.industry,
            status=tenant.status,
            settings=tenant.settings,
            created_at=tenant.created_at,
            role="owner",
        )

    async def get_user_tenants(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
    ) -> List[TenantResponse]:
        """Fetch all tenants where the user has active membership."""
        query = (
            select(Tenant, TenantMember.role)
            .join(TenantMember, Tenant.id == TenantMember.tenant_id)
            .where(
                TenantMember.user_id == user_id,
                TenantMember.status == "active",
                Tenant.status != "deleted",
            )
        )
        result = await session.execute(query)
        rows = result.all()

        return [
            TenantResponse(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                industry=tenant.industry,
                status=tenant.status,
                settings=tenant.settings,
                created_at=tenant.created_at,
                role=role,
            )
            for tenant, role in rows
        ]

    async def get_tenant_by_id(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> TenantResponse:
        """Fetch a specific tenant, strictly verifying user membership."""
        query = (
            select(Tenant, TenantMember.role)
            .join(TenantMember, Tenant.id == TenantMember.tenant_id)
            .where(
                Tenant.id == tenant_id,
                TenantMember.user_id == user_id,
                TenantMember.status == "active",
                Tenant.status != "deleted",
            )
        )
        result = await session.execute(query)
        row = result.first()
        if not row:
            raise TenantIsolationError("Access denied: You do not belong to this tenant workspace")

        tenant, role = row
        return TenantResponse(
            id=tenant.id,
            name=tenant.name,
            slug=tenant.slug,
            industry=tenant.industry,
            status=tenant.status,
            settings=tenant.settings,
            created_at=tenant.created_at,
            role=role,
        )

    async def add_tenant_member(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        request: TenantMemberInviteRequest,
    ) -> TenantMemberResponse:
        """Invite/assign a registered user to a tenant workspace with a specific RBAC role."""
        p_res = await session.execute(select(Profile).where(Profile.email == request.email))
        profile = p_res.scalar_one_or_none()
        if not profile:
            raise ResourceNotFoundError("User", request.email)

        existing = await session.execute(
            select(TenantMember).where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.user_id == profile.id,
            )
        )
        member = existing.scalar_one_or_none()
        if member:
            member.role = request.role
            member.status = "active"
        else:
            member = TenantMember(
                tenant_id=tenant_id,
                user_id=profile.id,
                role=request.role,
                status="active",
            )
            session.add(member)

        await session.flush()

        audit = AuditLog(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_type="user",
            action="tenant.member.added",
            resource_type="tenant_member",
            resource_id=member.id,
            metadata_={"email": request.email, "role": request.role},
        )
        session.add(audit)
        await session.commit()
        await session.refresh(member)

        return TenantMemberResponse(
            id=member.id,
            tenant_id=member.tenant_id,
            user_id=member.user_id,
            role=member.role,
            status=member.status,
            created_at=member.created_at,
            email=profile.email,
            full_name=profile.full_name,
        )

    async def list_tenant_members(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> List[TenantMemberResponse]:
        """List all members belonging to a tenant workspace."""
        query = (
            select(TenantMember, Profile)
            .join(Profile, TenantMember.user_id == Profile.id)
            .where(TenantMember.tenant_id == tenant_id)
        )
        res = await session.execute(query)
        rows = res.all()
        return [
            TenantMemberResponse(
                id=member.id,
                tenant_id=member.tenant_id,
                user_id=member.user_id,
                role=member.role,
                status=member.status,
                created_at=member.created_at,
                email=profile.email,
                full_name=profile.full_name,
            )
            for member, profile in rows
        ]

    async def purge_tenant_data(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        confirmation_slug: str,
    ) -> bool:
        """Cascading Account Deletion and Data Purge (GDPR Compliance).

        Atomically purges all tenant records across all child tables
        via database cascading delete, revokes integrations, and records audit.
        """
        # 1. Verify caller is Tenant Owner
        query = select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == user_id,
            TenantMember.status == "active",
        )
        result = await session.execute(query)
        membership = result.scalar_one_or_none()

        if not membership or membership.role != "owner":
            raise PermissionDeniedError("Only the tenant Owner can authorize account deletion and data purge")

        # 2. Fetch tenant and confirm slug match
        t_query = select(Tenant).where(Tenant.id == tenant_id)
        t_res = await session.execute(t_query)
        tenant = t_res.scalar_one_or_none()
        if not tenant:
            raise ResourceNotFoundError("Tenant", str(tenant_id))

        if tenant.slug != confirmation_slug:
            raise TaloxException(
                message=f"Confirmation handle mismatch. Expected '{tenant.slug}'",
                code="CONFIRMATION_MISMATCH",
                status_code=400,
            )

        logger.warning(
            "STARTING ATOMIC CASCADING PURGE FOR TENANT",
            tenant_id=str(tenant_id),
            slug=tenant.slug,
            authorized_by=str(user_id),
        )

        # 3. Create unlinked immutable audit log before purge
        audit = AuditLog(
            tenant_id=None,  # Unlinked to preserve audit record without referencing purged tenant
            actor_id=user_id,
            actor_type="user",
            action="tenant.purged",
            resource_type="tenant",
            resource_id=tenant_id,
            metadata_={
                "slug": tenant.slug,
                "reason": "Customer requested complete account termination and cascading data purge",
            },
        )
        session.add(audit)

        # 4. Explicit cascading deletion of all tenant child records across all engines
        child_tables = [
            UsageRecord,
            Notification,
            Integration,
            Approval,
            AgentExecution,
            AgentTask,
            TenantAgent,
            MarketingMetric,
            MarketingCampaign,
            Lead,
            BusinessMetric,
            BusinessRecord,
            Invoice,
            Payment,
            ServiceSubscription,
            TenantMember,
        ]
        for table in child_tables:
            await session.execute(delete(table).where(table.tenant_id == tenant_id))

        # 5. Delete the tenant root record
        await session.delete(tenant)
        await session.commit()

        logger.info(
            "CASCADING TENANT PURGE COMPLETED SUCCESSFULLY",
            tenant_id=str(tenant_id),
        )
        return True


tenant_service = TenantService()
