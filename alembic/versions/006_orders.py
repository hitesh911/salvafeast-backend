"""orders and customer models

Revision ID: 006_orders
Revises: 005_tables
Create Date: 2026-08-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision: str = "006_orders"
down_revision: Union[str, None] = "005_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

order_type_enum = ENUM(
    "dine_in", "pickup", "pre_order", name="ordertype", create_type=False
)
order_status_enum = ENUM(
    "placed",
    "accepted",
    "preparing",
    "ready",
    "served",
    "completed",
    "cancelled",
    name="orderstatus",
    create_type=False,
)
payment_status_enum = ENUM("unpaid", "paid", name="paymentstatus", create_type=False)


def upgrade() -> None:
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE ordertype AS ENUM ('dine_in', 'pickup', 'pre_order'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )
    )
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE orderstatus AS ENUM "
            "('placed', 'accepted', 'preparing', 'ready', 'served', 'completed', 'cancelled'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )
    )
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE paymentstatus AS ENUM ('unpaid', 'paid'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )
    )

    op.add_column("outlets", sa.Column("upi_vpa", sa.String(length=255), nullable=True))

    op.create_table(
        "customers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone"),
    )
    op.create_index(op.f("ix_customers_phone"), "customers", ["phone"], unique=False)

    op.create_table(
        "outlet_customers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("outlet_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column(
            "first_visit_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_visit_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("total_orders", sa.Integer(), nullable=False),
        sa.Column("total_spend", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("outlet_id", "customer_id", name="uq_outlet_customer"),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("outlet_id", sa.UUID(), nullable=False),
        sa.Column("table_id", sa.UUID(), nullable=True),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("order_type", order_type_enum, nullable=False),
        sa.Column("status", order_status_enum, nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("payment_status", payment_status_enum, nullable=False),
        sa.Column("guest_name", sa.String(length=255), nullable=True),
        sa.Column("guest_phone", sa.String(length=50), nullable=True),
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
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"]),
        sa.ForeignKeyConstraint(["table_id"], ["tables.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_orders_outlet_id"), "orders", ["outlet_id"], unique=False)

    op.create_table(
        "order_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("menu_item_id", sa.UUID(), nullable=False),
        sa.Column("variant_id", sa.UUID(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("item_price_at_order", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["menu_item_id"], ["menu_items.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["menu_item_variants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "order_item_addons",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_item_id", sa.UUID(), nullable=False),
        sa.Column("addon_id", sa.UUID(), nullable=False),
        sa.Column("addon_price_at_order", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["addon_id"], ["menu_item_addons.id"]),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "order_status_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("status", order_status_enum, nullable=False),
        sa.Column("changed_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["changed_by"], ["outlet_users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("order_status_logs")
    op.drop_table("order_item_addons")
    op.drop_table("order_items")
    op.drop_index(op.f("ix_orders_outlet_id"), table_name="orders")
    op.drop_table("orders")
    op.drop_table("outlet_customers")
    op.drop_index(op.f("ix_customers_phone"), table_name="customers")
    op.drop_table("customers")
    op.drop_column("outlets", "upi_vpa")

    op.execute(sa.text("DROP TYPE IF EXISTS paymentstatus"))
    op.execute(sa.text("DROP TYPE IF EXISTS orderstatus"))
    op.execute(sa.text("DROP TYPE IF EXISTS ordertype"))
