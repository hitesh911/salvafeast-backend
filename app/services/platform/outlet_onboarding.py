from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.menu_category import MenuCategory
from app.models.outlet import Outlet
from app.models.table import Table
from app.services.outlet_qr import assign_counter_qr
from app.services.table_qr import assign_table_qr, generate_qr_token

DEFAULT_MENU_CATEGORIES = [
    "Starters",
    "Main Course",
    "Rice & Breads",
    "Beverages",
    "Desserts",
]

DEFAULT_TABLE_NUMBERS = ["1", "2", "3", "4", "5"]
DEFAULT_GST_RATE_PERCENT = Decimal("5.00")
DEFAULT_TABLE_COUNT = 5


def default_invoice_prefix(slug: str) -> str:
    return slug.upper().replace("-", "")[:20] or "INV"


def seed_default_outlet_data(db: Session, outlet: Outlet) -> None:
    existing = (
        db.query(MenuCategory.id)
        .filter(MenuCategory.outlet_id == outlet.id)
        .first()
    )
    if existing is not None:
        return

    for sort_order, name in enumerate(DEFAULT_MENU_CATEGORIES):
        db.add(
            MenuCategory(
                outlet_id=outlet.id,
                name=name,
                sort_order=sort_order,
            )
        )

    outlet.invoice_prefix = default_invoice_prefix(outlet.slug)
    outlet.gst_rate_percent = DEFAULT_GST_RATE_PERCENT

    assign_counter_qr(db, outlet)

    for table_number in DEFAULT_TABLE_NUMBERS:
        table = Table(
            outlet_id=outlet.id,
            table_number=table_number,
            qr_token=generate_qr_token(),
        )
        db.add(table)
        db.flush()
        assign_table_qr(db, table, outlet, qr_token=table.qr_token)
