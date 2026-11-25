"""Pydantic Schemas for Authentication and User Profiles.
"""

from typing import Optional
import uuid

from pydantic import BaseModel, EmailStr, Field


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Password must be at least 8 characters long")
    full_name: str = Field(min_length=2, max_length=255)
    phone: Optional[str] = None
    account_type: Optional[str] = Field(default=None, description="Optional account role hint: client or owner")
    turnstile_token: Optional[str] = None


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str
    turnstile_token: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    turnstile_token: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    email: str
    full_name: str
    is_super_admin: bool = False


class UserProfileResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: Optional[str] = None
    is_super_admin: bool = False
    email_verified: bool = False
