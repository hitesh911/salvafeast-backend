from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.public.deps import require_user
from app.core.security import create_order_tracking_token
from app.db.database import get_db
from app.models.offer import Offer
from app.models.outlet import Outlet
from app.models.outlet_customer import OutletCustomer
from app.models.user import User
from app.schemas.customer import MarketingOptInResponse, MarketingOptInUpdate
from app.schemas.public import (
    PublicOfferSummary,
    PublicOutletDetailResponse,
    PublicOutletInfo,
    PublicOutletListResponse,
    PublicOutletSummary,
)
from app.services.outlet_profile import (
    build_public_outlet_info,
    build_public_outlet_summary,
)

router = APIRouter(prefix="/outlets", tags=["public-outlets"])


def _get_active_outlet(db: Session, slug: str) -> Outlet:
    outlet = db.query(Outlet).filter(Outlet.slug == slug).first()
    if outlet is None or not outlet.active_status:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlet not found")
    return outlet


def _build_public_outlet_info(outlet: Outlet) -> PublicOutletInfo:
    return build_public_outlet_info(outlet)


def _build_outlet_summary(outlet: Outlet) -> PublicOutletSummary:
    return build_public_outlet_summary(outlet)


def _is_offer_active(offer: Offer, now: datetime) -> bool:
    if not offer.active_status:
        return False
    if offer.start_date is not None and now < offer.start_date:
        return False
    if offer.end_date is not None and now > offer.end_date:
        return False
    return True


def _active_offers_for_outlet(db: Session, outlet_id: UUID) -> list[PublicOfferSummary]:
    now = datetime.now(timezone.utc)
    offers = (
        db.query(Offer)
        .filter(Offer.outlet_id == outlet_id, Offer.active_status.is_(True))
        .order_by(Offer.title)
        .all()
    )
    return [
        PublicOfferSummary(
            id=offer.id,
            title=offer.title,
            description=offer.description,
            offer_code=offer.offer_code,
            discount_type=offer.discount_type.value,
            discount_value=offer.discount_value,
        )
        for offer in offers
        if _is_offer_active(offer, now)
    ]


@router.get("", response_model=PublicOutletListResponse)
def list_public_outlets(
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Outlet).filter(Outlet.active_status.is_(True))
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(Outlet.name.ilike(term) | Outlet.address.ilike(term))
    total = query.count()
    outlets = query.order_by(Outlet.name).offset(offset).limit(limit).all()
    return PublicOutletListResponse(
        items=[_build_outlet_summary(outlet) for outlet in outlets],
        total=total,
    )


@router.get("/{slug}", response_model=PublicOutletDetailResponse)
def get_public_outlet(slug: str, db: Session = Depends(get_db)):
    outlet = _get_active_outlet(db, slug)
    return PublicOutletDetailResponse(
        outlet=_build_public_outlet_info(outlet),
        active_offers=_active_offers_for_outlet(db, outlet.id),
    )


@router.get("/{slug}/offers", response_model=list[PublicOfferSummary])
def list_public_outlet_offers(slug: str, db: Session = Depends(get_db)):
    outlet = _get_active_outlet(db, slug)
    return _active_offers_for_outlet(db, outlet.id)


@router.patch("/{slug}/marketing-opt-in", response_model=MarketingOptInResponse)
def update_marketing_opt_in(
    slug: str,
    payload: MarketingOptInUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    outlet = _get_active_outlet(db, slug)
    outlet_customer = (
        db.query(OutletCustomer)
        .filter(
            OutletCustomer.outlet_id == outlet.id,
            OutletCustomer.user_id == user.id,
        )
        .first()
    )
    if outlet_customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no order history at this outlet yet",
        )

    outlet_customer.marketing_opt_in = payload.opt_in
    db.commit()
    return MarketingOptInResponse(
        outlet_id=outlet.id,
        marketing_opt_in=outlet_customer.marketing_opt_in,
    )
