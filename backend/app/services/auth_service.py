"""Authentication Service — Handles User Registration, Login, and Profile Management.
"""

import uuid
from typing import Optional

from app.config import settings
from app.core.exceptions import TaloxException
from app.core.logging import logger
from app.core.security import create_access_token, get_password_hash, verify_password
from app.database.models.tenant import Profile
from app.schemas.auth import TokenResponse, UserLoginRequest, UserRegisterRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class AuthService:
    """Manages profile records and JWT credential verification."""

    # In development/local mode, we store password hash in settings / profile metadata.
    # In live Supabase mode, Supabase Auth handles password management.
    # We maintain a password store dictionary for local development resilience.
    _local_password_hashes = {}
    _explicit_client_ids = set()

    async def is_platform_super_admin(
        self,
        session: AsyncSession,
        profile: Profile,
    ) -> bool:
        """Determine whether a user is the Platform Owner / Super Admin vs a regular Client.

        Rules:
        1. Explicit client accounts (`account_type="client"`) are never Super Admins.
        2. Any email listed in `settings.super_admin_emails` or ending with `@talox.com` / `@talox.io` is a Super Admin.
        3. The initial bootstrap account (first registered profile in the platform DB) is treated as Platform Owner
           unless explicitly registered as a client. All subsequent tenant owners are strictly Clients.
        """
        if str(profile.id) in self._explicit_client_ids:
            return False

        email_lower = (profile.email or "").lower()
        configured_admins = {e.lower() for e in settings.super_admin_emails}
        if email_lower in configured_admins or email_lower.endswith("@talox.com") or email_lower.endswith("@talox.io"):
            return True

        first_profile_res = await session.execute(
            select(Profile.id).order_by(Profile.created_at.asc(), Profile.id.asc()).limit(1)
        )
        first_profile_id = first_profile_res.scalar_one_or_none()
        return first_profile_id == profile.id

    async def register_user(
        self,
        session: AsyncSession,
        request: UserRegisterRequest,
    ) -> TokenResponse:
        """Register a new user profile and issue JWT token."""
        # 1. Check if profile already exists
        query = select(Profile).where(Profile.email == request.email.lower())
        existing = await session.execute(query)
        if existing.scalar_one_or_none():
            raise TaloxException(
                message="An account with this email address already exists",
                code="EMAIL_ALREADY_REGISTERED",
                status_code=409,
            )

        # 2. Create profile
        user_id = uuid.uuid4()
        profile = Profile(
            id=user_id,
            full_name=request.full_name,
            email=request.email.lower(),
            phone=request.phone,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)

        # 3. Store password hash for verification
        self._local_password_hashes[str(user_id)] = get_password_hash(request.password)
        if request.account_type == "client":
            self._explicit_client_ids.add(str(user_id))

        is_super = await self.is_platform_super_admin(session, profile)
        logger.info("New user registered", user_id=str(user_id), email=profile.email, is_super_admin=is_super)

        # 4. Generate JWT token
        token = create_access_token(
            data={
                "sub": str(user_id),
                "email": profile.email,
                "name": profile.full_name,
                "is_super_admin": is_super,
            }
        )

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user_id=profile.id,
            email=profile.email,
            full_name=profile.full_name,
            is_super_admin=is_super,
        )

    async def login_user(
        self,
        session: AsyncSession,
        request: UserLoginRequest,
    ) -> TokenResponse:
        """Verify user credentials and issue signed JWT access token."""
        query = select(Profile).where(Profile.email == request.email.lower())
        result = await session.execute(query)
        profile = result.scalar_one_or_none()

        if not profile:
            raise TaloxException(
                message="Invalid email or password",
                code="INVALID_CREDENTIALS",
                status_code=401,
            )

        # Verify password hash
        stored_hash = self._local_password_hashes.get(str(profile.id))
        if stored_hash and not verify_password(request.password, stored_hash):
            raise TaloxException(
                message="Invalid email or password",
                code="INVALID_CREDENTIALS",
                status_code=401,
            )

        is_super = await self.is_platform_super_admin(session, profile)
        token = create_access_token(
            data={
                "sub": str(profile.id),
                "email": profile.email,
                "name": profile.full_name,
                "is_super_admin": is_super,
            }
        )

        logger.info("User logged in successfully", user_id=str(profile.id), is_super_admin=is_super)

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user_id=profile.id,
            email=profile.email,
            full_name=profile.full_name,
            is_super_admin=is_super,
        )

    async def get_profile(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
    ) -> Optional[Profile]:
        """Fetch profile by user ID."""
        query = select(Profile).where(Profile.id == user_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()


auth_service = AuthService()
