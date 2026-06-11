"""add zhparser extension + chinese_zh text search config + content_tsvector dict swap

TD-047 切片 2 — 中文分词 ILIKE 限制治理。

本迁移做 4 件事：
1. **合并 multi-head**：009_ai_applications (REQ-011) + 009_kg_source_resolution (REQ-010)
   两个并行 head 在此合并；这是 main 上 pre-existing 多头状态的收口。
2. **创建 zhparser 扩展**（依赖 metaedu/postgres-zhparser:pg16 镜像，TD-047 切片 1）。
3. **创建 chinese_zh 文本搜索配置**：以 zhparser 为 PARSER，对 n/v/a/i/e/l token 走 simple 字典。
4. **重建 document_chunks.content_tsvector 列字典**：从 'simple' 切到 'chinese_zh'，
   触发全表 to_tsvector 重算（dev 库 < 50k chunks 估 < 5s；生产大表需评估锁等待）。

回滚：
- ALTER TABLE 把 content_tsvector 回 'simple' 字典
- DROP TEXT SEARCH CONFIGURATION chinese_zh
- **不**主动 DROP EXTENSION zhparser（cascading 风险，留给运维按需）
- **不**主动反向 unmerge two 9-heads（alembic 不支持自动 unmerge；这是单向收口）

**已知 downgrade 限制（mergepoint）**：
- `alembic downgrade -1` 在 mergepoint 上报 `Ambiguous walk`（alembic 不知道回哪个 9-head）。
- `alembic downgrade <fromrev>:<torev>` API 不支持 range revision（CommandError）。
- 生产 / 运维 downgrade 路径：用 `alembic downgrade 010_zhparser_chinese:009_kg_source_resolution --sql`
  生成回滚 SQL，手工执行（包括 `UPDATE alembic_version SET version_num='009_...'`）。
- 验证方式：spec AC-2 已通过 `--sql` 输出验证回滚 SQL 正确生成。

依赖：metaedu/postgres-zhparser:pg16 镜像必须先就位（TD-047 切片 1），否则
CREATE EXTENSION zhparser 会报 UndefinedObjectError 阻塞 alembic upgrade head。

Revision ID: 010_zhparser_chinese
Revises: 009_ai_applications, 009_kg_source_resolution
Create Date: 2026-06-11

"""
from typing import Sequence, Union

from alembic import op


revision: str = "010_zhparser_chinese"
down_revision: Union[str, Sequence[str], None] = (
    "009_ai_applications",
    "009_kg_source_resolution",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. zhparser 扩展
    op.execute("CREATE EXTENSION IF NOT EXISTS zhparser;")

    # 2. chinese_zh 文本搜索配置
    #    CREATE TEXT SEARCH CONFIGURATION 不支持 IF NOT EXISTS；
    #    先 SELECT 判断，存在则跳过（幂等）。
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_ts_config WHERE cfgname = 'chinese_zh'
            ) THEN
                EXECUTE 'CREATE TEXT SEARCH CONFIGURATION chinese_zh (PARSER = zhparser)';
                EXECUTE 'ALTER TEXT SEARCH CONFIGURATION chinese_zh '
                     || 'ADD MAPPING FOR n,v,a,i,e,l WITH simple';
            END IF;
        END $$;
        """
    )

    # 3. document_chunks.content_tsvector 列字典从 'simple' 切到 'chinese_zh'
    #    ALTER TABLE ... USING 触发全表重算。
    op.execute(
        "ALTER TABLE metaedu.document_chunks "
        "ALTER COLUMN content_tsvector TYPE tsvector "
        "USING to_tsvector('chinese_zh', content);"
    )


def downgrade() -> None:
    # 1. content_tsvector 回 'simple' 字典
    op.execute(
        "ALTER TABLE metaedu.document_chunks "
        "ALTER COLUMN content_tsvector TYPE tsvector "
        "USING to_tsvector('simple', content);"
    )

    # 2. 删 chinese_zh 文本搜索配置
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS chinese_zh;")

    # 3. 不主动 DROP EXTENSION zhparser
    #    扩展可能被其它对象引用，DROP 会 cascading；运维按需手动 DROP EXTENSION zhparser CASCADE。
    #
    # 4. 不主动 unmerge 两个 9-head（alembic 不支持自动 unmerge）。
