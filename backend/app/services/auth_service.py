"""Authentication Service — Handles User Registration, Login, and Profile Management.
"""

import hmac
import uuid
from typing import Dict, Optional, Set

from app.config import settings
from app.core.exceptions import TaloxException
from app.core.logging import logger
from app.core.security import create_access_token, get_password_hash, verify_password
from app.database.models.automation import AuditLog
from app.database.models.tenant import Profile
from app.schemas.auth import TokenResponse, UserLoginRequest, UserRegisterRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class AuthService:
    """Manages profile records and JWT credential verification."""

    # In development/local mode, we store password hash in settings / profile metadata.
    # In live Supabase mode, Supabase Auth handles password management.
    # We maintain a password store dictionary for local development resilience.
    _local_password_hashes: Dict[str, str] = {}
    _explicit_client_ids: Set[str] = set()

    def _check_super_admin_bootstrap_gate(
        self,
        email_clean: str,
        password: str,
        *,
        for_registration: bool = False,
    ) -> None:
        """Enforce production/staging bootstrap gating and minimum password length for super-admin setup."""
        if len(password or "") < 8:
            logger.warning(
                "Blocked super-admin bootstrap with insufficient password length",
                email=email_clean,
                for_registration=for_registration,
            )
            raise TaloxException(
                message="Super-admin bootstrap password must be at least 8 characters long",
                code="INVALID_CREDENTIALS" if not for_registration else "WEAK_PASSWORD",
                status_code=401 if not for_registration else 400,
            )

        if settings.app_env in ("production", "staging"):
            configured_bootstrap = (settings.super_admin_bootstrap_password or "").strip()
            authorized = False
            if configured_bootstrap:
                authorized = hmac.compare_digest(password, configured_bootstrap)
            elif settings.allow_super_admin_bootstrap:
                authorized = True

            if not authorized:
                logger.warning(
                    "Blocked unauthorized super-admin bootstrap attempt",
                    email=email_clean,
                    for_registration=for_registration,
                )
                if for_registration:
                    raise TaloxException(
                        message="Super-admin registration is restricted in production/staging",
                        code="SUPER_ADMIN_BOOTSTRAP_REQUIRED",
                        status_code=403,
                    )
                raise TaloxException(
                    message="Invalid email or password",
                    code="INVALID_CREDENTIALS",
                    status_code=401,
                )

    async def is_platform_super_admin(
        self,
        session: AsyncSession,
        profile: Profile,
    ) -> bool:
        """Determine whether a user is a Platform Owner / Super Admin.

        STRICT ENFORCEMENT:
        Only emails configured in `settings.super_admin_emails` are recognized as
        Platform Super Admins. No other administrative accounts can exist.
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
        sole_admins = {e.strip().lower() for e in settings.super_admin_emails}
        is_admin_attempt = email_clean in sole_admins

        # 1. Check if profile already exists
        query = select(Profile).where(Profile.email == email_clean)
        existing = await session.execute(query)
        if existing.scalar_one_or_none():
            raise TaloxException(
                message="An account with this email address already exists",
                code="EMAIL_ALREADY_REGISTERED",
                status_code=409,
            )

        if is_admin_attempt:
            self._check_super_admin_bootstrap_gate(
                email_clean,
                request.password,
                for_registration=True,
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
        if is_admin_attempt:
            session.add(
                AuditLog(
                    actor_id=user_id,
                    actor_type="admin",
                    action="admin.super_admin.bootstrapped_register",
                    resource_type="profile",
                    resource_id=user_id,
                    metadata_={"email": email_clean, "app_env": settings.app_env},
                )
            )
        await session.commit()
        await session.refresh(profile)

        # 3. Store in local cache for speed
        self._local_password_hashes[str(user_id)] = hashed_password
        if request.account_type == "client":
            self._explicit_client_ids.add(str(user_id))

        is_super = await self.is_platform_super_admin(session, profile)
        if is_super:
            logger.info("Super-admin account registered via bootstrap gate", user_id=str(user_id), email=profile.email)
        else:
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
            # If the user is a configured super admin, require bootstrap gate before creating profile
            if is_admin_attempt:
                self._check_super_admin_bootstrap_gate(
                    email_clean,
                    request.password,
                    for_registration=False,
                )
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
                session.add(
                    AuditLog(
                        actor_id=user_id,
                        actor_type="admin",
                        action="admin.super_admin.bootstrapped_first_login",
                        resource_type="profile",
                        resource_id=user_id,
                        metadata_={"email": email_clean, "app_env": settings.app_env},
                    )
                )
                await session.commit()
                await session.refresh(profile)
                self._local_password_hashes[str(user_id)] = hashed
                logger.info(
                    "Super-admin profile bootstrapped on first login",
                    user_id=str(user_id),
                    email=email_clean,
                )
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
                if not is_admin_attempt:
                    raise TaloxException(
                        message="Invalid email or password",
                        code="INVALID_CREDENTIALS",
                        status_code=401,
                    )
                self._check_super_admin_bootstrap_gate(
                    email_clean,
                    request.password,
                    for_registration=False,
                )
                # First-time password set strictly for bootstrapped super admin profile
                new_hash = get_password_hash(request.password)
                profile.password_hash = new_hash
                self._local_password_hashes[str(profile.id)] = new_hash
                session.add(
                    AuditLog(
                        actor_id=profile.id,
                        actor_type="admin",
                        action="admin.super_admin.password_bootstrapped",
                        resource_type="profile",
                        resource_id=profile.id,
                        metadata_={"email": email_clean, "app_env": settings.app_env},
                    )
                )
                await session.commit()
                logger.info(
                    "Super-admin password bootstrapped on first login",
                    user_id=str(profile.id),
                    email=email_clean,
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
