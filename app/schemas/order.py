from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.phone import OptionalIndianPhone
from app.models.enums import (
    CancelledBy,
    CancelRequestStatus,
    OrderStatus,
    OrderType,
    PaymentCollection,
    PaymentMethod,
    PaymentStatus,
)
from app.schemas.auth import OtpRequest, OtpRequestResponse, OtpVerifyRequest, TokenResponse

__all__ = [
    "OtpRequest",
    "OtpRequestResponse",
    "OtpVerifyRequest",
    "TokenResponse",
    "OrderItemInput",
    "OrderPlacementRequest",
    "StaffOrderCreate",
    "OrderPlacementResponse",
    "OrderItemAddonResponse",
    "OrderItemResponse",
    "OrderStatusLogResponse",
    "OrderSummaryResponse",
    "PaginatedOrderSummaries",
    "OrderDetailResponse",
    "PublicOrderItemAddonStatus",
    "PublicOrderItemStatus",
    "PublicOrderStatusResponse",
    "OrderStatusUpdate",
    "PaymentStatusUpdate",
    "ConfirmPaymentRequest",
]


class OrderItemInput(BaseModel):
    menu_item_id: UUID
    variant_id: UUID | None = None
    quantity: int = Field(ge=1)
    addon_ids: list[UUID] = []
    notes: str | None = None


class OrderPlacementRequest(BaseModel):
    table_qr_token: str | None = None
    order_type: OrderType
    items: list[OrderItemInput]
    guest_name: str | None = None
    guest_phone: OptionalIndianPhone = None
    offer_code: str | None = None
    collection: PaymentCollection | None = None

    @model_validator(mode="after")
    def normalize_table_for_order_type(self) -> "OrderPlacementRequest":
        if self.order_type != OrderType.dine_in:
            self.table_qr_token = None
        elif not self.table_qr_token:
            raise ValueError("table_qr_token is required for dine-in orders")
        return self


class StaffOrderCreate(BaseModel):
    table_id: UUID | None = None
    order_type: OrderType
    items: list[OrderItemInput]
    guest_name: str | None = None
    guest_phone: OptionalIndianPhone = None
    offer_code: str | None = None
    is_quick_bill: bool = False
    user_id: UUID | None = None
    link_customer: bool = False

    @model_validator(mode="after")
    def validate_customer_fields(self) -> "StaffOrderCreate":
        if self.user_id is not None and self.link_customer:
            raise ValueError("Provide either user_id or link_customer, not both")
        if self.link_customer and not self.guest_phone:
            raise ValueError("guest_phone is required when link_customer is true")
        return self


class OrderItemAddonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    addon_id: UUID
    addon_price_at_order: Decimal


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    menu_item_id: UUID
    variant_id: UUID | None
    quantity: int
    item_price_at_order: Decimal
    notes: str | None
    addons: list[OrderItemAddonResponse] = []


class OrderStatusLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: OrderStatus
    changed_by: UUID | None
    created_at: datetime


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    outlet_id: UUID
    table_id: UUID | None
    user_id: UUID | None
    offer_id: UUID | None
    order_type: OrderType
    status: OrderStatus
    subtotal_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    payment_status: PaymentStatus
    payment_method: PaymentMethod | None = None
    payment_collection: PaymentCollection | None = None
    guest_name: str | None
    guest_phone: str | None
    cancelled_by: CancelledBy | None = None
    cancel_requested_at: datetime | None = None
    cancel_request_status: CancelRequestStatus | None = None
    created_at: datetime
    updated_at: datetime


class OrderSummaryResponse(OrderResponse):
    table_number: str | None = None


class PaginatedOrderSummaries(BaseModel):
    items: list[OrderSummaryResponse]
    total: int
    page: int
    page_size: int


class OrderDetailResponse(OrderResponse):
    table_number: str | None = None
    items: list[OrderItemResponse] = []
    status_logs: list[OrderStatusLogResponse] = []


class OrderPlacementResponse(BaseModel):
    order: OrderDetailResponse
    upi_payment_link: str | None = None
    tracking_token: str


class PublicOrderItemAddonStatus(BaseModel):
    addon_id: UUID


class PublicOrderItemStatus(BaseModel):
    menu_item_id: UUID
    variant_id: UUID | None = None
    quantity: int
    item_price_at_order: Decimal
    notes: str | None = None
    addons: list[PublicOrderItemAddonStatus] = []


class PublicOrderStatusResponse(BaseModel):
    id: UUID
    status: OrderStatus
    payment_status: PaymentStatus
    subtotal_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    order_type: OrderType
    created_at: datetime
    updated_at: datetime
    table_number: str | None = None
    items: list[PublicOrderItemStatus] = []
    orders_ahead: int = 0
    queue_position: int | None = None
    estimated_wait_minutes: int | None = None
    estimated_ready_at: datetime | None = None
    cancelled_by: CancelledBy | None = None
    cancel_requested_at: datetime | None = None
    cancel_request_status: CancelRequestStatus | None = None
    payment_collection: PaymentCollection | None = None
    upi_vpa: str | None = None
    upi_payee_name: str | None = None
    upi_qr_image_url: str | None = None


class ConfirmPaymentRequest(BaseModel):
    payment_method: PaymentMethod


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class PaymentStatusUpdate(BaseModel):
    payment_status: PaymentStatus
    payment_method: PaymentMethod | None = None

    @model_validator(mode="after")
    def validate_payment_method(self) -> "PaymentStatusUpdate":
        if self.payment_status == PaymentStatus.paid and self.payment_method is None:
            raise ValueError("payment_method is required when payment_status is paid")
        return self
