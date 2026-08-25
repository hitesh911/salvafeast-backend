from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.enums import DiscountType
from app.models.offer import Offer
from app.models.offer_redemption import OfferRedemption


@dataclass
class LineSubtotal:
    menu_item_id: UUID
    amount: Decimal


def _offer_applicable_menu_item_ids(offer: Offer) -> set[UUID]:
    return {row.menu_item_id for row in offer.menu_items}


def _qualifying_subtotal(
    line_subtotals: list[LineSubtotal], applicable_ids: set[UUID] | None
) -> Decimal:
    if applicable_ids is None:
        return sum((line.amount for line in line_subtotals), Decimal("0"))
    return sum(
        (line.amount for line in line_subtotals if line.menu_item_id in applicable_ids),
        Decimal("0"),
    )


def _is_offer_in_date_window(offer: Offer, now: datetime) -> bool:
    if offer.start_date is not None and now < offer.start_date:
        return False
    if offer.end_date is not None and now > offer.end_date:
        return False
    return True


def load_offer_for_outlet(db: Session, outlet_id: UUID, offer_code: str) -> Offer:
    offer = (
        db.query(Offer)
        .options(joinedload(Offer.menu_items))
        .filter(Offer.outlet_id == outlet_id, Offer.offer_code == offer_code)
        .first()
    )
    if offer is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid offer code",
        )
    return offer


def validate_offer_for_order(
    db: Session,
    offer: Offer,
    line_subtotals: list[LineSubtotal],
) -> None:
    now = datetime.now(timezone.utc)
    if not offer.active_status or not _is_offer_in_date_window(offer, now):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid offer code",
        )

    if offer.usage_limit is not None:
        redemption_count = (
            db.query(OfferRedemption).filter(OfferRedemption.offer_id == offer.id).count()
        )
        if redemption_count >= offer.usage_limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Offer limit reached",
            )

    applicable_ids = _offer_applicable_menu_item_ids(offer)
    if applicable_ids:
        order_item_ids = {line.menu_item_id for line in line_subtotals}
        if not applicable_ids.intersection(order_item_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid offer code",
            )


def compute_discount_amount(
    offer: Offer, subtotal_amount: Decimal, line_subtotals: list[LineSubtotal]
) -> Decimal:
    applicable_ids = _offer_applicable_menu_item_ids(offer)
    discount_base = (
        _qualifying_subtotal(line_subtotals, applicable_ids)
        if applicable_ids
        else subtotal_amount
    )

    if offer.discount_type == DiscountType.flat:
        return min(offer.discount_value, discount_base)

    discount = discount_base * (offer.discount_value / Decimal("100"))
    return min(discount, discount_base).quantize(Decimal("0.01"))
