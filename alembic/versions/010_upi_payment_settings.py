"""outlet UPI payment settings fields

Revision ID: 010_upi_payment_settings
Revises: 009_billing
Create Date: 2026-08-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_upi_payment_settings"
down_revision: Union[str, None] = "009_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("outlets", sa.Column("upi_payee_name", sa.String(length=255), nullable=True))
    op.add_column("outlets", sa.Column("upi_qr_image_url", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("outlets", "upi_qr_image_url")
    op.drop_column("outlets", "upi_payee_name")
