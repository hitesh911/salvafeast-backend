"""outlet structured address and listing fields

Revision ID: 029_outlet_listing_profile
Revises: 028_payment_review
Create Date: 2026-08-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "029_outlet_listing_profile"
down_revision: Union[str, None] = "028_payment_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("outlets", sa.Column("address_line1", sa.String(length=255), nullable=True))
    op.add_column("outlets", sa.Column("address_line2", sa.String(length=255), nullable=True))
    op.add_column("outlets", sa.Column("landmark", sa.String(length=255), nullable=True))
    op.add_column("outlets", sa.Column("area", sa.String(length=128), nullable=True))
    op.add_column("outlets", sa.Column("city", sa.String(length=128), nullable=True))
    op.add_column("outlets", sa.Column("state", sa.String(length=128), nullable=True))
    op.add_column("outlets", sa.Column("pincode", sa.String(length=12), nullable=True))
    op.add_column("outlets", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("outlets", sa.Column("whatsapp_phone", sa.String(length=50), nullable=True))
    op.add_column("outlets", sa.Column("fssai_number", sa.String(length=50), nullable=True))
    op.add_column("outlets", sa.Column("cost_for_two", sa.Integer(), nullable=True))
    op.add_column(
        "outlets",
        sa.Column("is_pure_veg", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("outlets", sa.Column("outlet_type", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("outlets", "outlet_type")
    op.drop_column("outlets", "is_pure_veg")
    op.drop_column("outlets", "cost_for_two")
    op.drop_column("outlets", "fssai_number")
    op.drop_column("outlets", "whatsapp_phone")
    op.drop_column("outlets", "email")
    op.drop_column("outlets", "pincode")
    op.drop_column("outlets", "state")
    op.drop_column("outlets", "city")
    op.drop_column("outlets", "area")
    op.drop_column("outlets", "landmark")
    op.drop_column("outlets", "address_line2")
    op.drop_column("outlets", "address_line1")
