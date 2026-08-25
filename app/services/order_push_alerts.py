"""Web Push delivery for consumer order status alerts."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.enums import OrderStatus
from app.models.order import Order
from app.models.outlet import Outlet
from app.models.user import User

logger = logging.getLogger(__name__)

STATUS_ALERTS: dict[OrderStatus, tuple[str, str]] = {
    OrderStatus.accepted: (
        "Order accepted",
        "{outlet} confirmed your order.",
    ),
    OrderStatus.preparing: (
        "Preparing your food",
        "{outlet} is preparing your order.",
    ),
    OrderStatus.ready: (
        "Order ready",
        "Your order at {outlet} is ready for pickup.",
    ),
    OrderStatus.served: (
        "Order served",
        "Your order at {outlet} has been served.",
    ),
    OrderStatus.completed: (
        "Order complete",
        "Thanks for ordering from {outlet}!",
    ),
    OrderStatus.cancelled: (
        "Order cancelled",
        "Your order at {outlet} was cancelled.",
    ),
}


def _parse_subscription(push_token: str) -> dict | None:
    try:
        data = json.loads(push_token)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if "endpoint" not in data or "keys" not in data:
        return None
    return data


def _order_tracking_path(outlet_slug: str, order_id: UUID) -> str:
    return f"/{outlet_slug}/orders/{order_id}?from=account"


def send_order_status_push(
    db: Session,
    order: Order,
    outlet: Outlet,
    new_status: OrderStatus,
) -> bool:
    if not settings.push_notifications_enabled:
        return False
    if new_status == OrderStatus.placed:
        return False
    if not order.user_id:
        return False

    alert = STATUS_ALERTS.get(new_status)
    if alert is None:
        return False

    user = db.query(User).filter(User.id == order.user_id).first()
    if user is None or not user.push_token:
        return False

    subscription = _parse_subscription(user.push_token)
    if subscription is None:
        logger.warning("Invalid push_token for user %s", user.id)
        return False

    title, body_template = alert
    body = body_template.format(outlet=outlet.name)
    payload = json.dumps(
        {
            "title": title,
            "body": body,
            "data": {"url": _order_tracking_path(outlet.slug, order.id)},
        }
    )

    try:
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:{settings.VAPID_CONTACT_EMAIL}"},
        )
        return True
    except WebPushException as exc:
        if exc.response is not None and exc.response.status_code in (404, 410):
            user.push_token = None
            db.commit()
            logger.info("Cleared expired push subscription for user %s", user.id)
        else:
            logger.warning(
                "Push failed for order %s user %s: %s",
                order.id,
                user.id,
                exc,
            )
        return False
    except Exception:
        logger.exception(
            "Unexpected push error for order %s user %s",
            order.id,
            user.id,
        )
        return False


def run_order_status_push(
    order_id: UUID,
    outlet_id: UUID,
    new_status: OrderStatus,
) -> None:
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        outlet = db.query(Outlet).filter(Outlet.id == outlet_id).first()
        if order is None or outlet is None:
            return
        send_order_status_push(db, order, outlet, new_status)
    finally:
        db.close()
