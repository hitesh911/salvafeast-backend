"""analytics query indexes

Revision ID: 008_analytics_indexes
Revises: 007_offers
Create Date: 2026-08-22

"""
from typing import Sequence, Union

from alembic import op

revision: str = "008_analytics_indexes"
down_revision: Union[str, None] = "007_offers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_orders_outlet_id_created_at",
        "orders",
        ["outlet_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_orders_outlet_id_status",
        "orders",
        ["outlet_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_order_items_order_id_menu_item_id",
        "order_items",
        ["order_id", "menu_item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_order_items_order_id_menu_item_id", table_name="order_items")
    op.drop_index("ix_orders_outlet_id_status", table_name="orders")
    op.drop_index("ix_orders_outlet_id_created_at", table_name="orders")
