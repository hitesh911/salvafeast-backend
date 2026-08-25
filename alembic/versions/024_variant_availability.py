"""add is_available to menu item variants

Revision ID: 024_variant_availability
Revises: 023_push_token_length
Create Date: 2026-08-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "024_variant_availability"
down_revision: Union[str, None] = "023_push_token_length"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "menu_item_variants",
        sa.Column(
            "is_available",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.alter_column("menu_item_variants", "is_available", server_default=None)


def downgrade() -> None:
    op.drop_column("menu_item_variants", "is_available")
