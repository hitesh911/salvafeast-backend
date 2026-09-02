from datetime import datetime
from typing import Union
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.api.v1.deps import require_outlet_permission
from app.db.database import get_db
from app.models.enums import OrderStatus, PaymentMethod, PaymentStatus
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_status_log import OrderStatusLog
from app.models.outlet import Outlet
from app.schemas.order import (
    OrderDetailResponse,
    OrderItemAddonResponse,
    OrderItemResponse,
    OrderStatusLogResponse,
    OrderStatusUpdate,
    OrderSummaryResponse,
    PaginatedOrderSummaries,
    PaymentStatusUpdate,
    ConfirmPaymentRequest,
    StaffOrderCreate,
)
from app.services.order_cancellation import (
    apply_staff_cancellation,
    approve_cancel_request,
    reject_cancel_request,
)
from app.services.order_push_alerts import run_order_status_push
from app.services.order_status import validate_status_transition
from app.services.orders import (
    OrderItemInput,
    create_order,
    order_customer_display,
    resolve_staff_user_id,
    resolve_table_id_for_outlet,
    validate_order_type_and_table,
)

router = APIRouter(prefix="/outlets/{outlet_id}", tags=["orders"])

_ACTIVE_BOARD_STATUSES = [
    OrderStatus.payment_review,
    OrderStatus.placed,
    OrderStatus.accepted,
    OrderStatus.preparing,
    OrderStatus.ready,
    OrderStatus.served,
]


class OrderBoardVersionResponse(BaseModel):
    version: str


def _get_order(db: Session, outlet_id: UUID, order_id: UUID) -> Order:
    order = db.query(Order).filter(Order.id == order_id, Order.outlet_id == outlet_id).first()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def _get_outlet(db: Session, outlet_id: UUID) -> Outlet:
    outlet = db.query(Outlet).filter(Outlet.id == outlet_id).first()
    if outlet is None or not outlet.active_status:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlet not found")
    return outlet


def _load_order_detail(db: Session, outlet_id: UUID, order_id: UUID) -> Order:
    order = (
        db.query(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.addons),
            selectinload(Order.status_logs),
            selectinload(Order.table),
            selectinload(Order.user),
        )
        .filter(Order.id == order_id, Order.outlet_id == outlet_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def _build_order_detail(order: Order) -> OrderDetailResponse:
    table_number = order.table.table_number if order.table else None
    guest_name, guest_phone = order_customer_display(order)
    return OrderDetailResponse(
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
        payment_collection=order.payment_collection,
        guest_name=guest_name,
        guest_phone=guest_phone,
        cancelled_by=order.cancelled_by,
        cancel_requested_at=order.cancel_requested_at,
        cancel_request_status=order.cancel_request_status,
        created_at=order.created_at,
        updated_at=order.updated_at,
        table_number=table_number,
        items=[
            OrderItemResponse(
                id=item.id,
                menu_item_id=item.menu_item_id,
                variant_id=item.variant_id,
                quantity=item.quantity,
                item_price_at_order=item.item_price_at_order,
                notes=item.notes,
                addons=[OrderItemAddonResponse.model_validate(a) for a in item.addons],
            )
            for item in order.items
        ],
        status_logs=[
            OrderStatusLogResponse.model_validate(log)
            for log in sorted(order.status_logs, key=lambda log: log.created_at)
        ],
    )


@router.post(
    "/orders",
    response_model=OrderDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_staff_order(
    outlet_id: UUID,
    payload: StaffOrderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_outlet_permission("orders.edit")),
):
    if current_user.user_type != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can create staff orders",
        )

    outlet = _get_outlet(db, outlet_id)
    table_id = resolve_table_id_for_outlet(db, outlet_id, payload.table_id)
    validate_order_type_and_table(payload.order_type, table_id)

    resolved_user_id = resolve_staff_user_id(
        db,
        user_id=payload.user_id,
        link_customer=payload.link_customer,
        guest_phone=payload.guest_phone,
        guest_name=payload.guest_name,
    )

    items_input = [
        OrderItemInput(
            menu_item_id=item.menu_item_id,
            variant_id=item.variant_id,
            quantity=item.quantity,
            addon_ids=item.addon_ids,
            notes=item.notes,
        )
        for item in payload.items
    ]

    initial_status = (
        OrderStatus.served if payload.is_quick_bill else OrderStatus.accepted
    )

    order, _upi_link = create_order(
        db=db,
        outlet=outlet,
        order_type=payload.order_type,
        items_input=items_input,
        table_id=table_id,
        user_id=resolved_user_id,
        guest_name=payload.guest_name,
        guest_phone=payload.guest_phone,
        offer_code=payload.offer_code,
        initial_status=initial_status,
        changed_by=current_user.id,
    )
    order = _load_order_detail(db, outlet_id, order.id)
    return _build_order_detail(order)


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
        payment_collection=order.payment_collection,
        guest_name=guest_name,
        guest_phone=guest_phone,
        cancelled_by=order.cancelled_by,
        cancel_requested_at=order.cancel_requested_at,
        cancel_request_status=order.cancel_request_status,
        created_at=order.created_at,
        updated_at=order.updated_at,
        table_number=order.table.table_number if order.table else None,
    )


@router.get("/orders/board-version", response_model=OrderBoardVersionResponse)
def get_order_board_version(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("orders.view")),
):
    max_updated, count = (
        db.query(func.max(Order.updated_at), func.count(Order.id))
        .filter(
            Order.outlet_id == outlet_id,
            Order.status.in_(_ACTIVE_BOARD_STATUSES),
        )
        .one()
    )
    stamp = max_updated.isoformat() if max_updated is not None else "none"
    return OrderBoardVersionResponse(version=f"{stamp}:{count}")


@router.get(
    "/orders",
    response_model=Union[
        list[OrderSummaryResponse],
        list[OrderDetailResponse],
        PaginatedOrderSummaries,
    ],
)
def list_orders(
    outlet_id: UUID,
    status_filter: OrderStatus | None = Query(default=None, alias="status"),
    since: datetime | None = Query(default=None),
    from_dt: datetime | None = Query(default=None, alias="from"),
    to_dt: datetime | None = Query(default=None, alias="to"),
    statuses: list[OrderStatus] | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_items: bool = Query(default=False),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("orders.view")),
):
    load_options = [selectinload(Order.table), selectinload(Order.user)]
    if include_items:
        load_options.extend(
            [
                selectinload(Order.items).selectinload(OrderItem.addons),
                selectinload(Order.status_logs),
            ]
        )

    query = (
        db.query(Order)
        .options(*load_options)
        .filter(Order.outlet_id == outlet_id)
    )
    if status_filter is not None:
        query = query.filter(Order.status == status_filter)
    if statuses:
        query = query.filter(Order.status.in_(statuses))
    range_from = from_dt or since
    if range_from is not None:
        query = query.filter(Order.updated_at >= range_from)
    if to_dt is not None:
        query = query.filter(Order.updated_at <= to_dt)

    if page is not None:
        total = query.count()
        orders = (
            query.order_by(Order.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return PaginatedOrderSummaries(
            items=[_order_to_summary(order) for order in orders],
            total=total,
            page=page,
            page_size=page_size,
        )

    orders = query.order_by(Order.created_at.desc()).all()
    if include_items:
        return [_build_order_detail(order) for order in orders]
    return [_order_to_summary(order) for order in orders]


@router.get("/orders/{order_id}", response_model=OrderDetailResponse)
def get_order(
    outlet_id: UUID,
    order_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("orders.view")),
):
    order = _load_order_detail(db, outlet_id, order_id)
    return _build_order_detail(order)


@router.patch("/orders/{order_id}/status", response_model=OrderDetailResponse)
def update_order_status(
    outlet_id: UUID,
    order_id: UUID,
    payload: OrderStatusUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(require_outlet_permission("orders.edit")),
):
    order = _get_order(db, outlet_id, order_id)
    validate_status_transition(order.status, payload.status, order.payment_status)
    if payload.status == OrderStatus.cancelled:
        apply_staff_cancellation(db, order, current_user.id if current_user.user_type == "user" else None)
    order.status = payload.status

    changed_by = current_user.id if current_user.user_type == "user" else None
    db.add(OrderStatusLog(order_id=order.id, status=payload.status, changed_by=changed_by))
    db.commit()
    background_tasks.add_task(
        run_order_status_push,
        order.id,
        outlet_id,
        payload.status,
    )
    order = _load_order_detail(db, outlet_id, order_id)
    return _build_order_detail(order)


@router.post(
    "/orders/{order_id}/cancel-request/approve",
    response_model=OrderDetailResponse,
)
def approve_cancel_request_endpoint(
    outlet_id: UUID,
    order_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(require_outlet_permission("orders.edit")),
):
    order = _get_order(db, outlet_id, order_id)
    changed_by = current_user.id if current_user.user_type == "user" else None
    approve_cancel_request(db, order, changed_by)
    db.commit()
    background_tasks.add_task(
        run_order_status_push,
        order.id,
        outlet_id,
        OrderStatus.cancelled,
    )
    order = _load_order_detail(db, outlet_id, order_id)
    return _build_order_detail(order)


@router.post(
    "/orders/{order_id}/cancel-request/reject",
    response_model=OrderDetailResponse,
)
def reject_cancel_request_endpoint(
    outlet_id: UUID,
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_outlet_permission("orders.edit")),
):
    order = _get_order(db, outlet_id, order_id)
    reject_cancel_request(db, order)
    db.commit()
    order = _load_order_detail(db, outlet_id, order_id)
    return _build_order_detail(order)


@router.post(
    "/orders/{order_id}/confirm-payment",
    response_model=OrderDetailResponse,
)
def confirm_prepaid_payment(
    outlet_id: UUID,
    order_id: UUID,
    payload: ConfirmPaymentRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(require_outlet_permission("orders.edit")),
):
    order = _get_order(db, outlet_id, order_id)
    if order.status != OrderStatus.payment_review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This order is not waiting for payment confirmation",
        )
    order.status = OrderStatus.placed
    order.payment_status = PaymentStatus.paid
    order.payment_method = payload.payment_method
    changed_by = current_user.id if current_user.user_type == "user" else None
    db.add(
        OrderStatusLog(
            order_id=order.id, status=OrderStatus.placed, changed_by=changed_by
        )
    )
    db.commit()
    background_tasks.add_task(
        run_order_status_push,
        order.id,
        outlet_id,
        OrderStatus.placed,
    )
    order = _load_order_detail(db, outlet_id, order_id)
    return _build_order_detail(order)


@router.patch("/orders/{order_id}/payment-status", response_model=OrderDetailResponse)
def update_payment_status(
    outlet_id: UUID,
    order_id: UUID,
    payload: PaymentStatusUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("orders.edit")),
):
    order = _get_order(db, outlet_id, order_id)
    order.payment_status = payload.payment_status
    if payload.payment_status == PaymentStatus.paid:
        order.payment_method = payload.payment_method
    else:
        order.payment_method = None
    db.commit()
    order = _load_order_detail(db, outlet_id, order_id)
    return _build_order_detail(order)
