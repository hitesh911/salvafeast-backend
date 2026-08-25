from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import DiscountType


def _validate_offer_dates(
    start_date: datetime | None, end_date: datetime | None
) -> None:
    if start_date is not None and end_date is not None and start_date >= end_date:
        raise ValueError("start_date must be before end_date")


class OfferCreate(BaseModel):
    title: str
    description: str | None = None
    offer_code: str
    discount_type: DiscountType
    discount_value: Decimal = Field(gt=0)
    start_date: datetime | None = None
    end_date: datetime | None = None
    active_status: bool = True
    usage_limit: int | None = Field(default=None, ge=1)
    applicable_item_ids: list[UUID] = []

    @model_validator(mode="after")
    def validate_dates(self) -> "OfferCreate":
        _validate_offer_dates(self.start_date, self.end_date)
        return self


class OfferUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    offer_code: str | None = None
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = Field(default=None, gt=0)
    start_date: datetime | None = None
    end_date: datetime | None = None
    active_status: bool | None = None
    usage_limit: int | None = Field(default=None, ge=1)
    applicable_item_ids: list[UUID] | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "OfferUpdate":
        _validate_offer_dates(self.start_date, self.end_date)
        return self


class OfferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    outlet_id: UUID
    title: str
    description: str | None
    offer_code: str
    discount_type: DiscountType
    discount_value: Decimal
    start_date: datetime | None
    end_date: datetime | None
    active_status: bool
    usage_limit: int | None
    applicable_item_ids: list[UUID] = []
    redeemed_count: int = 0
    created_at: datetime
    updated_at: datetime
