"""unified users model

Revision ID: 019_unified_users
Revises: 018_outlet_consumer_profile
Create Date: 2026-08-23

"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "019_unified_users"
down_revision: Union[str, None] = "018_outlet_consumer_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("push_token", sa.String(length=512), nullable=True),
        sa.Column("push_token_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    op.create_table(
        "outlet_memberships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("outlet_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", UUID(as_uuid=True), nullable=False),
        sa.Column("active_status", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("user_id", "outlet_id", name="uq_outlet_membership_user_outlet"),
    )
    op.create_index("ix_outlet_memberships_user_id", "outlet_memberships", ["user_id"])
    op.create_index("ix_outlet_memberships_outlet_id", "outlet_memberships", ["outlet_id"])

    conn = op.get_bind()
    phone_to_user: dict[str, uuid.UUID] = {}
    outlet_user_to_user: dict[uuid.UUID, uuid.UUID] = {}
    customer_to_user: dict[uuid.UUID, uuid.UUID] = {}

    outlet_users = conn.execute(
        sa.text(
            "SELECT id, outlet_id, name, phone, email, role_id, active_status, "
            "last_login, created_at FROM outlet_users ORDER BY created_at ASC"
        )
    ).mappings().all()

    for row in outlet_users:
        phone = row["phone"]
        if phone in phone_to_user:
            user_id = phone_to_user[phone]
        else:
            user_id = uuid.uuid4()
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, phone, name, email, last_login, created_at) "
                    "VALUES (:id, :phone, :name, :email, :last_login, :created_at)"
                ),
                {
                    "id": user_id,
                    "phone": phone,
                    "name": row["name"],
                    "email": row["email"],
                    "last_login": row["last_login"],
                    "created_at": row["created_at"],
                },
            )
            phone_to_user[phone] = user_id

        membership_id = uuid.uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO outlet_memberships "
                "(id, user_id, outlet_id, role_id, active_status, created_at) "
                "VALUES (:id, :user_id, :outlet_id, :role_id, :active_status, :created_at)"
            ),
            {
                "id": membership_id,
                "user_id": user_id,
                "outlet_id": row["outlet_id"],
                "role_id": row["role_id"],
                "active_status": row["active_status"],
                "created_at": row["created_at"],
            },
        )
        outlet_user_to_user[row["id"]] = user_id

    customers = conn.execute(
        sa.text(
            "SELECT id, phone, name, push_token, push_token_updated_at, created_at "
            "FROM customers ORDER BY created_at ASC"
        )
    ).mappings().all()

    for row in customers:
        phone = row["phone"]
        if phone in phone_to_user:
            user_id = phone_to_user[phone]
            conn.execute(
                sa.text(
                    "UPDATE users SET "
                    "name = COALESCE(users.name, :name), "
                    "push_token = COALESCE(users.push_token, :push_token), "
                    "push_token_updated_at = COALESCE(users.push_token_updated_at, :push_token_updated_at), "
                    "created_at = LEAST(users.created_at, :created_at) "
                    "WHERE users.id = :user_id"
                ),
                {
                    "user_id": user_id,
                    "name": row["name"],
                    "push_token": row["push_token"],
                    "push_token_updated_at": row["push_token_updated_at"],
                    "created_at": row["created_at"],
                },
            )
        else:
            user_id = uuid.uuid4()
            conn.execute(
                sa.text(
                    "INSERT INTO users "
                    "(id, phone, name, push_token, push_token_updated_at, created_at) "
                    "VALUES (:id, :phone, :name, :push_token, :push_token_updated_at, :created_at)"
                ),
                {
                    "id": user_id,
                    "phone": phone,
                    "name": row["name"],
                    "push_token": row["push_token"],
                    "push_token_updated_at": row["push_token_updated_at"],
                    "created_at": row["created_at"],
                },
            )
            phone_to_user[phone] = user_id
        customer_to_user[row["id"]] = user_id

    op.add_column("orders", sa.Column("user_id", UUID(as_uuid=True), nullable=True))
    for customer_id, user_id in customer_to_user.items():
        conn.execute(
            sa.text("UPDATE orders SET user_id = :user_id WHERE customer_id = :customer_id"),
            {"user_id": user_id, "customer_id": customer_id},
        )
    op.drop_constraint("orders_customer_id_fkey", "orders", type_="foreignkey")
    op.drop_column("orders", "customer_id")
    op.create_foreign_key("orders_user_id_fkey", "orders", "users", ["user_id"], ["id"])

    op.add_column("outlet_customers", sa.Column("user_id", UUID(as_uuid=True), nullable=True))
    for customer_id, user_id in customer_to_user.items():
        conn.execute(
            sa.text(
                "UPDATE outlet_customers SET user_id = :user_id WHERE customer_id = :customer_id"
            ),
            {"user_id": user_id, "customer_id": customer_id},
        )
    op.drop_constraint("uq_outlet_customer", "outlet_customers", type_="unique")
    op.drop_constraint("outlet_customers_customer_id_fkey", "outlet_customers", type_="foreignkey")
    op.drop_column("outlet_customers", "customer_id")
    op.alter_column("outlet_customers", "user_id", nullable=False)
    op.create_foreign_key(
        "outlet_customers_user_id_fkey", "outlet_customers", "users", ["user_id"], ["id"]
    )
    op.create_unique_constraint(
        "uq_outlet_customer", "outlet_customers", ["outlet_id", "user_id"]
    )

    op.add_column("offer_redemptions", sa.Column("user_id", UUID(as_uuid=True), nullable=True))
    for customer_id, user_id in customer_to_user.items():
        conn.execute(
            sa.text(
                "UPDATE offer_redemptions SET user_id = :user_id WHERE customer_id = :customer_id"
            ),
            {"user_id": user_id, "customer_id": customer_id},
        )
    op.drop_constraint("offer_redemptions_customer_id_fkey", "offer_redemptions", type_="foreignkey")
    op.drop_column("offer_redemptions", "customer_id")
    op.create_foreign_key(
        "offer_redemptions_user_id_fkey", "offer_redemptions", "users", ["user_id"], ["id"]
    )

    for outlet_user_id, user_id in outlet_user_to_user.items():
        conn.execute(
            sa.text(
                "UPDATE order_status_logs SET changed_by = :user_id WHERE changed_by = :outlet_user_id"
            ),
            {"user_id": user_id, "outlet_user_id": outlet_user_id},
        )
        conn.execute(
            sa.text(
                "UPDATE expenses SET created_by = :user_id WHERE created_by = :outlet_user_id"
            ),
            {"user_id": user_id, "outlet_user_id": outlet_user_id},
        )
        conn.execute(
            sa.text(
                "UPDATE invoices SET created_by = :user_id WHERE created_by = :outlet_user_id"
            ),
            {"user_id": user_id, "outlet_user_id": outlet_user_id},
        )

    op.drop_constraint("order_status_logs_changed_by_fkey", "order_status_logs", type_="foreignkey")
    op.create_foreign_key(
        "order_status_logs_changed_by_fkey", "order_status_logs", "users", ["changed_by"], ["id"]
    )
    op.drop_constraint("expenses_created_by_fkey", "expenses", type_="foreignkey")
    op.create_foreign_key(
        "expenses_created_by_fkey", "expenses", "users", ["created_by"], ["id"]
    )
    op.drop_constraint("invoices_created_by_fkey", "invoices", type_="foreignkey")
    op.create_foreign_key(
        "invoices_created_by_fkey", "invoices", "users", ["created_by"], ["id"]
    )

    op.drop_table("outlet_users")
    op.drop_table("customers")


def downgrade() -> None:
    raise NotImplementedError("Unified users migration cannot be downgraded")
