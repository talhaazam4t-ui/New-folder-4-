"""Authentication API Endpoints.
"""

from app.database.models.tenant import Profile
from app.database.supabase import get_db
from app.dependencies import get_current_user
from app.schemas.auth import (
    TokenResponse,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
)
from app.services.auth_service import auth_service
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
async def register(
    request: UserRegisterRequest,
    session: AsyncSession = Depends(get_db),
):
    """Register a new user account."""
    return await auth_service.register_user(session, request)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: UserLoginRequest,
    session: AsyncSession = Depends(get_db),
):
    """Log in with email and password to receive JWT access token."""
    return await auth_service.login_user(session, request)


@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    current_user: Profile = Depends(get_current_user),
):
    """Fetch profile of currently authenticated user."""
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        phone=current_user.phone,
    )
