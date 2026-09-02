from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from app.api.v1.public.deps import get_optional_user
from app.core.security import create_order_tracking_token, decode_order_tracking_token
from app.db.database import get_db
from app.models.enums import OrderStatus, PaymentCollection, PaymentMethod, PaymentStatus
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outlet import Outlet
from app.models.user import User
from app.schemas.order import (
    OrderDetailResponse,
    OrderItemAddonResponse,
    OrderItemResponse,
    OrderPlacementRequest,
    OrderPlacementResponse,
    OrderStatusLogResponse,
    PublicOrderItemAddonStatus,
    PublicOrderItemStatus,
    PublicOrderStatusResponse,
)
from app.services.order_cancellation import (
    cancel_order_by_user,
    request_cancel_by_user,
)
from app.services.order_push_alerts import run_order_status_push
from app.services.order_queue import build_order_queue_info
from app.services.orders import (
    OrderItemInput,
    create_order,
    resolve_order_customer_contact,
    resolve_table_for_outlet,
    validate_order_type_and_table,
)

router = APIRouter(prefix="/outlets", tags=["public-orders"])


def _get_active_outlet(db: Session, slug: str) -> Outlet:
    outlet = db.query(Outlet).filter(Outlet.slug == slug).first()
    if outlet is None or not outlet.active_status:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlet not found")
    return outlet


def _build_order_detail(order: Order) -> OrderDetailResponse:
    table_number = order.table.table_number if order.table else None
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
        guest_name=order.guest_name,
        guest_phone=order.guest_phone,
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


def _load_order_detail(db: Session, order_id: UUID) -> Order:
    order = (
        db.query(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.addons),
            selectinload(Order.status_logs),
            selectinload(Order.table),
        )
        .filter(Order.id == order_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def _authorize_consumer_order(
    db: Session,
    slug: str,
    order_id: UUID,
    token: str | None,
    optional_user: User | None,
) -> tuple[Outlet, Order]:
    outlet = _get_active_outlet(db, slug)
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.outlet_id == outlet.id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if optional_user is not None and order.user_id == optional_user.id:
        return outlet, order

    if token:
        try:
            payload = decode_order_tracking_token(token)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )
        if payload.get("user_type") != "order_guest":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )
        if payload.get("outlet_slug") != slug or payload.get("sub") != str(order_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Token mismatch"
            )
        return outlet, order

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _load_public_order(db: Session, order_id: UUID) -> Order:
    order = (
        db.query(Order)
        .options(
            selectinload(Order.table),
            selectinload(Order.items).selectinload(OrderItem.addons),
        )
        .filter(Order.id == order_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def _build_public_order_status(order: Order, db: Session) -> PublicOrderStatusResponse:
    queue = build_order_queue_info(db, order)
    outlet = db.query(Outlet).filter(Outlet.id == order.outlet_id).first()
    return PublicOrderStatusResponse(
        id=order.id,
        status=order.status,
        payment_status=order.payment_status,
        subtotal_amount=order.subtotal_amount,
        discount_amount=order.discount_amount,
        total_amount=order.total_amount,
        order_type=order.order_type,
        created_at=order.created_at,
        updated_at=order.updated_at,
        table_number=order.table.table_number if order.table else None,
        items=[
            PublicOrderItemStatus(
                menu_item_id=item.menu_item_id,
                variant_id=item.variant_id,
                quantity=item.quantity,
                item_price_at_order=item.item_price_at_order,
                notes=item.notes,
                addons=[
                    PublicOrderItemAddonStatus(addon_id=a.addon_id) for a in item.addons
                ],
            )
            for item in order.items
        ],
        orders_ahead=queue.orders_ahead,
        queue_position=queue.queue_position,
        estimated_wait_minutes=queue.estimated_wait_minutes,
        estimated_ready_at=queue.estimated_ready_at,
        cancelled_by=order.cancelled_by,
        cancel_requested_at=order.cancel_requested_at,
        cancel_request_status=order.cancel_request_status,
        payment_collection=order.payment_collection,
        upi_vpa=outlet.upi_vpa if outlet else None,
        upi_payee_name=outlet.upi_payee_name if outlet else None,
        upi_qr_image_url=outlet.upi_qr_image_url if outlet else None,
    )


@router.post("/{slug}/orders", response_model=OrderPlacementResponse, status_code=status.HTTP_201_CREATED)
def place_order(
    slug: str,
    payload: OrderPlacementRequest,
    db: Session = Depends(get_db),
    optional_user: User | None = Depends(get_optional_user),
):
    outlet = _get_active_outlet(db, slug)
    table_id = resolve_table_for_outlet(db, outlet, payload.table_qr_token)
    validate_order_type_and_table(payload.order_type, table_id)

    user_id: UUID | None = None
    if outlet.require_customer_login:
        if optional_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = optional_user.id
    elif optional_user is not None:
        user_id = optional_user.id

    guest_name, guest_phone = resolve_order_customer_contact(
        optional_user,
        payload.guest_name,
        payload.guest_phone,
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

    payment_status = PaymentStatus.unpaid
    payment_method = None
    payment_collection = None
    initial_status = None
    if outlet.require_prepaid:
        if payload.collection is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Choose Pay with UPI or Pay at counter",
            )
        if payload.collection == PaymentCollection.upi:
            has_upi = bool((outlet.upi_vpa or "").strip() or outlet.upi_qr_image_url)
            if not has_upi:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This outlet is not accepting UPI yet",
                )
        payment_collection = payload.collection
        initial_status = OrderStatus.payment_review

    order, upi_link = create_order(
        db=db,
        outlet=outlet,
        order_type=payload.order_type,
        items_input=items_input,
        table_id=table_id,
        user_id=user_id,
        guest_name=guest_name,
        guest_phone=guest_phone,
        offer_code=payload.offer_code,
        initial_status=initial_status or OrderStatus.placed,
        payment_status=payment_status,
        payment_method=payment_method,
        payment_collection=payment_collection,
    )
    order = _load_order_detail(db, order.id)
    tracking_token = create_order_tracking_token(str(order.id), slug)
    return OrderPlacementResponse(
        order=_build_order_detail(order),
        upi_payment_link=upi_link,
        tracking_token=tracking_token,
    )


@router.get("/{slug}/orders/{order_id}", response_model=PublicOrderStatusResponse)
def get_public_order_status(
    slug: str,
    order_id: UUID,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    _authorize_consumer_order(db, slug, order_id, token, None)
    order = _load_public_order(db, order_id)
    return _build_public_order_status(order, db)


@router.post("/{slug}/orders/{order_id}/cancel", response_model=PublicOrderStatusResponse)
def cancel_public_order(
    slug: str,
    order_id: UUID,
    background_tasks: BackgroundTasks,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
    optional_user: User | None = Depends(get_optional_user),
):
    outlet, order = _authorize_consumer_order(db, slug, order_id, token, optional_user)
    changed_by = optional_user.id if optional_user is not None else None
    cancel_order_by_user(db, order, changed_by)
    db.commit()
    background_tasks.add_task(
        run_order_status_push,
        order.id,
        outlet.id,
        OrderStatus.cancelled,
    )
    order = _load_public_order(db, order_id)
    return _build_public_order_status(order, db)


@router.post(
    "/{slug}/orders/{order_id}/cancel-request",
    response_model=PublicOrderStatusResponse,
)
def request_cancel_public_order(
    slug: str,
    order_id: UUID,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
    optional_user: User | None = Depends(get_optional_user),
):
    _, order = _authorize_consumer_order(db, slug, order_id, token, optional_user)
    request_cancel_by_user(db, order)
    db.commit()
    order = _load_public_order(db, order_id)
    return _build_public_order_status(order, db)
