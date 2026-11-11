import pytest
from app.database.supabase import reset_db


@pytest.fixture(autouse=True)
async def clean_database():
    """Reset database tables before each test for complete test isolation."""
    await reset_db()
