"""add require_customer_login to outlets

Revision ID: 003_outlet_settings
Revises: 002_otp_auth
Create Date: 2026-08-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_outlet_settings"
down_revision: Union[str, None] = "002_otp_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outlets",
        sa.Column(
            "require_customer_login",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("outlets", "require_customer_login", server_default=None)


def downgrade() -> None:
    op.drop_column("outlets", "require_customer_login")
