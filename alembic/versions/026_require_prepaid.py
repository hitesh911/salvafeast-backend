"""add require_prepaid to outlets

Revision ID: 026_require_prepaid
Revises: 025_qr_studio
Create Date: 2026-08-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "026_require_prepaid"
down_revision: Union[str, None] = "025_qr_studio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outlets",
        sa.Column(
            "require_prepaid",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("outlets", "require_prepaid", server_default=None)


def downgrade() -> None:
    op.drop_column("outlets", "require_prepaid")
