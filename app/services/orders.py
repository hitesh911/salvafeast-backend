from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.enums import OrderStatus, OrderType, PaymentCollection, PaymentMethod, PaymentStatus
from app.models.menu_item import MenuItem
from app.models.menu_item_addon import MenuItemAddon
from app.models.menu_item_variant import MenuItemVariant
from app.models.offer import Offer
from app.models.offer_redemption import OfferRedemption
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_item_addon import OrderItemAddon
from app.models.order_status_log import OrderStatusLog
from app.models.outlet import Outlet
from app.models.outlet_customer import OutletCustomer
from app.models.table import Table
from app.services.offers import (
    LineSubtotal,
    compute_discount_amount,
    load_offer_for_outlet,
    validate_offer_for_order,
)


def _clean_contact(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def resolve_order_customer_contact(
    user: User | None,
    guest_name: str | None,
    guest_phone: str | None,
) -> tuple[str | None, str | None]:
    """Snapshot customer name/phone on the order from guest fields and/or user profile."""
    name = _clean_contact(guest_name)
    phone = _clean_contact(guest_phone)
    if user is None:
        return name, phone
    if not name:
        name = _clean_contact(user.name)
    if not phone:
        phone = _clean_contact(user.phone)
    return name, phone


def order_customer_display(order: Order) -> tuple[str | None, str | None]:
    """Resolve name/phone for staff views, falling back to the linked user."""
    return resolve_order_customer_contact(
        order.user, order.guest_name, order.guest_phone
    )


def build_upi_payment_link(outlet: Outlet, order: Order) -> str | None:
    if not outlet.upi_vpa:
        return None
    amount = format(order.total_amount, "f")
    return f"upi://pay?pa={outlet.upi_vpa}&am={amount}&tn=Order-{order.id}"


def upsert_outlet_customer(
    db: Session, outlet_id: UUID, user_id: UUID, order_amount: Decimal
) -> None:
    now = datetime.now(timezone.utc)
    outlet_customer = (
        db.query(OutletCustomer)
        .filter(
            OutletCustomer.outlet_id == outlet_id,
            OutletCustomer.user_id == user_id,
        )
        .first()
    )
    if outlet_customer is None:
        outlet_customer = OutletCustomer(
            outlet_id=outlet_id,
            user_id=user_id,
            first_visit_at=now,
            last_visit_at=now,
            total_orders=1,
            total_spend=order_amount,
        )
        db.add(outlet_customer)
    else:
        outlet_customer.last_visit_at = now
        outlet_customer.total_orders += 1
        outlet_customer.total_spend += order_amount


class OrderItemInput:
    def __init__(
        self,
        menu_item_id: UUID,
        variant_id: UUID | None,
        quantity: int,
        addon_ids: list[UUID],
        notes: str | None,
    ):
        self.menu_item_id = menu_item_id
        self.variant_id = variant_id
        self.quantity = quantity
        self.addon_ids = addon_ids
        self.notes = notes


def create_order(
    db: Session,
    outlet: Outlet,
    order_type: OrderType,
    items_input: list[OrderItemInput],
    table_id: UUID | None,
    user_id: UUID | None,
    guest_name: str | None,
    guest_phone: str | None,
    offer_code: str | None = None,
    *,
    initial_status: OrderStatus = OrderStatus.placed,
    payment_status: PaymentStatus = PaymentStatus.unpaid,
    payment_method: PaymentMethod | None = None,
    payment_collection: PaymentCollection | None = None,
    changed_by: UUID | None = None,
) -> tuple[Order, str | None]:
    if not items_input:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order must contain at least one item",
        )

    order_items: list[OrderItem] = []
    line_subtotals: list[LineSubtotal] = []
    subtotal_amount = Decimal("0")

    for item_input in items_input:
        menu_item = (
            db.query(MenuItem)
            .filter(MenuItem.id == item_input.menu_item_id, MenuItem.outlet_id == outlet.id)
            .first()
        )
        if menu_item is None or not menu_item.is_available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Menu item {item_input.menu_item_id} is unavailable",
            )

        price_delta = Decimal("0")
        if item_input.variant_id is not None:
            variant = (
                db.query(MenuItemVariant)
                .filter(
                    MenuItemVariant.id == item_input.variant_id,
                    MenuItemVariant.menu_item_id == menu_item.id,
                )
                .first()
            )
            if variant is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Variant {item_input.variant_id} does not belong to menu item",
                )
            if not variant.is_available:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Variant {item_input.variant_id} is unavailable",
                )
            price_delta = variant.price_delta

        item_price = menu_item.base_price + price_delta
        addon_total = Decimal("0")
        order_item_addons: list[OrderItemAddon] = []

        for addon_id in item_input.addon_ids:
            addon = (
                db.query(MenuItemAddon)
                .filter(
                    MenuItemAddon.id == addon_id,
                    MenuItemAddon.menu_item_id == menu_item.id,
                    MenuItemAddon.is_available.is_(True),
                )
                .first()
            )
            if addon is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Addon {addon_id} is unavailable for this menu item",
                )
            addon_total += addon.price
            order_item_addons.append(
                OrderItemAddon(addon_id=addon.id, addon_price_at_order=addon.price)
            )

        line_total = (item_price + addon_total) * item_input.quantity
        subtotal_amount += line_total
        line_subtotals.append(LineSubtotal(menu_item_id=menu_item.id, amount=line_total))

        order_item = OrderItem(
            menu_item_id=menu_item.id,
            variant_id=item_input.variant_id,
            quantity=item_input.quantity,
            item_price_at_order=item_price,
            notes=item_input.notes,
            addons=order_item_addons,
        )
        order_items.append(order_item)

    offer: Offer | None = None
    discount_amount = Decimal("0")
    if offer_code:
        offer = load_offer_for_outlet(db, outlet.id, offer_code)
        validate_offer_for_order(db, offer, line_subtotals)
        discount_amount = compute_discount_amount(offer, subtotal_amount, line_subtotals)

    total_amount = subtotal_amount - discount_amount

    order = Order(
        outlet_id=outlet.id,
        table_id=table_id,
        user_id=user_id,
        offer_id=offer.id if offer else None,
        order_type=order_type,
        status=initial_status,
        subtotal_amount=subtotal_amount,
        discount_amount=discount_amount,
        total_amount=total_amount,
        payment_status=payment_status,
        payment_method=payment_method,
        payment_collection=payment_collection,
        guest_name=guest_name,
        guest_phone=guest_phone,
        items=order_items,
        status_logs=[
            OrderStatusLog(status=initial_status, changed_by=changed_by)
        ],
    )
    db.add(order)
    db.flush()

    if offer is not None:
        db.add(
            OfferRedemption(
                offer_id=offer.id,
                order_id=order.id,
                user_id=user_id,
            )
        )

    if user_id is not None:
        upsert_outlet_customer(db, outlet.id, user_id, total_amount)

    db.commit()
    db.refresh(order)
    upi_link = build_upi_payment_link(outlet, order)
    return order, upi_link


def resolve_table_id_for_outlet(
    db: Session, outlet_id: UUID, table_id: UUID | None
) -> UUID | None:
    if table_id is None:
        return None
    table = (
        db.query(Table)
        .filter(Table.id == table_id, Table.outlet_id == outlet_id)
        .first()
    )
    if table is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid table for this outlet",
        )
    if not table.active_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Table is inactive",
        )
    return table.id


def resolve_table_for_outlet(
    db: Session, outlet: Outlet, table_qr_token: str | None
) -> UUID | None:
    if table_qr_token is None:
        return None
    table = db.query(Table).filter(Table.qr_token == table_qr_token).first()
    if table is None or table.outlet_id != outlet.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid table token for this outlet",
        )
    if not table.active_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Table is inactive",
        )
    return table.id


def validate_order_type_and_table(order_type: OrderType, table_id: UUID | None) -> None:
    if order_type == OrderType.dine_in and table_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dine-in orders require a table",
        )
    if order_type != OrderType.dine_in and table_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{order_type.value} orders cannot have a table",
        )


def resolve_staff_user_id(
    db: Session,
    *,
    user_id: UUID | None,
    link_customer: bool,
    guest_phone: str | None,
    guest_name: str | None,
) -> UUID | None:
    if user_id is not None and link_customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either user_id or link_customer, not both",
        )

    if user_id is not None:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User not found",
            )
        return user.id

    if link_customer:
        if not guest_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="guest_phone is required when link_customer is true",
            )
        from app.services.users import find_or_create_user

        user = find_or_create_user(db, guest_phone, name=guest_name)
        return user.id

    return None


def find_or_create_user_for_order(db: Session, phone: str) -> User:
    from app.services.users import find_or_create_user

    return find_or_create_user(db, phone)
