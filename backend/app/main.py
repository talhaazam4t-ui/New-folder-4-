"""Main FastAPI Application Entrypoint for Talox Tech Stream.

Configures:
1. Lifespan event handlers (logging setup, resource checks).
2. CORS middleware.
3. SlowAPI rate limiting (cost protection).
4. Standardized JSON response envelope and exception handlers.
5. API v1 routing and system health checks.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from app.api.router import api_v1_router
from app.config import settings
from app.core.exceptions import TaloxException
from app.core.logging import logger, setup_logging
from app.core.rate_limit import limiter
from app.database.supabase import init_db
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded


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
    yield
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
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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


# System Health Check & Frontend Delivery Endpoints
@app.get("/", tags=["Frontend"])
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


@app.get("/health", tags=["Health"])
async def platform_health():
    """Alternative health check endpoint for Render and container probes."""
    return await health_check()


@app.get("/api/v1/health", tags=["Health"])
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


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa_and_static(full_path: str):
    """Serve client-side routes and static assets, preserving API routes and Swagger docs."""
    clean_path = full_path.strip("/")
    if (
        clean_path.startswith("api/")
        or clean_path == "api"
        or clean_path in ("docs", "redoc", "openapi.json", "health")
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")

    if STATIC_DIR:
        # 1. Exact file match (e.g. favicon.ico, 404.html, index.txt)
        direct_file = STATIC_DIR / clean_path
        if direct_file.is_file():
            return FileResponse(direct_file)

        # 2. Directory index match (e.g. login -> login/index.html)
        dir_index = STATIC_DIR / clean_path / "index.html"
        if dir_index.is_file():
            return FileResponse(dir_index)

        # 3. HTML file match (e.g. login -> login.html)
        html_file = STATIC_DIR / f"{clean_path}.html"
        if html_file.is_file():
            return FileResponse(html_file)

        # 4. Fallback to root index.html for client-side SPA routing
        index_file = STATIC_DIR / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Static assets not found")
