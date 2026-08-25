"""refresh tokens table

Revision ID: 020_refresh_tokens
Revises: 019_unified_users
Create Date: 2026-08-23

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "020_refresh_tokens"
down_revision: Union[str, None] = "019_unified_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("session_kind", sa.String(length=50), nullable=False),
        sa.Column("subject_id", UUID(as_uuid=True), nullable=False),
        sa.Column("outlet_id", UUID(as_uuid=True), nullable=True),
        sa.Column("session_meta", JSONB, nullable=True),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", UUID(as_uuid=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"], ["refresh_tokens.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_refresh_tokens_session_kind", "refresh_tokens", ["session_kind"])
    op.create_index("ix_refresh_tokens_subject_id", "refresh_tokens", ["subject_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])
    op.create_index(
        "ix_refresh_tokens_subject_session",
        "refresh_tokens",
        ["subject_id", "session_kind"],
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_subject_session", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_subject_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_session_kind", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
