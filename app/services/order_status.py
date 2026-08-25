from fastapi import HTTPException, status

from app.models.enums import OrderStatus, PaymentStatus

LIVE_STATUSES = {
    OrderStatus.placed,
    OrderStatus.accepted,
    OrderStatus.preparing,
    OrderStatus.ready,
    OrderStatus.served,
}

TERMINAL_STATUSES = {OrderStatus.completed, OrderStatus.cancelled}


def validate_status_transition(
    current: OrderStatus,
    new_status: OrderStatus,
    payment_status: PaymentStatus,
) -> None:
    if current == new_status:
        return

    if current in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot move an order that is already {current.value}",
        )

    if new_status == OrderStatus.cancelled:
        return

    if current == OrderStatus.payment_review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirm payment before sending this order to the kitchen",
        )

    if new_status in LIVE_STATUSES:
        if current in LIVE_STATUSES:
            return
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status transition from '{current.value}' to '{new_status.value}'",
        )

    if new_status == OrderStatus.completed:
        if current not in LIVE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status transition from '{current.value}' to '{new_status.value}'",
            )
        if payment_status != PaymentStatus.paid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Settle the order before marking it completed",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Invalid status transition from '{current.value}' to '{new_status.value}'",
    )
