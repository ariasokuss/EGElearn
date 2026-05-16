import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    ref_code: str | None = Field(None, max_length=64)
    visitor_id: str | None = Field(None, max_length=36)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class GoogleCredentialRequest(BaseModel):
    """JWT `credential` from Google Identity Services (One Tap / Sign-In button)."""

    credential: str = Field(
        ..., min_length=1, description="Google ID token (JWT string)"
    )


class DesktopLoginRequest(BaseModel):
    token: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class GoogleAuthorizationUrlResponse(BaseModel):
    authorization_url: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access token TTL in seconds


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(None, max_length=100)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class RequestEmailChangeRequest(BaseModel):
    new_email: EmailStr
    password: str


class ConfirmEmailChangeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    is_active: bool
    is_verified: bool
    display_name: str | None = None
    avatar_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
