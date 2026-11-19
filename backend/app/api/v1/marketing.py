"""Marketing and Growth Engine API Endpoints (Section 9.2).

Implements all 12 required endpoints for competitor/audience research, content generation,
campaign lifecycle + human approval publishing, lead capture, AI lead qualification, and ROI analytics.
"""

import uuid
from typing import List, Optional

from app.core.tenant_context import TenantContext
from app.database.supabase import get_db
from app.dependencies import require_permission
from app.schemas.marketing import (
    AudienceResearchRequest,
    CampaignCreateRequest,
    CampaignResponse,
    CampaignUpdateRequest,
    CompetitorResearchRequest,
    ContentGenerationRequest,
    LeadAppointmentBookingRequest,
    LeadCreateRequest,
    LeadGenerationRequest,
    LeadOutreachRequest,
    LeadResponse,
    LeadUpdateRequest,
    MarketingAnalyticsResponse,
    SalesChatbotMessageRequest,
    SalesChatbotMessageResponse,
)
from app.services.marketing_service import marketing_service
from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/marketing", tags=["Marketing & Growth Engine"])


@router.post("/research/competitors")
async def run_competitor_research(
    request: CompetitorResearchRequest,
    context: TenantContext = Depends(require_permission("marketing.research")),
):
    """Analyze market competitors and identify positioning gaps."""
    data = await marketing_service.research_competitors(
        tenant_id=context.tenant_id,
        request=request,
    )
    return {"success": True, "data": data, "message": "Competitor research completed"}


@router.post("/research/audience")
async def run_audience_research(
    request: AudienceResearchRequest,
    context: TenantContext = Depends(require_permission("marketing.research")),
):
    """Discover ideal customer personas and audience targeting segments."""
    data = await marketing_service.research_audience(
        tenant_id=context.tenant_id,
        request=request,
    )
    return {"success": True, "data": data, "message": "Audience research completed"}


@router.post("/content/generate")
async def generate_marketing_content(
    request: ContentGenerationRequest,
    context: TenantContext = Depends(require_permission("marketing.content.generate")),
):
    """Generate channel-specific marketing copy and creative assets."""
    data = await marketing_service.generate_content(
        tenant_id=context.tenant_id,
        request=request,
    )
    return {"success": True, "data": data, "message": "Marketing content generated"}


@router.post("/campaigns", status_code=status.HTTP_201_CREATED, response_model=CampaignResponse)
async def create_marketing_campaign(
    request: CampaignCreateRequest,
    context: TenantContext = Depends(require_permission("marketing.campaign.create")),
    session: AsyncSession = Depends(get_db),
):
    """Draft a new marketing campaign and automatically queue a human approval request."""
    return await marketing_service.create_campaign(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        request=request,
    )


@router.get("/campaigns", response_model=List[CampaignResponse])
async def list_marketing_campaigns(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """List all marketing campaigns for the tenant."""
    return await marketing_service.list_campaigns(
        session=session,
        tenant_id=context.tenant_id,
    )


@router.patch("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def update_marketing_campaign(
    campaign_id: uuid.UUID,
    request: CampaignUpdateRequest,
    context: TenantContext = Depends(require_permission("marketing.campaign.create")),
    session: AsyncSession = Depends(get_db),
):
    """Update a marketing campaign draft (cannot activate without explicit `/approve` endpoint)."""
    return await marketing_service.update_campaign(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        campaign_id=campaign_id,
        request=request,
    )


@router.post("/campaigns/{campaign_id}/approve", response_model=CampaignResponse)
async def approve_and_publish_campaign(
    campaign_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("marketing.campaign.publish")),
    session: AsyncSession = Depends(get_db),
):
    """Approve and publish a marketing campaign (Owner permission required)."""
    return await marketing_service.approve_and_publish_campaign(
        session=session,
        tenant_id=context.tenant_id,
        reviewer_id=context.user_id,
        campaign_id=campaign_id,
    )


@router.post("/leads", status_code=status.HTTP_201_CREATED, response_model=LeadResponse)
async def create_lead(
    request: LeadCreateRequest,
    context: TenantContext = Depends(require_permission("leads.create")),
    session: AsyncSession = Depends(get_db),
):
    """Capture a new lead in the tenant CRM."""
    return await marketing_service.create_lead(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        request=request,
    )


@router.get("/leads", response_model=List[LeadResponse])
async def list_leads(
    status_filter: Optional[str] = Query(None, alias="status"),
    context: TenantContext = Depends(require_permission("leads.read")),
    session: AsyncSession = Depends(get_db),
):
    """List tenant leads with optional status filtering."""
    return await marketing_service.list_leads(
        session=session,
        tenant_id=context.tenant_id,
        status_filter=status_filter,
    )


@router.patch("/leads/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: uuid.UUID,
    request: LeadUpdateRequest,
    context: TenantContext = Depends(require_permission("leads.update")),
    session: AsyncSession = Depends(get_db),
):
    """Update lead status, contact info, or qualification score."""
    return await marketing_service.update_lead(
        session=session,
        tenant_id=context.tenant_id,
        lead_id=lead_id,
        request=request,
    )


@router.post("/leads/{lead_id}/qualify", response_model=LeadResponse)
async def qualify_lead(
    lead_id: uuid.UUID,
    context: TenantContext = Depends(require_permission("leads.update")),
    session: AsyncSession = Depends(get_db),
):
    """Run AI lead qualification scoring on a specific lead."""
    return await marketing_service.qualify_lead(
        session=session,
        tenant_id=context.tenant_id,
        lead_id=lead_id,
    )


@router.post("/leads/generate")
async def generate_leads_google_maps(
    request: LeadGenerationRequest,
    context: TenantContext = Depends(require_permission("leads.create")),
    session: AsyncSession = Depends(get_db),
):
    """Run industry-specific Lead Generation (Google Maps/Places & business directories) with deduplication."""
    data = await marketing_service.generate_leads_from_google_maps(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        request=request,
    )
    return {"success": True, "data": data}


@router.post("/leads/{lead_id}/outreach")
async def send_lead_outreach(
    lead_id: uuid.UUID,
    request: LeadOutreachRequest,
    context: TenantContext = Depends(require_permission("leads.update")),
    session: AsyncSession = Depends(get_db),
):
    """Execute personalized AI outreach to a lead (WhatsApp or Email) with opt-out and approval compliance."""
    data = await marketing_service.execute_personalized_outreach(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        lead_id=lead_id,
        request=request,
    )
    return {"success": True, "data": data}


@router.post("/leads/{lead_id}/book-appointment")
async def book_lead_appointment(
    lead_id: uuid.UUID,
    request: LeadAppointmentBookingRequest,
    context: TenantContext = Depends(require_permission("leads.update")),
    session: AsyncSession = Depends(get_db),
):
    """Book a meeting/appointment for a qualified lead and record calendar conversion."""
    data = await marketing_service.book_lead_appointment(
        session=session,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        lead_id=lead_id,
        request=request,
    )
    return {"success": True, "data": data}


@router.get("/analytics", response_model=MarketingAnalyticsResponse)
async def get_marketing_analytics(
    context: TenantContext = Depends(require_permission("tenant.read")),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve aggregated campaign performance, lead funnel, and ROI analytics."""
    return await marketing_service.get_analytics(
        session=session,
        tenant_id=context.tenant_id,
    )


@router.post("/chatbot/message", response_model=SalesChatbotMessageResponse)
async def sales_chatbot_message(
    request: SalesChatbotMessageRequest,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    session: AsyncSession = Depends(get_db),
):
    """Public & in-app AI Sales & Support Chatbot for Pre-Registration Visitors and Dashboard Assistance.

    - Guides visitors through 27 industries and package tiers.
    - Provides WhatsApp contact (+92 339 8701000) for human assistance.
    - Intent Trigger: detects hot buying intent / human request and logs trigger alert.
    - Seamless Transition: returns pre-loaded URL (/register?industry=...&package=...) to avoid repeating onboarding.
    """
    tenant_uuid = None
    if x_tenant_id:
        try:
            tenant_uuid = uuid.UUID(x_tenant_id)
        except ValueError:
            pass

    return await marketing_service.handle_sales_chatbot_message(
        request=request,
        session=session,
        tenant_id=tenant_uuid,
    )
