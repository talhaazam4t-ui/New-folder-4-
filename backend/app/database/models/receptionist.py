"""SQLAlchemy Models for Office Receptionist (AI Voice Agent — Retell AI, Twilio, Cal.com).
"""

import uuid
from datetime import datetime
from typing import Optional

from app.database.models.base import Base, TimestampMixin
from app.database.models.tenant import GUID
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class PlatformVoiceCredential(Base, TimestampMixin):
    """Super-admin-managed encrypted master credentials for Retell AI, Twilio, and Cal.com."""

    __tablename__ = "platform_voice_credentials"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    encrypted_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="unconfigured", nullable=False)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True,
    )


class ReceptionistConfig(Base, TimestampMixin):
    """Per-tenant Office Receptionist AI Voice Agent configuration."""

    __tablename__ = "receptionist_configs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    operating_hours: Mapped[str] = mapped_column(
        String(500),
        default="Mon-Fri 9:00 AM - 6:00 PM",
        nullable=False,
    )
    fallback_phone_number: Mapped[str] = mapped_column(String(50), nullable=False)
    greeting_message: Mapped[str] = mapped_column(
        Text,
        default="Hello! Thank you for calling. How may I assist you today?",
        nullable=False,
    )
    faqs_knowledge_base: Mapped[str] = mapped_column(Text, default="", nullable=False)
    calcom_booking_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    calcom_event_type_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    encrypted_calcom_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Provisioned Voice Infrastructure
    twilio_phone_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    twilio_phone_sid: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    retell_agent_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    retell_llm_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    voice_id: Mapped[str] = mapped_column(String(100), default="11labs-Adrian", nullable=False)
    provisioning_status: Mapped[str] = mapped_column(
        String(40),
        default="pending_onboarding",
        nullable=False,
    )
    provisioning_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    call_forwarding_guide: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ReceptionistCallLog(Base, TimestampMixin):
    """Per-tenant AI Voice Receptionist call logs, transcripts, transfers, and Cal.com bookings."""

    __tablename__ = "receptionist_call_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    config_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("receptionist_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    external_call_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    caller_phone: Mapped[str] = mapped_column(String(50), default="Unknown", nullable=False)
    caller_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    to_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    direction: Mapped[str] = mapped_column(String(20), default="inbound", nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="completed", nullable=False)
    booking_status: Mapped[str] = mapped_column(String(40), default="none", nullable=False)
    booked_appointment_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    calcom_booking_uid: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    transferred_to_human: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recording_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
