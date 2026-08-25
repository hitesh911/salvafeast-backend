"""order cancellation fields

Revision ID: 027_order_cancellation
Revises: 026_require_prepaid
Create Date: 2026-08-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "027_order_cancellation"
down_revision: Union[str, None] = "026_require_prepaid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

cancelled_by_enum = sa.Enum("user", "staff", name="cancelled_by", native_enum=False)
cancel_request_status_enum = sa.Enum(
    "pending",
    "approved",
    "rejected",
    name="cancel_request_status",
    native_enum=False,
)


def upgrade() -> None:
    cancelled_by_enum.create(op.get_bind(), checkfirst=True)
    cancel_request_status_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "orders",
        sa.Column("cancelled_by", cancelled_by_enum, nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column(
            "cancel_requested_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "cancel_request_status",
            cancel_request_status_enum,
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("orders", "cancel_request_status")
    op.drop_column("orders", "cancel_requested_at")
    op.drop_column("orders", "cancelled_by")
    cancel_request_status_enum.drop(op.get_bind(), checkfirst=True)
    cancelled_by_enum.drop(op.get_bind(), checkfirst=True)
