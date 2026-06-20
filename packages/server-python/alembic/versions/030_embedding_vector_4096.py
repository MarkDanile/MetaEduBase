"""change embedding columns from text to vector(4096)

TD-069: dev DB `document_chunks.embedding` / `knowledge_nodes.embedding`
两列当前 text 类型，pgvector 扩展已装但 `<=>` cosine 操作符要求 vector 类型。
本迁移把两列改为 vector(4096)，USING expression 自动把现有 text 字符串
（如 "[-0.011,0.002,...]"）转成合法 vector；NULL 值也兼容。

Revision ID: 030_embedding_vector_4096
Revises: 011_files_template_id
Create Date: 2026-06-19

"""
from typing import Sequence, Union

from alembic import op

revision: str = "030_embedding_vector_4096"
down_revision: Union[str, None] = "011_files_template_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # document_chunks.embedding: 1062 行已有真实硅流 4096 维数据，USING 转换
    op.execute(
        "ALTER TABLE metaedu.document_chunks "
        "ALTER COLUMN embedding TYPE vector(4096) "
        "USING embedding::vector(4096)"
    )

    # knowledge_nodes.embedding: 599 行 100% NULL，USING 兼容 NULL
    op.execute(
        "ALTER TABLE metaedu.knowledge_nodes "
        "ALTER COLUMN embedding TYPE vector(4096) "
        "USING embedding::vector(4096)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE metaedu.document_chunks "
        "ALTER COLUMN embedding TYPE text "
        "USING embedding::text"
    )
    op.execute(
        "ALTER TABLE metaedu.knowledge_nodes "
        "ALTER COLUMN embedding TYPE text "
        "USING embedding::text"
    )
