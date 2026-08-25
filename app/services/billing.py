from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.enums import OrderStatus, PaymentMethod, PaymentStatus
from app.models.expense import Expense
from app.models.invoice import Invoice
from app.models.order import Order
from app.services.analytics import outlet_settled_orders_query


def list_invoices(
    db: Session,
    outlet_id: UUID,
    start: datetime,
    end: datetime,
) -> list[Invoice]:
    return (
        db.query(Invoice)
        .filter(
            Invoice.outlet_id == outlet_id,
            Invoice.generated_at >= start,
            Invoice.generated_at <= end,
        )
        .order_by(Invoice.generated_at.desc())
        .all()
    )


def get_invoice(db: Session, outlet_id: UUID, invoice_id: UUID) -> Invoice:
    invoice = (
        db.query(Invoice)
        .filter(Invoice.id == invoice_id, Invoice.outlet_id == outlet_id)
        .first()
    )
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return invoice


def get_reconciliation(
    db: Session,
    outlet_id: UUID,
    start: datetime,
    end: datetime,
) -> tuple[list[tuple[PaymentMethod | None, Decimal, int]], Decimal, Decimal]:
    paid_rows = (
        db.query(
            Order.payment_method,
            func.coalesce(func.sum(Order.total_amount), 0),
            func.count(Order.id),
        )
        .filter(
            Order.outlet_id == outlet_id,
            Order.created_at >= start,
            Order.created_at <= end,
            Order.payment_status == PaymentStatus.paid,
            Order.status != OrderStatus.cancelled,
        )
        .group_by(Order.payment_method)
        .all()
    )

    breakdown = [
        (row[0], Decimal(str(row[1])), int(row[2]))
        for row in paid_rows
    ]
    grand_total = sum(item[1] for item in breakdown)

    pending = (
        db.query(func.coalesce(func.sum(Order.total_amount), 0))
        .filter(
            Order.outlet_id == outlet_id,
            Order.created_at >= start,
            Order.created_at <= end,
            Order.payment_status == PaymentStatus.unpaid,
            Order.status != OrderStatus.cancelled,
        )
        .scalar()
    )
    pending_collection = Decimal(str(pending or 0))
    return breakdown, grand_total, pending_collection


def get_profit_loss(
    db: Session,
    outlet_id: UUID,
    start: datetime,
    end: datetime,
    from_date: date,
    to_date: date,
) -> tuple[Decimal, Decimal, Decimal, list[tuple[str, Decimal]]]:
    revenue_row = (
        outlet_settled_orders_query(db, outlet_id, start, end)
        .with_entities(func.coalesce(func.sum(Order.total_amount), 0))
        .scalar()
    )
    revenue = Decimal(str(revenue_row or 0))

    expense_rows = (
        db.query(Expense.category, func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.outlet_id == outlet_id,
            Expense.expense_date >= from_date,
            Expense.expense_date <= to_date,
        )
        .group_by(Expense.category)
        .order_by(Expense.category)
        .all()
    )
    expense_breakdown = [(row[0], Decimal(str(row[1]))) for row in expense_rows]
    total_expenses = sum(amount for _, amount in expense_breakdown)
    net = revenue - total_expenses
    return revenue, total_expenses, net, expense_breakdown
