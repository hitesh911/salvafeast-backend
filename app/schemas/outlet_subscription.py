from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import BillingInterval, PlatformInvoiceStatus, SubscriptionStatus


class OutletSubscriptionDetailResponse(BaseModel):
    id: UUID
    outlet_id: UUID
    plan_id: UUID
    plan_name: str
    plan_slug: str
    price_monthly: Decimal
    price_yearly: Decimal | None
    billing_interval: BillingInterval
    included_modules: list[str]
    limits: dict | None
    features: dict | None
    status: SubscriptionStatus
    current_period_start: datetime | None
    current_period_end: datetime | None
    trial_ends_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OutletPlanOptionResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    price_monthly: Decimal
    price_yearly: Decimal | None
    included_modules: list[str]
    limits: dict | None
    is_current: bool


class OutletPlatformInvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    outlet_id: UUID
    subscription_id: UUID | None
    invoice_number: str
    amount: Decimal
    status: PlatformInvoiceStatus
    period_start: date | None
    period_end: date | None
    due_date: date | None
    paid_at: datetime | None
    notes: str | None
    created_at: datetime
