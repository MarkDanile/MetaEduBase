"""TD-089 cleanup: drop redundant/dead erasure-fence index objects.

Revision ID: 035_erasure_fence_ix_cleanup
Revises: 034_agent_erasure_foundation
Create Date: 2026-07-28

`034` 为 `agent_erasure_fences` 声明了两类由 PK 蕴含、不带来独立价值的对象：

- `uq_agent_erasure_fence_owner`（UK，与 PK `(tenant_id, conversation_id, owner_key)`
  同三列）。PostgreSQL 对「UK 列 ⊆ PK 列」去重，**从不创建**该约束——它是死声明，
  并非一棵真实存在的冗余 btree（TD-089 复核，纯 PostgreSQL 回滚事务复现证实）。
- `ix_agent_erasure_fence_conversation`（PK 前缀 `(tenant_id, conversation_id)`）。
  这是唯一**真实被创建**的冗余 btree：PK btree 已可服务 conversation 前缀查询，
  `_backfill_conversation` 的 `ON CONFLICT DO NOTHING` 仲裁也用 PK。它只增加写放大。

本迁移只做索引/约束对象清理，不改任何列或数据，可安全在线执行：

- upgrade：真实 DROP 冗余 ix；并幂等 `DROP CONSTRAINT IF EXISTS` 死 UK（正常为空
  操作，仅防御某个被手工补建过的库）。`034` 的 `downgrade()` 已改为
  `DROP INDEX IF EXISTS`（幂等），故本迁移删除该 ix 不会导致 `034` 回滚报
  「index does not exist」。
- downgrade：仅还原冗余前缀 ix（死 UK 从不存在，无需也不应重建）。

PR #506（`034`）合并后 `034` 已冻结，故以新增 `035` 而非原地修订 `034` 处理。
"""

from collections.abc import Sequence

from alembic import op

revision: str = "035_erasure_fence_ix_cleanup"
down_revision: str | None = "034_agent_erasure_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "agent_erasure_fences"
_SCHEMA = "metaedu"
_REDUNDANT_IX = "ix_agent_erasure_fence_conversation"
_DEAD_UK = "uq_agent_erasure_fence_owner"


def upgrade() -> None:
    # 真实存在的冗余前缀 btree：PK 已可服务 conversation 前缀查询，DROP 只省写放大。
    op.drop_index(_REDUNDANT_IX, table_name=_TABLE, schema=_SCHEMA)
    # 死声明 UK：PostgreSQL 从不创建（UK ⊆ PK 去重）。幂等 drop 仅作环境兜底，
    # 防御某个被手工补建过的库；正常情况下为空操作。
    op.execute(
        f'ALTER TABLE "{_SCHEMA}"."{_TABLE}" '
        f"DROP CONSTRAINT IF EXISTS {_DEAD_UK}"
    )


def downgrade() -> None:
    # 仅还原冗余前缀 ix（死 UK 从不存在，无需也不应重建）。先幂等清理再重建：
    # 035 downgrade 恢复 ix 后若 034 downgrade 已删除它，重跑 035 downgrade 会撞上
    # 残留 ix，故 DROP INDEX IF EXISTS 兜底保证可重复执行。
    op.execute(
        f'DROP INDEX IF EXISTS "{_SCHEMA}"."{_REDUNDANT_IX}"'
    )
    op.create_index(
        _REDUNDANT_IX,
        _TABLE,
        ["tenant_id", "conversation_id"],
        schema=_SCHEMA,
    )
