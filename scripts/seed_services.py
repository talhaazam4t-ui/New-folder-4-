"""Idempotent Platform Catalog & Agent Registry Seeder.

Seeds the 6 core SaaS business services and 8 bounded AI agents into the database.
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

DEFAULT_SERVICES = [
    {
        "name": "Business Financial Tracking & Ledger",
        "slug": "business-financial-tracking",
        "category": "finance",
        "description": "Multi-currency income, rent, expense, and outstanding payment reconciliation with immutable audit trails.",
    },
    {
        "name": "AI Marketing & Growth Automation",
        "slug": "ai-marketing-growth",
        "category": "marketing",
        "description": "Competitor intelligence, audience discovery, ad copy studio, and human-approved campaign orchestration.",
    },
    {
        "name": "WhatsApp Business Concierge & Webhook Sync",
        "slug": "whatsapp-business-concierge",
        "category": "communication",
        "description": "Self-service Meta Embedded Signup, inbound payment extraction with ambiguity protection, and automated lead replies.",
    },
    {
        "name": "Multi-Agent Task Orchestration Suite",
        "slug": "multi-agent-orchestration",
        "category": "automation",
        "description": "Bounded Planner, Researcher, Executor, and Reviewer agents with token quota and circuit-breaker cost protection.",
    },
    {
        "name": "Lead CRM & AI Qualification Engine",
        "slug": "lead-crm-qualification",
        "category": "sales",
        "description": "Multi-channel lead capture and automated AI qualification scoring.",
    },
    {
        "name": "Executive Analytics & Compliance Vault",
        "slug": "executive-analytics-compliance",
        "category": "governance",
        "description": "Cross-engine KPI dashboards, token cost telemetry, PII prompt redaction, and GDPR cascading account purge.",
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
            if not existing.scalar_one_or_none():
                srv = Service(
                    name=item["name"],
                    slug=item["slug"],
                    category=item["category"],
                    description=item["description"],
                    configuration_schema={"tier": "standard"},
                    active=True,
                )
                session.add(srv)
                created_count += 1
        await session.commit()
        await agent_registry._ensure_db_registry(session)

    logger.info("Seeded platform catalog and agent registry", new_services=created_count)
    return created_count


if __name__ == "__main__":
    asyncio.run(seed_platform_catalog())
