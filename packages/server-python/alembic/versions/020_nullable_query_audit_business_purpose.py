"""020 allow business_purpose to be NULL in query_audit_log.

BUG-015: the front-end ``QueryPanel`` previously exposed TWO redundant
inputs (``company_name`` and ``business_purpose``) that forced users
to retype context the system already records elsewhere. Removing the
``business_purpose`` form requirement means audit rows may be written
with ``business_purpose=NULL`` when the user opted out of typing it.

This migration flips ``metaedu.query_audit_log.business_purpose`` from
NOT NULL → NULL-able. The application-layer guards (in
:class:`RBACService.log_query` and :class:`QueryService`) are also
relaxed to accept ``None`` and forward it to the DB unchanged. The DB
itself becomes the final tolerance gate — historical NOT NULL rows are
untouched, only new rows can be nullable.

Revision ID: 020_audit_bp_nullable
Revises: 019_add_dataset_entity_type
Create Date: 2026-07-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "020_audit_bp_nullable"
down_revision: str | None = "019_add_dataset_entity_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "query_audit_log",
        "business_purpose",
        existing_type=sa.Text(),
        nullable=True,
        schema="metaedu",
    )


def downgrade() -> None:
    op.alter_column(
        "query_audit_log",
        "business_purpose",
        existing_type=sa.Text(),
        nullable=False,
        schema="metaedu",
    )
