"""User Profile & Membership Self-Service API Endpoints.
"""

from typing import Optional

from app.database.models.tenant import Profile
from app.database.supabase import get_db
from app.dependencies import get_current_user
from app.schemas.auth import UserProfileResponse
from app.services.auth_service import auth_service
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/users", tags=["Users"])


class UserProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Retrieve the authenticated user's profile."""
    is_super = await auth_service.is_platform_super_admin(session, current_user)
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        phone=current_user.phone,
        is_super_admin=is_super,
    )


@router.patch("/me", response_model=UserProfileResponse)
async def update_my_profile(
    request: UserProfileUpdateRequest,
    current_user: Profile = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Update the authenticated user's full name or phone number."""
    if request.full_name is not None:
        current_user.full_name = request.full_name
    if request.phone is not None:
        current_user.phone = request.phone
    await session.commit()
    await session.refresh(current_user)
    is_super = await auth_service.is_platform_super_admin(session, current_user)
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        phone=current_user.phone,
        is_super_admin=is_super,
    )
