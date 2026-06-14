"""add files.template_id column

BUG-005 fix: BUG-005-files-doc-type-not-backfilled 收口。

`extract_template` 任务完成后，模板选择结果（L1/L2/L3 命中）有
`template_obj.id` 和 `selection.matched_type`，但 `files.doc_type` 一直 NULL
（dev 库 100% NULL），且 `files.template_id` 字段在 schema 中**完全不存在**。

本次迁移新增 `files.template_id`（uuid, nullable）+ 索引，回写逻辑由
`app.contexts.document.application.tasks.extract_template._update_files_doc_type`
helper 在 L207 UPDATE structured_data 同一事务内执行。

回滚：
- drop index
- drop column

Revision ID: 011_files_template_id
Revises: 010_zhparser_chinese
Create Date: 2026-06-14

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "011_files_template_id"
down_revision: str | None = "010_zhparser_chinese"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Template matched by extract_template; null when no match",
        ),
    )
    op.create_index(
        "ix_files_template_id",
        "files",
        ["template_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_files_template_id", table_name="files")
    op.drop_column("files", "template_id")
