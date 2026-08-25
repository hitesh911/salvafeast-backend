"""menu item dietary type

Revision ID: 017_menu_dietary_type
Revises: 016_plan_yearly_modules
Create Date: 2026-08-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017_menu_dietary_type"
down_revision: Union[str, None] = "016_plan_yearly_modules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "menu_items",
        sa.Column("dietary_type", sa.String(length=16), nullable=True),
    )
    op.execute("UPDATE menu_items SET dietary_type = 'veg' WHERE is_veg IS TRUE")
    op.execute("UPDATE menu_items SET dietary_type = 'non_veg' WHERE is_veg IS FALSE")
    op.drop_column("menu_items", "is_veg")


def downgrade() -> None:
    op.add_column("menu_items", sa.Column("is_veg", sa.Boolean(), nullable=True))
    op.execute("UPDATE menu_items SET is_veg = TRUE WHERE dietary_type = 'veg'")
    op.execute("UPDATE menu_items SET is_veg = FALSE WHERE dietary_type = 'non_veg'")
    op.drop_column("menu_items", "dietary_type")
