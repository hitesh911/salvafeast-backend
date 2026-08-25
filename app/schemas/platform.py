from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BillingInterval, PlatformInvoiceStatus, SubscriptionStatus, VerificationStatus
from app.schemas.analytics import (
    ItemSalesPoint,
    PeakHourPoint,
    RevenueTrendPoint,
)


class PlatformAdminMeResponse(BaseModel):
    id: UUID
    name: str
    email: str
    created_at: datetime


class PlatformOutletRevenueItem(BaseModel):
    outlet_id: UUID
    outlet_name: str
    revenue: Decimal


class PlatformHealthAlert(BaseModel):
    code: str
    message: str
    outlet_id: UUID | None = None
    outlet_name: str | None = None


class PlatformAnalyticsOverviewResponse(BaseModel):
    total_outlets: int
    active_outlets: int
    inactive_outlets: int
    total_orders: int
    total_revenue: Decimal
    mrr: Decimal
    overdue_invoices_count: int
    outlets_on_trial: int
    top_outlets_by_revenue: list[PlatformOutletRevenueItem]
    health_alerts: list[PlatformHealthAlert] = []


class SupportSessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    outlet_id: UUID
    outlet_name: str
    outlet_slug: str
    expires_at: datetime
    refresh_expires_at: datetime


class PlatformAuditLogItem(BaseModel):
    id: UUID
    actor_id: UUID
    actor_name: str
    action: str
    resource_type: str
    resource_id: UUID | None
    metadata_json: dict | None
    created_at: datetime


class PaginatedPlatformAuditLogs(BaseModel):
    items: list[PlatformAuditLogItem]
    total: int
    page: int
    page_size: int


class SupportAccessLogItem(BaseModel):
    id: UUID
    platform_admin_id: UUID
    platform_admin_name: str
    outlet_id: UUID
    outlet_name: str
    started_at: datetime


class PaginatedSupportAccessLogs(BaseModel):
    items: list[SupportAccessLogItem]
    total: int
    page: int
    page_size: int


class PlatformOutletListItem(BaseModel):
    id: UUID
    name: str
    slug: str
    active_status: bool
    verification_status: VerificationStatus
    require_customer_login: bool
    require_prepaid: bool
    created_at: datetime
    owner_name: str | None = None
    owner_phone: str | None = None
    subscription_plan_name: str | None = None
    subscription_status: SubscriptionStatus | None = None
    platform_invoice_overdue: bool = False
    last_order_at: datetime | None = None
    orders_30d: int = 0
    revenue_30d: Decimal = Decimal("0")


class PlatformOutletProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255)
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
    opening_hours: dict | None = None
    fssai_number: str | None = Field(default=None, max_length=50)
    cost_for_two: int | None = Field(default=None, ge=0, le=100000)
    is_pure_veg: bool | None = None
    outlet_type: str | None = None
    gst_number: str | None = Field(default=None, max_length=50)


class PlatformOutletDetailResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    logo_url: str | None
    cover_image_url: str | None = None
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
    phone: str | None
    email: str | None = None
    whatsapp_phone: str | None = None
    description: str | None = None
    cuisine_tags: list[str] = []
    opening_hours: dict | None = None
    fssai_number: str | None = None
    cost_for_two: int | None = None
    is_pure_veg: bool = False
    outlet_type: str | None = None
    gst_number: str | None
    active_status: bool
    verification_status: VerificationStatus
    require_customer_login: bool
    require_prepaid: bool
    created_at: datetime
    updated_at: datetime
    owner_name: str | None = None
    owner_phone: str | None = None
    subscription_plan_name: str | None = None
    subscription_status: SubscriptionStatus | None = None
    platform_invoice_overdue: bool = False
    last_order_at: datetime | None = None
    orders_30d: int = 0
    revenue_30d: Decimal = Decimal("0")
    active_staff_count: int = 0


class PlatformStaffItem(BaseModel):
    id: UUID
    user_id: UUID
    outlet_id: UUID
    name: str
    phone: str
    email: str | None
    role_id: UUID
    role_name: str
    active_status: bool
    last_login: datetime | None
    created_at: datetime


class PlatformStaffUpdate(BaseModel):
    active_status: bool | None = None
    role_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)


class PlatformStaffCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=10, max_length=15)
    role_id: UUID
    email: str | None = Field(default=None, max_length=255)


class PlatformPermissionItem(BaseModel):
    id: UUID
    key: str
    description: str
    module: str


class PlatformRoleItem(BaseModel):
    id: UUID
    name: str
    is_system_default: bool
    permission_keys: list[str] = []


class PlatformRoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    permission_ids: list[UUID] = Field(min_length=1)


class PlatformRoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    permission_ids: list[UUID] | None = Field(default=None, min_length=1)


class PlatformOwnershipTransferRequest(BaseModel):
    new_owner_user_id: UUID
    demote_previous_to: str = Field(default="Manager", min_length=1, max_length=100)


class PlatformOwnershipTransferResponse(BaseModel):
    previous_owner_id: UUID
    new_owner_id: UUID


class PlatformCustomerListItem(BaseModel):
    user_id: UUID
    phone: str
    name: str | None
    outlet_count: int
    total_spend_network: Decimal
    last_visit_at: datetime | None


class PaginatedPlatformCustomers(BaseModel):
    items: list[PlatformCustomerListItem]
    total: int
    page: int
    page_size: int


class PlatformCustomerOutletAffiliation(BaseModel):
    outlet_id: UUID
    outlet_name: str
    total_orders: int
    total_spend: Decimal
    first_visit_at: datetime
    last_visit_at: datetime
    marketing_opt_in: bool


class PlatformCustomerOrderSummary(BaseModel):
    id: UUID
    outlet_id: UUID
    outlet_name: str
    order_type: str
    status: str
    total_amount: Decimal
    created_at: datetime


class PlatformCustomerDetailResponse(BaseModel):
    user_id: UUID
    phone: str
    name: str | None
    created_at: datetime
    outlet_affiliations: list[PlatformCustomerOutletAffiliation]
    total_spend_network: Decimal
    total_orders_network: int
    recent_orders: list[PlatformCustomerOrderSummary]


class SubscriptionPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    price_monthly: Decimal
    price_yearly: Decimal | None
    features: dict | None
    included_modules: list[str] = []
    limits: dict | None = None
    active_status: bool
    created_at: datetime


class SubscriptionPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=64)
    price_monthly: Decimal = Field(ge=0)
    price_yearly: Decimal | None = Field(default=None, ge=0)
    features: dict | None = None
    modules: list[str] | None = None
    limits: dict | None = None
    active_status: bool = True


class SubscriptionPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    price_monthly: Decimal | None = Field(default=None, ge=0)
    price_yearly: Decimal | None = Field(default=None, ge=0)
    features: dict | None = None
    modules: list[str] | None = None
    limits: dict | None = None
    active_status: bool | None = None


class OutletSubscriptionResponse(BaseModel):
    id: UUID
    outlet_id: UUID
    outlet_name: str
    plan_id: UUID
    plan_name: str
    plan_slug: str
    price_monthly: Decimal
    price_yearly: Decimal | None
    billing_interval: BillingInterval
    status: SubscriptionStatus
    current_period_start: datetime | None
    current_period_end: datetime | None
    trial_ends_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OutletSubscriptionAssign(BaseModel):
    plan_id: UUID
    status: SubscriptionStatus = SubscriptionStatus.trial
    billing_interval: BillingInterval = BillingInterval.monthly
    trial_days: int = Field(default=14, ge=0, le=90)


class PlatformInvoiceResponse(BaseModel):
    id: UUID
    outlet_id: UUID
    outlet_name: str
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


class PlatformInvoiceCreate(BaseModel):
    outlet_id: UUID
    amount: Decimal | None = None
    period_start: date | None = None
    period_end: date | None = None
    due_date: date | None = None
    notes: str | None = None


class PlatformInvoiceUpdate(BaseModel):
    status: PlatformInvoiceStatus | None = None
    notes: str | None = None


class PlatformBillingOverviewResponse(BaseModel):
    mrr: Decimal
    arr: Decimal
    overdue_total: Decimal
    overdue_count: int
    active_subscriptions: int
    trial_subscriptions: int
    plan_distribution: list[dict]


class PlatformAdminListItem(BaseModel):
    id: UUID
    name: str
    email: str
    active_status: bool
    created_at: datetime


class PlatformAdminCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class PlatformAdminUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    active_status: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class PlatformRevenueTrendResponse(BaseModel):
    points: list[RevenueTrendPoint]


class PlatformTopItemsResponse(BaseModel):
    items: list[ItemSalesPoint]


class PlatformPeakHoursResponse(BaseModel):
    hours: list[PeakHourPoint]
