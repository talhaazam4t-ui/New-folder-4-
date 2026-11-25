"""Authentication API Endpoints."""

from app.config import settings
from app.core.rate_limit import limiter
from app.core.turnstile import is_turnstile_enabled, verify_turnstile_token
from app.database.models.tenant import Profile
from app.database.supabase import get_db
from app.dependencies import get_current_user
from app.schemas.auth import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
    VerifyEmailRequest,
)
from app.services.auth_service import auth_service
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/public-config")
async def get_auth_public_config():
    """Return non-secret frontend auth capabilities (e.g. Cloudflare Turnstile Site Key)."""
    return {
        "success": True,
        "data": {
            "turnstile_enabled": is_turnstile_enabled(),
            "turnstile_site_key": (settings.turnstile_site_key or "").strip() if is_turnstile_enabled() else None,
        },
    }


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
@limiter.limit("20/minute")
async def register(
    request: Request,
    payload: UserRegisterRequest,
    session: AsyncSession = Depends(get_db),
):
    """Register a new user account."""
    await verify_turnstile_token(
        payload.turnstile_token,
        request.client.host if request.client else None,
    )
    return await auth_service.register_user(session, payload)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("20/minute")
async def login(
    request: Request,
    payload: UserLoginRequest,
    session: AsyncSession = Depends(get_db),
):
    """Log in with email and password to receive JWT access token."""
    await verify_turnstile_token(
        payload.turnstile_token,
        request.client.host if request.client else None,
    )
    return await auth_service.login_user(session, payload)


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_db),
):
    """Request a password reset email link."""
    await verify_turnstile_token(
        payload.turnstile_token,
        request.client.host if request.client else None,
    )
    data = await auth_service.request_password_reset(session, payload.email)
    return {"success": True, "data": data, "message": data["message"]}


@router.post("/reset-password")
@limiter.limit("10/minute")
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_db),
):
    """Complete password reset using a valid single-use reset token."""
    data = await auth_service.reset_password(session, payload.token, payload.new_password)
    return {"success": True, "data": data, "message": "Password updated successfully. You can now log in."}


@router.post("/verify-email")
@limiter.limit("10/minute")
async def verify_email(
    request: Request,
    payload: VerifyEmailRequest,
    session: AsyncSession = Depends(get_db),
):
    """Verify user email address using single-use verification token."""
    data = await auth_service.verify_email(session, payload.token)
    return {"success": True, "data": data, "message": "Email verified successfully."}


@router.post("/resend-verification")
@limiter.limit("3/minute")
async def resend_verification(
    request: Request,
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Resend email verification link to the currently logged-in user."""
    data = await auth_service.send_verification_email(session, current_user)
    return {"success": True, "data": data, "message": "Verification email dispatched."}


@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Fetch profile of currently authenticated user."""
    is_super = await auth_service.is_platform_super_admin(session, current_user)
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        phone=current_user.phone,
        is_super_admin=is_super,
        email_verified=bool(getattr(current_user, "email_verified", False)),
    )
