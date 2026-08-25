from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session, selectinload

from app.api.v1.public.deps import require_user
from app.core.security import create_order_tracking_token
from app.db.database import get_db
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.outlet import Outlet
from app.models.user import User
from app.schemas.customer import (
    ConsumerOrderDetailResponse,
    ConsumerOrderSummary,
    PushTokenResponse,
    PushTokenUpdate,
)
from app.schemas.order import (
    OrderDetailResponse,
    OrderItemAddonResponse,
    OrderItemResponse,
    OrderStatusLogResponse,
)
from app.schemas.user_profile import UserProfileResponse, UserProfileUpdate
from app.services.outlet_media import store_user_avatar
from app.services.user_profile import build_user_profile_response, update_user_profile

router = APIRouter(prefix="/users", tags=["public-users"])


@router.get("/me", response_model=UserProfileResponse)
def get_my_profile(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    return build_user_profile_response(db, user)


@router.patch("/me", response_model=UserProfileResponse)
def patch_my_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    user = update_user_profile(db, user, payload)
    return build_user_profile_response(db, user)


@router.post("/me/avatar", response_model=UserProfileResponse)
async def upload_my_avatar(
    avatar: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    from datetime import datetime, timezone

    user.avatar_url = await store_user_avatar(user.id, avatar)
    if user.name and user.name.strip() and user.profile_completed_at is None:
        user.profile_completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return build_user_profile_response(db, user)


@router.delete("/me/avatar", response_model=UserProfileResponse)
def delete_my_avatar(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    user.avatar_url = None
    db.commit()
    db.refresh(user)
    return build_user_profile_response(db, user)


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
        guest_name=order.guest_name,
        guest_phone=order.guest_phone,
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


def _load_user_order(db: Session, user_id: UUID, order_id: UUID) -> tuple[Order, Outlet]:
    row = (
        db.query(Order, Outlet)
        .join(Outlet, Outlet.id == Order.outlet_id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.addons),
            selectinload(Order.status_logs),
            selectinload(Order.table),
        )
        .filter(Order.id == order_id, Order.user_id == user_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return row


@router.patch("/me/push-token", response_model=PushTokenResponse)
def update_push_token(
    payload: PushTokenUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    from datetime import datetime, timezone

    user.push_token = payload.push_token
    user.push_token_updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return PushTokenResponse(
        push_token=user.push_token,
        push_token_updated_at=user.push_token_updated_at,
    )


@router.get("/me/orders", response_model=list[ConsumerOrderSummary])
def list_my_orders(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    rows = (
        db.query(Order, Outlet)
        .join(Outlet, Outlet.id == Order.outlet_id)
        .filter(Order.user_id == user.id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return [
        ConsumerOrderSummary(
            id=order.id,
            outlet_id=order.outlet_id,
            outlet_slug=outlet.slug,
            outlet_name=outlet.name,
            outlet_logo_url=outlet.logo_url,
            order_type=order.order_type,
            status=order.status,
            subtotal_amount=order.subtotal_amount,
            discount_amount=order.discount_amount,
            total_amount=order.total_amount,
            payment_status=order.payment_status,
            payment_method=order.payment_method,
            created_at=order.created_at,
        )
        for order, outlet in rows
    ]


@router.get("/me/orders/{order_id}", response_model=ConsumerOrderDetailResponse)
def get_my_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    order, outlet = _load_user_order(db, user.id, order_id)
    tracking_token = create_order_tracking_token(str(order.id), outlet.slug)
    return ConsumerOrderDetailResponse(
        order=_build_order_detail(order),
        outlet_slug=outlet.slug,
        tracking_token=tracking_token,
    )
