"""offers and order discount fields

Revision ID: 007_offers
Revises: 006_orders
Create Date: 2026-08-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision: str = "007_offers"
down_revision: Union[str, None] = "006_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

discount_type_enum = ENUM("flat", "percentage", name="discounttype", create_type=False)


def upgrade() -> None:
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE discounttype AS ENUM ('flat', 'percentage'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )
    )

    op.create_table(
        "offers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("outlet_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("offer_code", sa.String(length=50), nullable=False),
        sa.Column("discount_type", discount_type_enum, nullable=False),
        sa.Column("discount_value", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_status", sa.Boolean(), nullable=False),
        sa.Column("usage_limit", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint("outlet_id", "offer_code", name="uq_outlet_offer_code"),
    )
    op.create_index(op.f("ix_offers_outlet_id"), "offers", ["outlet_id"], unique=False)

    op.create_table(
        "offer_menu_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("offer_id", sa.UUID(), nullable=False),
        sa.Column("menu_item_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["menu_item_id"], ["menu_items.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_id", "menu_item_id", name="uq_offer_menu_item"),
    )

    op.add_column("orders", sa.Column("offer_id", sa.UUID(), nullable=True))
    op.add_column(
        "orders",
        sa.Column("subtotal_amount", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column(
            "discount_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute("UPDATE orders SET subtotal_amount = total_amount WHERE subtotal_amount IS NULL")
    op.alter_column("orders", "subtotal_amount", nullable=False)
    op.alter_column("orders", "discount_amount", server_default=None)
    op.create_foreign_key("fk_orders_offer_id", "orders", "offers", ["offer_id"], ["id"])

    op.create_table(
        "offer_redemptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("offer_id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_offer_redemptions_offer_id"), "offer_redemptions", ["offer_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_offer_redemptions_offer_id"), table_name="offer_redemptions")
    op.drop_table("offer_redemptions")
    op.drop_constraint("fk_orders_offer_id", "orders", type_="foreignkey")
    op.drop_column("orders", "discount_amount")
    op.drop_column("orders", "subtotal_amount")
    op.drop_column("orders", "offer_id")
    op.drop_table("offer_menu_items")
    op.drop_index(op.f("ix_offers_outlet_id"), table_name="offers")
    op.drop_table("offers")
    op.execute(sa.text("DROP TYPE IF EXISTS discounttype"))
