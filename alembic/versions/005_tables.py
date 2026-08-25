"""tables and outlet cover_image_url

Revision ID: 005_tables
Revises: 004_menu
Create Date: 2026-08-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_tables"
down_revision: Union[str, None] = "004_menu"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outlets",
        sa.Column("cover_image_url", sa.String(length=512), nullable=True),
    )
    op.create_table(
        "tables",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("outlet_id", sa.UUID(), nullable=False),
        sa.Column("table_number", sa.String(length=50), nullable=False),
        sa.Column("qr_token", sa.String(length=64), nullable=False),
        sa.Column("qr_code_image_url", sa.String(length=1024), nullable=True),
        sa.Column("active_status", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("qr_token"),
    )
    op.create_index(op.f("ix_tables_outlet_id"), "tables", ["outlet_id"], unique=False)
    op.create_index(op.f("ix_tables_qr_token"), "tables", ["qr_token"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tables_qr_token"), table_name="tables")
    op.drop_index(op.f("ix_tables_outlet_id"), table_name="tables")
    op.drop_table("tables")
    op.drop_column("outlets", "cover_image_url")
