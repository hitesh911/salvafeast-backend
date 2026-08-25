"""content feed tables and outlet coordinates

Revision ID: 021_content_feed
Revises: 020_refresh_tokens
Create Date: 2026-08-23

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "021_content_feed"
down_revision: Union[str, None] = "020_refresh_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("outlets", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("outlets", sa.Column("longitude", sa.Float(), nullable=True))

    op.create_table(
        "content_posts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("outlet_id", UUID(as_uuid=True), nullable=False),
        sa.Column("menu_item_id", UUID(as_uuid=True), nullable=True),
        sa.Column("embed_url", sa.String(length=512), nullable=False),
        sa.Column("embed_platform", sa.String(length=16), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"]),
        sa.ForeignKeyConstraint(["menu_item_id"], ["menu_items.id"]),
    )
    op.create_index("ix_content_posts_outlet_id", "content_posts", ["outlet_id"])
    op.create_index("ix_content_posts_created_at", "content_posts", ["created_at"])
    op.create_index("ix_content_posts_is_hidden", "content_posts", ["is_hidden"])
    op.create_index("ix_content_posts_report_count", "content_posts", ["report_count"])

    op.create_table(
        "content_post_likes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("content_post_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["content_post_id"], ["content_posts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "content_post_id", "user_id", name="uq_content_post_like_user"
        ),
    )
    op.create_index(
        "ix_content_post_likes_content_post_id",
        "content_post_likes",
        ["content_post_id"],
    )
    op.create_index("ix_content_post_likes_user_id", "content_post_likes", ["user_id"])

    op.create_table(
        "content_post_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("content_post_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reported_by_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["content_post_id"], ["content_posts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["reported_by_user_id"], ["users.id"]),
    )
    op.create_index(
        "ix_content_post_reports_content_post_id",
        "content_post_reports",
        ["content_post_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_post_reports_content_post_id", table_name="content_post_reports")
    op.drop_table("content_post_reports")
    op.drop_index("ix_content_post_likes_user_id", table_name="content_post_likes")
    op.drop_index("ix_content_post_likes_content_post_id", table_name="content_post_likes")
    op.drop_table("content_post_likes")
    op.drop_index("ix_content_posts_report_count", table_name="content_posts")
    op.drop_index("ix_content_posts_is_hidden", table_name="content_posts")
    op.drop_index("ix_content_posts_created_at", table_name="content_posts")
    op.drop_index("ix_content_posts_outlet_id", table_name="content_posts")
    op.drop_table("content_posts")
    op.drop_column("outlets", "longitude")
    op.drop_column("outlets", "latitude")
