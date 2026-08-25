from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.order import Order
from app.models.outlet import Outlet
from app.models.outlet_customer import OutletCustomer
from app.models.enums import OrderStatus
from app.models.user import User
from app.services.customers import list_outlet_customers


def search_platform_customers(
    db: Session,
    *,
    phone: str | None,
    name: str | None,
    page: int,
    page_size: int,
) -> tuple[list[dict], int]:
    query = db.query(User)
    if phone:
        query = query.filter(User.phone.ilike(f"%{phone.strip()}%"))
    if name:
        query = query.filter(User.name.ilike(f"%{name.strip()}%"))
    if not phone and not name:
        query = query.order_by(User.created_at.desc())

    total = query.count()
    users = (
        query.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items: list[dict] = []
    for user in users:
        affiliations = (
            db.query(OutletCustomer)
            .options(joinedload(OutletCustomer.user))
            .filter(OutletCustomer.user_id == user.id)
            .all()
        )
        total_spend = sum((a.total_spend for a in affiliations), Decimal("0"))
        last_visit = max((a.last_visit_at for a in affiliations), default=None)
        items.append(
            {
                "user_id": user.id,
                "phone": user.phone,
                "name": user.name,
                "outlet_count": len(affiliations),
                "total_spend_network": total_spend,
                "last_visit_at": last_visit,
            }
        )
    return items, total


def get_platform_customer_detail(db: Session, user_id: UUID) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    affiliations = (
        db.query(OutletCustomer, Outlet)
        .join(Outlet, Outlet.id == OutletCustomer.outlet_id)
        .filter(OutletCustomer.user_id == user_id)
        .order_by(OutletCustomer.last_visit_at.desc())
        .all()
    )

    outlet_affiliations = [
        {
            "outlet_id": outlet.id,
            "outlet_name": outlet.name,
            "total_orders": oc.total_orders,
            "total_spend": oc.total_spend,
            "first_visit_at": oc.first_visit_at,
            "last_visit_at": oc.last_visit_at,
            "marketing_opt_in": oc.marketing_opt_in,
        }
        for oc, outlet in affiliations
    ]

    total_spend = sum((a["total_spend"] for a in outlet_affiliations), Decimal("0"))
    total_orders = sum(a["total_orders"] for a in outlet_affiliations)

    recent_orders_rows = (
        db.query(Order, Outlet)
        .join(Outlet, Outlet.id == Order.outlet_id)
        .filter(
            Order.user_id == user_id,
            Order.status != OrderStatus.cancelled,
        )
        .order_by(Order.created_at.desc())
        .limit(20)
        .all()
    )
    recent_orders = [
        {
            "id": order.id,
            "outlet_id": outlet.id,
            "outlet_name": outlet.name,
            "order_type": order.order_type.value,
            "status": order.status.value,
            "total_amount": order.total_amount,
            "created_at": order.created_at,
        }
        for order, outlet in recent_orders_rows
    ]

    return {
        "user_id": user.id,
        "phone": user.phone,
        "name": user.name,
        "created_at": user.created_at,
        "outlet_affiliations": outlet_affiliations,
        "total_spend_network": total_spend,
        "total_orders_network": total_orders,
        "recent_orders": recent_orders,
    }


def list_platform_outlet_customers(
    db: Session,
    outlet_id: UUID,
    sort: str,
    min_orders: int | None,
    page: int,
    page_size: int,
):
    return list_outlet_customers(db, outlet_id, sort, min_orders, page, page_size)
