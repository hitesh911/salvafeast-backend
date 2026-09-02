from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from app.api.v1.deps import require_outlet_permission
from app.db.database import get_db
from app.models.order import Order
from app.models.outlet_customer import OutletCustomer
from app.models.user import User
from app.core.phone import IndianPhone
from app.schemas.customer import (
    CustomerLookupResponse,
    OutletCustomerDetail,
    OutletCustomerListItem,
    PaginatedOutletCustomers,
)
from app.schemas.outlet_settings import OutletCustomerUpdate
from app.schemas.order import OrderSummaryResponse
from app.services.customers import get_outlet_customer, list_outlet_customers
from app.services.orders import order_customer_display

router = APIRouter(prefix="/outlets/{outlet_id}", tags=["customers"])


def _to_list_item(outlet_customer: OutletCustomer) -> OutletCustomerListItem:
    user = outlet_customer.user
    return OutletCustomerListItem(
        user_id=user.id,
        phone=user.phone,
        name=user.name,
        total_orders=outlet_customer.total_orders,
        total_spend=outlet_customer.total_spend,
        first_visit_at=outlet_customer.first_visit_at,
        last_visit_at=outlet_customer.last_visit_at,
        marketing_opt_in=outlet_customer.marketing_opt_in,
    )


def _load_user_orders(db: Session, outlet_id: UUID, user_id: UUID) -> list[Order]:
    return (
        db.query(Order)
        .options(selectinload(Order.table), selectinload(Order.user))
        .filter(Order.outlet_id == outlet_id, Order.user_id == user_id)
        .order_by(Order.created_at.desc())
        .all()
    )


def _order_to_summary(order: Order) -> OrderSummaryResponse:
    guest_name, guest_phone = order_customer_display(order)
    return OrderSummaryResponse(
        id=order.id,
        outlet_id=order.outlet_id,
        table_id=order.table_id,
        user_id=order.user_id,
        offer_id=order.offer_id,
        order_type=order.order_type,
        status=order.status,
        subtotal_amount=order.subtotal_amount,
        discount_amount=order.discount_amount,
        total_amount=order.total_amount,
        payment_status=order.payment_status,
        payment_method=order.payment_method,
        guest_name=guest_name,
        guest_phone=guest_phone,
        created_at=order.created_at,
        updated_at=order.updated_at,
        table_number=order.table.table_number if order.table else None,
    )


@router.get("/customers/lookup", response_model=CustomerLookupResponse)
def lookup_customer_by_phone(
    outlet_id: UUID,
    phone: IndianPhone = Query(...),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("customers.view")),
):
    user = db.query(User).filter(User.phone == phone).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    outlet_customer = (
        db.query(OutletCustomer)
        .filter(
            OutletCustomer.outlet_id == outlet_id,
            OutletCustomer.user_id == user.id,
        )
        .first()
    )

    return CustomerLookupResponse(
        user_id=user.id,
        phone=user.phone,
        name=user.name,
        total_orders=outlet_customer.total_orders if outlet_customer else None,
        last_visit_at=outlet_customer.last_visit_at if outlet_customer else None,
    )


@router.get("/customers", response_model=PaginatedOutletCustomers)
def list_customers(
    outlet_id: UUID,
    sort: str = Query(default="-last_visit_at"),
    min_orders: int | None = Query(default=None, ge=1),
    phone: str | None = Query(default=None),
    name: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("customers.view")),
):
    rows, total = list_outlet_customers(
        db, outlet_id, sort, min_orders, page, page_size, phone=phone, name=name
    )
    return PaginatedOutletCustomers(
        items=[_to_list_item(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/customers/{user_id}", response_model=OutletCustomerDetail)
def get_customer(
    outlet_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("customers.view")),
):
    outlet_customer = get_outlet_customer(db, outlet_id, user_id)
    orders = _load_user_orders(db, outlet_id, user_id)
    user = outlet_customer.user
    return OutletCustomerDetail(
        user_id=user.id,
        phone=user.phone,
        name=user.name,
        total_orders=outlet_customer.total_orders,
        total_spend=outlet_customer.total_spend,
        first_visit_at=outlet_customer.first_visit_at,
        last_visit_at=outlet_customer.last_visit_at,
        marketing_opt_in=outlet_customer.marketing_opt_in,
        orders=[_order_to_summary(order) for order in orders],
    )


@router.patch("/customers/{user_id}", response_model=OutletCustomerDetail)
def update_customer(
    outlet_id: UUID,
    user_id: UUID,
    payload: OutletCustomerUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("customers.edit")),
):
    outlet_customer = get_outlet_customer(db, outlet_id, user_id)
    user = outlet_customer.user
    if payload.name is not None:
        user.name = payload.name.strip() or None
    if payload.marketing_opt_in is not None:
        outlet_customer.marketing_opt_in = payload.marketing_opt_in
    db.commit()
    db.refresh(outlet_customer)
    db.refresh(user)
    orders = _load_user_orders(db, outlet_id, user_id)
    return OutletCustomerDetail(
        user_id=user.id,
        phone=user.phone,
        name=user.name,
        total_orders=outlet_customer.total_orders,
        total_spend=outlet_customer.total_spend,
        first_visit_at=outlet_customer.first_visit_at,
        last_visit_at=outlet_customer.last_visit_at,
        marketing_opt_in=outlet_customer.marketing_opt_in,
        orders=[_order_to_summary(order) for order in orders],
    )
