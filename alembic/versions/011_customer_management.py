"""customer management fields

Revision ID: 011_customer_management
Revises: 010_upi_payment_settings
Create Date: 2026-08-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_customer_management"
down_revision: Union[str, None] = "010_upi_payment_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("push_token", sa.String(length=512), nullable=True))
    op.add_column(
        "customers",
        sa.Column("push_token_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outlet_customers",
        sa.Column(
            "marketing_opt_in",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.alter_column("outlet_customers", "marketing_opt_in", server_default=None)


def downgrade() -> None:
    op.drop_column("outlet_customers", "marketing_opt_in")
    op.drop_column("customers", "push_token_updated_at")
    op.drop_column("customers", "push_token")
