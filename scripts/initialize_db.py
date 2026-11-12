"""Database Initialization Script for Talox Tech Stream.

Initializes all 22 multi-tenant tables in PostgreSQL (Supabase) or local development SQLite.
Usage:
    python scripts/initialize_db.py
"""

import asyncio
import sys
from pathlib import Path

# Ensure backend package is importable
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.core.logging import logger  # noqa: E402
from app.database.supabase import init_db  # noqa: E402


async def run_initialization() -> bool:
    logger.info("Initializing Talox Tech Stream database schema...")
    await init_db()
    logger.info("Database schema initialization complete.")
    return True


if __name__ == "__main__":
    asyncio.run(run_initialization())
