"""Database connection & Supabase client provider.

Supports:
1. Production pooled async PostgreSQL (via asyncpg / Supabase direct URL).
2. Supabase PostgREST client for client-safe and administrative operations.
3. Fallback to local SQLite / in-memory for testing and local development without cloud network access.
"""

import os
from typing import AsyncGenerator, Optional

from app.config import settings
from app.core.logging import logger
from app.database.models.base import Base
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from supabase import Client, create_client

# Global database engine and session factory
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _get_sqlite_url() -> str:
    return os.environ.get("TALOX_SQLITE_DB_URL") or "sqlite+aiosqlite:///talox_dev.db"


def get_engine() -> AsyncEngine:
    """Initialize or return the singleton SQLAlchemy async engine."""
    global _engine
    if _engine is not None:
        return _engine

    db_url = settings.supabase_database_url

    if db_url and (db_url.startswith("postgresql") or db_url.startswith("postgres")):
        # Format connection string for asyncpg if not already prefixed
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        logger.info(
            "Connecting to production Supabase PostgreSQL via asyncpg",
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
        )
        _engine = create_async_engine(
            db_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            connect_args={
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            },
            echo=settings.debug,
        )
    else:
        # Strict Production Guardrail: Prohibit silent SQLite fallback in production/staging
        if settings.app_env in ("production", "staging"):
            raise RuntimeError(
                "Production environment error: SUPABASE_DATABASE_URL is not set or invalid. "
                "Silent fallback to SQLite in production/staging is strictly prohibited. "
                "Please configure a valid PostgreSQL connection string."
            )

        logger.info("Using local SQLite async engine for development/testing")
        _engine = create_async_engine(
            _get_sqlite_url(),
            connect_args={"check_same_thread": False},
            echo=False,
        )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the configured async session factory."""
    global _session_factory
    if _session_factory is not None:
        return _session_factory

    engine = get_engine()
    _session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for yielding transactional database sessions."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db(engine: Optional[AsyncEngine] = None) -> None:
    """Initialize database connectivity and (in dev/test or opt-in) create schema tables."""
    global _engine, _session_factory
    import app.database.models  # noqa: F401

    target_engine = engine or get_engine()
    auto_create = settings.auto_create_tables or os.environ.get("AUTO_CREATE_TABLES", "").lower() == "true"
    try:
        if settings.app_env in ("production", "staging") and not auto_create:
            async with target_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database connectivity verified successfully (production mode)")
        else:
            async with target_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables initialized successfully")
    except Exception as exc:
        if engine is None and settings.app_env == "development":
            logger.warning(
                "Primary database connection failed in development; falling back to local SQLite",
                error=str(exc),
            )
            _engine = create_async_engine(
                _get_sqlite_url(),
                connect_args={"check_same_thread": False},
                echo=False,
            )
            _session_factory = None
            async with _engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Fallback SQLite database tables initialized successfully")
        else:
            raise


async def reset_db(engine: Optional[AsyncEngine] = None) -> None:
    """Drop and recreate all schema tables for clean test isolation."""
    import app.database.models  # noqa: F401

    target_engine = engine or get_engine()
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        from app.services.auth_service import auth_service
        auth_service._explicit_client_ids.clear()
        auth_service._local_password_hashes.clear()
    except Exception:
        pass
    try:
        from app.api.v1.admin import reset_sync_flags
        reset_sync_flags()
    except Exception:
        pass
    logger.info("Database reset cleanly")


# Supabase Client SDK singletons
_supabase_anon: Optional[Client] = None
_supabase_admin: Optional[Client] = None


def get_supabase_client() -> Client:
    """Client-facing Supabase client using Anon Key."""
    global _supabase_anon
    if _supabase_anon is None:
        _supabase_anon = create_client(
            settings.supabase_url,
            settings.supabase_anon_key
        )
    return _supabase_anon


def get_supabase_admin_client() -> Client:
    """Server-side administrative Supabase client using Service Role Key.
    MUST NEVER be leaked to frontend clients.
    """
    global _supabase_admin
    if _supabase_admin is None:
        _supabase_admin = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key
        )
    return _supabase_admin
