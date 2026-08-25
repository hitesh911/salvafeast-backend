from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import require_outlet_permission
from app.db.database import get_db
from app.models.outlet import Outlet
from app.schemas.outlet_subscription import (
    OutletPlanOptionResponse,
    OutletPlatformInvoiceResponse,
    OutletSubscriptionDetailResponse,
)
from app.services import subscription as subscription_service

router = APIRouter(
    prefix="/outlets/{outlet_id}/subscription",
    tags=["outlet-subscription"],
)


def _get_outlet(db: Session, outlet_id: UUID) -> Outlet:
    from fastapi import HTTPException, status

    outlet = db.query(Outlet).filter(Outlet.id == outlet_id).first()
    if outlet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlet not found")
    return outlet


@router.get("/plans", response_model=list[OutletPlanOptionResponse])
def list_available_plans(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("subscription.view")),
):
    _get_outlet(db, outlet_id)
    plans = subscription_service.list_available_plans(db, outlet_id)
    return [OutletPlanOptionResponse(**plan) for plan in plans]


@router.get("", response_model=OutletSubscriptionDetailResponse | None)
def get_subscription(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("subscription.view")),
):
    _get_outlet(db, outlet_id)
    sub = subscription_service.get_outlet_subscription_optional(db, outlet_id)
    if sub is None:
        return None
    return OutletSubscriptionDetailResponse(**subscription_service.outlet_subscription_to_dict(sub))


@router.get("/invoices", response_model=list[OutletPlatformInvoiceResponse])
def list_invoices(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("subscription.view")),
):
    _get_outlet(db, outlet_id)
    invoices = subscription_service.list_outlet_invoices(db, outlet_id)
    return [
        OutletPlatformInvoiceResponse(**subscription_service.outlet_invoice_to_dict(inv))
        for inv in invoices
    ]


@router.post("/cancel", response_model=OutletSubscriptionDetailResponse)
def cancel_subscription(
    outlet_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("subscription.edit")),
):
    _get_outlet(db, outlet_id)
    sub = subscription_service.cancel_subscription(db, outlet_id)
    db.commit()
    sub = subscription_service.get_outlet_subscription(db, outlet_id)
    return OutletSubscriptionDetailResponse(**subscription_service.outlet_subscription_to_dict(sub))
