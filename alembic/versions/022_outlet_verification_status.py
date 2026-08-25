"""outlet verification status

Revision ID: 022_outlet_verification_status
Revises: 021_content_feed
Create Date: 2026-08-23

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022_outlet_verification_status"
down_revision: Union[str, None] = "021_content_feed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outlets",
        sa.Column(
            "verification_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
    )
    op.execute("UPDATE outlets SET verification_status = 'verified'")
    op.create_index(
        "ix_outlets_verification_status",
        "outlets",
        ["verification_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_outlets_verification_status", table_name="outlets")
    op.drop_column("outlets", "verification_status")
