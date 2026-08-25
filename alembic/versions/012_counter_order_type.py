"""add counter order type

Revision ID: 012_counter_order_type
Revises: 011_customer_management
Create Date: 2026-08-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_counter_order_type"
down_revision: Union[str, None] = "011_customer_management"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE ordertype ADD VALUE IF NOT EXISTS 'counter'"))


def downgrade() -> None:
    # PostgreSQL cannot remove a value from an existing enum safely.
    pass
