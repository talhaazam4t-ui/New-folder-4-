"""Prepaid Credit Wallet, Usage Ledger & 7-Day Free Trial Service.

Implements:
1. `tenant_wallets` management with configurable low-balance alerts & auto-pause protection.
2. Idempotent `usage_ledger` accounting across AI calls, WhatsApp messages, lead scrapes, and outreach.
3. 7-Day Free Trial / Free Audit funnel with 100 starter credits and automatic cron expiration.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.exceptions import ResourceNotFoundError, TaloxException
from app.core.logging import logger
from app.database.models.automation import AuditLog
from app.database.models.billing import Payment, TenantWallet, UsageLedger
from app.database.models.service import ServiceSubscription
from app.database.models.tenant import Tenant
from app.services.notification_service import notification_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

CREDIT_RATES: Dict[str, float] = {
    "ai_call_minute": 5.0,
    "whatsapp_message": 1.0,
    "lead_scrape": 2.0,
    "outreach_dispatch": 1.0,
}

TRIAL_GRANT_CREDITS = 100.0
TRIAL_DURATION_DAYS = 7
PLAN_ACTIVATION_BONUS_CREDITS = 500.0

CREDIT_PACKS: List[Dict[str, Any]] = [
    {
        "pack_id": "pack_starter",
        "name": "Starter Top-Up (250 Credits)",
        "credits": 250.0,
        "amount_usd": 25.0,
        "amount_pkr": 7000.0,
        "description": "Ideal for testing outbound campaigns, WhatsApp replies, and voice call minutes.",
    },
    {
        "pack_id": "pack_growth",
        "name": "Growth Top-Up (1,000 Credits)",
        "credits": 1000.0,
        "amount_usd": 89.0,
        "amount_pkr": 24900.0,
        "description": "Best value for active AI Receptionist, Lead Discovery, and Omnichannel Concierge.",
    },
    {
        "pack_id": "pack_scale",
        "name": "Scale Agency Pack (3,000 Credits)",
        "credits": 3000.0,
        "amount_usd": 229.0,
        "amount_pkr": 64000.0,
        "description": "High-volume credit reserve for multi-channel sales agencies and clinics.",
    },
]


def get_credit_pack(pack_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not pack_id:
        return None
    target = pack_id.strip().lower()
    for pack in CREDIT_PACKS:
        if pack["pack_id"] == target:
            return pack
    return None


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize SQLite naive or tz-aware datetimes into UTC-aware datetimes."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso_utc(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return _ensure_utc(parsed)
    except Exception:
        return None


class WalletService:
    """Manages prepaid credit wallets, metered usage deductions, and 7-day free trials."""

    async def get_or_create_wallet(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> TenantWallet:
        res = await session.execute(
            select(TenantWallet).where(TenantWallet.tenant_id == tenant_id)
        )
        wallet = res.scalar_one_or_none()
        if wallet:
            return wallet

        wallet = TenantWallet(
            tenant_id=tenant_id,
            balance_credits=0.0,
            reserved_credits=0.0,
            currency="USD",
            low_balance_threshold=25.0,
            auto_pause_enabled=False,
            is_paused=False,
            lifetime_credited=0.0,
            lifetime_debited=0.0,
        )
        session.add(wallet)
        await session.flush()
        return wallet

    def get_trial_state(self, tenant: Optional[Tenant]) -> Dict[str, Any]:
        settings_map = dict(tenant.settings or {}) if tenant else {}
        trial_used = bool(settings_map.get("trial_used", False))
        trial_active = bool(settings_map.get("trial_active", False))
        trial_expired = bool(settings_map.get("trial_expired", False))
        started_raw = settings_map.get("trial_started_at")
        ends_raw = settings_map.get("trial_ends_at")
        ends_dt = _parse_iso_utc(ends_raw)
        days_remaining = 0
        if trial_active and ends_dt:
            delta_sec = (ends_dt - datetime.now(timezone.utc)).total_seconds()
            days_remaining = max(0, int((delta_sec + 86399) // 86400)) if delta_sec > 0 else 0

        return {
            "trial_used": trial_used,
            "trial_active": trial_active,
            "trial_expired": trial_expired,
            "trial_started_at": started_raw,
            "trial_ends_at": ends_raw,
            "trial_days_remaining": days_remaining,
            "trial_grant_credits": TRIAL_GRANT_CREDITS,
            "trial_duration_days": TRIAL_DURATION_DAYS,
        }

    def _serialize_wallet(self, wallet: TenantWallet) -> Dict[str, Any]:
        return {
            "id": str(wallet.id),
            "tenant_id": str(wallet.tenant_id),
            "balance_credits": round(float(wallet.balance_credits or 0.0), 2),
            "reserved_credits": round(float(wallet.reserved_credits or 0.0), 2),
            "currency": wallet.currency,
            "low_balance_threshold": round(float(wallet.low_balance_threshold or 25.0), 2),
            "auto_pause_enabled": bool(wallet.auto_pause_enabled),
            "is_paused": bool(wallet.is_paused),
            "low_balance_alert": bool(
                wallet.auto_pause_enabled
                and float(wallet.balance_credits or 0.0) <= float(wallet.low_balance_threshold or 25.0)
            ),
            "lifetime_credited": round(float(wallet.lifetime_credited or 0.0), 2),
            "lifetime_debited": round(float(wallet.lifetime_debited or 0.0), 2),
            "updated_at": wallet.updated_at.isoformat() if wallet.updated_at else None,
        }

    def _serialize_ledger_row(self, row: UsageLedger) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "entry_type": row.entry_type,
            "category": row.category,
            "credits_delta": round(float(row.credits_delta), 2),
            "balance_after": round(float(row.balance_after), 2),
            "unit_count": float(row.unit_count),
            "unit_cost": float(row.unit_cost),
            "reference_id": row.reference_id,
            "description": row.description,
            "metadata": row.metadata_ or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    async def get_wallet_summary(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        ledger_limit: int = 50,
    ) -> Dict[str, Any]:
        wallet = await self.get_or_create_wallet(session, tenant_id)
        t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = t_res.scalar_one_or_none()
        ledger_res = await session.execute(
            select(UsageLedger)
            .where(UsageLedger.tenant_id == tenant_id)
            .order_by(UsageLedger.created_at.desc())
            .limit(ledger_limit)
        )
        entries = [self._serialize_ledger_row(r) for r in ledger_res.scalars().all()]
        await session.commit()
        return {
            "wallet": self._serialize_wallet(wallet),
            "credit_rates": CREDIT_RATES,
            "credit_packs": CREDIT_PACKS,
            "trial": self.get_trial_state(tenant),
            "ledger": entries,
        }

    async def update_wallet_settings(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        low_balance_threshold: Optional[float] = None,
        auto_pause_enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        wallet = await self.get_or_create_wallet(session, tenant_id)
        if low_balance_threshold is not None:
            wallet.low_balance_threshold = max(0.0, round(float(low_balance_threshold), 2))
        if auto_pause_enabled is not None:
            wallet.auto_pause_enabled = bool(auto_pause_enabled)
            if not wallet.auto_pause_enabled:
                wallet.is_paused = False
            elif float(wallet.balance_credits or 0.0) <= 0.0:
                wallet.is_paused = True

        await session.commit()
        await session.refresh(wallet)
        return self._serialize_wallet(wallet)

    async def credit_wallet(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        credits: float,
        category: str,
        description: str,
        entry_type: str = "credit",
        reference_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        enable_auto_pause: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Credit a tenant wallet idempotently and record a ledger row."""
        wallet = await self.get_or_create_wallet(session, tenant_id)
        clean_credits = round(max(0.0, float(credits)), 2)

        if reference_id:
            dup_res = await session.execute(
                select(UsageLedger).where(
                    UsageLedger.tenant_id == tenant_id,
                    UsageLedger.reference_id == reference_id,
                )
            )
            existing_entry = dup_res.scalar_one_or_none()
            if existing_entry:
                return {
                    "idempotent": True,
                    "credits_added": 0.0,
                    "wallet": self._serialize_wallet(wallet),
                    "ledger_entry": self._serialize_ledger_row(existing_entry),
                }

        new_balance = round(float(wallet.balance_credits or 0.0) + clean_credits, 2)
        wallet.balance_credits = new_balance
        wallet.lifetime_credited = round(float(wallet.lifetime_credited or 0.0) + clean_credits, 2)
        if enable_auto_pause is not None:
            wallet.auto_pause_enabled = bool(enable_auto_pause)
        if new_balance > 0.0:
            wallet.is_paused = False
        if new_balance > float(wallet.low_balance_threshold or 25.0):
            wallet.low_balance_notified_at = None

        entry = UsageLedger(
            tenant_id=tenant_id,
            wallet_id=wallet.id,
            entry_type=entry_type,
            category=category,
            credits_delta=clean_credits,
            balance_after=new_balance,
            unit_count=1.0,
            unit_cost=clean_credits,
            reference_id=reference_id,
            description=description,
            metadata_=dict(metadata or {}),
        )
        session.add(entry)
        await session.commit()
        await session.refresh(wallet)
        await session.refresh(entry)
        return {
            "idempotent": False,
            "credits_added": clean_credits,
            "wallet": self._serialize_wallet(wallet),
            "ledger_entry": self._serialize_ledger_row(entry),
        }

    async def assert_wallet_active(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        estimated_credits: float = 1.0,
    ) -> TenantWallet:
        """Guard paid metered actions when auto-pause is active and credits are exhausted."""
        wallet = await self.get_or_create_wallet(session, tenant_id)
        bal = float(wallet.balance_credits or 0.0)
        if wallet.is_paused or (wallet.auto_pause_enabled and bal < float(estimated_credits)):
            if wallet.auto_pause_enabled and not wallet.is_paused:
                wallet.is_paused = True
                await session.commit()
            raise TaloxException(
                message=(
                    "Insufficient prepaid credits — workspace automation has been auto-paused. "
                    "Top up credits on /billing to resume immediately."
                ),
                code="INSUFFICIENT_CREDITS",
                status_code=402,
                details={
                    "balance_credits": round(bal, 2),
                    "required_credits": float(estimated_credits),
                    "is_paused": True,
                },
            )
        return wallet

    async def debit_credits(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        category: str,
        unit_count: float = 1.0,
        description: str = "",
        reference_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        enforce_pause: bool = True,
    ) -> Dict[str, Any]:
        """Deduct metered usage credits, trigger low-balance alerts, and auto-pause at zero."""
        wallet = await self.get_or_create_wallet(session, tenant_id)

        if reference_id:
            dup_res = await session.execute(
                select(UsageLedger).where(
                    UsageLedger.tenant_id == tenant_id,
                    UsageLedger.reference_id == reference_id,
                )
            )
            existing_entry = dup_res.scalar_one_or_none()
            if existing_entry:
                return {
                    "idempotent": True,
                    "credits_deducted": 0.0,
                    "wallet": self._serialize_wallet(wallet),
                    "ledger_entry": self._serialize_ledger_row(existing_entry),
                }

        rate = float(CREDIT_RATES.get(category, 1.0))
        units = max(0.0, float(unit_count))
        cost = round(units * rate, 2)
        current_bal = float(wallet.balance_credits or 0.0)

        if enforce_pause and (wallet.is_paused or (wallet.auto_pause_enabled and current_bal < cost)):
            if wallet.auto_pause_enabled and not wallet.is_paused:
                wallet.is_paused = True
                await session.commit()
            raise TaloxException(
                message=(
                    "Insufficient prepaid credits — workspace automation has been auto-paused. "
                    "Top up credits on /billing to resume immediately."
                ),
                code="INSUFFICIENT_CREDITS",
                status_code=402,
                details={
                    "balance_credits": round(current_bal, 2),
                    "required_credits": cost,
                    "category": category,
                    "is_paused": True,
                },
            )

        new_balance = round(max(0.0, current_bal - cost), 2)
        wallet.balance_credits = new_balance
        wallet.lifetime_debited = round(float(wallet.lifetime_debited or 0.0) + cost, 2)

        hit_zero_pause = False
        if wallet.auto_pause_enabled and new_balance <= 0.0:
            wallet.is_paused = True
            hit_zero_pause = True

        should_alert_low = False
        now_utc = datetime.now(timezone.utc)
        threshold = float(wallet.low_balance_threshold or 25.0)
        if wallet.auto_pause_enabled and new_balance <= threshold:
            last_alert = _ensure_utc(wallet.low_balance_notified_at)
            if last_alert is None or (now_utc - last_alert) >= timedelta(hours=12):
                wallet.low_balance_notified_at = now_utc
                should_alert_low = True

        entry = UsageLedger(
            tenant_id=tenant_id,
            wallet_id=wallet.id,
            entry_type="debit",
            category=category,
            credits_delta=-cost,
            balance_after=new_balance,
            unit_count=units,
            unit_cost=rate,
            reference_id=reference_id,
            description=description or f"Metered usage: {category} ({units}x)",
            metadata_=dict(metadata or {}),
        )
        session.add(entry)
        await session.commit()
        await session.refresh(wallet)
        await session.refresh(entry)

        if hit_zero_pause or should_alert_low:
            title = (
                "Credit Wallet Exhausted — Automation Auto-Paused"
                if hit_zero_pause
                else f"Low Credit Balance Alert ({new_balance:.0f} Credits Left)"
            )
            msg = (
                "Your prepaid credit balance reached 0. Paid outbound sends and calls are paused until you top up on /billing."
                if hit_zero_pause
                else f"Your credit wallet dropped to {new_balance:.2f} credits (below threshold {threshold:.0f}). Top up soon to avoid interruption."
            )
            await notification_service.send_notification(
                session=session,
                tenant_id=tenant_id,
                title=title,
                message=msg,
                channel="in_app",
            )

        return {
            "idempotent": False,
            "credits_deducted": cost,
            "wallet": self._serialize_wallet(wallet),
            "ledger_entry": self._serialize_ledger_row(entry),
        }

    async def start_free_trial(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Activate a 7-Day Free Trial / Free Audit with 100 starter credits and metered auto-pause."""
        res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = res.scalar_one_or_none()
        if not tenant:
            raise ResourceNotFoundError("Tenant", str(tenant_id))

        curr_settings = dict(tenant.settings or {})
        if curr_settings.get("trial_used"):
            raise TaloxException(
                message="Free trial has already been claimed for this workspace.",
                code="TRIAL_ALREADY_USED",
                status_code=409,
            )

        now_utc = datetime.now(timezone.utc)
        ends_utc = now_utc + timedelta(days=TRIAL_DURATION_DAYS)
        curr_settings.update(
            {
                "trial_used": True,
                "trial_active": True,
                "trial_expired": False,
                "trial_started_at": now_utc.isoformat(),
                "trial_ends_at": ends_utc.isoformat(),
                "payment_approved": True,
                "automation_approved_by_owner": True,
            }
        )
        tenant.settings = curr_settings
        tenant.status = "active"

        subs_res = await session.execute(
            select(ServiceSubscription).where(ServiceSubscription.tenant_id == tenant_id)
        )
        for sub in subs_res.scalars().all():
            if sub.status != "canceled":
                sub.status = "active"
                if sub.expires_at is None or _ensure_utc(sub.expires_at) < ends_utc:
                    sub.expires_at = ends_utc

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=user_id,
                actor_type="user",
                action="tenant.free_trial_started",
                resource_type="tenant",
                resource_id=tenant_id,
                metadata_={
                    "trial_days": TRIAL_DURATION_DAYS,
                    "grant_credits": TRIAL_GRANT_CREDITS,
                    "ends_at": ends_utc.isoformat(),
                },
            )
        )
        await session.commit()

        grant = await self.credit_wallet(
            session=session,
            tenant_id=tenant_id,
            credits=TRIAL_GRANT_CREDITS,
            category="trial_grant",
            description=f"{TRIAL_DURATION_DAYS}-Day Free Trial & AI Audit starter credits",
            entry_type="trial_grant",
            reference_id=f"trial_grant:{tenant_id}",
            metadata={"trial_ends_at": ends_utc.isoformat()},
            enable_auto_pause=True,
        )

        await notification_service.send_notification(
            session=session,
            tenant_id=tenant_id,
            title="7-Day Free Trial Activated (100 Credits Added)",
            message=(
                f"Your {TRIAL_DURATION_DAYS}-day free trial is live until {ends_utc.strftime('%Y-%m-%d %H:%M UTC')}. "
                "Explore AI Receptionist calls, lead discovery, and WhatsApp automations!"
            ),
            channel="in_app",
            user_id=user_id,
        )

        summary = await self.get_wallet_summary(session, tenant_id)
        summary["grant"] = grant
        return summary

    async def expire_elapsed_trials(self, session: AsyncSession) -> Dict[str, Any]:
        """Cron/worker sweep: expire 7-day trials whose window elapsed without a completed payment."""
        res = await session.execute(select(Tenant).where(Tenant.status == "active"))
        tenants = res.scalars().all()
        now_utc = datetime.now(timezone.utc)

        checked = 0
        expired_count = 0
        graduated_count = 0

        for tenant in tenants:
            settings_map = dict(tenant.settings or {})
            if not settings_map.get("trial_active"):
                continue
            checked += 1

            ends_dt = _parse_iso_utc(settings_map.get("trial_ends_at"))
            if ends_dt is None or ends_dt > now_utc:
                continue

            pay_res = await session.execute(
                select(Payment.id)
                .where(Payment.tenant_id == tenant.id, Payment.status == "completed")
                .limit(1)
            )
            has_paid = pay_res.scalar_one_or_none() is not None

            if has_paid:
                settings_map["trial_active"] = False
                settings_map["trial_expired"] = False
                tenant.settings = settings_map
                graduated_count += 1
                await session.commit()
                continue

            settings_map["trial_active"] = False
            settings_map["trial_expired"] = True
            settings_map["payment_approved"] = False
            settings_map["automation_approved_by_owner"] = False
            tenant.settings = settings_map
            tenant.status = "pending_approval"

            session.add(
                AuditLog(
                    tenant_id=tenant.id,
                    actor_type="system",
                    action="tenant.free_trial_expired",
                    resource_type="tenant",
                    resource_id=tenant.id,
                    metadata_={"expired_at": now_utc.isoformat()},
                )
            )
            await session.commit()

            await notification_service.send_notification(
                session=session,
                tenant_id=tenant.id,
                title="7-Day Free Trial Ended — Upgrade to Continue",
                message=(
                    "Your 7-day free trial has ended without an active payment. "
                    "Complete checkout on /billing (Lemon Squeezy, PayFast/Safepay PKR, Stripe USD, or Bank Transfer) to reactivate automations."
                ),
                channel="in_app",
            )
            expired_count += 1

        if expired_count or graduated_count:
            logger.info(
                "Trial expiration sweep completed",
                checked=checked,
                expired=expired_count,
                graduated=graduated_count,
            )

        return {
            "checked": checked,
            "expired": expired_count,
            "graduated": graduated_count,
        }


wallet_service = WalletService()
