from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.enums import (
    CancelledBy,
    CancelRequestStatus,
    OrderStatus,
)
from app.models.order import Order
from app.models.order_status_log import OrderStatusLog
from app.services.order_status import TERMINAL_STATUSES, validate_status_transition

REQUESTABLE_STATUSES = {
    OrderStatus.accepted,
    OrderStatus.preparing,
    OrderStatus.ready,
    OrderStatus.served,
}


def _ensure_not_terminal(order: Order) -> None:
    if order.status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order is already {order.status.value}",
        )


def cancel_order_by_user(db: Session, order: Order, changed_by: UUID | None) -> None:
    _ensure_not_terminal(order)
    if order.status not in {OrderStatus.placed, OrderStatus.payment_review}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request cancellation instead — the outlet has already accepted this order",
        )
    if order.cancel_request_status == CancelRequestStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A cancellation request is already pending",
        )

    validate_status_transition(
        order.status, OrderStatus.cancelled, order.payment_status
    )
    order.status = OrderStatus.cancelled
    order.cancelled_by = CancelledBy.user
    order.cancel_requested_at = None
    order.cancel_request_status = None
    db.add(
        OrderStatusLog(
            order_id=order.id,
            status=OrderStatus.cancelled,
            changed_by=changed_by,
        )
    )


def request_cancel_by_user(db: Session, order: Order) -> None:
    _ensure_not_terminal(order)
    if order.status in {OrderStatus.placed, OrderStatus.payment_review}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use cancel order while the order is still waiting for the kitchen",
        )
    if order.status not in REQUESTABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This order can no longer be cancelled",
        )
    if order.cancel_request_status == CancelRequestStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A cancellation request is already pending",
        )

    order.cancel_requested_at = datetime.now(timezone.utc)
    order.cancel_request_status = CancelRequestStatus.pending


def approve_cancel_request(
    db: Session, order: Order, staff_user_id: UUID | None
) -> None:
    _ensure_not_terminal(order)
    if order.cancel_request_status != CancelRequestStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending cancellation request for this order",
        )

    validate_status_transition(
        order.status, OrderStatus.cancelled, order.payment_status
    )
    order.status = OrderStatus.cancelled
    order.cancelled_by = CancelledBy.staff
    order.cancel_request_status = CancelRequestStatus.approved
    db.add(
        OrderStatusLog(
            order_id=order.id,
            status=OrderStatus.cancelled,
            changed_by=staff_user_id,
        )
    )


def reject_cancel_request(db: Session, order: Order) -> None:
    if order.cancel_request_status != CancelRequestStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending cancellation request for this order",
        )
    order.cancel_request_status = CancelRequestStatus.rejected


def apply_staff_cancellation(
    db: Session,
    order: Order,
    staff_user_id: UUID | None,
) -> None:
    order.cancelled_by = CancelledBy.staff
    if order.cancel_request_status == CancelRequestStatus.pending:
        order.cancel_request_status = CancelRequestStatus.approved
    else:
        order.cancel_requested_at = None
        order.cancel_request_status = None
