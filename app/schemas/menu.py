from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DietaryType


class MenuCategoryCreate(BaseModel):
    name: str
    sort_order: int = 0


class MenuCategoryUpdate(BaseModel):
    name: str | None = None
    sort_order: int | None = None


class MenuCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    outlet_id: UUID
    name: str
    sort_order: int
    created_at: datetime
    updated_at: datetime


class MenuItemCreate(BaseModel):
    category_id: UUID
    name: str
    description: str | None = None
    base_price: Decimal = Field(ge=0)
    dietary_type: DietaryType | None = None
    is_available: bool = True
    sort_order: int = 0


class MenuItemUpdate(BaseModel):
    category_id: UUID | None = None
    name: str | None = None
    description: str | None = None
    base_price: Decimal | None = Field(default=None, ge=0)
    dietary_type: DietaryType | None = None
    is_available: bool | None = None
    sort_order: int | None = None


class MenuItemAvailabilityUpdate(BaseModel):
    is_available: bool


class MenuItemImageCreate(BaseModel):
    image_url: str
    sort_order: int = 0


class MenuItemImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    menu_item_id: UUID
    image_url: str
    sort_order: int
    created_at: datetime


class MenuItemVariantCreate(BaseModel):
    name: str
    price_delta: Decimal
    is_available: bool = True
    sort_order: int = 0


class MenuItemVariantUpdate(BaseModel):
    name: str | None = None
    price_delta: Decimal | None = None
    is_available: bool | None = None
    sort_order: int | None = None


class MenuItemVariantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    menu_item_id: UUID
    name: str
    price_delta: Decimal
    is_available: bool
    sort_order: int


class MenuItemAddonCreate(BaseModel):
    name: str
    price: Decimal = Field(ge=0)
    is_available: bool = True


class MenuItemAddonUpdate(BaseModel):
    name: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    is_available: bool | None = None


class MenuItemAddonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    menu_item_id: UUID
    name: str
    price: Decimal
    is_available: bool


class MenuItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    outlet_id: UUID
    category_id: UUID
    name: str
    description: str | None
    base_price: Decimal
    dietary_type: DietaryType | None
    is_available: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class MenuItemDetailResponse(MenuItemResponse):
    images: list[MenuItemImageResponse] = []
    variants: list[MenuItemVariantResponse] = []
    addons: list[MenuItemAddonResponse] = []


class MenuImageUploadUrlRequest(BaseModel):
    filename: str
    content_type: str


class MenuImageUploadUrlResponse(BaseModel):
    upload_url: str
    image_url: str
