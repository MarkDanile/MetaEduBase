"""TD-089：清理 ``agent_erasure_fences`` 冗余/无效索引（PK 蕴含的 UK 死声明 + PK 前缀 ix）。

背景与归因（technical-debt.md#td-089）：``ErasureFenceModel`` 曾声明
``uq_agent_erasure_fence_owner``（与 PK ``(tenant_id, conversation_id, owner_key)``
同三列）。经离线 ``--sql`` + 真实建库（test_db_setup 与裸 ``alembic upgrade head``）
+ 纯 PostgreSQL 回滚事务复现证实：**PostgreSQL 自身**对「UK 列 ⊆ PK 列」去重（只建
PK），故该 UK 是从不创建的死声明，并非第二棵冗余 btree。``ix_agent_erasure_fence_conversation``
（PK 前缀 ``(tenant_id, conversation_id)``）才是唯一实际存在、真实被创建的冗余 btree
——PK btree 已可服务 conversation 前缀查询，``_backfill_conversation`` 的
``ON CONFLICT DO NOTHING`` 仲裁也用 PK。

因清理发生在 PR #506（``034``）合并**之后**，``034`` 已冻结，必须新增 ``035``
迁移（不得原地改已合并迁移）：

- 删 ``ix_agent_erasure_fence_conversation`` 冗余 btree（真实存在，真实 DROP）。
- 幂等 ``DROP CONSTRAINT IF EXISTS uq_agent_erasure_fence_owner``：该 UK 从不创建，
  此 drop 仅作环境兜底（防御某个被手工补建过的库），正常情况下为空操作。

本模块独立于其他 erasure schema 测试并在其之后运行（含真实迁移往返，避免影响同
进程其他 DB 依赖测试）。
"""

from __future__ import annotations

import asyncio
import warnings
from pathlib import Path
from typing import cast

import asyncpg
from alembic.config import Config
from sqlalchemy import Table

from alembic import command
from app.config import settings
from app.contexts.agent_workspace.infrastructure import models as workspace_models
from tests.conftest import TEST_DB_URL

SERVER_ROOT = Path(__file__).resolve().parents[2]
TABLE = "agent_erasure_fences"
DEAD_UK = "uq_agent_erasure_fence_owner"
REDUNDANT_IX = "ix_agent_erasure_fence_conversation"


def _db_url() -> str:
    return TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://", 1)


def _sqlalchemy_url() -> str:
    return _db_url().replace("postgresql://", "postgresql+asyncpg://", 1)


def _run_alembic(direction: str, revision: str) -> None:
    original_url = settings.database_url
    settings.database_url = _sqlalchemy_url()
    try:
        config = Config(str(SERVER_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(SERVER_ROOT / "alembic"))
        fn = command.upgrade if direction == "upgrade" else command.downgrade
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            fn(config, revision)
    finally:
        settings.database_url = original_url


# ---------------------------------------------------------------------------
# 源级守卫：models metadata 与 035 迁移文件本身的声明（不依赖 DB）。
# ---------------------------------------------------------------------------


def test_models_fence_has_no_dead_uk_or_redundant_ix() -> None:
    """models metadata 不得再声明死 UK 或冗余前缀 ix。"""
    table = cast(Table, workspace_models.ErasureFenceModel.__table__)
    # 死 UK 不在 UniqueConstraint 集合。
    assert all(c.name != DEAD_UK for c in table.constraints)
    # 冗余 ix 不在 Index 集合（FK 索引 PostgreSQL 不自动建，但 034 也未声明；
    # 此处只锁 PK 前缀冗余 ix 不回归）。
    assert all(ix.name != REDUNDANT_IX for ix in table.indexes)


def test_models_fence_pk_covers_owner_lookup() -> None:
    """PK 仍为 (tenant_id, conversation_id, owner_key)——owner 查找仍由 PK 服务。"""
    table = cast(Table, workspace_models.ErasureFenceModel.__table__)
    assert [c.name for c in table.primary_key.columns] == [
        "tenant_id",
        "conversation_id",
        "owner_key",
    ]


def test_035_migration_drops_redundant_ix_and_dead_uk_idempotently() -> None:
    """035 迁移文件：down_revision 指向 034，upgrade 删冗余 ix 并幂等删死 UK。"""
    path = SERVER_ROOT / "alembic" / "versions" / "035_erasure_fence_ix_cleanup.py"
    source = path.read_text(encoding="utf-8")
    assert 'revision: str = "035_erasure_fence_ix_cleanup"' in source
    assert 'down_revision: str | None = "034_agent_erasure_foundation"' in source
    assert REDUNDANT_IX in source
    assert DEAD_UK in source
    assert "IF EXISTS" in source


# ---------------------------------------------------------------------------
# 库级守卫：现库（034 head）中死 UK 不存在、冗余 ix 存在（035 待清理）。
# 这些是 TD-089「UK 从不创建、ix 真实创建」结论的库级证据。
# ---------------------------------------------------------------------------


async def _fence_constraint_names() -> set[str]:
    connection = await asyncpg.connect(_db_url())
    try:
        rows = await connection.fetch(
            "SELECT con.conname FROM pg_constraint con "
            "JOIN pg_class rel ON rel.oid = con.conrelid "
            "JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace "
            "WHERE nsp.nspname = 'metaedu' AND rel.relname = $1",
            TABLE,
        )
        return {row["conname"] for row in rows}
    finally:
        await connection.close()


async def _fence_index_names() -> set[str]:
    connection = await asyncpg.connect(_db_url())
    try:
        rows = await connection.fetch(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'metaedu' AND tablename = $1",
            TABLE,
        )
        return {row["indexname"] for row in rows}
    finally:
        await connection.close()


def test_live_db_dead_uk_never_created() -> None:
    """现库证实：死 UK 从不被 PostgreSQL 创建（UK ⊆ PK 去重）。"""
    names = asyncio.run(_fence_constraint_names())
    assert DEAD_UK not in names


def test_live_db_pk_present_and_owner_prefix_lookup_served() -> None:
    """现库（035 head）：PK 索引存在且覆盖 (tenant_id, conversation_id, owner_key)。

    owner 查找与 conversation 前缀查询由 PK btree 服务（PK 前两列即前缀），删除冗余
    前缀 ix 不损失该能力；PostgreSQL 不为 FK 自动建索引，故库中除 PK 外无其他索引。
    """
    names = asyncio.run(_fence_index_names())
    assert "pk_agent_erasure_fences" in names
    # 终态：冗余前缀 ix 已删除，fence 表只剩 PK btree。
    assert REDUNDANT_IX not in names
    assert names == {"pk_agent_erasure_fences"}


# ---------------------------------------------------------------------------
# 035 迁移往返：upgrade 后冗余 ix 与死 UK 均不存在，PK 保留；downgrade 还原 ix。
# ---------------------------------------------------------------------------


def test_035_upgrade_removes_redundant_ix_and_dead_uk() -> None:
    _run_alembic("upgrade", "head")
    indexes = asyncio.run(_fence_index_names())
    constraints = asyncio.run(_fence_constraint_names())
    assert REDUNDANT_IX not in indexes
    assert DEAD_UK not in constraints
    assert "pk_agent_erasure_fences" in indexes


def test_035_downgrade_upgrade_round_trip() -> None:
    _run_alembic("upgrade", "head")
    try:
        _run_alembic("downgrade", "034_agent_erasure_foundation")
        # downgrade 还原冗余前缀 ix。
        assert REDUNDANT_IX in asyncio.run(_fence_index_names())
    finally:
        _run_alembic("upgrade", "head")
    indexes = asyncio.run(_fence_index_names())
    assert REDUNDANT_IX not in indexes
    assert "pk_agent_erasure_fences" in indexes


def test_models_metadata_matches_live_db_fence_objects() -> None:
    """metadata 与现库（035 head）一致：声明的约束 ⊆ 库中实际对象，无漂移。"""
    _run_alembic("upgrade", "head")
    table = cast(Table, workspace_models.ErasureFenceModel.__table__)
    declared = {c.name for c in table.constraints if c.name is not None}
    declared |= {ix.name for ix in table.indexes if ix.name is not None}
    live = asyncio.run(_fence_constraint_names()) | asyncio.run(_fence_index_names())
    # 声明对象全部真实存在（死 UK / 冗余 ix 已不在声明，也不在库）。
    assert declared <= live
    assert DEAD_UK not in declared
    assert REDUNDANT_IX not in declared
