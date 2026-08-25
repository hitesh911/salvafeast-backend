"""qr studio designs, permissions, and plan modules

Revision ID: 025_qr_studio
Revises: 024_variant_availability
Create Date: 2026-08-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "025_qr_studio"
down_revision: Union[str, None] = "024_variant_availability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "outlet_qr_designs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outlet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("template_id", sa.String(length=32), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.UniqueConstraint("outlet_id", "kind", name="uq_outlet_qr_design_kind"),
    )
    op.create_index(
        op.f("ix_outlet_qr_designs_outlet_id"),
        "outlet_qr_designs",
        ["outlet_id"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            INSERT INTO permissions (id, key, description, module)
            SELECT gen_random_uuid(), 'qr_studio.view', 'View qr_studio', 'qr_studio'
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE key = 'qr_studio.view')
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO permissions (id, key, description, module)
            SELECT gen_random_uuid(), 'qr_studio.edit', 'Edit qr_studio', 'qr_studio'
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE key = 'qr_studio.edit')
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO role_permissions (id, role_id, permission_id)
            SELECT gen_random_uuid(), r.id, p.id
            FROM roles r
            JOIN permissions p ON p.key IN ('qr_studio.view', 'qr_studio.edit')
            WHERE r.name IN ('Owner', 'Manager')
              AND NOT EXISTS (
                SELECT 1 FROM role_permissions rp
                WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE subscription_plans
            SET features = jsonb_set(
              COALESCE(features, '{}'::jsonb),
              '{modules}',
              (
                SELECT COALESCE(jsonb_agg(to_jsonb(m)), '[]'::jsonb)
                FROM (
                  SELECT DISTINCT unnest(
                    COALESCE(
                      ARRAY(SELECT jsonb_array_elements_text(features->'modules')),
                      ARRAY[]::text[]
                    ) || ARRAY['qr_studio']
                  ) AS m
                ) mods
              ),
              true
            )
            WHERE slug IN ('growth', 'enterprise')
              AND (
                features IS NULL
                OR features->'modules' IS NULL
                OR NOT (features->'modules' ? 'qr_studio')
              )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE permission_id IN (
              SELECT id FROM permissions WHERE key IN ('qr_studio.view', 'qr_studio.edit')
            )
            """
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM permissions WHERE key IN ('qr_studio.view', 'qr_studio.edit')"
        )
    )
    op.drop_index(op.f("ix_outlet_qr_designs_outlet_id"), table_name="outlet_qr_designs")
    op.drop_table("outlet_qr_designs")
