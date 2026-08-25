from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import OutletType
from app.services.outlet_address import DAY_KEYS, validate_opening_hours


class DayHours(BaseModel):
    open: str | None = None
    close: str | None = None
    closed: bool = False


class OutletProfileSettingsResponse(BaseModel):
    name: str
    phone: str | None
    address: str | None
    address_line1: str | None = None
    address_line2: str | None = None
    landmark: str | None = None
    area: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    email: str | None = None
    whatsapp_phone: str | None = None
    description: str | None = None
    cuisine_tags: list[str] = []
    opening_hours: dict[str, Any] | None = None
    fssai_number: str | None = None
    cost_for_two: int | None = None
    is_pure_veg: bool = False
    outlet_type: OutletType | None = None
    logo_url: str | None
    cover_image_url: str | None = None
    slug: str


class OutletProfileSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=512)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    landmark: str | None = Field(default=None, max_length=255)
    area: str | None = Field(default=None, max_length=128)
    city: str | None = Field(default=None, max_length=128)
    state: str | None = Field(default=None, max_length=128)
    pincode: str | None = Field(default=None, max_length=12)
    latitude: float | None = None
    longitude: float | None = None
    email: str | None = Field(default=None, max_length=255)
    whatsapp_phone: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=1024)
    cuisine_tags: list[str] | None = None
    opening_hours: dict[str, Any] | None = None
    fssai_number: str | None = Field(default=None, max_length=50)
    cost_for_two: int | None = Field(default=None, ge=0, le=100000)
    is_pure_veg: bool | None = None
    outlet_type: OutletType | None = None

    @field_validator("opening_hours")
    @classmethod
    def _validate_hours(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        try:
            return validate_opening_hours(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("cuisine_tags")
    @classmethod
    def _normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [tag.strip() for tag in value if tag and tag.strip()][:20]


class OutletInvoicingSettingsResponse(BaseModel):
    gst_rate_percent: Decimal | None
    invoice_prefix: str | None


class OutletInvoicingSettingsUpdate(BaseModel):
    gst_rate_percent: Decimal | None = Field(default=None, ge=0, le=100)
    invoice_prefix: str | None = Field(default=None, max_length=20)


class OutletPreferencesResponse(BaseModel):
    require_customer_login: bool
    require_prepaid: bool


class OutletPreferencesUpdate(BaseModel):
    require_customer_login: bool | None = None
    require_prepaid: bool | None = None


class OutletRoleItem(BaseModel):
    id: str
    name: str
    is_system_default: bool
    permission_keys: list[str] = []


class OutletRoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    permission_ids: list[str] = Field(min_length=1)


class OutletRoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    permission_ids: list[str] | None = Field(default=None, min_length=1)


class OutletPermissionItem(BaseModel):
    id: str
    key: str
    description: str
    module: str


class OwnershipTransferRequest(BaseModel):
    new_owner_user_id: str
    demote_previous_to: str = Field(default="Manager", min_length=1, max_length=100)


class OwnershipTransferResponse(BaseModel):
    previous_owner_id: str
    new_owner_id: str


class OutletStaffItem(BaseModel):
    id: str
    user_id: str
    outlet_id: str
    name: str
    phone: str
    email: str | None
    role_id: str
    role_name: str
    active_status: bool
    last_login: str | None
    created_at: str


class OutletStaffCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=10, max_length=15)
    role_id: str
    email: str | None = Field(default=None, max_length=255)


class OutletStaffUpdate(BaseModel):
    active_status: bool | None = None
    role_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)


class OutletCustomerUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    marketing_opt_in: bool | None = None


# Re-export for hours editors
__all__ = [
    "DAY_KEYS",
    "DayHours",
    "OutletProfileSettingsResponse",
    "OutletProfileSettingsUpdate",
    "OutletInvoicingSettingsResponse",
    "OutletInvoicingSettingsUpdate",
    "OutletPreferencesResponse",
    "OutletPreferencesUpdate",
    "OutletRoleItem",
    "OutletRoleCreate",
    "OutletRoleUpdate",
    "OutletPermissionItem",
    "OwnershipTransferRequest",
    "OwnershipTransferResponse",
    "OutletStaffItem",
    "OutletStaffCreate",
    "OutletStaffUpdate",
    "OutletCustomerUpdate",
]
