"""plan yearly pricing and billing interval

Revision ID: 016_plan_yearly_modules
Revises: 015_platform_crm
Create Date: 2026-08-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016_plan_yearly_modules"
down_revision: Union[str, None] = "015_platform_crm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscription_plans",
        sa.Column("price_yearly", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "outlet_subscriptions",
        sa.Column(
            "billing_interval",
            sa.String(length=16),
            nullable=False,
            server_default="monthly",
        ),
    )


def downgrade() -> None:
    op.drop_column("outlet_subscriptions", "billing_interval")
    op.drop_column("subscription_plans", "price_yearly")
