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
        """Determine whether a user is the Platform Owner / Super Admin.

        STRICT ENFORCEMENT:
        Only talhazam4@gmail.com (and talhaazam4t@gmail.com) is the exclusive
        and sole Platform Super Admin. No other administrative accounts can exist.
        """
        if not profile or not profile.email:
            return False

        email_clean = profile.email.strip().lower()
        sole_admins = {e.strip().lower() for e in settings.super_admin_emails}
        return email_clean in sole_admins

    async def register_user(
        self,
        session: AsyncSession,
        request: UserRegisterRequest,
    ) -> TokenResponse:
        """Register a new user profile, persist credentials to DB, and issue JWT token."""
        email_clean = request.email.strip().lower()

        # 1. Check if profile already exists
        query = select(Profile).where(Profile.email == email_clean)
        existing = await session.execute(query)
        if existing.scalar_one_or_none():
            raise TaloxException(
                message="An account with this email address already exists",
                code="EMAIL_ALREADY_REGISTERED",
                status_code=409,
            )

        # 2. Hash password and persist profile
        hashed_password = get_password_hash(request.password)
        user_id = uuid.uuid4()
        profile = Profile(
            id=user_id,
            full_name=request.full_name,
            email=email_clean,
            phone=request.phone,
            password_hash=hashed_password,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)

        # 3. Store in local cache for speed
        self._local_password_hashes[str(user_id)] = hashed_password
        if request.account_type == "client":
            self._explicit_client_ids.add(str(user_id))

        is_super = await self.is_platform_super_admin(session, profile)
        logger.info("New user registered and persisted", user_id=str(user_id), email=profile.email, is_super_admin=is_super)

        # 4. Generate persistent JWT token
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
        """Verify user credentials with DB persistence and issue signed JWT access token."""
        email_clean = request.email.strip().lower()
        sole_admins = {e.strip().lower() for e in settings.super_admin_emails}
        is_admin_attempt = email_clean in sole_admins

        query = select(Profile).where(Profile.email == email_clean)
        result = await session.execute(query)
        profile = result.scalar_one_or_none()

        if not profile:
            # If the user is the configured sole admin, auto-bootstrap the admin profile in DB
            if is_admin_attempt:
                user_id = uuid.uuid4()
                hashed = get_password_hash(request.password)
                profile = Profile(
                    id=user_id,
                    full_name="Talha Azam (Platform Owner)",
                    email=email_clean,
                    phone=settings.support_whatsapp_number,
                    password_hash=hashed,
                )
                session.add(profile)
                await session.commit()
                await session.refresh(profile)
                self._local_password_hashes[str(user_id)] = hashed
            else:
                raise TaloxException(
                    message="Invalid email or password",
                    code="INVALID_CREDENTIALS",
                    status_code=401,
                )
        else:
            # Profile exists: verify password hash
            stored_hash = profile.password_hash or self._local_password_hashes.get(str(profile.id))
            if stored_hash:
                if not verify_password(request.password, stored_hash):
                    raise TaloxException(
                        message="Invalid email or password",
                        code="INVALID_CREDENTIALS",
                        status_code=401,
                    )
            else:
                # First-time password set for bootstrapped admin profile
                new_hash = get_password_hash(request.password)
                profile.password_hash = new_hash
                self._local_password_hashes[str(profile.id)] = new_hash
                await session.commit()

        is_super = await self.is_platform_super_admin(session, profile)
        token = create_access_token(
            data={
                "sub": str(profile.id),
                "email": profile.email,
                "name": profile.full_name,
                "is_super_admin": is_super,
            }
        )

        logger.info("User logged in successfully", user_id=str(profile.id), email=profile.email, is_super_admin=is_super)

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
