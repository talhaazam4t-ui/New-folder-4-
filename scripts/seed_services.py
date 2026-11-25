"""Idempotent Platform Catalog & Agent Registry Seeder.

Seeds the 6 core SaaS business services (with dynamic industry profiles, packages, pricing tiers,
limitations, required integrations, and onboarding requirements for Financing, Clinics / Hospitals,
Real Estate / Property, and E-Commerce) and 8 bounded AI agents into the database.
Usage:
    python scripts/seed_services.py
"""

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.agents.registry import agent_registry  # noqa: E402
from app.core.logging import logger  # noqa: E402
from app.database.models.service import Service  # noqa: E402
from app.database.supabase import get_session_factory, init_db  # noqa: E402
from sqlalchemy import select  # noqa: E402

SUPPORTED_INDUSTRIES = [
    "Financing",
    "Clinics / Hospitals",
    "Real Estate / Property",
    "E-Commerce",
]

DEFAULT_SERVICES = [
    {
        "name": "Business Financial Tracking & Ledger",
        "slug": "business-financial-tracking",
        "category": "finance",
        "description": "Multi-currency income, rent, expense, and outstanding payment reconciliation with immutable audit trails.",
        "configuration_schema": {
            "tier": "standard",
            "base_price": 99.0,
            "industries": ["Financing", "Real Estate / Property", "Clinics / Hospitals", "E-Commerce"],
            "required_integrations": ["whatsapp", "gmail"],
            "onboarding_requirements": [
                "Connect WhatsApp Cloud API for payment receipt extraction",
                "Connect Gmail / Email for automated invoice & ledger alerts",
            ],
            "features": [
                "Automated revenue & expense ledger",
                "Ambiguity-protected WhatsApp payment capture",
                "Immutable double-entry audit trail",
                "Monthly P&L and cashflow reports",
            ],
            "limitations": "Up to 5,000 ledger entries/month on Starter; unlimited on Enterprise.",
            "packages": [
                {
                    "plan_name": "starter",
                    "display_name": "Starter Ledger",
                    "price": 99.0,
                    "billing_interval": "monthly",
                    "features": ["Up to 1,000 transactions/mo", "WhatsApp receipt capture", "Monthly summary report"],
                    "limitations": "1 workspace bank/ledger feed",
                },
                {
                    "plan_name": "growth",
                    "display_name": "Growth Finance Automation",
                    "price": 249.0,
                    "billing_interval": "monthly",
                    "features": ["Up to 10,000 transactions/mo", "Automated overdue payment reminders", "Weekly financial digest"],
                    "limitations": "Up to 5 currencies",
                },
                {
                    "plan_name": "enterprise",
                    "display_name": "Enterprise Treasury Suite",
                    "price": 499.0,
                    "billing_interval": "monthly",
                    "features": ["Unlimited transactions", "Custom compliance exports", "Dedicated account SLA"],
                    "limitations": "None",
                },
            ],
            "industry_profiles": {
                "Financing": {
                    "headline": "Loan Repayment, Advisory Retainer & Portfolio Ledger Automation",
                    "required_integrations": ["whatsapp", "gmail"],
                },
                "Real Estate / Property": {
                    "headline": "Automated Rent Collection, Unit Ledger & Landlord Payout Reconciliation",
                    "required_integrations": ["whatsapp", "gmail"],
                },
                "Clinics / Hospitals": {
                    "headline": "Patient Billing, Consultation Fee & Insurance Copay Ledger",
                    "required_integrations": ["whatsapp", "gmail"],
                },
                "E-Commerce": {
                    "headline": "Order Settlement, COD Reconciliation & Supplier Expense Tracking",
                    "required_integrations": ["whatsapp", "gmail"],
                },
            },
        },
    },
    {
        "name": "AI Marketing & Growth Automation",
        "slug": "ai-marketing-growth",
        "category": "marketing",
        "description": "Competitor intelligence, audience discovery, personalized outreach, and human-approved campaign orchestration.",
        "configuration_schema": {
            "tier": "standard",
            "base_price": 149.0,
            "industries": ["Financing", "Clinics / Hospitals", "Real Estate / Property", "E-Commerce"],
            "required_integrations": ["google_business", "whatsapp", "gmail"],
            "onboarding_requirements": [
                "Connect Google Business / Maps for local market & lead discovery",
                "Connect WhatsApp Cloud API for personalized prospect outreach",
                "Connect Gmail for multi-channel follow-up sequences",
            ],
            "features": [
                "AI Lead Generation from Google Maps & business directories",
                "Contextual personalized outreach via WhatsApp & Email",
                "Competitor positioning & audience persona analysis",
                "Mandatory Owner approval before live campaign dispatch",
            ],
            "limitations": "Up to 1,500 outreach messages/month on Starter; 10,000/month on Growth.",
            "packages": [
                {
                    "plan_name": "starter",
                    "display_name": "Starter Outreach",
                    "price": 149.0,
                    "billing_interval": "monthly",
                    "monthly_lead_limit": 500,
                    "features": ["500 qualified leads/mo", "1,500 outreach messages/mo", "Monthly conversion report"],
                    "limitations": "Single outreach campaign active at a time",
                },
                {
                    "plan_name": "growth",
                    "display_name": "Growth Pipeline Engine",
                    "price": 349.0,
                    "billing_interval": "monthly",
                    "monthly_lead_limit": 2500,
                    "features": ["2,500 qualified leads/mo", "10,000 outreach messages/mo", "Multi-channel WhatsApp + Email"],
                    "limitations": "Up to 5 active campaigns",
                },
                {
                    "plan_name": "enterprise",
                    "display_name": "Enterprise Demand Gen",
                    "price": 699.0,
                    "billing_interval": "monthly",
                    "monthly_lead_limit": 5000,
                    "features": ["Up to 5,000 lead discoveries/mo", "Custom industry targeting", "Dedicated strategist review"],
                    "limitations": "None",
                },
            ],
            "industry_profiles": {
                "Financing": {
                    "headline": "B2B Borrower & SME Financing Lead Generation + Personalized Outreach",
                    "required_integrations": ["google_business", "gmail", "whatsapp"],
                },
                "Clinics / Hospitals": {
                    "headline": "Patient Acquisition, Health Checkup Campaigns & Local Clinic Growth",
                    "required_integrations": ["google_business", "whatsapp", "gmail"],
                },
                "Real Estate / Property": {
                    "headline": "High-Intent Investor, Buyer & Commercial Tenant Lead Generation",
                    "required_integrations": ["google_business", "whatsapp", "gmail"],
                },
                "E-Commerce": {
                    "headline": "VIP Customer Reactivation, Abandoned Cart Recovery & Wholesale Outreach",
                    "required_integrations": ["whatsapp", "gmail"],
                },
            },
        },
    },
    {
        "name": "WhatsApp Business Concierge & Webhook Sync",
        "slug": "whatsapp-business-concierge",
        "category": "communication",
        "description": "24/7 AI Receptionist, appointment booking, customer support, and automated lead replies on WhatsApp.",
        "configuration_schema": {
            "tier": "standard",
            "base_price": 129.0,
            "industries": ["Financing", "Clinics / Hospitals", "Real Estate / Property", "E-Commerce"],
            "required_integrations": ["whatsapp", "google_calendar", "booking_provider"],
            "onboarding_requirements": [
                "Connect WhatsApp Cloud API (Meta Embedded Signup)",
                "Connect Google Calendar for live appointment slot synchronization",
                "Connect Appointment / Booking Provider for automated confirmations",
            ],
            "features": [
                "24/7 AI Receptionist & instant inquiry response",
                "Automated appointment booking & calendar sync",
                "Customer support FAQ resolution & human escalation",
                "Automated meeting reminders & no-show reduction",
            ],
            "limitations": "Up to 3,000 conversations/month on Starter.",
            "packages": [
                {
                    "plan_name": "starter",
                    "display_name": "Starter AI Receptionist",
                    "price": 129.0,
                    "billing_interval": "monthly",
                    "features": ["24/7 WhatsApp AI Receptionist", "Google Calendar booking sync", "Up to 3,000 messages/mo"],
                    "limitations": "1 WhatsApp Business number",
                },
                {
                    "plan_name": "growth",
                    "display_name": "Growth Concierge & Booking",
                    "price": 279.0,
                    "billing_interval": "monthly",
                    "features": ["Up to 15,000 messages/mo", "Automated booking reminders", "Multi-language support"],
                    "limitations": "Up to 3 WhatsApp Business numbers",
                },
                {
                    "plan_name": "enterprise",
                    "display_name": "Enterprise Omnichannel Desk",
                    "price": 549.0,
                    "billing_interval": "monthly",
                    "features": ["Unlimited conversations", "Custom CRM/EHR booking webhook", "Priority SLA"],
                    "limitations": "None",
                },
            ],
            "industry_profiles": {
                "Financing": {
                    "headline": "24/7 Loan Pre-Qualification Concierge & Advisor Consultation Booking",
                    "required_integrations": ["whatsapp", "google_calendar"],
                },
                "Clinics / Hospitals": {
                    "headline": "24/7 Patient Triage Receptionist, Doctor Appointment Booking & Reminders",
                    "required_integrations": ["whatsapp", "google_calendar", "booking_provider"],
                },
                "Real Estate / Property": {
                    "headline": "Instant Property Inquiry Responder & Automated Site Viewing Scheduler",
                    "required_integrations": ["whatsapp", "google_calendar"],
                },
                "E-Commerce": {
                    "headline": "24/7 Order Tracking Support, Return Concierge & WhatsApp Catalog Assistant",
                    "required_integrations": ["whatsapp", "gmail"],
                },
            },
        },
    },
    {
        "name": "Multi-Agent Task Orchestration Suite",
        "slug": "multi-agent-orchestration",
        "category": "automation",
        "description": "Managed end-to-end AI workflow orchestration combining Lead Gen, Qualification, Outreach, and Booking.",
        "configuration_schema": {
            "tier": "standard",
            "base_price": 199.0,
            "industries": ["Financing", "Clinics / Hospitals", "Real Estate / Property", "E-Commerce"],
            "required_integrations": ["whatsapp", "google_calendar", "gmail"],
            "onboarding_requirements": [
                "Connect WhatsApp Cloud API",
                "Connect Google Calendar",
                "Connect Gmail / Email provider",
            ],
            "features": [
                "Done-for-you Master Orchestrator workflow execution",
                "Quality Assurance verification on every AI output",
                "Token budget protection & automatic retry handling",
                "Executive business outcome reporting",
            ],
            "limitations": "Managed by Talox Operations Team; 5,000 workflow runs/mo on Starter.",
            "packages": [
                {
                    "plan_name": "starter",
                    "display_name": "Starter Managed Automation",
                    "price": 199.0,
                    "billing_interval": "monthly",
                    "features": ["5,000 automated agent tasks/mo", "QA verification gate", "Weekly outcome digest"],
                    "limitations": "Standard model routing",
                },
                {
                    "plan_name": "growth",
                    "display_name": "Growth Autonomous Suite",
                    "price": 399.0,
                    "billing_interval": "monthly",
                    "features": ["25,000 automated agent tasks/mo", "Priority reasoning models", "Real-time outcome feed"],
                    "limitations": "Fair-use token quota",
                },
                {
                    "plan_name": "enterprise",
                    "display_name": "Enterprise Managed AI Ops",
                    "price": 799.0,
                    "billing_interval": "monthly",
                    "features": ["Unlimited managed workflows", "Custom business rules", "Dedicated AI systems engineer"],
                    "limitations": "None",
                },
            ],
            "industry_profiles": {
                "Financing": {
                    "headline": "Full-Funnel Financial Advisory & Applicant Qualification Automation",
                    "required_integrations": ["whatsapp", "google_calendar", "gmail"],
                },
                "Clinics / Hospitals": {
                    "headline": "End-to-End Patient Intake, Appointment Scheduling & Follow-Up Care",
                    "required_integrations": ["whatsapp", "google_calendar", "booking_provider"],
                },
                "Real Estate / Property": {
                    "headline": "Complete Lead-to-Viewing-to-Lease Managed AI Pipeline",
                    "required_integrations": ["whatsapp", "google_calendar", "google_business"],
                },
                "E-Commerce": {
                    "headline": "Autonomous Customer Support, VIP Retention & Post-Purchase Upsell",
                    "required_integrations": ["whatsapp", "gmail"],
                },
            },
        },
    },
    {
        "name": "Lead CRM & AI Qualification Engine",
        "slug": "lead-crm-qualification",
        "category": "sales",
        "description": "Tiered global B2B lead discovery + personalized Gmail, WhatsApp & LinkedIn outreach with Human-in-the-Loop approval.",
        "configuration_schema": {
            "tier": "standard",
            "base_price": 149.0,
            "industries": ["Financing", "Clinics / Hospitals", "Real Estate / Property", "E-Commerce"],
            "required_integrations": ["google_business", "whatsapp", "gmail", "google_calendar"],
            "onboarding_requirements": [
                "Connect Gmail OAuth for automatic company-specific drafts & approved sends",
                "Connect WhatsApp Cloud API (or use 1-click WhatsApp link) for direct prospect outreach",
                "Connect Google Calendar / Cal.com for qualified meeting handoff",
            ],
            "features": [
                "Global daily company discovery across your target niche & cities",
                "Company-specific personalized pitches for Gmail, WhatsApp & LinkedIn",
                "Mandatory Human-in-the-Loop Approval before sending any message",
                "Concise real-time lead quota & conversion performance tracking",
            ],
            "limitations": "Up to 150 verified leads/month on Starter; 500 on Growth; 1,500 on Enterprise.",
            "packages": [
                {
                    "plan_name": "starter",
                    "display_name": "Starter Lead Tier (150 Leads/Mo)",
                    "price": 149.0,
                    "billing_interval": "monthly",
                    "monthly_lead_limit": 150,
                    "features": [
                        "150 verified global leads/mo",
                        "Personalized Gmail Drafts, WhatsApp & LinkedIn notes",
                        "Human-in-the-Loop Approval Queue",
                    ],
                    "limitations": "Up to 150 leads/month",
                },
                {
                    "plan_name": "growth",
                    "display_name": "Growth Pipeline Tier (500 Leads/Mo)",
                    "price": 349.0,
                    "billing_interval": "monthly",
                    "monthly_lead_limit": 500,
                    "features": [
                        "500 verified global leads/mo",
                        "Daily automated global niche & city rotation",
                        "Gmail + WhatsApp + LinkedIn multi-channel outreach & Calendar sync",
                    ],
                    "limitations": "Up to 500 leads/month",
                },
                {
                    "plan_name": "enterprise",
                    "display_name": "Enterprise Scale Tier (1,500 Leads/Mo)",
                    "price": 699.0,
                    "billing_interval": "monthly",
                    "monthly_lead_limit": 1500,
                    "features": [
                        "1,500 verified global leads/mo",
                        "Multi-city international expansion & CRM conversion reporting",
                        "Dedicated outreach specialist SLA",
                    ],
                    "limitations": "Up to 1,500 leads/month",
                },
            ],
            "industry_profiles": {
                "Financing": {
                    "headline": "Credit & Financing Readiness Lead Qualification Engine",
                    "required_integrations": ["google_business", "whatsapp", "google_calendar"],
                },
                "Clinics / Hospitals": {
                    "headline": "Elective Procedure & Specialist Consultation Patient Qualification",
                    "required_integrations": ["google_business", "whatsapp", "google_calendar"],
                },
                "Real Estate / Property": {
                    "headline": "Buyer Budget, Timeline & Location Qualification Engine",
                    "required_integrations": ["google_business", "whatsapp", "google_calendar"],
                },
                "E-Commerce": {
                    "headline": "B2B Wholesale & High-Ticket Buyer Qualification Engine",
                    "required_integrations": ["whatsapp", "gmail"],
                },
            },
        },
    },
    {
        "name": "Executive Analytics & Compliance Vault",
        "slug": "executive-analytics-compliance",
        "category": "governance",
        "description": "Managed service performance reporting, conversion attribution, PII protection, and compliance auditing.",
        "configuration_schema": {
            "tier": "standard",
            "base_price": 99.0,
            "industries": ["Financing", "Clinics / Hospitals", "Real Estate / Property", "E-Commerce"],
            "required_integrations": ["gmail"],
            "onboarding_requirements": [
                "Connect Gmail / Email to receive automated executive performance reports",
            ],
            "features": [
                "Real-time Leads, Messages, Meetings & Conversion KPI viewer",
                "Automated weekly & monthly executive PDF/Email digests",
                "Strict PII & financial credential redaction",
                "GDPR-compliant data governance & audit trails",
            ],
            "limitations": "12-month historical retention on Starter; 7-year retention on Enterprise.",
            "packages": [
                {
                    "plan_name": "starter",
                    "display_name": "Starter Reporting",
                    "price": 99.0,
                    "billing_interval": "monthly",
                    "features": ["Live KPI dashboard", "Monthly executive summary", "PII redaction vault"],
                    "limitations": "12-month retention",
                },
                {
                    "plan_name": "growth",
                    "display_name": "Growth BI & Attribution",
                    "price": 199.0,
                    "billing_interval": "monthly",
                    "features": ["Weekly executive reports", "Campaign & appointment ROI attribution", "3-year retention"],
                    "limitations": "Up to 10 report recipients",
                },
                {
                    "plan_name": "enterprise",
                    "display_name": "Enterprise Compliance Vault",
                    "price": 399.0,
                    "billing_interval": "monthly",
                    "features": ["7-year immutable audit archive", "HIPAA/Financial compliance pack", "Custom SLA"],
                    "limitations": "None",
                },
            ],
            "industry_profiles": {
                "Financing": {
                    "headline": "Financial Regulatory Audit Trail & Portfolio Conversion Analytics",
                    "required_integrations": ["gmail"],
                },
                "Clinics / Hospitals": {
                    "headline": "Patient Privacy Redaction & Clinic Appointment Outcome Analytics",
                    "required_integrations": ["gmail"],
                },
                "Real Estate / Property": {
                    "headline": "Property Portfolio Yield, Viewing-to-Close & Lead ROI Analytics",
                    "required_integrations": ["gmail"],
                },
                "E-Commerce": {
                    "headline": "Customer Acquisition Cost, Support Resolution & Revenue Attribution",
                    "required_integrations": ["gmail"],
                },
            },
        },
    },
    {
        "name": "Office Receptionist (AI Voice Agent)",
        "slug": "office-receptionist",
        "category": "communication",
        "description": (
            "24/7 AI Voice Receptionist powered by Retell AI, Telnyx, and Cal.com — answers live phone calls, "
            "handles FAQs, books appointments directly into Cal.com, and transfers urgent/human requests live."
        ),
        "configuration_schema": {
            "industries": [
                "Financing",
                "Clinics / Hospitals",
                "Real Estate / Property",
                "E-Commerce",
            ],
            "required_integrations": [],
            "onboarding_requirements": [
                "Enter Business Name, Operating Hours, Greeting & FAQs",
                "Provide Personal / Fallback Phone Number for live human transfers",
                "Connect your free Cal.com API Key & Event Type ID for isolated live appointment booking",
            ],
            "features": [
                "Dedicated Telnyx AI phone number with automatic Voice Routing & Call Forwarding guide",
                "Custom Retell AI voice agent trained on your business hours, greeting, and FAQs",
                "Isolated Cal.com availability lookup & live call appointment booking",
                "Instant live call transfer to your personal/fallback number for emergencies or human requests",
                "Full call logs, duration, AI call summaries, and booked appointments dashboard",
            ],
            "limitations": "Includes 300 voice minutes/mo on Starter; 1,500 on Growth; unlimited routing on Enterprise.",
            "packages": [
                {
                    "plan_name": "starter",
                    "display_name": "Starter Voice Receptionist",
                    "price": 199.0,
                    "billing_interval": "monthly",
                    "features": [
                        "1 dedicated Telnyx AI number",
                        "Retell AI voice agent + custom FAQs",
                        "Cal.com appointment booking + live transfer",
                        "300 voice minutes/month",
                    ],
                    "limitations": "1 concurrent line",
                },
                {
                    "plan_name": "growth",
                    "display_name": "Growth AI Receptionist",
                    "price": 399.0,
                    "billing_interval": "monthly",
                    "features": [
                        "Up to 3 Telnyx lines",
                        "1,500 voice minutes/month",
                        "Priority Cal.com routing + SMS/WhatsApp follow-ups",
                        "Full transcripts & call analytics",
                    ],
                    "limitations": "Up to 5 concurrent calls",
                },
                {
                    "plan_name": "enterprise",
                    "display_name": "Enterprise Voice Desk",
                    "price": 799.0,
                    "billing_interval": "monthly",
                    "features": [
                        "Unlimited lines & custom voice cloning",
                        "Multi-department warm call transfers",
                        "Dedicated SLA & CRM sync",
                    ],
                    "limitations": "None",
                },
            ],
            "industry_profiles": {
                "Financing": {
                    "headline": "24/7 Financial Advisory Phone Receptionist & Cal.com Consultation Booking",
                    "required_integrations": [],
                },
                "Clinics / Hospitals": {
                    "headline": "24/7 Clinic AI Voice Receptionist, Patient Triage & Emergency Doctor Transfer",
                    "required_integrations": [],
                },
                "Real Estate / Property": {
                    "headline": "24/7 Property Viewing Phone Receptionist & Live Broker Transfer",
                    "required_integrations": [],
                },
                "E-Commerce": {
                    "headline": "24/7 Order Support Voice Desk & Escalation Routing",
                    "required_integrations": [],
                },
            },
        },
    },
]


async def seed_platform_catalog() -> int:
    await init_db()
    factory = get_session_factory()
    created_count = 0
    async with factory() as session:
        for item in DEFAULT_SERVICES:
            existing = await session.execute(
                select(Service).where(Service.slug == item["slug"])
            )
            srv = existing.scalar_one_or_none()
            if not srv:
                srv = Service(
                    name=item["name"],
                    slug=item["slug"],
                    category=item["category"],
                    description=item["description"],
                    configuration_schema=item["configuration_schema"],
                    active=True,
                )
                session.add(srv)
                created_count += 1
            else:
                # Ensure existing seeded services have the latest industry configuration_schema
                if not srv.configuration_schema or "packages" not in srv.configuration_schema:
                    srv.configuration_schema = item["configuration_schema"]
        await session.commit()
        await agent_registry._ensure_db_registry(session)

    logger.info("Seeded platform catalog and agent registry", new_services=created_count)
    return created_count


if __name__ == "__main__":
    asyncio.run(seed_platform_catalog())
