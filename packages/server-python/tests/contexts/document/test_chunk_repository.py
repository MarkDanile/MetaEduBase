"""`ChunkRepository.update_tsvector` 单元测试 — TD-047 切片 5.

验证 SQL 已切到 ``to_tsvector('chinese_zh', content)``。不依赖真 PG（mock SQL
执行 + 参数捕获），在没有 zhparser 镜像的沙箱 / CI 上也能跑。

真 PG 中文 fixture 端到端测试（验证中文分词序列）依赖 zhparser 扩展，由 dev
库 backfill 真跑（TD-047 切片 4 + 6）承担，结果记录在 PR 描述。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.contexts.document.infrastructure.chunk_repository import ChunkRepository


async def test_update_tsvector_uses_chinese_zh_dict() -> None:
    """TD-047 切片 3: SQL SET content_tsvector = to_tsvector('chinese_zh', content)。"""

    captured_sql: list[str] = []
    session = MagicMock()

    async def execute(stmt, params=None):
        captured_sql.append(str(stmt))
        return MagicMock()

    session.execute = AsyncMock(side_effect=execute)
    repo = ChunkRepository(session)
    await repo.update_tsvector(uuid.uuid4())

    assert len(captured_sql) == 1
    sql = captured_sql[0]
    assert "to_tsvector('chinese_zh', content)" in sql
    assert "to_tsvector('simple'" not in sql  # 旧字典已被替换


async def test_update_tsvector_binds_chunk_id() -> None:
    """TD-047 切片 3: bind param 用 :cid, 不拼字符串。"""

    captured_params: list[dict] = []
    session = MagicMock()

    async def execute(stmt, params=None):
        captured_params.append(params or {})
        return MagicMock()

    session.execute = AsyncMock(side_effect=execute)
    repo = ChunkRepository(session)
    chunk_id = uuid.uuid4()
    await repo.update_tsvector(chunk_id)

    assert len(captured_params) == 1
    assert captured_params[0]["cid"] == chunk_id


async def test_update_tsvector_does_not_use_ilike() -> None:
    """TD-047 切片 3: SQL 不应再含 ILIKE (旧 backfill_node_source 字节级匹配遗留)。"""

    captured_sql: list[str] = []
    session = MagicMock()

    async def execute(stmt, params=None):
        captured_sql.append(str(stmt))
        return MagicMock()

    session.execute = AsyncMock(side_effect=execute)
    repo = ChunkRepository(session)
    await repo.update_tsvector(uuid.uuid4())

    sql = captured_sql[0]
    assert "ILIKE" not in sql
