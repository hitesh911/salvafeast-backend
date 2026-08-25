from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.enums import BillingInterval, PlatformInvoiceStatus, SubscriptionStatus
from app.models.outlet import Outlet
from app.models.outlet_subscription import OutletSubscription
from app.models.platform_invoice import PlatformInvoice
from app.models.subscription_plan import SubscriptionPlan


def list_plans(db: Session, active_only: bool = False) -> list[SubscriptionPlan]:
    query = db.query(SubscriptionPlan).order_by(SubscriptionPlan.price_monthly.asc())
    if active_only:
        query = query.filter(SubscriptionPlan.active_status.is_(True))
    return query.all()


def get_plan(db: Session, plan_id: UUID) -> SubscriptionPlan:
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan


def delete_plan(db: Session, plan_id: UUID) -> None:
    plan = get_plan(db, plan_id)
    in_use = (
        db.query(OutletSubscription.id)
        .filter(OutletSubscription.plan_id == plan.id)
        .first()
    )
    if in_use is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete plan while outlets are subscribed",
        )
    db.delete(plan)
    db.flush()


def assign_outlet_subscription(
    db: Session,
    outlet: Outlet,
    plan_id: UUID,
    status_value: SubscriptionStatus,
    trial_days: int,
    billing_interval: BillingInterval = BillingInterval.monthly,
) -> OutletSubscription:
    plan = get_plan(db, plan_id)
    now = datetime.now(timezone.utc)
    sub = (
        db.query(OutletSubscription)
        .filter(OutletSubscription.outlet_id == outlet.id)
        .first()
    )
    if sub is None:
        sub = OutletSubscription(outlet_id=outlet.id, plan_id=plan.id)
        db.add(sub)
    else:
        sub.plan_id = plan.id

    sub.status = status_value
    sub.billing_interval = billing_interval
    period_days = 365 if billing_interval == BillingInterval.yearly else 30
    sub.current_period_start = now
    sub.current_period_end = now + timedelta(days=period_days)
    sub.trial_ends_at = (
        now + timedelta(days=trial_days) if status_value == SubscriptionStatus.trial else None
    )
    db.flush()
    return sub


def get_default_trial_plan(db: Session) -> SubscriptionPlan | None:
    return (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.active_status.is_(True))
        .order_by(SubscriptionPlan.price_monthly.asc())
        .first()
    )


def list_subscriptions(
    db: Session,
    status_filter: SubscriptionStatus | None = None,
) -> list[OutletSubscription]:
    query = (
        db.query(OutletSubscription)
        .options(joinedload(OutletSubscription.plan), joinedload(OutletSubscription.outlet))
        .order_by(OutletSubscription.updated_at.desc())
    )
    if status_filter is not None:
        query = query.filter(OutletSubscription.status == status_filter)
    return query.all()


def subscription_to_dict(sub: OutletSubscription) -> dict:
    plan = sub.plan
    return {
        "id": sub.id,
        "outlet_id": sub.outlet_id,
        "outlet_name": sub.outlet.name if sub.outlet else "",
        "plan_id": sub.plan_id,
        "plan_name": plan.name if plan else "",
        "plan_slug": plan.slug if plan else "",
        "price_monthly": plan.price_monthly if plan else Decimal("0"),
        "price_yearly": plan.price_yearly if plan else None,
        "billing_interval": sub.billing_interval,
        "status": sub.status,
        "current_period_start": sub.current_period_start,
        "current_period_end": sub.current_period_end,
        "trial_ends_at": sub.trial_ends_at,
        "created_at": sub.created_at,
        "updated_at": sub.updated_at,
    }


def _next_invoice_number(db: Session) -> str:
    count = db.query(func.count(PlatformInvoice.id)).scalar() or 0
    year = datetime.now(timezone.utc).year
    return f"SF-{year}-{int(count) + 1:05d}"


def create_platform_invoice(
    db: Session,
    outlet: Outlet,
    *,
    amount: Decimal | None,
    period_start: date | None,
    period_end: date | None,
    due_date: date | None,
    notes: str | None,
) -> PlatformInvoice:
    sub = (
        db.query(OutletSubscription)
        .options(joinedload(OutletSubscription.plan))
        .filter(OutletSubscription.outlet_id == outlet.id)
        .first()
    )
    invoice_amount = amount
    if invoice_amount is None:
        if sub and sub.plan:
            if sub.billing_interval == BillingInterval.yearly and sub.plan.price_yearly is not None:
                invoice_amount = sub.plan.price_yearly
            else:
                invoice_amount = sub.plan.price_monthly
        else:
            invoice_amount = Decimal("0")

    invoice = PlatformInvoice(
        outlet_id=outlet.id,
        subscription_id=sub.id if sub else None,
        invoice_number=_next_invoice_number(db),
        amount=invoice_amount,
        status=PlatformInvoiceStatus.draft,
        period_start=period_start,
        period_end=period_end,
        due_date=due_date,
        notes=notes,
    )
    db.add(invoice)
    db.flush()
    return invoice


def list_invoices(
    db: Session,
    *,
    outlet_id: UUID | None = None,
    status_filter: PlatformInvoiceStatus | None = None,
    overdue_only: bool = False,
) -> list[PlatformInvoice]:
    query = (
        db.query(PlatformInvoice)
        .options(joinedload(PlatformInvoice.outlet))
        .order_by(PlatformInvoice.created_at.desc())
    )
    if outlet_id is not None:
        query = query.filter(PlatformInvoice.outlet_id == outlet_id)
    if status_filter is not None:
        query = query.filter(PlatformInvoice.status == status_filter)
    if overdue_only:
        query = query.filter(PlatformInvoice.status == PlatformInvoiceStatus.overdue)
    return query.all()


def invoice_to_dict(invoice: PlatformInvoice) -> dict:
    return {
        "id": invoice.id,
        "outlet_id": invoice.outlet_id,
        "outlet_name": invoice.outlet.name if invoice.outlet else "",
        "subscription_id": invoice.subscription_id,
        "invoice_number": invoice.invoice_number,
        "amount": invoice.amount,
        "status": invoice.status,
        "period_start": invoice.period_start,
        "period_end": invoice.period_end,
        "due_date": invoice.due_date,
        "paid_at": invoice.paid_at,
        "notes": invoice.notes,
        "created_at": invoice.created_at,
    }


def billing_overview(db: Session) -> dict:
    from app.services.platform.outlets import compute_mrr, count_overdue_invoices

    mrr = compute_mrr(db)
    overdue_invoices = list_invoices(db, overdue_only=True)
    overdue_total = sum((inv.amount for inv in overdue_invoices), Decimal("0"))
    active_subs = (
        db.query(func.count(OutletSubscription.id))
        .filter(OutletSubscription.status == SubscriptionStatus.active)
        .scalar()
        or 0
    )
    trial_subs = (
        db.query(func.count(OutletSubscription.id))
        .filter(OutletSubscription.status == SubscriptionStatus.trial)
        .scalar()
        or 0
    )
    plan_rows = (
        db.query(
            SubscriptionPlan.name,
            func.count(OutletSubscription.id),
        )
        .outerjoin(OutletSubscription, OutletSubscription.plan_id == SubscriptionPlan.id)
        .group_by(SubscriptionPlan.id, SubscriptionPlan.name)
        .all()
    )
    return {
        "mrr": mrr,
        "arr": mrr * 12,
        "overdue_total": overdue_total,
        "overdue_count": count_overdue_invoices(db),
        "active_subscriptions": int(active_subs),
        "trial_subscriptions": int(trial_subs),
        "plan_distribution": [
            {"plan_name": row[0], "outlet_count": int(row[1])} for row in plan_rows
        ],
    }
