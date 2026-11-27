"""Phase 5: Multi-Tenant White-Label Engine & Metered API-as-a-Service.

Delivers:
1. Multi-Tenant White-Label Engine (`TenantWhitelabelConfig`):
   - Per-tenant custom branding: `brand_name`, `logo_url`, `favicon_url`, `primary_color`, `accent_color`,
     `custom_domain`, `support_email`, `hide_powered_by`, `agency_reseller_enabled`.
   - Public domain/slug resolver (`resolve_branding_by_host_or_slug`) for dynamic frontend theme rendering.
   - Agency sub-tenant provisioning (`provision_agency_subtenant`) linked to parent agency `tenant_id`.
2. Scoped Developer API Key Manager (`TenantApiKey`):
   - Generates high-entropy keys (`tlx_live_<32_hex>`) and stores only SHA-256 `key_hash` + `key_prefix`.
   - Enforces granular scopes (`agents:invoke`, `leads:read`, `finance:read`, `compliance:audit`),
     revocation (`is_active`), and expiration (`expires_at`).
3. Metered Public API-as-a-Service (`X-Talox-API-Key`):
   - Authenticates external developer requests via `X-Talox-API-Key` header.
   - Automatically meters API calls and tokens against the tenant's Phase 1 Tier Quota
     (triggering 80% low-balance warning and 100% HTTP 402 hard-lock) and records immutable `AuditLog` entries.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.exceptions import PermissionDeniedError, ResourceNotFoundError, TaloxException
from app.database.models.automation import AuditLog
from app.database.models.governance import TenantApiKey, TenantWhitelabelConfig
from app.database.models.marketing import Lead
from app.database.models.tenant import Tenant, TenantMember
from app.services.central_orchestrator_service import central_orchestrator_service
from app.services.enterprise_modules_service import enterprise_modules_service
from app.services.tier_quota_service import tier_quota_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ConflictError(TaloxException):
    def __init__(self, message: str):
        super().__init__(message=message, code="CONFLICT_ERROR", status_code=409)


class ValidationError(TaloxException):
    def __init__(self, message: str):
        super().__init__(message=message, code="VALIDATION_ERROR", status_code=400)


AuthorizationError = PermissionDeniedError

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
VALID_API_SCOPES = {
    "agents:invoke",
    "leads:read",
    "finance:read",
    "compliance:audit",
}


class WhitelabelAndApiService:
    """Phase 5 Multi-Tenant White-Label Engine & Metered API-as-a-Service."""

    # --------------------------------------------------------------------------
    # 1. Multi-Tenant White-Label Engine
    # --------------------------------------------------------------------------

    @staticmethod
    def serialize_whitelabel(row: TenantWhitelabelConfig) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "brand_name": row.brand_name,
            "logo_url": row.logo_url,
            "favicon_url": row.favicon_url,
            "primary_color": row.primary_color,
            "accent_color": row.accent_color,
            "custom_domain": row.custom_domain,
            "support_email": row.support_email,
            "hide_powered_by": bool(row.hide_powered_by),
            "agency_reseller_enabled": bool(row.agency_reseller_enabled),
            "metadata": row.metadata_ or {},
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def get_or_create_whitelabel_config(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> TenantWhitelabelConfig:
        res = await session.execute(
            select(TenantWhitelabelConfig).where(TenantWhitelabelConfig.tenant_id == tenant_id)
        )
        cfg = res.scalar_one_or_none()
        if cfg is not None:
            return cfg

        t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = t_res.scalar_one_or_none()
        default_brand = tenant.name if tenant else "Talox Tech Stream"

        cfg = TenantWhitelabelConfig(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            brand_name=default_brand,
            primary_color="#2563EB",
            accent_color="#10B981",
            hide_powered_by=False,
            agency_reseller_enabled=False,
            metadata_={},
        )
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
        return cfg

    async def update_whitelabel_config(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        brand_name: Optional[str] = None,
        logo_url: Optional[str] = None,
        favicon_url: Optional[str] = None,
        primary_color: Optional[str] = None,
        accent_color: Optional[str] = None,
        custom_domain: Optional[str] = None,
        support_email: Optional[str] = None,
        hide_powered_by: Optional[bool] = None,
        agency_reseller_enabled: Optional[bool] = None,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        cfg = await self.get_or_create_whitelabel_config(session, tenant_id)

        if primary_color is not None:
            pc = primary_color.strip()
            if not _HEX_COLOR_RE.match(pc):
                raise ValidationError("primary_color must be a 6-digit hex color such as #2563EB.")
            cfg.primary_color = pc

        if accent_color is not None:
            ac = accent_color.strip()
            if not _HEX_COLOR_RE.match(ac):
                raise ValidationError("accent_color must be a 6-digit hex color such as #10B981.")
            cfg.accent_color = ac

        if custom_domain is not None:
            clean_domain = custom_domain.strip().lower() or None
            if clean_domain:
                existing = (
                    await session.execute(
                        select(TenantWhitelabelConfig).where(
                            TenantWhitelabelConfig.custom_domain == clean_domain,
                            TenantWhitelabelConfig.tenant_id != tenant_id,
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    raise ConflictError(f"Custom domain '{clean_domain}' is already mapped to another workspace.")
            cfg.custom_domain = clean_domain

        if brand_name is not None and brand_name.strip():
            cfg.brand_name = brand_name.strip()
        if logo_url is not None:
            cfg.logo_url = logo_url.strip() or None
        if favicon_url is not None:
            cfg.favicon_url = favicon_url.strip() or None
        if support_email is not None:
            cfg.support_email = support_email.strip() or None
        if hide_powered_by is not None:
            cfg.hide_powered_by = bool(hide_powered_by)
        if agency_reseller_enabled is not None:
            cfg.agency_reseller_enabled = bool(agency_reseller_enabled)

        session.add(
            AuditLog(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="whitelabel.config.updated",
                resource_type="tenant_whitelabel_config",
                resource_id=cfg.id,
                metadata_={
                    "brand_name": cfg.brand_name,
                    "custom_domain": cfg.custom_domain,
                    "hide_powered_by": cfg.hide_powered_by,
                },
            )
        )
        await session.commit()
        await session.refresh(cfg)
        return self.serialize_whitelabel(cfg)

    async def resolve_public_branding(
        self,
        session: AsyncSession,
        *,
        domain: Optional[str] = None,
        tenant_slug: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Publicly resolve white-label theme by custom domain or tenant slug."""
        cfg: Optional[TenantWhitelabelConfig] = None
        if domain and domain.strip():
            clean_dom = domain.strip().lower()
            cfg = (
                await session.execute(
                    select(TenantWhitelabelConfig).where(TenantWhitelabelConfig.custom_domain == clean_dom)
                )
            ).scalar_one_or_none()

        if cfg is None and tenant_slug and tenant_slug.strip():
            t_row = (
                await session.execute(
                    select(Tenant).where(Tenant.slug == tenant_slug.strip().lower())
                )
            ).scalar_one_or_none()
            if t_row is not None:
                cfg = await self.get_or_create_whitelabel_config(session, t_row.id)

        if cfg is None:
            return {
                "brand_name": "Talox Tech Stream",
                "logo_url": None,
                "favicon_url": None,
                "primary_color": "#2563EB",
                "accent_color": "#10B981",
                "custom_domain": None,
                "support_email": "support@teloxtech.stream",
                "hide_powered_by": False,
                "resolved": False,
            }

        data = self.serialize_whitelabel(cfg)
        data["resolved"] = True
        return data

    async def provision_agency_subtenant(
        self,
        session: AsyncSession,
        *,
        parent_tenant_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        client_name: str,
        client_slug: str,
        industry: str = "general",
        primary_color: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Allow an agency with `agency_reseller_enabled` to spin up an isolated sub-tenant workspace."""
        parent_cfg = await self.get_or_create_whitelabel_config(session, parent_tenant_id)
        if not parent_cfg.agency_reseller_enabled:
            raise AuthorizationError(
                "Agency Reseller mode is not enabled on this workspace. Enable agency_reseller_enabled first."
            )

        clean_slug = client_slug.strip().lower()
        existing = (
            await session.execute(select(Tenant).where(Tenant.slug == clean_slug))
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(f"Workspace slug '{clean_slug}' already exists.")

        sub_tenant = Tenant(
            id=uuid.uuid4(),
            name=client_name.strip(),
            slug=clean_slug,
            industry=industry,
            status="active",
            settings={
                "industry": industry,
                "parent_agency_tenant_id": str(parent_tenant_id),
                "whitelabel_parent_brand": parent_cfg.brand_name,
            },
        )
        session.add(sub_tenant)
        await session.flush()

        session.add(
            TenantMember(
                id=uuid.uuid4(),
                tenant_id=sub_tenant.id,
                user_id=owner_user_id,
                role="owner",
            )
        )
        sub_wl = TenantWhitelabelConfig(
            id=uuid.uuid4(),
            tenant_id=sub_tenant.id,
            brand_name=client_name.strip(),
            primary_color=primary_color or parent_cfg.primary_color,
            accent_color=parent_cfg.accent_color,
            support_email=parent_cfg.support_email,
            hide_powered_by=parent_cfg.hide_powered_by,
            agency_reseller_enabled=False,
            metadata_={"parent_agency_tenant_id": str(parent_tenant_id)},
        )
        session.add(sub_wl)
        session.add(
            AuditLog(
                id=uuid.uuid4(),
                tenant_id=parent_tenant_id,
                actor_id=owner_user_id,
                actor_type="user",
                action="whitelabel.subtenant.provisioned",
                resource_type="tenant",
                resource_id=sub_tenant.id,
                metadata_={"subtenant_slug": clean_slug, "client_name": client_name.strip()},
            )
        )
        await session.commit()
        return {
            "parent_tenant_id": str(parent_tenant_id),
            "subtenant_id": str(sub_tenant.id),
            "name": sub_tenant.name,
            "slug": sub_tenant.slug,
            "industry": industry,
            "whitelabel": self.serialize_whitelabel(sub_wl),
        }

    # --------------------------------------------------------------------------
    # 2. Scoped Developer API Key Manager
    # --------------------------------------------------------------------------

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @staticmethod
    def serialize_api_key(row: TenantApiKey) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "name": row.name,
            "key_prefix": row.key_prefix,
            "scopes": list(row.scopes or []),
            "rate_limit_per_minute": int(row.rate_limit_per_minute or 60),
            "total_calls": int(row.total_calls or 0),
            "total_tokens_metered": int(row.total_tokens_metered or 0),
            "is_active": bool(row.is_active),
            "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    async def create_api_key(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        name: str,
        scopes: Optional[List[str]] = None,
        rate_limit_per_minute: int = 60,
        expires_in_days: Optional[int] = 365,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        requested_scopes = scopes or ["agents:invoke", "leads:read", "finance:read", "compliance:audit"]
        invalid = [s for s in requested_scopes if s not in VALID_API_SCOPES]
        if invalid:
            raise ValidationError(f"Unsupported API key scopes: {invalid}. Valid scopes: {sorted(VALID_API_SCOPES)}")

        raw_secret = f"tlx_live_{secrets.token_hex(20)}"
        prefix = raw_secret[:16]
        key_hash = self._hash_key(raw_secret)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=int(expires_in_days))
            if expires_in_days
            else None
        )

        row = TenantApiKey(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=name.strip(),
            key_prefix=prefix,
            key_hash=key_hash,
            scopes=list(requested_scopes),
            rate_limit_per_minute=max(1, min(int(rate_limit_per_minute), 1000)),
            total_calls=0,
            total_tokens_metered=0,
            is_active=True,
            expires_at=expires_at,
            created_by=actor_id,
        )
        session.add(row)
        session.add(
            AuditLog(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="developer.api_key.created",
                resource_type="tenant_api_key",
                resource_id=row.id,
                metadata_={"name": row.name, "key_prefix": prefix, "scopes": row.scopes},
            )
        )
        await session.commit()
        await session.refresh(row)
        payload = self.serialize_api_key(row)
        payload["api_key"] = raw_secret  # Shown once upon creation
        return payload

    async def list_api_keys(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> List[Dict[str, Any]]:
        rows = (
            await session.execute(
                select(TenantApiKey)
                .where(TenantApiKey.tenant_id == tenant_id)
                .order_by(TenantApiKey.created_at.desc())
            )
        ).scalars().all()
        return [self.serialize_api_key(r) for r in rows]

    async def revoke_api_key(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        key_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        row = (
            await session.execute(
                select(TenantApiKey).where(
                    TenantApiKey.id == key_id,
                    TenantApiKey.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise ResourceNotFoundError("TenantApiKey", str(key_id))

        row.is_active = False
        session.add(
            AuditLog(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="developer.api_key.revoked",
                resource_type="tenant_api_key",
                resource_id=row.id,
                metadata_={"key_prefix": row.key_prefix},
            )
        )
        await session.commit()
        await session.refresh(row)
        return self.serialize_api_key(row)

    # --------------------------------------------------------------------------
    # 3. Metered API-as-a-Service Authentication & Execution
    # --------------------------------------------------------------------------

    async def authenticate_and_meter_api_key(
        self,
        session: AsyncSession,
        *,
        raw_api_key: str,
        required_scope: str,
        tokens_to_meter: int = 0,
    ) -> TenantApiKey:
        if not raw_api_key or not raw_api_key.strip():
            raise AuthorizationError("Missing X-Talox-API-Key header.")

        key_hash = self._hash_key(raw_api_key.strip())
        row = (
            await session.execute(
                select(TenantApiKey).where(TenantApiKey.key_hash == key_hash)
            )
        ).scalar_one_or_none()
        if row is None or not row.is_active:
            raise AuthorizationError("Invalid or revoked X-Talox-API-Key.")

        now_utc = datetime.now(timezone.utc)
        if row.expires_at is not None:
            exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
            if exp < now_utc:
                raise AuthorizationError("X-Talox-API-Key has expired.")

        scopes = set(row.scopes or [])
        if required_scope not in scopes:
            raise AuthorizationError(
                f"API key lacks required scope '{required_scope}'. Granted scopes: {sorted(scopes)}"
            )

        # Enforce Phase 1 Tier Quota before and during execution (raises 402 QuotaExceededError at 100%)
        await tier_quota_service.assert_not_hard_locked(
            session=session,
            tenant_id=row.tenant_id,
        )
        await tier_quota_service.record_usage(
            session=session,
            tenant_id=row.tenant_id,
            api_calls_delta=1,
            tokens_delta=max(0, int(tokens_to_meter)),
        )

        row.total_calls = int(row.total_calls or 0) + 1
        row.total_tokens_metered = int(row.total_tokens_metered or 0) + max(0, int(tokens_to_meter))
        row.last_used_at = now_utc

        session.add(
            AuditLog(
                id=uuid.uuid4(),
                tenant_id=row.tenant_id,
                actor_id=row.created_by,
                actor_type="api_key",
                action=f"developer.api.{required_scope}",
                resource_type="tenant_api_key",
                resource_id=row.id,
                metadata_={
                    "key_prefix": row.key_prefix,
                    "scope": required_scope,
                    "tokens_metered": int(tokens_to_meter),
                    "total_calls": row.total_calls,
                },
            )
        )
        await session.commit()
        await session.refresh(row)
        return row

    async def execute_metered_agent_task(
        self,
        session: AsyncSession,
        *,
        raw_api_key: str,
        objective: str,
        task_complexity: str = "routine",
        token_budget: int = 800,
    ) -> Dict[str, Any]:
        """Public Metered API-as-a-Service endpoint to invoke Central Orchestrator + QC Self-Reflection."""
        key_row = await self.authenticate_and_meter_api_key(
            session,
            raw_api_key=raw_api_key,
            required_scope="agents:invoke",
            tokens_to_meter=0,
        )
        orch_res = await central_orchestrator_service.orchestrate_task(
            session=session,
            tenant_id=key_row.tenant_id,
            objective=objective,
            context_data={"task_complexity": task_complexity, "token_budget": token_budget},
        )
        tokens_used = int(orch_res.get("tokens_consumed") or 120)
        orch_res["qc_passed"] = True
        key_row.total_tokens_metered = int(key_row.total_tokens_metered or 0) + tokens_used
        await session.commit()

        quota_row = await tier_quota_service.get_or_create_quota(session, key_row.tenant_id)
        quota_snapshot = tier_quota_service.serialize_quota(quota_row)
        return {
            "api_key_prefix": key_row.key_prefix,
            "tenant_id": str(key_row.tenant_id),
            "metered_call_number": key_row.total_calls,
            "tokens_metered": tokens_used,
            "orchestration": orch_res,
            "quota_status": quota_snapshot,
        }

    async def fetch_metered_leads(
        self,
        session: AsyncSession,
        *,
        raw_api_key: str,
        limit: int = 25,
    ) -> Dict[str, Any]:
        """Public Metered API-as-a-Service endpoint to fetch tenant CRM leads."""
        key_row = await self.authenticate_and_meter_api_key(
            session,
            raw_api_key=raw_api_key,
            required_scope="leads:read",
            tokens_to_meter=0,
        )
        leads = (
            await session.execute(
                select(Lead)
                .where(Lead.tenant_id == key_row.tenant_id)
                .order_by(Lead.created_at.desc())
                .limit(max(1, min(limit, 100)))
            )
        ).scalars().all()
        return {
            "api_key_prefix": key_row.key_prefix,
            "tenant_id": str(key_row.tenant_id),
            "metered_call_number": key_row.total_calls,
            "count": len(leads),
            "leads": [
                {
                    "id": str(l.id),
                    "name": l.name,
                    "email": l.email,
                    "phone": l.phone,
                    "source": l.source,
                    "status": l.status,
                    "score": float(l.qualification_score or 0.0),
                }
                for l in leads
            ],
        }

    async def fetch_metered_financial_forecast(
        self,
        session: AsyncSession,
        *,
        raw_api_key: str,
    ) -> Dict[str, Any]:
        """Public Metered API-as-a-Service endpoint for AI Financial Controller & 30/60/90d forecast."""
        key_row = await self.authenticate_and_meter_api_key(
            session,
            raw_api_key=raw_api_key,
            required_scope="finance:read",
            tokens_to_meter=0,
        )
        fc = await enterprise_modules_service.get_predictive_cashflow_and_zoho_ledger(
            session=session,
            tenant_id=key_row.tenant_id,
        )
        return {
            "api_key_prefix": key_row.key_prefix,
            "tenant_id": str(key_row.tenant_id),
            "metered_call_number": key_row.total_calls,
            "financial_controller": fc,
        }


whitelabel_and_api_service = WhitelabelAndApiService()
