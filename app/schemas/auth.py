from typing import Literal
from uuid import UUID
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.core.phone import IndianPhone


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class OtpRequest(BaseModel):
    phone: IndianPhone
    # staff = outlet admin/dashboard login; require active membership before sending OTP
    audience: Literal["consumer", "staff"] = "consumer"


class OtpRequestResponse(BaseModel):
    message: str = "If this phone number is registered, a WhatsApp verification code has been sent."


class OtpVerifyRequest(BaseModel):
    phone: IndianPhone
    otp_code: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class MembershipSummaryResponse(BaseModel):
    membership_id: UUID
    outlet_id: UUID
    outlet_name: str
    outlet_slug: str
    role_name: str
    active_status: bool


class AuthMeResponse(BaseModel):
    id: UUID
    name: str
    phone: str
    email: str | None = None
    avatar_url: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    dietary_preferences: list[str] = []
    profile_completed_at: datetime | None = None
    outlet_id: UUID | None = None
    outlet_name: str | None = None
    outlet_slug: str | None = None
    outlet_logo_url: str | None = None
    role_name: str | None = None
    permissions: list[str]
    memberships: list[MembershipSummaryResponse] = []
    is_support_session: bool = False
    require_customer_login: bool = False


class SelectOutletRequest(BaseModel):
    outlet_id: UUID
