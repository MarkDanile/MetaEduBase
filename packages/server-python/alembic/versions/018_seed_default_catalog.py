"""018 seed default education catalog + backfill catalog_id.

REQ-054 Task 1: For each tenant, creates a default ``education`` catalog,
backfills ``datasets.catalog_id`` and ``semantic_models.catalog_id`` to point
at it, then changes both columns to NOT NULL. ``knowledge_nodes`` and
``query_audit_log`` remain nullable (V1 — catalog is a soft tag on those
tables).

Revision ID: 018_seed_default_catalog
Revises: 017_add_catalog_id_fk
Create Date: 2026-07-07
"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "018_seed_default_catalog"
down_revision: str | None = "017_add_catalog_id_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keep in sync with app/shared/infrastructure/seed.py
DEFAULT_ADMIN_ID = "00000000-0000-0000-0000-000000000002"


def upgrade() -> None:
    # 1. Create default "education" catalog for every tenant that doesn't
    #    already have one.
    op.execute(
        f"""
        INSERT INTO metaedu.data_catalogs
            (tenant_id, code, name, description, entity_types,
             default_business_purpose, is_active, created_by)
        SELECT t.id, 'education', '中高职教育数据库',
               '默认教育主题域数据库（自动迁移自 REQ-052 扁平数据集）',
               '["customer","bill","contract"]'::jsonb,
               '教育数据分析', true, '{DEFAULT_ADMIN_ID}'::uuid
        FROM metaedu.tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM metaedu.data_catalogs dc
            WHERE dc.tenant_id = t.id AND dc.code = 'education'
        )
        """
    )

    # 2. Backfill datasets.catalog_id (match by tenant → education catalog)
    op.execute(
        """
        UPDATE metaedu.datasets d
        SET catalog_id = dc.id
        FROM metaedu.data_catalogs dc
        WHERE d.tenant_id = dc.tenant_id
          AND dc.code = 'education'
          AND d.catalog_id IS NULL
        """
    )

    # 3. Backfill semantic_models.catalog_id
    op.execute(
        """
        UPDATE metaedu.semantic_models sm
        SET catalog_id = dc.id
        FROM metaedu.data_catalogs dc
        WHERE sm.tenant_id = dc.tenant_id
          AND dc.code = 'education'
          AND sm.catalog_id IS NULL
        """
    )

    # 4. datasets.catalog_id → NOT NULL (safe after backfill)
    op.alter_column(
        "datasets",
        "catalog_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
        schema="metaedu",
    )

    # 5. semantic_models.catalog_id → NOT NULL
    op.alter_column(
        "semantic_models",
        "catalog_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
        schema="metaedu",
    )


def downgrade() -> None:
    op.alter_column(
        "semantic_models",
        "catalog_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
        schema="metaedu",
    )
    op.alter_column(
        "datasets",
        "catalog_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
        schema="metaedu",
    )
    op.execute("UPDATE metaedu.datasets SET catalog_id = NULL")
    op.execute("UPDATE metaedu.semantic_models SET catalog_id = NULL")
    op.execute("DELETE FROM metaedu.data_catalogs WHERE code = 'education'")
