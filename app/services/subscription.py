from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.plan_modules import (
    get_plan_limits,
    get_plan_modules,
    get_staff_limit,
    normalize_plan_features,
)
from app.models.enums import SubscriptionStatus
from app.models.outlet_subscription import OutletSubscription
from app.models.platform_invoice import PlatformInvoice
from app.models.subscription_plan import SubscriptionPlan
from app.services.platform.billing import invoice_to_dict, subscription_to_dict


def _subscription_query(db: Session):
    return db.query(OutletSubscription).options(
        joinedload(OutletSubscription.plan),
        joinedload(OutletSubscription.outlet),
    )


def get_outlet_subscription_optional(
    db: Session, outlet_id: UUID
) -> OutletSubscription | None:
    return (
        _subscription_query(db)
        .filter(OutletSubscription.outlet_id == outlet_id)
        .first()
    )


def get_outlet_subscription(db: Session, outlet_id: UUID) -> OutletSubscription:
    sub = get_outlet_subscription_optional(db, outlet_id)
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found for this outlet",
        )
    return sub


def _plan_metadata(plan: SubscriptionPlan | None) -> dict:
    if plan is None:
        return {
            "included_modules": [],
            "limits": None,
            "features": None,
            "price_yearly": None,
        }
    features = plan.features
    return {
        "included_modules": get_plan_modules(features, plan_slug=plan.slug),
        "limits": get_plan_limits(features, plan_slug=plan.slug) or None,
        "features": features,
        "price_yearly": plan.price_yearly,
    }


def outlet_subscription_to_dict(sub: OutletSubscription) -> dict:
    data = subscription_to_dict(sub)
    meta = _plan_metadata(sub.plan)
    data.update(meta)
    return data


def plan_option_to_dict(plan: SubscriptionPlan, *, is_current: bool) -> dict:
    features = plan.features
    return {
        "id": plan.id,
        "name": plan.name,
        "slug": plan.slug,
        "price_monthly": plan.price_monthly,
        "price_yearly": plan.price_yearly,
        "included_modules": get_plan_modules(features, plan_slug=plan.slug),
        "limits": get_plan_limits(features, plan_slug=plan.slug) or None,
        "is_current": is_current,
    }


def list_available_plans(db: Session, outlet_id: UUID) -> list[dict]:
    sub = get_outlet_subscription_optional(db, outlet_id)
    current_plan_id = sub.plan_id if sub else None
    plans = (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.active_status.is_(True))
        .order_by(SubscriptionPlan.price_monthly.asc())
        .all()
    )
    return [
        plan_option_to_dict(plan, is_current=plan.id == current_plan_id)
        for plan in plans
    ]


def list_outlet_invoices(db: Session, outlet_id: UUID) -> list[PlatformInvoice]:
    return (
        db.query(PlatformInvoice)
        .options(joinedload(PlatformInvoice.outlet))
        .filter(PlatformInvoice.outlet_id == outlet_id)
        .order_by(PlatformInvoice.created_at.desc())
        .all()
    )


def outlet_invoice_to_dict(invoice: PlatformInvoice) -> dict:
    data = invoice_to_dict(invoice)
    data.pop("outlet_name", None)
    return data


def cancel_subscription(db: Session, outlet_id: UUID) -> OutletSubscription:
    sub = get_outlet_subscription(db, outlet_id)
    if sub.status == SubscriptionStatus.cancelled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Subscription is already cancelled",
        )
    sub.status = SubscriptionStatus.cancelled
    db.flush()
    return sub


def enforce_outlet_plan_module(db: Session, outlet_id: UUID, module: str) -> None:
    if module == "subscription":
        return

    sub = get_outlet_subscription_optional(db, outlet_id)
    if sub is None or sub.plan is None:
        return
    if sub.status not in (SubscriptionStatus.trial, SubscriptionStatus.active):
        return

    allowed = get_plan_modules(sub.plan.features, plan_slug=sub.plan.slug)
    if module not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"The '{module}' module is not included in your subscription plan",
        )


def enforce_staff_limit(db: Session, outlet_id: UUID) -> None:
    sub = get_outlet_subscription_optional(db, outlet_id)
    if sub is None or sub.plan is None:
        return
    limit = get_staff_limit(sub.plan.features, plan_slug=sub.plan.slug)
    if limit is None:
        return
    from app.models.outlet_membership import OutletMembership

    count = db.query(OutletMembership).filter(OutletMembership.outlet_id == outlet_id).count()
    if count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Staff limit reached for your plan ({limit} users). Upgrade to add more staff.",
        )


def normalize_plan_payload_features(
    features: dict | None,
    *,
    modules: list[str] | None,
    limits: dict | None,
) -> dict | None:
    if modules is None and limits is None and features is None:
        return None
    try:
        normalized = normalize_plan_features(features, modules=modules, limits=limits)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return normalized or None
