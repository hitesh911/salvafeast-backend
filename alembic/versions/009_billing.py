"""billing and accounting tables

Revision ID: 009_billing
Revises: 008_analytics_indexes
Create Date: 2026-08-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision: str = "009_billing"
down_revision: Union[str, None] = "008_analytics_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

payment_method_enum = ENUM("upi", "cash", "card", "other", name="paymentmethod", create_type=False)


def upgrade() -> None:
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "CREATE TYPE paymentmethod AS ENUM ('upi', 'cash', 'card', 'other'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )
    )

    op.add_column("outlets", sa.Column("gst_rate_percent", sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column("outlets", sa.Column("invoice_prefix", sa.String(length=20), nullable=True))
    op.add_column("orders", sa.Column("payment_method", payment_method_enum, nullable=True))

    op.create_table(
        "outlet_invoice_sequences",
        sa.Column("outlet_id", sa.UUID(), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"]),
        sa.PrimaryKeyConstraint("outlet_id"),
    )

    op.create_table(
        "invoices",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("outlet_id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("invoice_number", sa.String(length=50), nullable=False),
        sa.Column("subtotal_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("taxable_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("cgst_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("sgst_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("pdf_url", sa.String(length=512), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["outlet_users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_invoice_order_id"),
        sa.UniqueConstraint("outlet_id", "invoice_number", name="uq_outlet_invoice_number"),
    )
    op.create_index(op.f("ix_invoices_outlet_id"), "invoices", ["outlet_id"], unique=False)

    op.create_table(
        "expenses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("outlet_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["outlet_users.id"]),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_expenses_outlet_id"), "expenses", ["outlet_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_expenses_outlet_id"), table_name="expenses")
    op.drop_table("expenses")
    op.drop_index(op.f("ix_invoices_outlet_id"), table_name="invoices")
    op.drop_table("invoices")
    op.drop_table("outlet_invoice_sequences")
    op.drop_column("orders", "payment_method")
    op.drop_column("outlets", "invoice_prefix")
    op.drop_column("outlets", "gst_rate_percent")
    op.execute(sa.text("DROP TYPE IF EXISTS paymentmethod"))
