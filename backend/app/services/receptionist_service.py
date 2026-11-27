"""Office Receptionist (AI Voice Agent) Service — Retell AI, Telnyx, and Cal.com.

Handles:
1. Super Admin encrypted master credentials management (DB vault + env-var fallback).
2. Per-tenant Office Receptionist onboarding configuration, encrypted Cal.com API key storage,
   and automatic Call Forwarding setup guide generation.
3. End-to-end Telnyx number provisioning/assignment + Retell AI Agent creation + Cal.com tools
   + live human/emergency call transfer routing.
4. Inbound Retell AI & Telnyx TeXML Voice webhook processing, Cal.com live function-calling tools,
   and call logs / booked appointments analytics.
"""

import math
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.core.exceptions import ResourceNotFoundError
from app.core.logging import logger
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    encrypt_sensitive_config,
)
from app.database.models.automation import AuditLog
from app.database.models.billing import Payment
from app.database.models.receptionist import (
    PlatformVoiceCredential,
    ReceptionistCallLog,
    ReceptionistConfig,
)
from app.database.models.tenant import Tenant
from app.integrations.voice.receptionist_providers import (
    calcom_adapter,
    generate_call_forwarding_guide,
    normalize_e164,
    retell_ai_adapter,
    telnyx_voice_adapter,
)
from app.schemas.receptionist import (
    AdminVoiceCredentialsUpdateRequest,
    CalComBookToolRequest,
    ReceptionistConfigUpsertRequest,
    ReceptionistFaqsUpdateRequest,
    SimulateVoiceCallRequest,
)
from app.services.billing_service import billing_service
from app.services.notification_service import notification_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _mask_secret(raw: Optional[str]) -> Optional[str]:
    val = (raw or "").strip()
    if not val:
        return None
    if len(val) <= 8:
        return "****"
    return f"{val[:4]}...{val[-4:]}"


class ReceptionistService:
    """Manages Office Receptionist master voice credentials, tenant provisioning, and call logs."""

    async def _resolve_master_credentials(self, session: AsyncSession) -> Dict[str, Any]:
        """Resolve decrypted master credentials from DB vault with env-var fallback (server-side only)."""
        res = await session.execute(select(PlatformVoiceCredential))
        by_provider = {row.provider: row for row in res.scalars().all()}

        def _get_vault_val(provider: str, field: str) -> str:
            row = by_provider.get(provider)
            if not row or not row.encrypted_config:
                return ""
            raw = row.encrypted_config.get(field) or ""
            if not raw:
                return ""
            dec = decrypt_secret(str(raw))
            return (dec or str(raw)).strip()

        retell_api_key = (
            _get_vault_val("retell", "api_key")
            or (settings.retell_api_key or os.environ.get("RETELL_API_KEY") or "").strip()
        )
        retell_webhook_secret = (
            _get_vault_val("retell", "webhook_secret")
            or (settings.retell_webhook_secret or os.environ.get("RETELL_WEBHOOK_SECRET") or "").strip()
        )
        telnyx_api_key = (
            _get_vault_val("telnyx", "api_key")
            or (settings.telnyx_api_key or os.environ.get("TELNYX_API_KEY") or "").strip()
        )
        telnyx_connection_id = (
            _get_vault_val("telnyx", "connection_id")
            or (settings.telnyx_connection_id or os.environ.get("TELNYX_CONNECTION_ID") or "").strip()
        )
        telnyx_default_number = (
            _get_vault_val("telnyx", "default_number")
            or (settings.telnyx_default_number or os.environ.get("TELNYX_DEFAULT_NUMBER") or "").strip()
        )
        telnyx_country = (
            _get_vault_val("telnyx", "default_country")
            or (settings.telnyx_default_country or "US").strip()
        )
        telnyx_sip_username = (
            _get_vault_val("telnyx", "sip_username")
            or (settings.telnyx_sip_username or os.environ.get("TELNYX_SIP_USERNAME") or "").strip()
        )
        telnyx_sip_password = (
            _get_vault_val("telnyx", "sip_password")
            or (settings.telnyx_sip_password or os.environ.get("TELNYX_SIP_PASSWORD") or "").strip()
        )
        calcom_api_key = (
            _get_vault_val("calcom", "api_key")
            or (settings.calcom_api_key or os.environ.get("CALCOM_API_KEY") or "").strip()
        )

        return {
            "retell_api_key": retell_api_key,
            "retell_webhook_secret": retell_webhook_secret,
            "telnyx_api_key": telnyx_api_key,
            "telnyx_connection_id": telnyx_connection_id,
            "telnyx_default_number": telnyx_default_number,
            "telnyx_default_country": telnyx_country or "US",
            "telnyx_sip_username": telnyx_sip_username,
            "telnyx_sip_password": telnyx_sip_password,
            "calcom_api_key": calcom_api_key,
            "sources": {
                "retell": "encrypted_vault"
                if _get_vault_val("retell", "api_key")
                else ("environment" if (settings.retell_api_key or os.environ.get("RETELL_API_KEY")) else "unconfigured"),
                "telnyx": "encrypted_vault"
                if _get_vault_val("telnyx", "api_key")
                else ("environment" if (settings.telnyx_api_key or os.environ.get("TELNYX_API_KEY")) else "unconfigured"),
                "calcom": "encrypted_vault"
                if _get_vault_val("calcom", "api_key")
                else ("environment" if (settings.calcom_api_key or os.environ.get("CALCOM_API_KEY")) else "unconfigured"),
            },
        }

    async def get_admin_voice_credentials_status(self, session: AsyncSession) -> Dict[str, Any]:
        """Return safe masked status of master Retell AI, Telnyx, and Cal.com credentials for Admin Settings."""
        creds = await self._resolve_master_credentials(session)
        return {
            "retell": {
                "configured": bool(creds["retell_api_key"]),
                "source": creds["sources"]["retell"],
                "api_key_masked": _mask_secret(creds["retell_api_key"]),
                "webhook_secret_configured": bool(creds["retell_webhook_secret"]),
            },
            "telnyx": {
                "configured": bool(creds["telnyx_api_key"]),
                "source": creds["sources"]["telnyx"],
                "api_key_masked": _mask_secret(creds["telnyx_api_key"]),
                "connection_id": creds["telnyx_connection_id"] or None,
                "default_number": creds["telnyx_default_number"] or None,
                "default_country": creds["telnyx_default_country"],
            },
            "calcom": {
                "configured": bool(creds["calcom_api_key"]),
                "source": creds["sources"]["calcom"],
                "api_key_masked": _mask_secret(creds["calcom_api_key"]),
            },
        }

    async def upsert_admin_voice_credentials(
        self,
        session: AsyncSession,
        admin_user_id: uuid.UUID,
        request: AdminVoiceCredentialsUpdateRequest,
    ) -> Dict[str, Any]:
        """Encrypt and save master Retell AI, Telnyx, and Cal.com API credentials in the DB vault."""
        updates_by_provider: Dict[str, Dict[str, Any]] = {}
        if request.retell_api_key or request.retell_webhook_secret:
            updates_by_provider["retell"] = {}
            if request.retell_api_key and request.retell_api_key.strip():
                updates_by_provider["retell"]["api_key"] = request.retell_api_key.strip()
            if request.retell_webhook_secret and request.retell_webhook_secret.strip():
                updates_by_provider["retell"]["webhook_secret"] = request.retell_webhook_secret.strip()

        if (
            request.telnyx_api_key
            or request.telnyx_connection_id is not None
            or request.telnyx_default_number is not None
            or request.telnyx_default_country
        ):
            telnyx_patch: Dict[str, Any] = {}
            if request.telnyx_api_key and request.telnyx_api_key.strip():
                telnyx_patch["api_key"] = request.telnyx_api_key.strip()
            if request.telnyx_connection_id and request.telnyx_connection_id.strip():
                telnyx_patch["connection_id"] = request.telnyx_connection_id.strip()
            if request.telnyx_default_number and request.telnyx_default_number.strip():
                telnyx_patch["default_number"] = normalize_e164(request.telnyx_default_number)
            if request.telnyx_default_country and request.telnyx_default_country.strip():
                telnyx_patch["default_country"] = request.telnyx_default_country.strip().upper()
            if telnyx_patch:
                updates_by_provider["telnyx"] = telnyx_patch

        if request.calcom_api_key and request.calcom_api_key.strip():
            updates_by_provider["calcom"] = {"api_key": request.calcom_api_key.strip()}

        for provider_name, raw_fields in updates_by_provider.items():
            res = await session.execute(
                select(PlatformVoiceCredential).where(PlatformVoiceCredential.provider == provider_name)
            )
            row = res.scalar_one_or_none()
            existing_cfg = dict(row.encrypted_config or {}) if row else {}
            enc_patch = encrypt_sensitive_config(raw_fields)
            # Encrypt additional voice-specific secret fields explicitly
            for secret_field in ("webhook_secret", "api_key"):
                if secret_field in raw_fields:
                    enc_patch[secret_field] = encrypt_secret(str(raw_fields[secret_field]))
            merged = {**existing_cfg, **enc_patch}
            if row:
                row.encrypted_config = merged
                row.status = "configured"
                row.updated_by = admin_user_id
            else:
                session.add(
                    PlatformVoiceCredential(
                        provider=provider_name,
                        encrypted_config=merged,
                        status="configured",
                        updated_by=admin_user_id,
                    )
                )

        await session.commit()
        return await self.get_admin_voice_credentials_status(session)

    def _to_config_dict(self, row: ReceptionistConfig) -> Dict[str, Any]:
        return {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "business_name": row.business_name,
            "operating_hours": row.operating_hours,
            "fallback_phone_number": row.fallback_phone_number,
            "greeting_message": row.greeting_message,
            "faqs_knowledge_base": row.faqs_knowledge_base,
            "calcom_booking_url": row.calcom_booking_url,
            "calcom_event_type_id": row.calcom_event_type_id,
            "calcom_api_key_configured": bool(row.encrypted_calcom_api_key),
            "telnyx_phone_number": row.telnyx_phone_number,
            "retell_agent_id": row.retell_agent_id,
            "voice_id": row.voice_id,
            "provisioning_status": row.provisioning_status,
            "provisioning_notes": row.provisioning_notes,
            "call_forwarding_guide": row.call_forwarding_guide or {},
            "updated_at": row.updated_at.isoformat() if row.updated_at else datetime.now(timezone.utc).isoformat(),
        }

    def _to_call_dict(self, row: ReceptionistCallLog) -> Dict[str, Any]:
        meta = dict(row.metadata_ or {})
        intel = meta.get("call_intelligence") or {}
        return {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "external_call_id": row.external_call_id,
            "caller_phone": row.caller_phone,
            "caller_name": row.caller_name,
            "to_number": row.to_number,
            "direction": row.direction,
            "duration_seconds": int(row.duration_seconds or 0),
            "status": row.status,
            "booking_status": row.booking_status,
            "booked_appointment_at": row.booked_appointment_at.isoformat() if row.booked_appointment_at else None,
            "calcom_booking_uid": row.calcom_booking_uid,
            "transferred_to_human": bool(row.transferred_to_human),
            "summary": row.summary,
            "transcript": row.transcript,
            "recording_url": row.recording_url,
            "sentiment": intel.get("sentiment"),
            "lead_tier": intel.get("lead_tier"),
            "lead_score": intel.get("lead_score"),
            "reminder_sent_at": meta.get("reminder_sent_at"),
            "created_at": row.created_at.isoformat() if row.created_at else datetime.now(timezone.utc).isoformat(),
        }

    def _backend_public_url(self) -> str:
        return (
            settings.backend_url
            or settings.frontend_url
            or "https://teloxtech.stream"
        ).rstrip("/")

    async def get_tenant_access_state(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> Dict[str, bool]:
        """Determine whether tenant has active Office Receptionist subscription and approved payment."""
        t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = t_res.scalar_one_or_none()
        t_settings = dict(tenant.settings or {}) if tenant else {}
        raw_payment_approved = t_settings.get("payment_approved")

        completed_pay = await session.execute(
            select(Payment).where(Payment.tenant_id == tenant_id, Payment.status == "completed").limit(1)
        )
        has_completed_payment = completed_pay.scalar_one_or_none() is not None

        if raw_payment_approved is True:
            payment_approved = True
        elif has_completed_payment:
            payment_approved = True
        elif raw_payment_approved is None and tenant is not None and tenant.status == "active":
            payment_approved = True
        else:
            payment_approved = False

        has_subscription = await billing_service.is_service_enabled_for_tenant(
            session, tenant_id, "office-receptionist"
        )
        return {
            "payment_approved": payment_approved,
            "has_subscription": has_subscription,
            "can_provision": bool(payment_approved and has_subscription),
        }

    async def get_config(self, session: AsyncSession, tenant_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id)
        )
        row = res.scalar_one_or_none()
        return self._to_config_dict(row) if row else None

    async def upsert_config(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        request: ReceptionistConfigUpsertRequest,
        is_super_admin: bool = False,
    ) -> Dict[str, Any]:
        """Save client's Office Receptionist onboarding details; provision Telnyx + Retell AI only after payment approval."""
        res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id)
        )
        row = res.scalar_one_or_none()
        norm_fallback = normalize_e164(request.fallback_phone_number)
        encrypted_cal_key = (
            encrypt_secret(request.calcom_api_key.strip())
            if request.calcom_api_key and request.calcom_api_key.strip()
            else None
        )

        if row:
            row.business_name = request.business_name.strip()
            row.operating_hours = request.operating_hours.strip()
            row.fallback_phone_number = norm_fallback
            row.greeting_message = request.greeting_message.strip()
            row.faqs_knowledge_base = request.faqs_knowledge_base.strip()
            row.calcom_booking_url = (request.calcom_booking_url or "").strip() or None
            row.calcom_event_type_id = (request.calcom_event_type_id or "").strip() or None
            if encrypted_cal_key:
                row.encrypted_calcom_api_key = encrypted_cal_key
            if request.voice_id:
                row.voice_id = request.voice_id.strip()
        else:
            row = ReceptionistConfig(
                tenant_id=tenant_id,
                business_name=request.business_name.strip(),
                operating_hours=request.operating_hours.strip(),
                fallback_phone_number=norm_fallback,
                greeting_message=request.greeting_message.strip(),
                faqs_knowledge_base=request.faqs_knowledge_base.strip(),
                calcom_booking_url=(request.calcom_booking_url or "").strip() or None,
                calcom_event_type_id=(request.calcom_event_type_id or "").strip() or None,
                encrypted_calcom_api_key=encrypted_cal_key,
                voice_id=(request.voice_id or "11labs-Adrian").strip(),
                provisioning_status="awaiting_payment",
            )
            session.add(row)

        await session.flush()

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=user_id,
                actor_type="user",
                action="receptionist.config.updated",
                resource_type="receptionist_config",
                resource_id=row.id,
                metadata_={"business_name": row.business_name, "has_calcom_url": bool(row.calcom_booking_url)},
            )
        )
        await session.commit()
        await session.refresh(row)

        access = await self.get_tenant_access_state(session, tenant_id)
        can_provision = is_super_admin or access["can_provision"]

        if request.auto_provision and can_provision:
            return await self.provision_voice_stack(session, tenant_id, user_id)

        if not can_provision:
            if row.provisioning_status != "active":
                row.provisioning_status = "awaiting_payment"
            row.provisioning_notes = (
                "Draft saved. Complete your bank transfer payment on the Dashboard — once Admin confirms "
                "payment, your Telnyx AI phone number and Retell AI voice agent will be provisioned automatically."
            )
            await session.commit()
            await session.refresh(row)
            return self._to_config_dict(row)

        if row.telnyx_phone_number:
            row.call_forwarding_guide = generate_call_forwarding_guide(
                fallback_phone=row.fallback_phone_number,
                assigned_telnyx_number=row.telnyx_phone_number,
                business_name=row.business_name,
            )
            await session.commit()
            await session.refresh(row)
        return self._to_config_dict(row)

    async def update_faqs(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        request: ReceptionistFaqsUpdateRequest,
        is_super_admin: bool = False,
    ) -> Dict[str, Any]:
        """Update client's FAQs/Greeting/Fallback/Cal.com settings and sync to Retell AI if provisioned."""
        res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id)
        )
        row = res.scalar_one_or_none()
        if not row:
            raise ResourceNotFoundError("ReceptionistConfig", str(tenant_id))

        row.faqs_knowledge_base = request.faqs_knowledge_base.strip()
        if request.greeting_message is not None:
            row.greeting_message = request.greeting_message.strip()
        if request.operating_hours is not None:
            row.operating_hours = request.operating_hours.strip()
        if request.fallback_phone_number is not None and request.fallback_phone_number.strip():
            row.fallback_phone_number = normalize_e164(request.fallback_phone_number)
        if request.calcom_booking_url is not None:
            row.calcom_booking_url = request.calcom_booking_url.strip() or None
        if request.calcom_event_type_id is not None:
            row.calcom_event_type_id = request.calcom_event_type_id.strip() or None
        if request.calcom_api_key and request.calcom_api_key.strip():
            row.encrypted_calcom_api_key = encrypt_secret(request.calcom_api_key.strip())

        await session.commit()
        access = await self.get_tenant_access_state(session, tenant_id)
        if is_super_admin or access["can_provision"]:
            return await self.provision_voice_stack(session, tenant_id, user_id)

        await session.refresh(row)
        return self._to_config_dict(row)

    async def provision_voice_stack(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """Provision/sync Telnyx phone number + TeXML Voice Webhooks + Retell AI Agent + Cal.com tools + Call Forwarding guide."""
        res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id)
        )
        row = res.scalar_one_or_none()
        if not row:
            # Create baseline config from tenant profile if admin triggers provision before client form
            t_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
            tenant = t_res.scalar_one_or_none()
            if not tenant:
                raise ResourceNotFoundError("Tenant", str(tenant_id))
            row = ReceptionistConfig(
                tenant_id=tenant_id,
                business_name=tenant.name,
                operating_hours="Mon-Fri 9:00 AM - 6:00 PM",
                fallback_phone_number="+10000000000",
                greeting_message=f"Hello! Thank you for calling {tenant.name}. How may I assist you today?",
                faqs_knowledge_base="",
            )
            session.add(row)
            await session.flush()

        master = await self._resolve_master_credentials(session)
        public_base = self._backend_public_url()
        voice_webhook_url = f"{public_base}/api/v1/receptionist/webhooks/telnyx/voice"
        status_callback_url = f"{public_base}/api/v1/receptionist/webhooks/telnyx/status"

        other_nums_res = await session.execute(
            select(ReceptionistConfig.telnyx_phone_number).where(
                ReceptionistConfig.tenant_id != tenant_id,
                ReceptionistConfig.telnyx_phone_number.is_not(None),
            )
        )
        assigned_phones = {
            normalize_e164(num)
            for num in other_nums_res.scalars().all()
            if num and normalize_e164(num)
        }

        # 1. Provision or assign dedicated Telnyx number + attach TeXML Voice Application
        telnyx_res = await telnyx_voice_adapter.provision_or_assign_number(
            tenant_id=str(tenant_id),
            api_key=master["telnyx_api_key"],
            voice_webhook_url=voice_webhook_url,
            status_callback_url=status_callback_url,
            connection_id=master["telnyx_connection_id"],
            default_number=master["telnyx_default_number"],
            country_code=master["telnyx_default_country"],
            existing_phone=row.telnyx_phone_number,
            existing_phone_id=row.telnyx_phone_id,
            assigned_phones=assigned_phones,
        )
        row.telnyx_phone_number = telnyx_res["phone_number"]
        row.telnyx_phone_id = telnyx_res["phone_id"]

        # 2. Provision or update dedicated Retell AI LLM + Voice Agent + link Telnyx number
        retell_res = await retell_ai_adapter.create_or_update_agent(
            api_key=master["retell_api_key"],
            tenant_id=str(tenant_id),
            business_name=row.business_name,
            operating_hours=row.operating_hours,
            greeting_message=row.greeting_message,
            faqs=row.faqs_knowledge_base,
            fallback_phone=row.fallback_phone_number,
            backend_base_url=public_base,
            telnyx_phone_number=row.telnyx_phone_number,
            calcom_booking_url=row.calcom_booking_url,
            voice_id=row.voice_id,
            existing_llm_id=row.retell_llm_id,
            existing_agent_id=row.retell_agent_id,
            telnyx_sip_username=master["telnyx_sip_username"],
            telnyx_sip_password=master["telnyx_sip_password"],
        )
        row.retell_llm_id = retell_res["retell_llm_id"]
        row.retell_agent_id = retell_res["retell_agent_id"]

        # 3. Generate Call Forwarding Setup Guide
        row.call_forwarding_guide = generate_call_forwarding_guide(
            fallback_phone=row.fallback_phone_number,
            assigned_telnyx_number=row.telnyx_phone_number or "+15550000000",
            business_name=row.business_name,
        )

        # 4. Determine honest provisioning status
        if telnyx_res["is_live"] and retell_res["is_live"]:
            row.provisioning_status = "active"
        elif telnyx_res["is_live"] or retell_res["is_live"]:
            row.provisioning_status = "active"
        else:
            row.provisioning_status = "sandbox_ready"

        row.provisioning_notes = f"Telnyx: {telnyx_res['note']} | Retell AI: {retell_res['note']}"

        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_id=actor_id,
                actor_type="user",
                action="receptionist.voice_agent.provisioned",
                resource_type="receptionist_config",
                resource_id=row.id,
                metadata_={
                    "telnyx_phone_number": row.telnyx_phone_number,
                    "retell_agent_id": row.retell_agent_id,
                    "status": row.provisioning_status,
                },
            )
        )
        await session.commit()
        await session.refresh(row)
        return self._to_config_dict(row)

    async def handle_calcom_availability_tool(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        date_str: str,
    ) -> Dict[str, Any]:
        """Retell AI custom function endpoint: check open Cal.com slots strictly using the tenant's own Cal.com credentials."""
        res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id)
        )
        cfg = res.scalar_one_or_none()
        client_cal_key = decrypt_secret(cfg.encrypted_calcom_api_key or "") if cfg else ""
        event_type_id = (cfg.calcom_event_type_id or "").strip() if cfg and cfg.calcom_event_type_id else None
        return await calcom_adapter.check_availability(
            api_key=client_cal_key,
            event_type_id=event_type_id,
            date_str=date_str,
        )

    async def handle_calcom_book_tool(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        request: CalComBookToolRequest,
    ) -> Dict[str, Any]:
        """Retell AI custom function endpoint: book appointment strictly into client's own Cal.com (or tenant-isolated dashboard log)."""
        res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id)
        )
        cfg = res.scalar_one_or_none()
        client_cal_key = decrypt_secret(cfg.encrypted_calcom_api_key or "") if cfg else ""
        event_type_id = (cfg.calcom_event_type_id or "").strip() if cfg and cfg.calcom_event_type_id else None

        booking = await calcom_adapter.create_booking(
            api_key=client_cal_key,
            event_type_id=event_type_id,
            start_iso=request.start_iso,
            attendee_name=request.attendee_name,
            attendee_email=request.attendee_email,
            attendee_phone=request.attendee_phone,
            notes=request.notes,
        )

        is_live_cal = bool(booking.get("is_live"))
        summary_msg = (
            f"Appointment booked for {request.attendee_name} via Cal.com ({request.start_iso})."
            if is_live_cal
            else f"Appointment request logged for {request.attendee_name} ({request.start_iso}) — connect personal Cal.com API Key & Event Type ID for calendar sync."
        )
        notif_msg = (
            f"{request.attendee_name} booked an appointment for {request.start_iso} via Cal.com."
            if is_live_cal
            else f"{request.attendee_name} requested an appointment for {request.start_iso} (logged in your dashboard)."
        )

        # Attach booking to existing call log or create a new call log entry
        call_id_str = request.call_id or f"call_cal_{uuid.uuid4().hex[:10]}"
        log_res = await session.execute(
            select(ReceptionistCallLog).where(
                ReceptionistCallLog.tenant_id == tenant_id,
                ReceptionistCallLog.external_call_id == call_id_str,
            )
        )
        call_log = log_res.scalar_one_or_none()
        try:
            appt_dt = datetime.fromisoformat(request.start_iso.replace("Z", "+00:00"))
        except Exception:
            appt_dt = datetime.now(timezone.utc) + timedelta(days=1)

        if call_log:
            call_log.booking_status = "booked"
            call_log.booked_appointment_at = appt_dt
            call_log.calcom_booking_uid = booking["booking_uid"]
            call_log.caller_name = call_log.caller_name or request.attendee_name
        else:
            call_log = ReceptionistCallLog(
                tenant_id=tenant_id,
                config_id=cfg.id if cfg else None,
                external_call_id=call_id_str,
                caller_phone=request.attendee_phone or "Unknown",
                caller_name=request.attendee_name,
                to_number=cfg.telnyx_phone_number if cfg else None,
                status="completed",
                booking_status="booked",
                booked_appointment_at=appt_dt,
                calcom_booking_uid=booking["booking_uid"],
                summary=summary_msg,
            )
            session.add(call_log)

        await notification_service.send_notification(
            session=session,
            tenant_id=tenant_id,
            title="New Appointment Booked by AI Receptionist",
            message=notif_msg,
            channel="in_app",
        )
        await session.commit()
        await session.refresh(call_log)

        from app.services.noshow_recovery_service import noshow_recovery_service
        from app.services.review_booster_service import review_booster_service

        await noshow_recovery_service.schedule_appointment_reminder(session, tenant_id, call_log)
        await review_booster_service.schedule_post_appointment_review(session, tenant_id, call_log)
        return booking

    async def handle_retell_webhook(
        self,
        session: AsyncSession,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Process Retell AI call_started / call_ended / call_analyzed webhooks."""
        call_obj = payload.get("call") or payload
        agent_id = call_obj.get("agent_id")
        to_number = call_obj.get("to_number")
        from_number = call_obj.get("from_number") or "Unknown"
        external_call_id = str(call_obj.get("call_id") or f"retell_{uuid.uuid4().hex[:10]}")

        cfg = None
        if agent_id:
            res = await session.execute(
                select(ReceptionistConfig).where(ReceptionistConfig.retell_agent_id == str(agent_id))
            )
            cfg = res.scalar_one_or_none()
        if not cfg and to_number:
            res = await session.execute(
                select(ReceptionistConfig).where(
                    ReceptionistConfig.telnyx_phone_number == normalize_e164(str(to_number))
                )
            )
            cfg = res.scalar_one_or_none()
        if not cfg:
            logger.warning("Retell webhook ignored: unmatched agent_id/to_number", agent_id=agent_id)
            return {"processed": False, "reason": "unmatched_agent"}

        duration_ms = call_obj.get("duration_ms") or 0
        duration_sec = int(call_obj.get("duration_seconds") or (duration_ms // 1000))
        analysis = call_obj.get("call_analysis") or {}
        summary = analysis.get("call_summary") or call_obj.get("summary")
        transcript = call_obj.get("transcript")
        disconnection = str(call_obj.get("disconnection_reason") or "").lower()
        transferred = "transfer" in disconnection or bool(call_obj.get("transferred_to_human"))
        status_val = "transferred" if transferred else (
            "in_progress" if payload.get("event") == "call_started" else "completed"
        )

        existing_res = await session.execute(
            select(ReceptionistCallLog).where(
                ReceptionistCallLog.tenant_id == cfg.tenant_id,
                ReceptionistCallLog.external_call_id == external_call_id,
            )
        )
        log = existing_res.scalar_one_or_none()
        if log:
            log.duration_seconds = max(log.duration_seconds, duration_sec)
            log.status = status_val
            if transferred:
                log.transferred_to_human = True
            if summary:
                log.summary = summary
            if transcript:
                log.transcript = transcript
            if call_obj.get("recording_url"):
                log.recording_url = str(call_obj["recording_url"])
        else:
            log = ReceptionistCallLog(
                tenant_id=cfg.tenant_id,
                config_id=cfg.id,
                external_call_id=external_call_id,
                caller_phone=str(from_number),
                to_number=cfg.telnyx_phone_number,
                direction="inbound",
                duration_seconds=duration_sec,
                status=status_val,
                transferred_to_human=transferred,
                summary=summary or "Inbound AI Receptionist call recorded.",
                transcript=transcript,
                recording_url=call_obj.get("recording_url"),
                metadata_={"event": payload.get("event"), "disconnection_reason": disconnection},
            )
            session.add(log)

        await session.commit()

        if status_val in ("completed", "transferred") and duration_sec > 0:
            from app.services.wallet_service import wallet_service

            billable_minutes = max(1, math.ceil(duration_sec / 60))
            await wallet_service.debit_credits(
                session=session,
                tenant_id=cfg.tenant_id,
                category="ai_call_minute",
                unit_count=float(billable_minutes),
                description=f"AI Voice Receptionist call ({duration_sec}s / {billable_minutes} min)",
                reference_id=f"retell_call:{external_call_id}",
                metadata={"duration_seconds": duration_sec, "status": status_val},
                enforce_pause=False,
            )

        if status_val in ("completed", "transferred"):
            from app.services.call_intelligence_service import call_intelligence_service

            await call_intelligence_service.analyze_call_and_score_lead(session, cfg.tenant_id, log)

        return {"processed": True, "call_log_id": str(log.id), "tenant_id": str(cfg.tenant_id)}

    async def handle_telnyx_voice_webhook(
        self,
        session: AsyncSession,
        to_number: str,
        from_number: str,
        call_sid: str,
        emergency_transfer: bool = False,
    ) -> str:
        """Return TeXML routing inbound Telnyx voice calls to Retell AI or live human transfer."""
        norm_to = normalize_e164(to_number)
        res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.telnyx_phone_number == norm_to)
        )
        cfg = res.scalar_one_or_none()
        if not cfg:
            return (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<Response><Say>Thank you for calling. This number is not yet assigned to an active workspace.</Say></Response>"
            )

        if emergency_transfer:
            session.add(
                ReceptionistCallLog(
                    tenant_id=cfg.tenant_id,
                    config_id=cfg.id,
                    external_call_id=call_sid or f"tx_{uuid.uuid4().hex[:10]}",
                    caller_phone=from_number or "Unknown",
                    to_number=norm_to,
                    status="transferred",
                    transferred_to_human=True,
                    summary=f"Live emergency/human call transfer routed to {cfg.fallback_phone_number}.",
                )
            )
            await session.commit()
            return telnyx_voice_adapter.build_live_transfer_texml(
                fallback_phone=cfg.fallback_phone_number,
                announcement=f"Transferring your call to {cfg.business_name} staff right now.",
            )

        return telnyx_voice_adapter.build_retell_sip_or_greeting_texml(
            business_name=cfg.business_name,
            greeting=cfg.greeting_message,
            fallback_phone=cfg.fallback_phone_number,
            retell_agent_id=cfg.retell_agent_id,
            telnyx_phone_number=cfg.telnyx_phone_number,
        )

    async def simulate_voice_call(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        request: SimulateVoiceCallRequest,
    ) -> Dict[str, Any]:
        """Simulate a realistic AI Receptionist call (appointment booking, FAQ, or live transfer) for QA/testing."""
        res = await session.execute(
            select(ReceptionistConfig).where(ReceptionistConfig.tenant_id == tenant_id)
        )
        cfg = res.scalar_one_or_none()
        if not cfg:
            raise ResourceNotFoundError("ReceptionistConfig", str(tenant_id))

        from app.services.wallet_service import wallet_service

        await wallet_service.assert_wallet_active(session, tenant_id, estimated_credits=5.0)

        call_id = f"sim_call_{uuid.uuid4().hex[:10]}"
        from app.integrations.ai_providers.router import route_and_execute_ai_task
        from app.services.rag_service import rag_service

        rag_hits = await rag_service.search_knowledge(
            session, tenant_id, request.notes or cfg.business_name or "services pricing hours", top_k=2
        )
        rag_context = (
            "\n".join(h.get("content", "")[:240] for h in rag_hits)
            if rag_hits
            else (cfg.faqs_knowledge_base or "Professional services and consultations.")[:300]
        )

        if request.scenario == "emergency_transfer":
            log = ReceptionistCallLog(
                tenant_id=tenant_id,
                config_id=cfg.id,
                external_call_id=call_id,
                caller_phone=request.caller_phone,
                caller_name=request.caller_name,
                to_number=cfg.telnyx_phone_number,
                duration_seconds=48,
                status="transferred",
                booking_status="none",
                transferred_to_human=True,
                summary=(
                    f"Caller {request.caller_name} requested urgent human assistance. "
                    f"Transferred live to {cfg.fallback_phone_number}."
                ),
                transcript=(
                    f"AI: {cfg.greeting_message}\n"
                    f"Caller: I have an urgent issue and need to speak with a real person immediately.\n"
                    f"AI: Understood — transferring you live to our team at {cfg.fallback_phone_number} right now."
                ),
                metadata_={"simulated": True, "scenario": request.scenario},
            )
            session.add(log)
        elif request.scenario == "faq_inquiry":
            ai_faq = await route_and_execute_ai_task(
                task_type="whatsapp_reply",
                prompt=(
                    f"You are the AI Voice Receptionist for {cfg.business_name} (Hours: {cfg.operating_hours}).\n"
                    f"Knowledge Base: {rag_context}\n"
                    f"Caller ({request.caller_name}) asks: '{request.notes or 'What are your hours and main services?'}'\n"
                    "Reply in 2 natural spoken sentences."
                ),
                tenant_id=str(tenant_id),
            )
            ai_spoken = (
                ai_faq.content.strip()
                if (ai_faq.success and ai_faq.content and "[Mock AI]" not in ai_faq.content)
                else f"{cfg.business_name} is open {cfg.operating_hours}. {rag_context[:180]}"
            )
            log = ReceptionistCallLog(
                tenant_id=tenant_id,
                config_id=cfg.id,
                external_call_id=call_id,
                caller_phone=request.caller_phone,
                caller_name=request.caller_name,
                to_number=cfg.telnyx_phone_number,
                duration_seconds=74,
                status="completed",
                booking_status="none",
                transferred_to_human=False,
                summary=f"Answered business hours ({cfg.operating_hours}) and RAG FAQ inquiry for {request.caller_name}.",
                transcript=(
                    f"AI: {cfg.greeting_message}\n"
                    f"Caller: {request.notes or 'What are your business hours and services?'}\n"
                    f"AI: {ai_spoken}"
                ),
                metadata_={"simulated": True, "scenario": request.scenario, "llm_model": ai_faq.model},
            )
            session.add(log)
        else:
            # Appointment booking via Cal.com adapter + RAG-grounded AI greeting
            slot_dt = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
                hour=14, minute=0, second=0, microsecond=0
            )
            booking = await self.handle_calcom_book_tool(
                session=session,
                tenant_id=tenant_id,
                request=CalComBookToolRequest(
                    start_iso=slot_dt.isoformat(),
                    attendee_name=request.caller_name,
                    attendee_phone=request.caller_phone,
                    notes=request.notes or "Scheduled during AI Voice Receptionist call",
                    call_id=call_id,
                ),
            )
            ai_book = await route_and_execute_ai_task(
                task_type="whatsapp_reply",
                prompt=(
                    f"You are the AI Voice Receptionist for {cfg.business_name}. "
                    f"Confirm to caller {request.caller_name} that their appointment is booked for tomorrow at 2:00 PM UTC "
                    f"(Reference: {booking['booking_uid']}) and mention one helpful detail from: {rag_context[:180]}. "
                    "Keep it to 2 natural spoken sentences."
                ),
                tenant_id=str(tenant_id),
            )
            ai_confirm_line = (
                ai_book.content.strip()
                if (ai_book.success and ai_book.content and "[Mock AI]" not in ai_book.content)
                else f"Confirmed! Your appointment with {cfg.business_name} is booked for tomorrow at 2:00 PM UTC (Ref: {booking['booking_uid']})."
            )
            log_res = await session.execute(
                select(ReceptionistCallLog).where(
                    ReceptionistCallLog.tenant_id == tenant_id,
                    ReceptionistCallLog.external_call_id == call_id,
                )
            )
            log = log_res.scalar_one()
            log.duration_seconds = 112
            log.summary = (
                f"Booked Cal.com appointment ({booking['booking_uid']}) for {request.caller_name} "
                f"on {slot_dt.strftime('%Y-%m-%d %H:%M UTC')}."
            )
            log.transcript = (
                f"AI: {cfg.greeting_message}\n"
                f"Caller: Hi, I'd like to schedule an appointment for tomorrow afternoon. {request.notes or ''}\n"
                f"AI: Let me check our {cfg.business_name} calendar — 2:00 PM UTC is open. Shall I book it for you?\n"
                f"Caller: Yes, please! My name is {request.caller_name}.\n"
                f"AI: {ai_confirm_line}"
            )
            log.metadata_ = {
                "simulated": True,
                "scenario": "appointment_booking",
                "booking": booking,
                "llm_model": ai_book.model,
            }

        await session.commit()
        await session.refresh(log)

        billable_minutes = max(1, math.ceil(int(log.duration_seconds or 60) / 60))
        await wallet_service.debit_credits(
            session=session,
            tenant_id=tenant_id,
            category="ai_call_minute",
            unit_count=float(billable_minutes),
            description=f"Simulated AI Receptionist call ({request.scenario}, {billable_minutes} min)",
            reference_id=f"sim_call:{call_id}",
            metadata={"scenario": request.scenario},
            enforce_pause=False,
        )

        from app.services.call_intelligence_service import call_intelligence_service

        await call_intelligence_service.analyze_call_and_score_lead(session, tenant_id, log)
        if log.booking_status == "booked" and log.booked_appointment_at:
            from app.services.review_booster_service import review_booster_service

            await review_booster_service.schedule_post_appointment_review(session, tenant_id, log)
        await session.refresh(log)

        return self._to_call_dict(log)

    async def list_calls_and_summary(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        limit: int = 50,
    ) -> Dict[str, Any]:
        res = await session.execute(
            select(ReceptionistCallLog)
            .where(ReceptionistCallLog.tenant_id == tenant_id)
            .order_by(ReceptionistCallLog.created_at.desc())
            .limit(limit)
        )
        rows = list(res.scalars().all())
        total_calls = len(rows)
        booked_calls = [
            r for r in rows if r.booking_status in ("booked", "confirmed", "reschedule_requested")
        ]
        transfers = sum(1 for r in rows if r.transferred_to_human)
        avg_duration = round(sum(int(r.duration_seconds or 0) for r in rows) / total_calls, 1) if total_calls else 0.0
        return {
            "summary": {
                "total_calls": total_calls,
                "appointments_booked": len(booked_calls),
                "human_transfers": transfers,
                "avg_duration_seconds": avg_duration,
            },
            "calls": [self._to_call_dict(r) for r in rows],
            "booked_appointments": [self._to_call_dict(r) for r in booked_calls],
        }


receptionist_service = ReceptionistService()
