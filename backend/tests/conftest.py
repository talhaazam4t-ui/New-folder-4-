import atexit
import os
import tempfile
from pathlib import Path

# Isolate SQLite test DB per process in temp dir so concurrent pytest runs never collide
_TEST_DB_PATH = Path(tempfile.gettempdir()) / f"talox_pytest_{os.getpid()}.db"
os.environ["SUPABASE_DATABASE_URL"] = ""
os.environ["TALOX_SQLITE_DB_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH.as_posix()}"

import pytest  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.database.supabase import reset_db  # noqa: E402


def _cleanup_test_db() -> None:
    try:
        if _TEST_DB_PATH.exists():
            _TEST_DB_PATH.unlink()
    except OSError:
        pass


atexit.register(_cleanup_test_db)


@pytest.fixture(autouse=True)
async def clean_database():
    """Reset database tables and rate limiter state before each test for complete test isolation."""
    limiter.reset()
    await reset_db()
