from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.api.v1.deps import require_outlet_permission
from app.db.database import get_db
from app.models.menu_item import MenuItem
from app.models.offer import Offer
from app.models.offer_menu_item import OfferMenuItem
from app.models.offer_redemption import OfferRedemption
from app.schemas.offer import OfferCreate, OfferResponse, OfferUpdate

router = APIRouter(prefix="/outlets/{outlet_id}", tags=["offers"])


def _validate_menu_items(db: Session, outlet_id: UUID, item_ids: list[UUID]) -> None:
    if not item_ids:
        return
    found = (
        db.query(MenuItem.id)
        .filter(MenuItem.outlet_id == outlet_id, MenuItem.id.in_(item_ids))
        .all()
    )
    if len(found) != len(set(item_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more menu items do not belong to this outlet",
        )


def _set_applicable_items(db: Session, offer: Offer, item_ids: list[UUID]) -> None:
    offer.menu_items.clear()
    for item_id in item_ids:
        db.add(OfferMenuItem(offer_id=offer.id, menu_item_id=item_id))


def _to_offer_response(offer: Offer, redeemed_count: int = 0) -> OfferResponse:
    return OfferResponse(
        id=offer.id,
        outlet_id=offer.outlet_id,
        title=offer.title,
        description=offer.description,
        offer_code=offer.offer_code,
        discount_type=offer.discount_type,
        discount_value=offer.discount_value,
        start_date=offer.start_date,
        end_date=offer.end_date,
        active_status=offer.active_status,
        usage_limit=offer.usage_limit,
        applicable_item_ids=[row.menu_item_id for row in offer.menu_items],
        redeemed_count=redeemed_count,
        created_at=offer.created_at,
        updated_at=offer.updated_at,
    )


def _get_offer(db: Session, outlet_id: UUID, offer_id: UUID) -> Offer:
    offer = (
        db.query(Offer)
        .options(selectinload(Offer.menu_items))
        .filter(Offer.id == offer_id, Offer.outlet_id == outlet_id)
        .first()
    )
    if offer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return offer


@router.get("/offers", response_model=list[OfferResponse])
def list_offers(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("offers.view")),
):
    offers = (
        db.query(Offer)
        .options(selectinload(Offer.menu_items))
        .filter(Offer.outlet_id == outlet_id)
        .order_by(Offer.created_at.desc())
        .all()
    )
    if not offers:
        return []

    offer_ids = [offer.id for offer in offers]
    redemption_counts = dict(
        db.query(OfferRedemption.offer_id, func.count(OfferRedemption.id))
        .filter(OfferRedemption.offer_id.in_(offer_ids))
        .group_by(OfferRedemption.offer_id)
        .all()
    )
    return [
        _to_offer_response(offer, redemption_counts.get(offer.id, 0))
        for offer in offers
    ]


@router.post("/offers", response_model=OfferResponse, status_code=status.HTTP_201_CREATED)
def create_offer(
    outlet_id: UUID,
    payload: OfferCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("offers.edit")),
):
    existing = (
        db.query(Offer)
        .filter(Offer.outlet_id == outlet_id, Offer.offer_code == payload.offer_code)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Offer code already exists for this outlet",
        )

    _validate_menu_items(db, outlet_id, payload.applicable_item_ids)

    offer = Offer(
        outlet_id=outlet_id,
        title=payload.title,
        description=payload.description,
        offer_code=payload.offer_code,
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
        start_date=payload.start_date,
        end_date=payload.end_date,
        active_status=payload.active_status,
        usage_limit=payload.usage_limit,
    )
    db.add(offer)
    db.flush()
    _set_applicable_items(db, offer, payload.applicable_item_ids)
    db.commit()
    db.refresh(offer)
    return _to_offer_response(offer, 0)


def _get_redemption_count(db: Session, offer_id: UUID) -> int:
    return (
        db.query(OfferRedemption).filter(OfferRedemption.offer_id == offer_id).count()
    )


@router.patch("/offers/{offer_id}", response_model=OfferResponse)
def update_offer(
    outlet_id: UUID,
    offer_id: UUID,
    payload: OfferUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("offers.edit")),
):
    offer = _get_offer(db, outlet_id, offer_id)

    if payload.offer_code is not None and payload.offer_code != offer.offer_code:
        existing = (
            db.query(Offer)
            .filter(
                Offer.outlet_id == outlet_id,
                Offer.offer_code == payload.offer_code,
                Offer.id != offer_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Offer code already exists for this outlet",
            )
        offer.offer_code = payload.offer_code

    if payload.title is not None:
        offer.title = payload.title
    if payload.description is not None:
        offer.description = payload.description
    if payload.discount_type is not None:
        offer.discount_type = payload.discount_type
    if payload.discount_value is not None:
        offer.discount_value = payload.discount_value
    if payload.start_date is not None:
        offer.start_date = payload.start_date
    if payload.end_date is not None:
        offer.end_date = payload.end_date
    if payload.active_status is not None:
        offer.active_status = payload.active_status
    if payload.usage_limit is not None:
        offer.usage_limit = payload.usage_limit

    if payload.applicable_item_ids is not None:
        _validate_menu_items(db, outlet_id, payload.applicable_item_ids)
        _set_applicable_items(db, offer, payload.applicable_item_ids)

    db.commit()
    db.refresh(offer)
    return _to_offer_response(offer, _get_redemption_count(db, offer.id))


@router.delete("/offers/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_offer(
    outlet_id: UUID,
    offer_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("offers.edit")),
):
    offer = _get_offer(db, outlet_id, offer_id)
    redemption_count = (
        db.query(OfferRedemption).filter(OfferRedemption.offer_id == offer.id).count()
    )
    if redemption_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Offer has redemptions and cannot be deleted. Set active_status to false instead.",
        )
    db.delete(offer)
    db.commit()
