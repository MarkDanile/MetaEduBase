"""019 add entity_type column to datasets.

REQ-054 review fix (V1): entity_types shifts from a preset whitelist to a
dynamic discovery list. Each dataset now carries its own ``entity_type``
(free-text, set at upload time). The catalog's discovered entity types are
aggregated via ``SELECT DISTINCT entity_type FROM datasets`` rather than
being declared upfront.

Revision ID: 019_add_dataset_entity_type
Revises: 018_seed_default_catalog
Create Date: 2026-07-08
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "019_add_dataset_entity_type"
down_revision: str | None = "018_seed_default_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column("entity_type", sa.String(50), nullable=True),
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_column("datasets", "entity_type", schema="metaedu")
