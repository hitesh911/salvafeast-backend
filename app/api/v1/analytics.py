from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import require_outlet_permission
from app.db.database import get_db
from app.schemas.analytics import (
    AnalyticsSummaryResponse,
    CustomerAnalyticsResponse,
    ItemSalesPoint,
    PeakHourPoint,
    RevenueTrendPoint,
    TableTurnoverResponse,
)
from app.services.analytics import (
    get_customer_analytics,
    get_peak_hours,
    get_revenue_trend,
    get_slow_items,
    get_summary,
    get_table_turnover_minutes,
    get_top_items,
    resolve_date_range,
)

router = APIRouter(prefix="/outlets/{outlet_id}", tags=["analytics"])


@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
def analytics_summary(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("analytics.view")),
):
    start, end, _, _ = resolve_date_range(from_date, to_date)
    total_revenue, total_orders = get_summary(db, outlet_id, start, end)
    average_order_value = (
        (total_revenue / total_orders).quantize(Decimal("0.01"))
        if total_orders > 0
        else Decimal("0")
    )
    return AnalyticsSummaryResponse(
        total_revenue=total_revenue,
        total_orders=total_orders,
        average_order_value=average_order_value,
    )


@router.get("/analytics/revenue-trend", response_model=list[RevenueTrendPoint])
def analytics_revenue_trend(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("analytics.view")),
):
    start, end, resolved_from, resolved_to = resolve_date_range(from_date, to_date)
    trend = get_revenue_trend(db, outlet_id, start, end, resolved_from, resolved_to)
    return [
        RevenueTrendPoint(date=day, revenue=revenue, order_count=order_count)
        for day, revenue, order_count in trend
    ]


@router.get("/analytics/top-items", response_model=list[ItemSalesPoint])
def analytics_top_items(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("analytics.view")),
):
    start, end, _, _ = resolve_date_range(from_date, to_date)
    rows = get_top_items(db, outlet_id, start, end, limit)
    return [
        ItemSalesPoint(
            menu_item_id=menu_item_id,
            name=name,
            quantity_sold=quantity_sold,
            revenue=revenue,
        )
        for menu_item_id, name, quantity_sold, revenue in rows
    ]


@router.get("/analytics/slow-items", response_model=list[ItemSalesPoint])
def analytics_slow_items(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("analytics.view")),
):
    start, end, _, _ = resolve_date_range(from_date, to_date)
    rows = get_slow_items(db, outlet_id, start, end, limit)
    return [
        ItemSalesPoint(
            menu_item_id=menu_item_id,
            name=name,
            quantity_sold=quantity_sold,
            revenue=revenue,
        )
        for menu_item_id, name, quantity_sold, revenue in rows
    ]


@router.get("/analytics/peak-hours", response_model=list[PeakHourPoint])
def analytics_peak_hours(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("analytics.view")),
):
    start, end, _, _ = resolve_date_range(from_date, to_date)
    rows = get_peak_hours(db, outlet_id, start, end)
    return [PeakHourPoint(hour=hour, order_count=order_count) for hour, order_count in rows]


@router.get("/analytics/customers", response_model=CustomerAnalyticsResponse)
def analytics_customers(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("analytics.view")),
):
    start, end, _, _ = resolve_date_range(from_date, to_date)
    new_customers, returning_customers = get_customer_analytics(db, outlet_id, start, end)
    total = new_customers + returning_customers
    repeat_rate = (
        (Decimal(returning_customers) / Decimal(total)).quantize(Decimal("0.0001"))
        if total > 0
        else Decimal("0")
    )
    return CustomerAnalyticsResponse(
        new_customers=new_customers,
        returning_customers=returning_customers,
        repeat_rate=repeat_rate,
    )


@router.get("/analytics/table-turnover", response_model=TableTurnoverResponse)
def analytics_table_turnover(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("analytics.view")),
):
    start, end, _, _ = resolve_date_range(from_date, to_date)
    average_turnover_minutes = get_table_turnover_minutes(db, outlet_id, start, end)
    return TableTurnoverResponse(average_turnover_minutes=average_turnover_minutes)
