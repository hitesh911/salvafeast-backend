"""support access audit log

Revision ID: 013_support_access_logs
Revises: 012_counter_order_type
Create Date: 2026-08-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "013_support_access_logs"
down_revision: Union[str, None] = "012_counter_order_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "support_access_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform_admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outlet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"]),
        sa.ForeignKeyConstraint(["platform_admin_id"], ["platform_admins.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_support_access_logs_outlet_id"),
        "support_access_logs",
        ["outlet_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_support_access_logs_platform_admin_id"),
        "support_access_logs",
        ["platform_admin_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_support_access_logs_platform_admin_id"),
        table_name="support_access_logs",
    )
    op.drop_index(
        op.f("ix_support_access_logs_outlet_id"),
        table_name="support_access_logs",
    )
    op.drop_table("support_access_logs")
