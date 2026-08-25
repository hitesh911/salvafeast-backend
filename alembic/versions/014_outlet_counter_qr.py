"""outlet counter qr image url

Revision ID: 014_outlet_counter_qr
Revises: 013_support_access_logs
Create Date: 2026-08-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014_outlet_counter_qr"
down_revision: Union[str, None] = "013_support_access_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outlets",
        sa.Column("counter_qr_image_url", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("outlets", "counter_qr_image_url")
