from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.enums import (
    OrderStatus,
    PaymentStatus,
    PlatformInvoiceStatus,
    SubscriptionStatus,
)
from app.models.order import Order
from app.models.outlet import Outlet
from app.models.outlet_membership import OutletMembership
from app.models.outlet_subscription import OutletSubscription
from app.models.platform_invoice import PlatformInvoice
from app.models.role import Role
from app.models.subscription_plan import SubscriptionPlan
from app.models.user import User


def _owner_for_outlet(db: Session, outlet_id: UUID) -> tuple[User, OutletMembership] | None:
    row = (
        db.query(OutletMembership, User)
        .join(User, User.id == OutletMembership.user_id)
        .join(Role, Role.id == OutletMembership.role_id)
        .filter(
            OutletMembership.outlet_id == outlet_id,
            Role.name == "Owner",
            Role.is_system_default.is_(True),
        )
        .order_by(OutletMembership.created_at.asc())
        .first()
    )
    if row is None:
        return None
    membership, user = row
    return user, membership


def _subscription_for_outlet(db: Session, outlet_id: UUID) -> OutletSubscription | None:
    return (
        db.query(OutletSubscription)
        .options(joinedload(OutletSubscription.plan))
        .filter(OutletSubscription.outlet_id == outlet_id)
        .first()
    )


def _outlet_has_overdue_invoice(db: Session, outlet_id: UUID) -> bool:
    return (
        db.query(PlatformInvoice.id)
        .filter(
            PlatformInvoice.outlet_id == outlet_id,
            PlatformInvoice.status == PlatformInvoiceStatus.overdue,
        )
        .first()
        is not None
    )


def _outlet_order_stats(
    db: Session, outlet_id: UUID, days: int = 30
) -> tuple[datetime | None, int, Decimal]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    last_order_at = (
        db.query(func.max(Order.created_at))
        .filter(
            Order.outlet_id == outlet_id,
            Order.status != OrderStatus.cancelled,
        )
        .scalar()
    )
    row = (
        db.query(
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_amount), 0),
        )
        .filter(
            Order.outlet_id == outlet_id,
            Order.created_at >= since,
            Order.status != OrderStatus.cancelled,
            Order.payment_status == PaymentStatus.paid,
        )
        .one()
    )
    return last_order_at, int(row[0]), Decimal(str(row[1]))


def enrich_outlet_list_item(db: Session, outlet: Outlet) -> dict:
    owner_row = _owner_for_outlet(db, outlet.id)
    sub = _subscription_for_outlet(db, outlet.id)
    last_order_at, orders_30d, revenue_30d = _outlet_order_stats(db, outlet.id)
    owner_user = owner_row[0] if owner_row else None
    return {
        "id": outlet.id,
        "name": outlet.name,
        "slug": outlet.slug,
        "active_status": outlet.active_status,
        "verification_status": outlet.verification_status,
        "require_customer_login": outlet.require_customer_login,
        "require_prepaid": outlet.require_prepaid,
        "created_at": outlet.created_at,
        "owner_name": owner_user.name if owner_user else None,
        "owner_phone": owner_user.phone if owner_user else None,
        "subscription_plan_name": sub.plan.name if sub and sub.plan else None,
        "subscription_status": sub.status if sub else None,
        "platform_invoice_overdue": _outlet_has_overdue_invoice(db, outlet.id),
        "last_order_at": last_order_at,
        "orders_30d": orders_30d,
        "revenue_30d": revenue_30d,
    }


def enrich_outlet_detail(db: Session, outlet: Outlet) -> dict:
    data = enrich_outlet_list_item(db, outlet)
    active_staff = (
        db.query(func.count(OutletMembership.id))
        .filter(
            OutletMembership.outlet_id == outlet.id,
            OutletMembership.active_status.is_(True),
        )
        .scalar()
        or 0
    )
    data.update(
        {
            "logo_url": outlet.logo_url,
            "cover_image_url": outlet.cover_image_url,
            "address": outlet.address,
            "address_line1": outlet.address_line1,
            "address_line2": outlet.address_line2,
            "landmark": outlet.landmark,
            "area": outlet.area,
            "city": outlet.city,
            "state": outlet.state,
            "pincode": outlet.pincode,
            "latitude": outlet.latitude,
            "longitude": outlet.longitude,
            "phone": outlet.phone,
            "email": outlet.email,
            "whatsapp_phone": outlet.whatsapp_phone,
            "description": outlet.description,
            "cuisine_tags": [
                str(t)
                for t in (outlet.cuisine_tags if isinstance(outlet.cuisine_tags, list) else [])
            ],
            "opening_hours": outlet.opening_hours
            if isinstance(outlet.opening_hours, dict)
            else None,
            "fssai_number": outlet.fssai_number,
            "cost_for_two": outlet.cost_for_two,
            "is_pure_veg": bool(outlet.is_pure_veg),
            "outlet_type": outlet.outlet_type.value if outlet.outlet_type else None,
            "gst_number": outlet.gst_number,
            "updated_at": outlet.updated_at,
            "active_staff_count": int(active_staff),
        }
    )
    return data


def compute_mrr(db: Session) -> Decimal:
    total = (
        db.query(func.coalesce(func.sum(SubscriptionPlan.price_monthly), 0))
        .join(OutletSubscription, OutletSubscription.plan_id == SubscriptionPlan.id)
        .filter(OutletSubscription.status == SubscriptionStatus.active)
        .scalar()
    )
    return Decimal(str(total))


def count_overdue_invoices(db: Session) -> int:
    return int(
        db.query(func.count(PlatformInvoice.id))
        .filter(PlatformInvoice.status == PlatformInvoiceStatus.overdue)
        .scalar()
        or 0
    )


def count_trial_subscriptions(db: Session) -> int:
    return int(
        db.query(func.count(OutletSubscription.id))
        .filter(OutletSubscription.status == SubscriptionStatus.trial)
        .scalar()
        or 0
    )


def compute_health_alerts(db: Session) -> list[dict]:
    alerts: list[dict] = []
    overdue_count = count_overdue_invoices(db)
    if overdue_count:
        alerts.append(
            {
                "severity": "warning",
                "code": "overdue_invoices",
                "message": f"{overdue_count} platform invoice(s) overdue",
            }
        )
    trial_count = count_trial_subscriptions(db)
    if trial_count:
        alerts.append(
            {
                "severity": "info",
                "code": "trials_active",
                "message": f"{trial_count} outlet(s) on trial",
            }
        )
    return alerts
