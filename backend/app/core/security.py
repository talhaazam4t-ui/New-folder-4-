"""Core Security Module

Provides:
1. Data Sanitization & Redaction (PII, Financial, and Secret Masking) before external AI calls.
2. Password Hashing and Verification.
3. JWT Token Generation and Decoding.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.config import settings
from jose import JWTError, jwt
from passlib.context import CryptContext

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate bcrypt hash for a password."""
    return pwd_context.hash(password)


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
    """Decode and validate a signed JWT token."""
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
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
