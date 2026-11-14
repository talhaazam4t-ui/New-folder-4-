import os

# Ensure testing uses local SQLite in-memory / dev database unless explicit test DB provided
os.environ["SUPABASE_DATABASE_URL"] = ""

import pytest  # noqa: E402
from app.database.supabase import reset_db  # noqa: E402


@pytest.fixture(autouse=True)
async def clean_database():
    """Reset database tables before each test for complete test isolation."""
    await reset_db()
