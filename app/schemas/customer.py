from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OrderStatus, OrderType, PaymentMethod, PaymentStatus
from app.schemas.order import OrderDetailResponse, OrderSummaryResponse


class CustomerLookupResponse(BaseModel):
    user_id: UUID
    phone: str
    name: str | None
    total_orders: int | None = None
    last_visit_at: datetime | None = None


class OutletCustomerListItem(BaseModel):
    user_id: UUID
    phone: str
    name: str | None
    total_orders: int
    total_spend: Decimal
    first_visit_at: datetime
    last_visit_at: datetime
    marketing_opt_in: bool


class PaginatedOutletCustomers(BaseModel):
    items: list[OutletCustomerListItem]
    total: int
    page: int
    page_size: int


class OutletCustomerDetail(BaseModel):
    user_id: UUID
    phone: str
    name: str | None
    total_orders: int
    total_spend: Decimal
    first_visit_at: datetime
    last_visit_at: datetime
    marketing_opt_in: bool
    orders: list[OrderSummaryResponse]


class PushTokenUpdate(BaseModel):
    push_token: str = Field(min_length=1, max_length=2048)


class PushTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    push_token: str
    push_token_updated_at: datetime


class MarketingOptInUpdate(BaseModel):
    opt_in: bool


class MarketingOptInResponse(BaseModel):
    outlet_id: UUID
    marketing_opt_in: bool


class ConsumerOrderSummary(BaseModel):
    id: UUID
    outlet_id: UUID
    outlet_slug: str
    outlet_name: str
    outlet_logo_url: str | None
    order_type: OrderType
    status: OrderStatus
    subtotal_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    payment_status: PaymentStatus
    payment_method: PaymentMethod | None = None
    created_at: datetime


class ConsumerOrderDetailResponse(BaseModel):
    order: OrderDetailResponse
    outlet_slug: str
    tracking_token: str
