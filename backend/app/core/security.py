"""Core Security Module

Provides:
1. Data Sanitization & Redaction (PII, Financial, and Secret Masking) before external AI calls.
2. Password Hashing and Verification.
3. JWT Token Generation and Decoding.
"""

import base64
import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
from app.config import settings
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt

# JWT Configuration — 30 Days Persistent Client Session
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 days persistent session (client remembered)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the stored bcrypt hash."""
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generate bcrypt hash for a password (truncated to 72 bytes for bcrypt safety)."""
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """Generate a signed JWT token containing claims."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(to_encode, settings.app_secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a signed JWT token with dual support for Supabase Auth and internal JWTs."""
    # 1. Attempt Supabase Auth verification if SUPABASE_JWT_SECRET is configured
    if settings.supabase_jwt_secret:
        try:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=[ALGORITHM],
                options={"verify_aud": False, "require_exp": True, "require_sub": True},
            )
            # Normalize claims from Supabase JWT format
            if "sub" in payload and "user_id" not in payload:
                payload["user_id"] = payload["sub"]
            app_meta = payload.get("app_metadata") or {}
            if isinstance(app_meta, dict):
                if "role" in app_meta and "role" not in payload:
                    payload["role"] = app_meta["role"]
                if "tenant_id" in app_meta and "tenant_id" not in payload:
                    payload["tenant_id"] = app_meta["tenant_id"]
            return payload
        except JWTError:
            pass

    # 2. Fallback to application secret key verification
    try:
        payload = jwt.decode(
            token,
            settings.app_secret_key,
            algorithms=[ALGORITHM],
            options={"require_exp": True, "require_sub": True},
        )
        return payload
    except JWTError:
        return None


# ==============================================================================
# SENSITIVE DATA REDACTION & SANITIZATION PIPELINE
# ==============================================================================

# Regex patterns for sensitive data
CREDIT_CARD_REGEX = re.compile(
    r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12}|(?:2131|1800|35\d{3})\d{11})\b"
)
CARD_WITH_SEPARATORS_REGEX = re.compile(
    r"\b(?:\d{4}[-\s]){3}\d{4}\b"
)
CVV_REGEX = re.compile(
    r"(?i)\b(?:cvv|cvc|security\s*code|cid)[:= ]+\s*(\d{3,4})\b"
)
PASSWORD_REGEX = re.compile(
    r"(?i)\b(?:password|passwd|pwd|secret)[:= ]+\s*([^\s,;]+)"
)
IBAN_REGEX = re.compile(
    r"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{4}[0-9]{7}([A-Z0-9]?){0,16}\b"
)
SSN_REGEX = re.compile(
    r"\b\d{3}-\d{2}-\d{4}\b"
)
NATIONAL_ID_REGEX = re.compile(
    r"\b\d{5}-\d{7}-\d{1}\b"
)
API_KEY_REGEX = re.compile(
    r"(?i)\b(?:bearer\s+[a-zA-Z0-9\-_]{20,}|(?:sk|pk|key|token)[-_][a-zA-Z0-9\-_]{20,})\b"
)


def sanitize_ai_prompt(prompt: str) -> str:
    """Mask sensitive PII, credentials, and financial numbers before external AI dispatch.

    Compliance guarantee:
    - Credit cards -> [REDACTED_CARD]
    - CVV/CVC -> cvv: [REDACTED_CVV]
    - Passwords -> password: [REDACTED_PASSWORD]
    - Bank IBANs -> [REDACTED_IBAN]
    - SSN / National IDs -> [REDACTED_ID]
    - API keys & Tokens -> [REDACTED_SECRET]
    """
    if not prompt:
        return ""

    sanitized = prompt

    # Redact API Keys / Bearer Tokens
    sanitized = API_KEY_REGEX.sub("[REDACTED_SECRET]", sanitized)

    # Redact Passwords
    sanitized = PASSWORD_REGEX.sub(r"password: [REDACTED_PASSWORD]", sanitized)

    # Redact CVV
    sanitized = CVV_REGEX.sub(r"cvv: [REDACTED_CVV]", sanitized)

    # Redact Formatted Credit Cards (with dashes or spaces)
    sanitized = CARD_WITH_SEPARATORS_REGEX.sub("[REDACTED_CARD]", sanitized)

    # Redact Raw Credit Cards (13-19 continuous digits)
    sanitized = CREDIT_CARD_REGEX.sub("[REDACTED_CARD]", sanitized)

    # Redact Bank IBANs
    sanitized = IBAN_REGEX.sub("[REDACTED_IBAN]", sanitized)

    # Redact SSN
    sanitized = SSN_REGEX.sub("[REDACTED_ID]", sanitized)

    # Redact Pakistani CNIC / Format National IDs
    sanitized = NATIONAL_ID_REGEX.sub("[REDACTED_ID]", sanitized)

    return sanitized


# ==============================================================================
# CREDENTIAL ENCRYPTION AT REST & SAFE API MASKING
# ==============================================================================

SENSITIVE_CONFIG_KEYS = {
    "access_token",
    "refresh_token",
    "api_key",
    "secret_key",
    "client_secret",
    "webhook_secret",
    "password",
    "oauth_code",
    "token",
    "secret",
    "private_key",
}


def _get_fernet() -> Fernet:
    """Derive a URL-safe 32-byte key from APP_SECRET_KEY for Fernet AES-128-CBC + HMAC encryption."""
    digest = hashlib.sha256(settings.app_secret_key.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def encrypt_secret(plain_value: str) -> str:
    """Encrypt a sensitive credential string at rest with prefix `enc:v1:`."""
    if not plain_value:
        return ""
    if plain_value.startswith("enc:v1:"):
        return plain_value
    token = _get_fernet().encrypt(plain_value.encode("utf-8")).decode("utf-8")
    return f"enc:v1:{token}"


def decrypt_secret(encrypted_value: str) -> str:
    """Decrypt a `enc:v1:` credential string on the backend when invoking a provider API."""
    if not encrypted_value:
        return ""
    if not encrypted_value.startswith("enc:v1:"):
        return encrypted_value
    raw_token = encrypted_value[len("enc:v1:"):]
    try:
        return _get_fernet().decrypt(raw_token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ""


def _is_sensitive_key(key: str) -> bool:
    key_lower = key.lower()
    return any(s in key_lower for s in SENSITIVE_CONFIG_KEYS)


def encrypt_sensitive_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Encrypt any sensitive keys inside an integration configuration dictionary before DB persistence."""
    if not config:
        return {}
    result: Dict[str, Any] = {}
    for k, v in config.items():
        if isinstance(v, dict):
            result[k] = encrypt_sensitive_config(v)
        elif isinstance(v, str) and _is_sensitive_key(k):
            result[k] = encrypt_secret(v)
        else:
            result[k] = v
    return result


def mask_sensitive_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Mask encrypted or sensitive values before returning integration configuration to any API client."""
    if not config:
        return {}
    masked: Dict[str, Any] = {}
    for k, v in config.items():
        if isinstance(v, dict):
            masked[k] = mask_sensitive_config(v)
        elif _is_sensitive_key(k) or (isinstance(v, str) and v.startswith("enc:v1:")):
            masked[k] = "***ENCRYPTED***"
        else:
            masked[k] = v
    return masked

