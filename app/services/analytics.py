from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import extract, func
from sqlalchemy.orm import Query, Session

from app.models.enums import OrderStatus, OrderType, PaymentStatus
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_status_log import OrderStatusLog
from app.models.outlet_customer import OutletCustomer


def resolve_date_range(
    from_date: date | None,
    to_date: date | None,
    default_days: int = 30,
) -> tuple[datetime, datetime, date, date]:
    today = datetime.now(timezone.utc).date()
    resolved_to = to_date or today
    resolved_from = from_date or (resolved_to - timedelta(days=default_days - 1))

    start = datetime.combine(resolved_from, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(resolved_to, datetime.max.time(), tzinfo=timezone.utc)
    return start, end, resolved_from, resolved_to


def non_cancelled_orders_query(
    db: Session,
    start: datetime,
    end: datetime,
) -> Query:
    """Kitchen/ops orders in range, excluding cancelled (all outlets)."""
    return db.query(Order).filter(
        Order.created_at >= start,
        Order.created_at <= end,
        Order.status != OrderStatus.cancelled,
    )


def settled_orders_query(
    db: Session,
    start: datetime,
    end: datetime,
) -> Query:
    """Paid orders only — revenue must not include unpaid tickets."""
    return non_cancelled_orders_query(db, start, end).filter(
        Order.payment_status == PaymentStatus.paid,
    )


def active_orders_query(
    db: Session,
    outlet_id: UUID,
    start: datetime,
    end: datetime,
) -> Query:
    return non_cancelled_orders_query(db, start, end).filter(Order.outlet_id == outlet_id)


def outlet_settled_orders_query(
    db: Session,
    outlet_id: UUID,
    start: datetime,
    end: datetime,
) -> Query:
    return settled_orders_query(db, start, end).filter(Order.outlet_id == outlet_id)


def get_summary(
    db: Session,
    outlet_id: UUID,
    start: datetime,
    end: datetime,
) -> tuple[Decimal, int]:
    row = (
        outlet_settled_orders_query(db, outlet_id, start, end)
        .with_entities(
            func.coalesce(func.sum(Order.total_amount), 0),
            func.count(Order.id),
        )
        .one()
    )
    total_revenue = Decimal(str(row[0]))
    total_orders = int(row[1])
    return total_revenue, total_orders


def get_platform_overview(
    db: Session,
    start: datetime,
    end: datetime,
) -> tuple[int, int, int, int, Decimal, list[tuple[UUID, str, Decimal]]]:
    from app.models.outlet import Outlet

    total_outlets = int(db.query(func.count(Outlet.id)).scalar() or 0)
    active_outlets = int(
        db.query(func.count(Outlet.id))
        .filter(Outlet.active_status.is_(True))
        .scalar()
        or 0
    )
    inactive_outlets = total_outlets - active_outlets

    totals = (
        settled_orders_query(db, start, end)
        .with_entities(
            func.coalesce(func.sum(Order.total_amount), 0),
            func.count(Order.id),
        )
        .one()
    )
    total_revenue = Decimal(str(totals[0]))
    total_orders = int(totals[1])

    top_rows = (
        db.query(
            Outlet.id,
            Outlet.name,
            func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
        )
        .outerjoin(
            Order,
            (Order.outlet_id == Outlet.id)
            & (Order.created_at >= start)
            & (Order.created_at <= end)
            & (Order.status != OrderStatus.cancelled)
            & (Order.payment_status == PaymentStatus.paid),
        )
        .group_by(Outlet.id, Outlet.name)
        .order_by(
            func.coalesce(func.sum(Order.total_amount), 0).desc(),
            Outlet.name.asc(),
        )
        .limit(10)
        .all()
    )
    top_outlets = [
        (row[0], row[1], Decimal(str(row[2]))) for row in top_rows
    ]

    return (
        total_outlets,
        active_outlets,
        inactive_outlets,
        total_orders,
        total_revenue,
        top_outlets,
    )


def get_revenue_trend(
    db: Session,
    outlet_id: UUID,
    start: datetime,
    end: datetime,
    from_date: date,
    to_date: date,
) -> list[tuple[date, Decimal, int]]:
    day = func.date_trunc("day", Order.created_at).label("day")
    rows = (
        outlet_settled_orders_query(db, outlet_id, start, end)
        .with_entities(
            day,
            func.coalesce(func.sum(Order.total_amount), 0),
            func.count(Order.id),
        )
        .group_by(day)
        .order_by(day)
        .all()
    )

    by_day = {
        row[0].date(): (Decimal(str(row[1])), int(row[2]))
        for row in rows
        if row[0] is not None
    }

    trend: list[tuple[date, Decimal, int]] = []
    current = from_date
    while current <= to_date:
        revenue, order_count = by_day.get(current, (Decimal("0"), 0))
        trend.append((current, revenue, order_count))
        current += timedelta(days=1)
    return trend


def get_top_items(
    db: Session,
    outlet_id: UUID,
    start: datetime,
    end: datetime,
    limit: int,
) -> list[tuple[UUID, str, int, Decimal]]:
    revenue_expr = func.sum(OrderItem.item_price_at_order * OrderItem.quantity)
    rows = (
        db.query(
            MenuItem.id,
            MenuItem.name,
            func.coalesce(func.sum(OrderItem.quantity), 0),
            func.coalesce(revenue_expr, 0),
        )
        .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            MenuItem.outlet_id == outlet_id,
            Order.outlet_id == outlet_id,
            Order.created_at >= start,
            Order.created_at <= end,
            Order.status != OrderStatus.cancelled,
            Order.payment_status == PaymentStatus.paid,
        )
        .group_by(MenuItem.id, MenuItem.name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
        .all()
    )
    return [
        (row[0], row[1], int(row[2]), Decimal(str(row[3])))
        for row in rows
    ]


def get_slow_items(
    db: Session,
    outlet_id: UUID,
    start: datetime,
    end: datetime,
    limit: int,
) -> list[tuple[UUID, str, int, Decimal]]:
    order_items = (
        db.query(
            OrderItem.menu_item_id.label("menu_item_id"),
            func.coalesce(func.sum(OrderItem.quantity), 0).label("quantity_sold"),
            func.coalesce(
                func.sum(OrderItem.item_price_at_order * OrderItem.quantity), 0
            ).label("revenue"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.outlet_id == outlet_id,
            Order.created_at >= start,
            Order.created_at <= end,
            Order.status != OrderStatus.cancelled,
            Order.payment_status == PaymentStatus.paid,
        )
        .group_by(OrderItem.menu_item_id)
        .subquery()
    )

    rows = (
        db.query(
            MenuItem.id,
            MenuItem.name,
            func.coalesce(order_items.c.quantity_sold, 0),
            func.coalesce(order_items.c.revenue, 0),
        )
        .outerjoin(order_items, order_items.c.menu_item_id == MenuItem.id)
        .filter(MenuItem.outlet_id == outlet_id)
        .order_by(func.coalesce(order_items.c.quantity_sold, 0).asc())
        .limit(limit)
        .all()
    )
    return [
        (row[0], row[1], int(row[2]), Decimal(str(row[3])))
        for row in rows
    ]


def get_peak_hours(
    db: Session,
    outlet_id: UUID,
    start: datetime,
    end: datetime,
) -> list[tuple[int, int]]:
    hour = extract("hour", Order.created_at).label("hour")
    rows = (
        active_orders_query(db, outlet_id, start, end)
        .with_entities(hour, func.count(Order.id))
        .group_by(hour)
        .all()
    )
    by_hour = {int(row[0]): int(row[1]) for row in rows if row[0] is not None}
    return [(hour, by_hour.get(hour, 0)) for hour in range(24)]


def get_customer_analytics(
    db: Session,
    outlet_id: UUID,
    start: datetime,
    end: datetime,
) -> tuple[int, int]:
    new_customers = (
        db.query(func.count(OutletCustomer.id))
        .filter(
            OutletCustomer.outlet_id == outlet_id,
            OutletCustomer.first_visit_at >= start,
            OutletCustomer.first_visit_at <= end,
        )
        .scalar()
        or 0
    )
    returning_customers = (
        db.query(func.count(OutletCustomer.id))
        .filter(
            OutletCustomer.outlet_id == outlet_id,
            OutletCustomer.total_orders > 1,
            OutletCustomer.last_visit_at >= start,
            OutletCustomer.last_visit_at <= end,
        )
        .scalar()
        or 0
    )
    return int(new_customers), int(returning_customers)


def get_table_turnover_minutes(
    db: Session,
    outlet_id: UUID,
    start: datetime,
    end: datetime,
) -> Decimal | None:
    placed_ts = (
        db.query(
            OrderStatusLog.order_id.label("order_id"),
            func.min(OrderStatusLog.created_at).label("placed_at"),
        )
        .filter(OrderStatusLog.status == OrderStatus.placed)
        .group_by(OrderStatusLog.order_id)
        .subquery()
    )
    served_ts = (
        db.query(
            OrderStatusLog.order_id.label("order_id"),
            func.min(OrderStatusLog.created_at).label("served_at"),
        )
        .filter(OrderStatusLog.status == OrderStatus.served)
        .group_by(OrderStatusLog.order_id)
        .subquery()
    )

    turnover_seconds = func.extract(
        "epoch", served_ts.c.served_at - placed_ts.c.placed_at
    )
    avg_minutes = (
        db.query(func.avg(turnover_seconds / 60))
        .select_from(Order)
        .join(placed_ts, placed_ts.c.order_id == Order.id)
        .join(served_ts, served_ts.c.order_id == Order.id)
        .filter(
            Order.outlet_id == outlet_id,
            Order.order_type == OrderType.dine_in,
            Order.table_id.isnot(None),
            Order.created_at >= start,
            Order.created_at <= end,
            Order.status != OrderStatus.cancelled,
            served_ts.c.served_at >= placed_ts.c.placed_at,
        )
        .scalar()
    )
    if avg_minutes is None:
        return None
    return Decimal(str(round(float(avg_minutes), 2)))


def get_network_revenue_trend(
    db: Session,
    start: datetime,
    end: datetime,
    from_date: date,
    to_date: date,
) -> list[tuple[date, Decimal, int]]:
    day = func.date_trunc("day", Order.created_at).label("day")
    rows = (
        settled_orders_query(db, start, end)
        .with_entities(
            day,
            func.coalesce(func.sum(Order.total_amount), 0),
            func.count(Order.id),
        )
        .group_by(day)
        .order_by(day)
        .all()
    )
    by_day = {
        row[0].date(): (Decimal(str(row[1])), int(row[2]))
        for row in rows
        if row[0] is not None
    }
    trend: list[tuple[date, Decimal, int]] = []
    current = from_date
    while current <= to_date:
        revenue, order_count = by_day.get(current, (Decimal("0"), 0))
        trend.append((current, revenue, order_count))
        current += timedelta(days=1)
    return trend
