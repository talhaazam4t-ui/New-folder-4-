"""Pydantic v2 Schemas for Office Receptionist (AI Voice Agent — Retell AI, Telnyx, Cal.com)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReceptionistConfigUpsertRequest(BaseModel):
    business_name: str = Field(min_length=2, max_length=255)
    operating_hours: str = Field(default="Mon-Fri 9:00 AM - 6:00 PM", max_length=500)
    fallback_phone_number: str = Field(min_length=6, max_length=50)
    greeting_message: str = Field(
        default="Hello! Thank you for calling. How can I help you today?",
        max_length=2000,
    )
    faqs_knowledge_base: str = Field(default="", max_length=15000)
    calcom_booking_url: Optional[str] = Field(default=None, max_length=500)
    calcom_event_type_id: Optional[str] = Field(default=None, max_length=100)
    calcom_api_key: Optional[str] = Field(default=None, max_length=300)
    voice_id: Optional[str] = Field(default="11labs-Adrian", max_length=100)
    auto_provision: bool = Field(default=True)


class ReceptionistFaqsUpdateRequest(BaseModel):
    faqs_knowledge_base: str = Field(default="", max_length=15000)
    greeting_message: Optional[str] = Field(default=None, max_length=2000)
    operating_hours: Optional[str] = Field(default=None, max_length=500)
    fallback_phone_number: Optional[str] = Field(default=None, max_length=50)
    calcom_booking_url: Optional[str] = Field(default=None, max_length=500)
    calcom_event_type_id: Optional[str] = Field(default=None, max_length=100)
    calcom_api_key: Optional[str] = Field(default=None, max_length=300)


class SimulateVoiceCallRequest(BaseModel):
    caller_name: str = Field(default="Sarah Jenkins", max_length=120)
    caller_phone: str = Field(default="+14155550199", max_length=50)
    scenario: str = Field(
        default="appointment_booking",
        description="appointment_booking | faq_inquiry | emergency_transfer",
    )
    notes: Optional[str] = Field(default=None, max_length=500)


class CalComAvailabilityToolRequest(BaseModel):
    date: str = Field(default="2026-11-25")


class CalComBookToolRequest(BaseModel):
    start_iso: str
    attendee_name: str = Field(min_length=1, max_length=120)
    attendee_email: Optional[str] = None
    attendee_phone: Optional[str] = None
    notes: Optional[str] = None
    call_id: Optional[str] = None


class AdminVoiceCredentialsUpdateRequest(BaseModel):
    retell_api_key: Optional[str] = None
    retell_webhook_secret: Optional[str] = None
    telnyx_api_key: Optional[str] = None
    telnyx_connection_id: Optional[str] = None
    telnyx_default_number: Optional[str] = None
    telnyx_default_country: Optional[str] = Field(default="US", max_length=5)
    calcom_api_key: Optional[str] = None


class ReceptionistCallLogResponse(BaseModel):
    id: str
    tenant_id: str
    external_call_id: str
    caller_phone: str
    caller_name: Optional[str]
    to_number: Optional[str]
    direction: str
    duration_seconds: int
    status: str
    booking_status: str
    booked_appointment_at: Optional[datetime]
    calcom_booking_uid: Optional[str]
    transferred_to_human: bool
    summary: Optional[str]
    transcript: Optional[str]
    recording_url: Optional[str]
    created_at: datetime


class ReceptionistConfigResponse(BaseModel):
    id: str
    tenant_id: str
    business_name: str
    operating_hours: str
    fallback_phone_number: str
    greeting_message: str
    faqs_knowledge_base: str
    calcom_booking_url: Optional[str]
    calcom_event_type_id: Optional[str]
    calcom_api_key_configured: bool
    telnyx_phone_number: Optional[str]
    retell_agent_id: Optional[str]
    voice_id: str
    provisioning_status: str
    provisioning_notes: Optional[str]
    call_forwarding_guide: Dict[str, Any]
    updated_at: datetime
