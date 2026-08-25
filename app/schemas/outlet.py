from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.phone import IndianPhone
from app.models.enums import OutletType, VerificationStatus


class OutletCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255)
    owner_name: str = Field(min_length=1, max_length=255)
    owner_phone: IndianPhone
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    whatsapp_phone: str | None = Field(default=None, max_length=50)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    landmark: str | None = Field(default=None, max_length=255)
    area: str | None = Field(default=None, max_length=128)
    city: str | None = Field(default=None, max_length=128)
    state: str | None = Field(default=None, max_length=128)
    pincode: str | None = Field(default=None, max_length=12)
    latitude: float | None = None
    longitude: float | None = None
    description: str | None = Field(default=None, max_length=1024)
    cuisine_tags: list[str] | None = None
    fssai_number: str | None = Field(default=None, max_length=50)
    cost_for_two: int | None = Field(default=None, ge=0, le=100000)
    is_pure_veg: bool = False
    outlet_type: OutletType | None = None
    gst_number: str | None = Field(default=None, max_length=50)

    @field_validator("cuisine_tags")
    @classmethod
    def _normalize_cuisine_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        for item in value:
            tag = item.strip()
            if tag and tag not in cleaned:
                cleaned.append(tag[:64])
        return cleaned or None

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class OutletListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    active_status: bool
    verification_status: VerificationStatus
    require_customer_login: bool
    require_prepaid: bool
    created_at: datetime


class OutletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    logo_url: str | None
    address: str | None
    phone: str | None
    gst_number: str | None
    active_status: bool
    verification_status: VerificationStatus
    require_customer_login: bool
    require_prepaid: bool
    created_at: datetime
    updated_at: datetime


class OutletSettingsUpdate(BaseModel):
    require_customer_login: bool | None = None
    require_prepaid: bool | None = None
    active_status: bool | None = None
    verification_status: VerificationStatus | None = None


class OutletOwnerResponse(BaseModel):
    membership_id: UUID
    user_id: UUID
    outlet_id: UUID
    name: str
    phone: str
    email: str | None
    role_id: UUID
    active_status: bool
    last_login: datetime | None
    created_at: datetime


class OutletOnboardResponse(BaseModel):
    outlet: OutletResponse
    owner: OutletOwnerResponse
