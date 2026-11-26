"""Phase 1 Tiered Usage & Token Metering Service (`starter`, `growth`, `enterprise`).

Implements:
1. Per-tenant monthly usage tracking across `tokens`, `api_calls`, and `voice_minutes`.
2. Automated Low-Balance Alert at >= 80% consumption of any meter (fires in-app notification + AuditLog).
3. Hard-Lock at >= 100% consumption (`HTTP 402 QUOTA_HARD_LOCKED_UPGRADE_REQUIRED`) with an explicit
   upgrade prompt (`upgrade_url: "/billing"`).
4. Seamless tier upgrade (`starter -> growth -> enterprise`) that raises limits and unlocks `hard_locked_100`.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.exceptions import TaloxException
from app.database.models.automation import AuditLog
from app.database.models.governance import TenantTierQuota
from app.services.notification_service import notification_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

TIER_LIMIT_PRESETS: Dict[str, Dict[str, Any]] = {
    "starter": {
        "tokens_limit": 100000,
        "api_calls_limit": 2500,
        "voice_minutes_limit": 60.0,
    },
    "growth": {
        "tokens_limit": 500000,
        "api_calls_limit": 15000,
        "voice_minutes_limit": 300.0,
    },
    "enterprise": {
        "tokens_limit": 2500000,
        "api_calls_limit": 100000,
        "voice_minutes_limit": 1500.0,
    },
}


def _current_month_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _normalize_tier(raw: Optional[str]) -> str:
    val = (raw or "starter").strip().lower()
    if "ent" in val or "scale" in val:
        return "enterprise"
    if "grow" in val or "pro" in val:
        return "growth"
    return "starter"


class TierQuotaService:
    """Manages per-tenant tiered usage limits, 80% alerts, and 100% hard-locks."""

    @staticmethod
    def serialize_quota(row: TenantTierQuota) -> Dict[str, Any]:
        tok_pct = round((int(row.tokens_used) / max(1, int(row.tokens_limit))) * 100.0, 2)
        api_pct = round((int(row.api_calls_used) / max(1, int(row.api_calls_limit))) * 100.0, 2)
        voice_pct = round((float(row.voice_minutes_used) / max(0.01, float(row.voice_minutes_limit))) * 100.0, 2)
        peak_pct = max(tok_pct, api_pct, voice_pct)
        return {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "tier": row.tier,
            "period_month": row.period_month,
            "tokens_limit": int(row.tokens_limit),
            "tokens_used": int(row.tokens_used),
            "tokens_percent": tok_pct,
            "api_calls_limit": int(row.api_calls_limit),
            "api_calls_used": int(row.api_calls_used),
            "api_calls_percent": api_pct,
            "voice_minutes_limit": round(float(row.voice_minutes_limit), 2),
            "voice_minutes_used": round(float(row.voice_minutes_used), 2),
            "voice_minutes_percent": voice_pct,
            "peak_usage_percent": peak_pct,
            "alert_80_triggered": bool(row.alert_80_triggered),
            "alert_80_notified_at": row.alert_80_notified_at.isoformat() if row.alert_80_notified_at else None,
            "hard_locked_100": bool(row.hard_locked_100),
            "hard_locked_at": row.hard_locked_at.isoformat() if row.hard_locked_at else None,
            "upgrade_required": bool(row.hard_locked_100),
            "upgrade_url": "/billing",
            "upgrade_prompt": (
                f"Your {row.tier.title()} plan has reached 100% of its monthly quota. "
                "Upgrade your subscription tier on /billing to unlock higher limits immediately."
                if row.hard_locked_100
                else None
            ),
        }

    async def get_or_create_quota(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        default_tier: str = "starter",
    ) -> TenantTierQuota:
        res = await session.execute(
            select(TenantTierQuota).where(TenantTierQuota.tenant_id == tenant_id)
        )
        row = res.scalar_one_or_none()
        month = _current_month_utc()
        if not row:
            norm_tier = _normalize_tier(default_tier)
            preset = TIER_LIMIT_PRESETS[norm_tier]
            row = TenantTierQuota(
                tenant_id=tenant_id,
                tier=norm_tier,
                period_month=month,
                tokens_limit=int(preset["tokens_limit"]),
                tokens_used=0,
                api_calls_limit=int(preset["api_calls_limit"]),
                api_calls_used=0,
                voice_minutes_limit=float(preset["voice_minutes_limit"]),
                voice_minutes_used=0.0,
                alert_80_triggered=False,
                hard_locked_100=False,
            )
            session.add(row)
            await session.flush()
            return row

        if row.period_month != month:
            row.period_month = month
            row.tokens_used = 0
            row.api_calls_used = 0
            row.voice_minutes_used = 0.0
            row.alert_80_triggered = False
            row.alert_80_notified_at = None
            row.hard_locked_100 = False
            row.hard_locked_at = None
            await session.flush()
        return row

    async def assert_not_hard_locked(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> TenantTierQuota:
        """Raise HTTP 402 with an explicit upgrade prompt if the tenant has hit 100% of their tier quota."""
        row = await self.get_or_create_quota(session, tenant_id)
        if row.hard_locked_100:
            raise TaloxException(
                message=(
                    f"100% of your {row.tier.title()} tier quota has been reached. "
                    "Execution is hard-locked. Please upgrade your subscription tier at /billing to continue."
                ),
                code="QUOTA_HARD_LOCKED_UPGRADE_REQUIRED",
                status_code=402,
                details=self.serialize_quota(row),
            )
        return row

    async def record_usage(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        tokens_delta: int = 0,
        api_calls_delta: int = 0,
        voice_minutes_delta: float = 0.0,
        enforce_lock_before: bool = True,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Increment tenant usage counters, trigger 80% low-balance alert, and hard-lock at 100%."""
        row = await self.get_or_create_quota(session, tenant_id)
        if enforce_lock_before and row.hard_locked_100:
            raise TaloxException(
                message=(
                    f"100% of your {row.tier.title()} tier quota has been reached. "
                    "Execution is hard-locked. Please upgrade your subscription tier at /billing to continue."
                ),
                code="QUOTA_HARD_LOCKED_UPGRADE_REQUIRED",
                status_code=402,
                details=self.serialize_quota(row),
            )

        row.tokens_used = int(row.tokens_used or 0) + max(0, int(tokens_delta))
        row.api_calls_used = int(row.api_calls_used or 0) + max(0, int(api_calls_delta))
        row.voice_minutes_used = round(float(row.voice_minutes_used or 0.0) + max(0.0, float(voice_minutes_delta)), 2)

        tok_ratio = int(row.tokens_used) / max(1, int(row.tokens_limit))
        api_ratio = int(row.api_calls_used) / max(1, int(row.api_calls_limit))
        voice_ratio = float(row.voice_minutes_used) / max(0.01, float(row.voice_minutes_limit))
        peak_ratio = max(tok_ratio, api_ratio, voice_ratio)
        now = datetime.now(timezone.utc)

        # 80% Low-Balance Alert Trigger
        if peak_ratio >= 0.80 and not row.alert_80_triggered:
            row.alert_80_triggered = True
            row.alert_80_notified_at = now
            session.add(
                AuditLog(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    actor_type="user" if actor_id else "system",
                    action="quota.threshold_80_reached",
                    resource_type="tenant_tier_quota",
                    resource_id=row.id,
                    metadata_={
                        "tier": row.tier,
                        "peak_usage_percent": round(peak_ratio * 100.0, 2),
                        "tokens_used": int(row.tokens_used),
                        "api_calls_used": int(row.api_calls_used),
                        "voice_minutes_used": float(row.voice_minutes_used),
                    },
                )
            )
            await notification_service.send_notification(
                session=session,
                tenant_id=tenant_id,
                title=f"80% {row.tier.title()} Tier Quota Alert",
                message=(
                    f"Your workspace has consumed {round(peak_ratio * 100.0, 1)}% of its {row.tier.title()} monthly quota. "
                    "Upgrade on /billing before reaching 100% to prevent automated execution locks."
                ),
                channel="in_app",
            )

        # 100% Hard-Lock Trigger
        if peak_ratio >= 1.00 and not row.hard_locked_100:
            row.hard_locked_100 = True
            row.hard_locked_at = now
            session.add(
                AuditLog(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    actor_type="user" if actor_id else "system",
                    action="quota.hard_locked_100",
                    resource_type="tenant_tier_quota",
                    resource_id=row.id,
                    metadata_={
                        "tier": row.tier,
                        "peak_usage_percent": round(peak_ratio * 100.0, 2),
                        "upgrade_url": "/billing",
                    },
                )
            )
            await notification_service.send_notification(
                session=session,
                tenant_id=tenant_id,
                title=f"100% Quota Reached — {row.tier.title()} Plan Hard-Locked",
                message=(
                    f"Your {row.tier.title()} plan has reached 100% usage and automated executions are paused. "
                    "Upgrade your tier at /billing to unlock immediately."
                ),
                channel="in_app",
            )

        await session.commit()
        await session.refresh(row)
        return self.serialize_quota(row)

    async def set_tenant_tier(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        new_tier: str,
        *,
        custom_limits: Optional[Dict[str, Any]] = None,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Upgrade/change tenant subscription tier and unlock hard-lock if below new limits."""
        norm_tier = _normalize_tier(new_tier)
        preset = dict(TIER_LIMIT_PRESETS[norm_tier])
        if custom_limits:
            preset.update(custom_limits)

        row = await self.get_or_create_quota(session, tenant_id, default_tier=norm_tier)
        row.tier = norm_tier
        row.tokens_limit = max(1, int(preset["tokens_limit"]))
        row.api_calls_limit = max(1, int(preset["api_calls_limit"]))
        row.voice_minutes_limit = max(1.0, float(preset["voice_minutes_limit"]))

        tok_ratio = int(row.tokens_used) / max(1, int(row.tokens_limit))
        api_ratio = int(row.api_calls_used) / max(1, int(row.api_calls_limit))
        voice_ratio = float(row.voice_minutes_used) / max(0.01, float(row.voice_minutes_limit))
        peak_ratio = max(tok_ratio, api_ratio, voice_ratio)

        if peak_ratio < 1.00:
            row.hard_locked_100 = False
            row.hard_locked_at = None
        if peak_ratio < 0.80:
            row.alert_80_triggered = False
            row.alert_80_notified_at = None

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user" if actor_id else "system",
                action="quota.tier_updated",
                resource_type="tenant_tier_quota",
                resource_id=row.id,
                metadata_={
                    "tier": norm_tier,
                    "tokens_limit": row.tokens_limit,
                    "api_calls_limit": row.api_calls_limit,
                    "voice_minutes_limit": float(row.voice_minutes_limit),
                    "hard_locked_100": row.hard_locked_100,
                },
            )
        )
        await session.commit()
        await session.refresh(row)
        return self.serialize_quota(row)


tier_quota_service = TierQuotaService()
