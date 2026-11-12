"""Main FastAPI Application Entrypoint for Talox Tech Stream.

Configures:
1. Lifespan event handlers (logging setup, resource checks).
2. CORS middleware.
3. SlowAPI rate limiting (cost protection).
4. Standardized JSON response envelope and exception handlers.
5. API v1 routing and system health checks.
"""

from contextlib import asynccontextmanager

from app.api.router import api_v1_router
from app.config import settings
from app.core.exceptions import TaloxException
from app.core.logging import logger, setup_logging
from app.core.rate_limit import limiter
from app.database.supabase import init_db
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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


# System Health Check Endpoints
@app.get("/", tags=["Health"])
async def root():
    """Root platform discovery endpoint."""
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
