"""outlet consumer profile fields

Revision ID: 018_outlet_consumer_profile
Revises: 017_menu_dietary_type
Create Date: 2026-08-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON

revision: str = "018_outlet_consumer_profile"
down_revision: Union[str, None] = "017_menu_dietary_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("outlets", sa.Column("description", sa.String(1024), nullable=True))
    op.add_column("outlets", sa.Column("cuisine_tags", JSON, nullable=True))
    op.add_column("outlets", sa.Column("opening_hours", JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("outlets", "opening_hours")
    op.drop_column("outlets", "cuisine_tags")
    op.drop_column("outlets", "description")
