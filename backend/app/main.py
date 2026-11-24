"""Main FastAPI Application Entrypoint for Talox Tech Stream.

Configures:
1. Lifespan event handlers (logging setup, resource checks).
2. CORS middleware.
3. SlowAPI rate limiting (cost protection).
4. Standardized JSON response envelope and exception handlers.
5. API v1 routing and system health checks.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from app.api.router import api_v1_router
from app.automation.scheduler import automation_scheduler
from app.automation.workers.task_worker import background_task_worker
from app.config import settings
from app.core.exceptions import TaloxException
from app.core.logging import logger, setup_logging
from app.core.rate_limit import limiter
from app.database.supabase import get_session_factory, init_db
from app.services.outreach_autopilot_service import outreach_autopilot_service
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response


async def _run_pending_task_queue_tick() -> None:
    """Periodic worker wrapper to process pending automation tasks."""
    try:
        factory = get_session_factory()
        async with factory() as session:
            await background_task_worker.process_pending_queue(session)
    except Exception as exc:
        logger.error("Background pending task queue tick failed", error=str(exc))


async def _run_stale_approval_expiration_tick() -> None:
    """Periodic worker wrapper to expire stale pending approvals."""
    try:
        factory = get_session_factory()
        async with factory() as session:
            await background_task_worker.expire_stale_approvals(session)
    except Exception as exc:
        logger.error("Background stale approval expiration tick failed", error=str(exc))


async def _run_daily_outreach_autopilot_tick() -> None:
    """Periodic worker wrapper for daily global niche lead discovery and Gmail draft creation."""
    try:
        factory = get_session_factory()
        async with factory() as session:
            await outreach_autopilot_service.run_scheduled_autopilot_tick(session)
    except Exception as exc:
        logger.error("Daily global outreach autopilot tick failed", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle management."""
    setup_logging()
    logger.info(
        "Talox Tech Stream starting up",
        environment=settings.app_env,
        debug=settings.debug,
        fast_model=settings.ai_default_fast_model,
        reasoning_model=settings.ai_default_reasoning_model,
    )
    # Initialize database tables
    try:
        await init_db()
    except Exception as exc:
        logger.error("Failed to initialize database tables", error=str(exc))

    automation_scheduler.start()
    if settings.app_env != "test" and not os.environ.get("PYTEST_CURRENT_TEST"):
        automation_scheduler.schedule_interval_job(
            job_id="background_pending_task_queue",
            func=_run_pending_task_queue_tick,
            seconds=30,
        )
        automation_scheduler.schedule_interval_job(
            job_id="background_stale_approval_expiration",
            func=_run_stale_approval_expiration_tick,
            seconds=60,
        )
        automation_scheduler.schedule_interval_job(
            job_id="daily_global_outreach_autopilot",
            func=_run_daily_outreach_autopilot_tick,
            seconds=1800,
        )

    yield
    automation_scheduler.shutdown()
    logger.info("Talox Tech Stream shutting down cleanly")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Custom Python Multi-Tenant SaaS Agent Platform",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Attach SlowAPI State and Exception Handler
async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    return _rate_limit_exceeded_handler(request, cast(RateLimitExceeded, exc))


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Rate Limiting Middleware (registered before CORSMiddleware so CORS wraps 429 responses)
app.add_middleware(SlowAPIMiddleware)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API v1 Endpoints
app.include_router(api_v1_router)

# Locate built frontend static directory
FRONTEND_DIST_DIRS = [
    Path(__file__).resolve().parent.parent / "static",  # /app/static (in Docker container)
    Path(__file__).resolve().parent.parent / "frontend" / "out",  # /app/frontend/out
    Path(__file__).resolve().parent.parent.parent / "frontend" / "out",  # Repo root / frontend / out (local dev)
]

STATIC_DIR = next((d for d in FRONTEND_DIST_DIRS if d.is_dir()), None)

# Mount Next.js _next static assets if available
if STATIC_DIR and (STATIC_DIR / "_next").is_dir():
    app.mount("/_next", StaticFiles(directory=str(STATIC_DIR / "_next")), name="next_static")


# Standardized Exception Handling
@app.exception_handler(TaloxException)
async def talox_exception_handler(request: Request, exc: TaloxException):
    """Handle all custom domain errors with consistent JSON envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Normalize FastAPI/Starlette HTTPException responses into the standard error envelope."""
    detail = exc.detail
    details: Any
    if isinstance(detail, dict):
        code = str(detail.get("code") or f"HTTP_{exc.status_code}")
        message = str(detail.get("message") or detail)
        details = detail.get("details") or {}
    else:
        code = f"HTTP_{exc.status_code}"
        message = str(detail or "HTTP error")
        details = {}

    return JSONResponse(
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "details": details,
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Normalize Pydantic/FastAPI 422 validation errors into the standard error envelope."""
    errors = exc.errors()
    summary = "; ".join(
        f"{'.'.join(str(part) for part in err.get('loc', []))}: {err.get('msg', 'Invalid value')}"
        for err in errors
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": summary or "Request validation failed",
                "details": errors,
            },
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unexpected server errors without leaking internals."""
    logger.error("Unhandled server exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please contact platform support.",
                "details": str(exc) if settings.debug else {},
            },
        },
    )


_MISSING_ASSET_EXTENSIONS = {
    ".js",
    ".css",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".txt",
    ".xml",
    ".json",
    ".webmanifest",
}


# System Health Check & Frontend Delivery Endpoints
@app.api_route("/", methods=["GET", "HEAD"], tags=["Frontend"])
async def root():
    """Root platform endpoint: serves frontend index.html if built, otherwise API discovery JSON."""
    if STATIC_DIR:
        index_file = STATIC_DIR / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
    return {
        "success": True,
        "data": {
            "name": settings.app_name,
            "version": "0.1.0",
            "environment": settings.app_env,
            "status": "online",
        },
        "message": "Talox Tech Stream API active",
    }


@app.api_route("/health", methods=["GET", "HEAD"], tags=["Health"])
async def platform_health():
    """Alternative health check endpoint for Render and container probes."""
    return await health_check()


@app.api_route("/api/v1/health", methods=["GET", "HEAD"], tags=["Health"])
async def health_check():
    """Health check for load balancers and container probes."""
    return {
        "success": True,
        "data": {
            "status": "healthy",
            "environment": settings.app_env,
            "ai_provider": settings.ai_provider,
            "whatsapp_provider": settings.whatsapp_provider,
            "payment_provider": settings.payment_provider,
        },
        "message": "All core systems operational",
    }


@app.get("/api/v1/agent-test", tags=["Rate-Limited Demonstration"])
@limiter.limit(f"{settings.rate_limit_agent_rpm}/minute")
async def rate_limited_agent_demo(request: Request):
    """Demonstration endpoint enforcing strict tenant/agent rate limits."""
    return {
        "success": True,
        "data": {
            "rate_limit_rpm": settings.rate_limit_agent_rpm,
            "status": "allowed",
        },
        "message": "Agent execution quota validated",
    }


@app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_spa_and_static(full_path: str):
    """Serve client-side routes and static assets, preserving API routes and Swagger docs."""
    clean_path = full_path.strip("/")
    if (
        clean_path.startswith("api/")
        or clean_path == "api"
        or clean_path.startswith("_next/")
        or clean_path == "_next"
        or clean_path in ("docs", "redoc", "openapi.json", "health")
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")

    if STATIC_DIR:
        static_root = STATIC_DIR.resolve()
        try:
            direct_file = (static_root / clean_path).resolve()
        except Exception:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Static asset not found")

        if not direct_file.is_relative_to(static_root):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Static asset not found")

        # 1. Exact file match (e.g. favicon.ico, 404.html, index.txt)
        if direct_file.is_file():
            return FileResponse(direct_file)

        # 2. Directory index match (e.g. login -> login/index.html)
        dir_index = (direct_file / "index.html").resolve()
        if dir_index.is_relative_to(static_root) and dir_index.is_file():
            return FileResponse(dir_index)

        # 3. HTML file match (e.g. login -> login.html)
        html_file = (static_root / f"{clean_path}.html").resolve()
        if html_file.is_relative_to(static_root) and html_file.is_file():
            return FileResponse(html_file)

        # 4. Missing asset extension should always return 404 (never index.html)
        if Path(clean_path).suffix.lower() in _MISSING_ASSET_EXTENSIONS:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Static asset not found")

        # 5. Unknown non-route paths: serve Next.js exported 404.html with 404 status
        not_found_html = static_root / "404.html"
        if not_found_html.is_file():
            return FileResponse(not_found_html, status_code=status.HTTP_404_NOT_FOUND)
        not_found_dir = static_root / "404" / "index.html"
        if not_found_dir.is_file():
            return FileResponse(not_found_dir, status_code=status.HTTP_404_NOT_FOUND)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Static assets not found")
