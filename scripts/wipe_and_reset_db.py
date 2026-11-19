"""Wipe and Reset Database Script for Talox Tech Stream.

Completely wipes all existing data, logs, records, and pre-created user accounts.
Prepares fresh schema, seeds standard catalog services and agent registry,
and configures settings.super_admin_emails as platform administrator accounts.

Usage:
    python scripts/wipe_and_reset_db.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.config import settings  # noqa: E402
from app.core.logging import logger  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.database.models.tenant import Profile  # noqa: E402
from app.database.supabase import get_session_factory, reset_db  # noqa: E402

from scripts.seed_services import seed_platform_catalog  # noqa: E402


async def run_clean_wipe_and_reset():
    logger.info("Executing complete database wipe and fresh state reset...")

    # 1. Drop and recreate all tables
    await reset_db()
    logger.info("All previous tables, logs, and pre-created accounts dropped.")

    # 2. Seed services and agent registry
    await seed_platform_catalog()
    logger.info("Standard services and agent registry seeded.")

    # 3. Configure sole admin account
    factory = get_session_factory()
    async with factory() as session:
        default_admin_hash = get_password_hash("Admin@12345!")

        for admin_email in settings.super_admin_emails:
            admin_profile = Profile(
                id=uuid.uuid4(),
                full_name="Talha Azam (Platform Owner)",
                email=admin_email.strip().lower(),
                phone=settings.support_whatsapp_number,
                password_hash=default_admin_hash,
            )
            session.add(admin_profile)

        await session.commit()
        logger.info(
            "Sole Admin accounts configured and persisted",
            admins=settings.super_admin_emails,
            phone=settings.support_whatsapp_number,
        )

    logger.info("Clean database wipe & fresh state initialization complete!")


if __name__ == "__main__":
    asyncio.run(run_clean_wipe_and_reset())
