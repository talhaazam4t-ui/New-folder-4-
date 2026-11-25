"""Authentication Service — Handles User Registration, Login, and Profile Management.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Any, Dict, Optional, Set
import uuid

from app.config import settings
from app.core.exceptions import TaloxException
from app.core.logging import logger
from app.core.security import create_access_token, get_password_hash, verify_password
from app.database.models.automation import AuditLog, AuthToken
from app.database.models.tenant import Profile
from app.integrations.email.adapter import email_adapter
from app.schemas.auth import TokenResponse, UserLoginRequest, UserRegisterRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _hash_auth_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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

        # Dispatch email verification link (non-blocking if transactional email fails)
        try:
            await self.send_verification_email(session, profile)
        except Exception as exc:
            logger.warning("Failed to issue verification email on signup", error=str(exc))

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

    async def _issue_auth_token(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        token_type: str,
        ttl_minutes: int,
    ) -> str:
        """Create a single-use cryptographic token, persisting only its SHA-256 hash."""
        raw_token = secrets.token_urlsafe(32)
        now_utc = datetime.now(timezone.utc)
        row = AuthToken(
            user_id=user_id,
            token_hash=_hash_auth_token(raw_token),
            token_type=token_type,
            expires_at=now_utc + timedelta(minutes=ttl_minutes),
        )
        session.add(row)
        await session.commit()
        return raw_token

    async def send_verification_email(
        self,
        session: AsyncSession,
        profile: Profile,
    ) -> Dict[str, Any]:
        """Issue an email verification token and dispatch the verification link."""
        raw_token = await self._issue_auth_token(
            session=session,
            user_id=profile.id,
            token_type="email_verify",
            ttl_minutes=60 * 24,
        )
        verify_url = f"{settings.frontend_url.rstrip('/')}/verify-email?token={raw_token}"
        delivery = await email_adapter.send_transactional_email(
            to_email=profile.email,
            subject="Verify your Talox Tech Stream email",
            html_body=(
                f"<p>Hi {profile.full_name},</p>"
                "<p>Confirm your email address to secure your Talox Tech Stream workspace:</p>"
                f"<p><a href='{verify_url}'>{verify_url}</a></p>"
                "<p>This link expires in 24 hours.</p>"
            ),
            text_body=f"Hi {profile.full_name},\n\nVerify your email: {verify_url}\n\nThis link expires in 24 hours.",
        )
        return {"sent": True, "delivery": delivery}

    async def verify_email(
        self,
        session: AsyncSession,
        token: str,
    ) -> Dict[str, Any]:
        """Validate email verification token and mark profile.email_verified = True."""
        now_utc = datetime.now(timezone.utc)
        token_hash = _hash_auth_token(token.strip())
        res = await session.execute(
            select(AuthToken).where(
                AuthToken.token_hash == token_hash,
                AuthToken.token_type == "email_verify",
            )
        )
        auth_tok = res.scalar_one_or_none()
        if not auth_tok or auth_tok.used_at is not None or _ensure_utc(auth_tok.expires_at) < now_utc:
            raise TaloxException(
                message="Verification link is invalid or has expired.",
                code="INVALID_VERIFICATION_TOKEN",
                status_code=400,
            )

        prof_res = await session.execute(select(Profile).where(Profile.id == auth_tok.user_id))
        profile = prof_res.scalar_one_or_none()
        if not profile:
            raise TaloxException(message="Account not found", code="USER_NOT_FOUND", status_code=404)

        profile.email_verified = True
        auth_tok.used_at = now_utc
        session.add(
            AuditLog(
                actor_id=profile.id,
                actor_type="user",
                action="auth.email.verified",
                resource_type="profile",
                resource_id=profile.id,
                metadata_={"email": profile.email},
            )
        )
        await session.commit()
        return {"email_verified": True, "email": profile.email}

    async def request_password_reset(
        self,
        session: AsyncSession,
        email: str,
    ) -> Dict[str, Any]:
        """Issue a 30-minute single-use password reset link if an account matches."""
        email_clean = email.strip().lower()
        res = await session.execute(select(Profile).where(Profile.email == email_clean))
        profile = res.scalar_one_or_none()

        if profile:
            raw_token = await self._issue_auth_token(
                session=session,
                user_id=profile.id,
                token_type="password_reset",
                ttl_minutes=30,
            )
            reset_url = f"{settings.frontend_url.rstrip('/')}/reset-password?token={raw_token}"
            await email_adapter.send_transactional_email(
                to_email=profile.email,
                subject="Reset your Talox Tech Stream password",
                html_body=(
                    f"<p>Hi {profile.full_name},</p>"
                    "<p>Click below to set a new password (valid for 30 minutes):</p>"
                    f"<p><a href='{reset_url}'>{reset_url}</a></p>"
                    "<p>If you did not request this, you can safely ignore this email.</p>"
                ),
                text_body=f"Hi {profile.full_name},\n\nReset your password (valid 30 min): {reset_url}",
            )
            session.add(
                AuditLog(
                    actor_id=profile.id,
                    actor_type="user",
                    action="auth.password_reset.requested",
                    resource_type="profile",
                    resource_id=profile.id,
                    metadata_={"email": profile.email},
                )
            )
            await session.commit()

        return {
            "accepted": True,
            "message": "If an account exists for that email address, a password reset link has been sent.",
        }

    async def reset_password(
        self,
        session: AsyncSession,
        token: str,
        new_password: str,
    ) -> Dict[str, Any]:
        """Validate password reset token, update bcrypt hash, and mark token used."""
        now_utc = datetime.now(timezone.utc)
        token_hash = _hash_auth_token(token.strip())
        res = await session.execute(
            select(AuthToken).where(
                AuthToken.token_hash == token_hash,
                AuthToken.token_type == "password_reset",
            )
        )
        auth_tok = res.scalar_one_or_none()
        if not auth_tok or auth_tok.used_at is not None or _ensure_utc(auth_tok.expires_at) < now_utc:
            raise TaloxException(
                message="Password reset link is invalid or has expired.",
                code="INVALID_RESET_TOKEN",
                status_code=400,
            )

        prof_res = await session.execute(select(Profile).where(Profile.id == auth_tok.user_id))
        profile = prof_res.scalar_one_or_none()
        if not profile:
            raise TaloxException(message="Account not found", code="USER_NOT_FOUND", status_code=404)

        new_hash = get_password_hash(new_password)
        profile.password_hash = new_hash
        self._local_password_hashes[str(profile.id)] = new_hash
        auth_tok.used_at = now_utc
        session.add(
            AuditLog(
                actor_id=profile.id,
                actor_type="user",
                action="auth.password.reset_completed",
                resource_type="profile",
                resource_id=profile.id,
                metadata_={"email": profile.email},
            )
        )
        await session.commit()
        return {"reset": True, "email": profile.email}


auth_service = AuthService()
