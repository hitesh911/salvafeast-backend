"""Queue position and ETA for consumer order tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.enums import OrderStatus
from app.models.order import Order
from app.models.order_status_log import OrderStatusLog

KITCHEN_QUEUE_STATUSES = (
    OrderStatus.placed,
    OrderStatus.accepted,
    OrderStatus.preparing,
)

DEFAULT_AVG_MINUTES = 15
MIN_HISTORY_SAMPLES = 3
HISTORY_LIMIT = 20
HISTORY_DAYS = 7
PARALLEL_TICKETS = 2
MIN_WAIT_MINUTES = 1
MAX_WAIT_MINUTES = 120


@dataclass(frozen=True)
class OrderQueueInfo:
    orders_ahead: int
    queue_position: int | None
    estimated_wait_minutes: int | None
    estimated_ready_at: datetime | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def count_orders_ahead(db: Session, order: Order) -> int:
    return (
        db.query(func.count(Order.id))
        .filter(
            Order.outlet_id == order.outlet_id,
            Order.status.in_(KITCHEN_QUEUE_STATUSES),
            Order.created_at < order.created_at,
            Order.id != order.id,
        )
        .scalar()
        or 0
    )


def average_place_to_ready_minutes(db: Session, outlet_id: UUID) -> float:
    since = _utc_now() - timedelta(days=HISTORY_DAYS)

    placed_ts = (
        db.query(
            OrderStatusLog.order_id.label("order_id"),
            func.min(OrderStatusLog.created_at).label("placed_at"),
        )
        .filter(OrderStatusLog.status == OrderStatus.placed)
        .group_by(OrderStatusLog.order_id)
        .subquery()
    )
    ready_ts = (
        db.query(
            OrderStatusLog.order_id.label("order_id"),
            func.min(OrderStatusLog.created_at).label("ready_at"),
        )
        .filter(OrderStatusLog.status == OrderStatus.ready)
        .group_by(OrderStatusLog.order_id)
        .subquery()
    )

    duration_seconds = func.extract("epoch", ready_ts.c.ready_at - placed_ts.c.placed_at)
    rows = (
        db.query(duration_seconds.label("seconds"), ready_ts.c.ready_at)
        .select_from(Order)
        .join(placed_ts, placed_ts.c.order_id == Order.id)
        .join(ready_ts, ready_ts.c.order_id == Order.id)
        .filter(
            Order.outlet_id == outlet_id,
            Order.status != OrderStatus.cancelled,
            Order.created_at >= since,
            ready_ts.c.ready_at >= placed_ts.c.placed_at,
        )
        .order_by(ready_ts.c.ready_at.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )

    minutes = [float(row.seconds) / 60.0 for row in rows if row.seconds is not None and row.seconds > 0]
    if len(minutes) < MIN_HISTORY_SAMPLES:
        return float(DEFAULT_AVG_MINUTES)
    return sum(minutes) / len(minutes)


def estimate_wait_minutes(orders_ahead: int, avg_minutes: float) -> int:
    tickets = orders_ahead + 1
    batches = ceil(tickets / PARALLEL_TICKETS)
    wait = int(round(batches * avg_minutes))
    return max(MIN_WAIT_MINUTES, min(MAX_WAIT_MINUTES, wait))


def build_order_queue_info(db: Session, order: Order) -> OrderQueueInfo:
    in_kitchen = order.status in KITCHEN_QUEUE_STATUSES
    orders_ahead = count_orders_ahead(db, order) if in_kitchen else 0
    queue_position = orders_ahead + 1 if in_kitchen else None

    if not in_kitchen:
        return OrderQueueInfo(
            orders_ahead=0,
            queue_position=None,
            estimated_wait_minutes=None,
            estimated_ready_at=None,
        )

    avg = average_place_to_ready_minutes(db, order.outlet_id)
    wait = estimate_wait_minutes(orders_ahead, avg)
    ready_at = _utc_now() + timedelta(minutes=wait)
    return OrderQueueInfo(
        orders_ahead=orders_ahead,
        queue_position=queue_position,
        estimated_wait_minutes=wait,
        estimated_ready_at=ready_at,
    )
