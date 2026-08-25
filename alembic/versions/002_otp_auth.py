"""otp auth and outlet user phone changes

Revision ID: 002_otp_auth
Revises: 001_initial
Create Date: 2026-08-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_otp_auth"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "otp_verifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=False),
        sa.Column("otp_code_hash", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_otp_verifications_phone"), "otp_verifications", ["phone"], unique=False)

    op.drop_constraint("outlet_users_email_key", "outlet_users", type_="unique")
    op.drop_column("outlet_users", "password_hash")
    op.alter_column("outlet_users", "email", existing_type=sa.String(length=255), nullable=True)
    op.alter_column("outlet_users", "phone", existing_type=sa.String(length=50), nullable=False)
    op.create_index(op.f("ix_outlet_users_phone"), "outlet_users", ["phone"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_outlet_users_phone"), table_name="outlet_users")
    op.alter_column("outlet_users", "phone", existing_type=sa.String(length=50), nullable=True)
    op.alter_column("outlet_users", "email", existing_type=sa.String(length=255), nullable=False)
    op.add_column(
        "outlet_users",
        sa.Column("password_hash", sa.String(length=255), nullable=False, server_default=""),
    )
    op.alter_column("outlet_users", "password_hash", server_default=None)
    op.create_unique_constraint("outlet_users_email_key", "outlet_users", ["email"])

    op.drop_index(op.f("ix_otp_verifications_phone"), table_name="otp_verifications")
    op.drop_table("otp_verifications")
