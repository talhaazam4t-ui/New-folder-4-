"""Pydantic Schemas for Marketing & Growth Engine (Campaigns, Leads, Research, Analytics).
"""

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CompetitorResearchRequest(BaseModel):
    industry: str = Field(min_length=2, max_length=100)
    competitors: List[str] = Field(min_length=1, max_length=10)
    region: str = Field(default="Global", max_length=100)


class AudienceResearchRequest(BaseModel):
    product_or_service: str = Field(min_length=2, max_length=255)
    target_industry: str = Field(min_length=2, max_length=100)
    price_point: Optional[str] = None


class ContentGenerationRequest(BaseModel):
    channel: Literal["whatsapp", "meta_ads", "google_ads", "linkedin", "email", "instagram"]
    topic: str = Field(min_length=3, max_length=500)
    tone: str = Field(default="professional", max_length=50)
    call_to_action: Optional[str] = None


class CampaignCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    platform: str = Field(min_length=2, max_length=50)
    objective: str = Field(min_length=2, max_length=100)
    budget: float = Field(default=0.0, ge=0.0)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    configuration: Optional[Dict[str, Any]] = None


class CampaignUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    objective: Optional[str] = Field(default=None, min_length=2, max_length=100)
    budget: Optional[float] = Field(default=None, ge=0.0)
    status: Optional[Literal["draft", "pending_approval", "paused", "completed"]] = None
    configuration: Optional[Dict[str, Any]] = None


class CampaignResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    platform: str
    objective: str
    status: str
    budget: float
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    configuration: Dict[str, Any]
    created_at: datetime


class LeadCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: Optional[str] = None
    phone: Optional[str] = None
    source: str = Field(default="website", max_length=50)
    notes: Optional[str] = Field(default=None, max_length=1000)
    metadata: Optional[Dict[str, Any]] = None


class LeadUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[Literal["new", "contacted", "qualified", "converted", "lost"]] = None
    qualification_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    metadata: Optional[Dict[str, Any]] = None


class LeadResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    source: str
    status: str
    qualification_score: float
    assigned_agent: Optional[str] = None
    metadata: Dict[str, Any]
    created_at: datetime


class LeadGenerationRequest(BaseModel):
    industry: str = Field(default="Real Estate / Property", min_length=2, max_length=100)
    location: str = Field(default="Riyadh & Dubai", min_length=2, max_length=120)
    keywords: Optional[str] = Field(default=None, max_length=200)
    limit: int = Field(default=3, ge=1, le=20)


class LeadOutreachRequest(BaseModel):
    channel: Literal["whatsapp", "email"] = "whatsapp"
    custom_context: Optional[str] = Field(default=None, max_length=500)
    require_approval: bool = False


class LeadAppointmentBookingRequest(BaseModel):
    meeting_title: str = Field(default="Strategy & Service Consultation", min_length=2, max_length=200)
    scheduled_iso: Optional[str] = None



class MarketingAnalyticsResponse(BaseModel):
    tenant_id: uuid.UUID
    total_campaigns: int
    active_campaigns: int
    draft_campaigns: int
    total_budget_allocated: float
    total_leads: int
    qualified_leads: int
    converted_leads: int
    average_qualification_score: float
    total_impressions: int
    total_clicks: int
    total_spend: float
    total_revenue: float
    roi_percentage: float


class SalesChatbotMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = Field(default=None, max_length=120)
    visitor_name: Optional[str] = Field(default=None, max_length=120)
    visitor_phone: Optional[str] = Field(default=None, max_length=50)
    current_industry: Optional[str] = Field(default=None, max_length=100)
    current_package: Optional[str] = Field(default=None, max_length=100)


class SalesChatbotMessageResponse(BaseModel):
    reply: str
    detected_industry: Optional[str] = None
    detected_service_slug: Optional[str] = None
    detected_plan_name: Optional[str] = None
    detected_price: Optional[float] = None
    hot_lead: bool = False
    alert_message: Optional[str] = None
    whatsapp_url: str = "https://wa.me/923238300330"
    onboarding_transition_url: Optional[str] = None
