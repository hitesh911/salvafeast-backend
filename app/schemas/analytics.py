from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class AnalyticsSummaryResponse(BaseModel):
    total_revenue: Decimal
    total_orders: int
    average_order_value: Decimal


class RevenueTrendPoint(BaseModel):
    date: date
    revenue: Decimal
    order_count: int


class ItemSalesPoint(BaseModel):
    menu_item_id: UUID
    name: str
    quantity_sold: int
    revenue: Decimal


class PeakHourPoint(BaseModel):
    hour: int = Field(ge=0, le=23)
    order_count: int


class CustomerAnalyticsResponse(BaseModel):
    new_customers: int
    returning_customers: int
    repeat_rate: Decimal


class TableTurnoverResponse(BaseModel):
    average_turnover_minutes: Decimal | None
