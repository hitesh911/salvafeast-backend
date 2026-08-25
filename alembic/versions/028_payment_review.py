"""payment_review status and payment_collection

Revision ID: 028_payment_review
Revises: 027_order_cancellation
Create Date: 2026-08-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "028_payment_review"
down_revision: Union[str, None] = "027_order_cancellation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            sa.text(
                "ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'payment_review'"
            )
        )
    op.add_column(
        "orders",
        sa.Column(
            "payment_collection",
            sa.String(length=16),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("orders", "payment_collection")
    # Postgres cannot remove enum values safely; leave payment_review in place.
