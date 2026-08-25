from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from app.db.database import get_db
from app.models.enums import OrderType
from app.models.menu_category import MenuCategory
from app.models.menu_item import MenuItem
from app.models.outlet import Outlet
from app.models.table import Table
from app.schemas.public import (
    PublicMenuCategory,
    PublicMenuItem,
    PublicMenuItemAddon,
    PublicMenuItemImage,
    PublicMenuItemVariant,
    PublicMenuResponse,
    PublicOrderingContext,
    PublicTableOption,
)
from app.services.outlet_profile import build_public_outlet_info

router = APIRouter(prefix="/outlets", tags=["public"])

AVAILABLE_ORDER_TYPES = [OrderType.dine_in, OrderType.pickup, OrderType.counter]


def _build_public_menu_item(item: MenuItem) -> PublicMenuItem:
    return PublicMenuItem(
        id=item.id,
        name=item.name,
        description=item.description,
        base_price=item.base_price,
        dietary_type=item.dietary_type,
        sort_order=item.sort_order,
        images=[
            PublicMenuItemImage.model_validate(img)
            for img in sorted(item.images, key=lambda i: i.sort_order)
        ],
        variants=[
            PublicMenuItemVariant.model_validate(v)
            for v in sorted(item.variants, key=lambda v: v.sort_order)
            if v.is_available
        ],
        addons=[
            PublicMenuItemAddon.model_validate(a)
            for a in item.addons
            if a.is_available
        ],
    )


@router.get("/{slug}/menu", response_model=PublicMenuResponse)
def get_public_menu(
    slug: str,
    t: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    outlet = db.query(Outlet).filter(Outlet.slug == slug).first()
    if outlet is None or not outlet.active_status:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outlet not found")

    scanned_table: Table | None = None
    table_id: UUID | None = None
    if t is not None:
        scanned_table = db.query(Table).filter(Table.qr_token == t).first()
        if scanned_table is None or scanned_table.outlet_id != outlet.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid table token for this outlet",
            )
        table_id = scanned_table.id

    active_tables = (
        db.query(Table)
        .filter(Table.outlet_id == outlet.id, Table.active_status.is_(True))
        .order_by(Table.table_number)
        .all()
    )

    entry_point = "table" if scanned_table is not None else "counter"
    default_order_type = OrderType.dine_in if scanned_table else OrderType.counter

    ordering = PublicOrderingContext(
        entry_point=entry_point,
        default_order_type=default_order_type,
        scanned_table_id=scanned_table.id if scanned_table else None,
        scanned_table_number=scanned_table.table_number if scanned_table else None,
        require_customer_login=outlet.require_customer_login,
        require_prepaid=outlet.require_prepaid,
        upi_vpa=outlet.upi_vpa,
        upi_payee_name=outlet.upi_payee_name,
        upi_qr_image_url=outlet.upi_qr_image_url,
        available_order_types=AVAILABLE_ORDER_TYPES,
        tables=[
            PublicTableOption(table_number=table.table_number, qr_token=table.qr_token)
            for table in active_tables
        ],
    )

    categories = (
        db.query(MenuCategory)
        .filter(MenuCategory.outlet_id == outlet.id)
        .options(
            selectinload(MenuCategory.items).selectinload(MenuItem.images),
            selectinload(MenuCategory.items).selectinload(MenuItem.variants),
            selectinload(MenuCategory.items).selectinload(MenuItem.addons),
        )
        .order_by(MenuCategory.sort_order, MenuCategory.name)
        .all()
    )

    public_categories: list[PublicMenuCategory] = []
    for category in categories:
        available_items = [
            _build_public_menu_item(item)
            for item in sorted(category.items, key=lambda i: (i.sort_order, i.name))
            if item.is_available
        ]
        public_categories.append(
            PublicMenuCategory(
                id=category.id,
                name=category.name,
                sort_order=category.sort_order,
                items=available_items,
            )
        )

    return PublicMenuResponse(
        outlet=build_public_outlet_info(outlet),
        table_id=table_id,
        ordering=ordering,
        menu=public_categories,
    )
