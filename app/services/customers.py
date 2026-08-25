from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Query, Session, joinedload

from app.models.outlet_customer import OutletCustomer
from app.models.user import User

ALLOWED_SORT_FIELDS = {
    "last_visit_at": OutletCustomer.last_visit_at,
    "first_visit_at": OutletCustomer.first_visit_at,
    "total_orders": OutletCustomer.total_orders,
    "total_spend": OutletCustomer.total_spend,
}


def parse_customer_sort(sort: str) -> tuple:
    descending = sort.startswith("-")
    field_name = sort[1:] if descending else sort
    column = ALLOWED_SORT_FIELDS.get(field_name)
    if column is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort field '{field_name}'",
        )
    return column.desc() if descending else column.asc()


def list_outlet_customers(
    db: Session,
    outlet_id: UUID,
    sort: str,
    min_orders: int | None,
    page: int,
    page_size: int,
    *,
    phone: str | None = None,
    name: str | None = None,
) -> tuple[list[OutletCustomer], int]:
    query: Query = (
        db.query(OutletCustomer)
        .options(joinedload(OutletCustomer.user))
        .join(User, User.id == OutletCustomer.user_id)
        .filter(OutletCustomer.outlet_id == outlet_id)
    )
    if min_orders is not None:
        query = query.filter(OutletCustomer.total_orders >= min_orders)
    if phone:
        query = query.filter(User.phone.ilike(f"%{phone.strip()}%"))
    if name:
        query = query.filter(User.name.ilike(f"%{name.strip()}%"))

    total = query.count()
    order_clause = parse_customer_sort(sort)
    rows = (
        query.order_by(order_clause)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def get_outlet_customer(
    db: Session,
    outlet_id: UUID,
    user_id: UUID,
) -> OutletCustomer:
    outlet_customer = (
        db.query(OutletCustomer)
        .options(joinedload(OutletCustomer.user))
        .filter(
            OutletCustomer.outlet_id == outlet_id,
            OutletCustomer.user_id == user_id,
        )
        .first()
    )
    if outlet_customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found at this outlet",
        )
    return outlet_customer
