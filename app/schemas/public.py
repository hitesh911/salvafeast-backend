from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import DietaryType, OrderType, OutletType, VerificationStatus


class PublicOutletInfo(BaseModel):
    id: UUID
    slug: str
    name: str
    logo_url: str | None
    cover_image_url: str | None
    address: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    landmark: str | None = None
    area: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    description: str | None = None
    cuisine_tags: list[str] = []
    opening_hours: dict | None = None
    cost_for_two: int | None = None
    is_pure_veg: bool = False
    outlet_type: OutletType | None = None
    verification_status: VerificationStatus


class PublicOutletSummary(BaseModel):
    id: UUID
    slug: str
    name: str
    logo_url: str | None
    cover_image_url: str | None
    address: str | None = None
    city: str | None = None
    area: str | None = None
    cuisine_tags: list[str] = []
    cost_for_two: int | None = None
    is_pure_veg: bool = False
    verification_status: VerificationStatus


class PublicOutletListResponse(BaseModel):
    items: list[PublicOutletSummary]
    total: int


class PublicOfferSummary(BaseModel):
    id: UUID
    title: str
    description: str | None
    offer_code: str
    discount_type: str
    discount_value: Decimal


class PublicOutletDetailResponse(BaseModel):
    outlet: PublicOutletInfo
    active_offers: list[PublicOfferSummary] = []


class PublicTableOption(BaseModel):
    table_number: str
    qr_token: str


class PublicOrderingContext(BaseModel):
    entry_point: Literal["counter", "table"]
    default_order_type: OrderType
    scanned_table_id: UUID | None
    scanned_table_number: str | None
    require_customer_login: bool
    require_prepaid: bool
    upi_vpa: str | None
    upi_payee_name: str | None
    upi_qr_image_url: str | None
    available_order_types: list[OrderType]
    tables: list[PublicTableOption]


class PublicMenuItemImage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    image_url: str
    sort_order: int


class PublicMenuItemVariant(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    price_delta: Decimal
    sort_order: int


class PublicMenuItemAddon(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    price: Decimal


class PublicMenuItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    base_price: Decimal
    dietary_type: DietaryType | None
    sort_order: int
    images: list[PublicMenuItemImage]
    variants: list[PublicMenuItemVariant]
    addons: list[PublicMenuItemAddon]


class PublicMenuCategory(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    sort_order: int
    items: list[PublicMenuItem]


class PublicMenuResponse(BaseModel):
    outlet: PublicOutletInfo
    table_id: UUID | None
    ordering: PublicOrderingContext
    menu: list[PublicMenuCategory]
