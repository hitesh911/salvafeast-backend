"""shared user profile fields

Revision ID: 030_user_profile
Revises: 029_outlet_listing_profile
Create Date: 2026-08-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030_user_profile"
down_revision: Union[str, None] = "029_outlet_listing_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("gender", sa.String(length=32), nullable=True))
    op.add_column(
        "users",
        sa.Column("dietary_preferences", sa.JSON(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("profile_completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "profile_completed_at")
    op.drop_column("users", "dietary_preferences")
    op.drop_column("users", "gender")
    op.drop_column("users", "date_of_birth")
    op.drop_column("users", "avatar_url")
