"""platform crm tables

Revision ID: 015_platform_crm
Revises: 014_outlet_counter_qr
Create Date: 2026-08-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "015_platform_crm"
down_revision: Union[str, None] = "014_outlet_counter_qr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "platform_admins",
        sa.Column("active_status", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "platform_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["platform_admins.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_platform_audit_logs_action"),
        "platform_audit_logs",
        ["action"],
        unique=False,
    )
    op.create_index(
        op.f("ix_platform_audit_logs_actor_id"),
        "platform_audit_logs",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_platform_audit_logs_created_at"),
        "platform_audit_logs",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "subscription_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("price_monthly", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("active_status", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "outlet_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outlet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("trial", "active", "past_due", "cancelled", name="subscription_status"),
            nullable=False,
        ),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("outlet_id", name="uq_outlet_subscription_outlet"),
    )
    op.create_index(
        op.f("ix_outlet_subscriptions_outlet_id"),
        "outlet_subscriptions",
        ["outlet_id"],
        unique=False,
    )

    op.create_table(
        "platform_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outlet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invoice_number", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "sent", "paid", "overdue", name="platform_invoice_status"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["outlet_subscriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number"),
    )
    op.create_index(
        op.f("ix_platform_invoices_outlet_id"),
        "platform_invoices",
        ["outlet_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_platform_invoices_outlet_id"), table_name="platform_invoices")
    op.drop_table("platform_invoices")
    op.drop_index(op.f("ix_outlet_subscriptions_outlet_id"), table_name="outlet_subscriptions")
    op.drop_table("outlet_subscriptions")
    op.drop_table("subscription_plans")
    op.drop_index(op.f("ix_platform_audit_logs_created_at"), table_name="platform_audit_logs")
    op.drop_index(op.f("ix_platform_audit_logs_actor_id"), table_name="platform_audit_logs")
    op.drop_index(op.f("ix_platform_audit_logs_action"), table_name="platform_audit_logs")
    op.drop_table("platform_audit_logs")
    op.drop_column("platform_admins", "active_status")
    sa.Enum(name="subscription_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="platform_invoice_status").drop(op.get_bind(), checkfirst=True)
