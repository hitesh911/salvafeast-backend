from datetime import date
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.orders import _build_order_detail, _load_order_detail
from app.api.v1.deps import require_outlet_permission
from app.db.database import get_db
from app.models.enums import OrderStatus
from app.models.expense import Expense
from app.schemas.billing import (
    ExpenseCreate,
    ExpenseResponse,
    ExpenseUpdate,
    InvoiceResponse,
    OrderSettleRequest,
    OrderSettleResponse,
    ProfitLossResponse,
    ReconciliationBreakdownItem,
    ReconciliationResponse,
    ExpenseCategoryBreakdown,
)
from app.services.analytics import resolve_date_range
from app.services.billing import (
    get_invoice,
    get_profit_loss,
    get_reconciliation,
    list_invoices,
)
from app.services.invoicing import create_invoice_for_order, settle_order
from app.services.order_push_alerts import run_order_status_push

router = APIRouter(prefix="/outlets/{outlet_id}", tags=["billing"])


def _get_expense(db: Session, outlet_id: UUID, expense_id: UUID) -> Expense:
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.outlet_id == outlet_id)
        .first()
    )
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
    return expense


@router.post("/orders/{order_id}/invoice", response_model=InvoiceResponse)
def create_order_invoice(
    outlet_id: UUID,
    order_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(require_outlet_permission("billing.edit")),
):
    if current_user.user_type != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can generate invoices",
        )
    invoice = create_invoice_for_order(db, outlet_id, order_id, current_user.id)
    return InvoiceResponse.model_validate(invoice)


@router.post("/orders/{order_id}/settle", response_model=OrderSettleResponse)
def settle_outlet_order(
    outlet_id: UUID,
    order_id: UUID,
    payload: OrderSettleRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(require_outlet_permission("billing.edit")),
):
    if current_user.user_type != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can settle orders",
        )

    order, invoice = settle_order(
        db, outlet_id, order_id, payload.payment_method, current_user.id
    )
    background_tasks.add_task(
        run_order_status_push,
        order.id,
        outlet_id,
        OrderStatus.completed,
    )
    order = _load_order_detail(db, outlet_id, order_id)
    return OrderSettleResponse(
        order=_build_order_detail(order),
        invoice=InvoiceResponse.model_validate(invoice),
    )


@router.get("/invoices", response_model=list[InvoiceResponse])
def list_outlet_invoices(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("billing.view")),
):
    start, end, _, _ = resolve_date_range(from_date, to_date)
    invoices = list_invoices(db, outlet_id, start, end)
    return [InvoiceResponse.model_validate(invoice) for invoice in invoices]


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
def get_outlet_invoice(
    outlet_id: UUID,
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("billing.view")),
):
    invoice = get_invoice(db, outlet_id, invoice_id)
    return InvoiceResponse.model_validate(invoice)


@router.get("/billing/reconciliation", response_model=ReconciliationResponse)
def billing_reconciliation(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("billing.view")),
):
    start, end, _, _ = resolve_date_range(from_date, to_date, default_days=7)
    breakdown, grand_total, pending_collection = get_reconciliation(db, outlet_id, start, end)
    return ReconciliationResponse(
        breakdown=[
            ReconciliationBreakdownItem(
                payment_method=payment_method,
                total_amount=total_amount,
                order_count=order_count,
            )
            for payment_method, total_amount, order_count in breakdown
        ],
        grand_total=grand_total,
        pending_collection=pending_collection,
    )


@router.post("/expenses", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
def create_expense(
    outlet_id: UUID,
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_outlet_permission("billing.edit")),
):
    if current_user.user_type != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can create expenses",
        )
    expense = Expense(
        outlet_id=outlet_id,
        category=payload.category,
        description=payload.description,
        amount=payload.amount,
        expense_date=payload.expense_date,
        created_by=current_user.id,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return ExpenseResponse.model_validate(expense)


@router.get("/expenses", response_model=list[ExpenseResponse])
def list_expenses(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("billing.view")),
):
    _, _, resolved_from, resolved_to = resolve_date_range(from_date, to_date)
    query = db.query(Expense).filter(
        Expense.outlet_id == outlet_id,
        Expense.expense_date >= resolved_from,
        Expense.expense_date <= resolved_to,
    )
    if category is not None:
        query = query.filter(Expense.category == category)
    expenses = query.order_by(Expense.expense_date.desc(), Expense.created_at.desc()).all()
    return [ExpenseResponse.model_validate(expense) for expense in expenses]


@router.patch("/expenses/{expense_id}", response_model=ExpenseResponse)
def update_expense(
    outlet_id: UUID,
    expense_id: UUID,
    payload: ExpenseUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("billing.edit")),
):
    expense = _get_expense(db, outlet_id, expense_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(expense, field, value)
    db.commit()
    db.refresh(expense)
    return ExpenseResponse.model_validate(expense)


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    outlet_id: UUID,
    expense_id: UUID,
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("billing.edit")),
):
    expense = _get_expense(db, outlet_id, expense_id)
    db.delete(expense)
    db.commit()


@router.get("/billing/profit-loss", response_model=ProfitLossResponse)
def billing_profit_loss(
    outlet_id: UUID,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _user=Depends(require_outlet_permission("billing.view")),
):
    start, end, resolved_from, resolved_to = resolve_date_range(from_date, to_date)
    revenue, total_expenses, net, expense_breakdown = get_profit_loss(
        db, outlet_id, start, end, resolved_from, resolved_to
    )
    return ProfitLossResponse(
        revenue=revenue,
        total_expenses=total_expenses,
        net=net,
        expense_breakdown=[
            ExpenseCategoryBreakdown(category=category, amount=amount)
            for category, amount in expense_breakdown
        ],
    )
