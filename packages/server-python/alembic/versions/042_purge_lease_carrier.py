"""R1-S5 SCH-A: agent_conversation_purges lease carrier——nullable 租约截止列 + partial index。

Revision ID: 042_purge_lease_carrier
Revises: 041_run_event_ref_tombstone
Create Date: 2026-08-17

Plan §R1-S5-D-A S5-SCH-7（契约冻结，评分 90 基线 `b15d766b`）：
- ``lease_expires_at TIMESTAMPTZ NULL``——scheduler 唯一写者的租约载体；
  ``NULL`` = 未认领（初始/释放态），既有行天然合法。**零 backfill**（Scheduler
  尚未启用，既有行全部视为未认领，不伪造历史租约）。
- **不新增 CHECK**——任何 state 相关 CHECK（如「终态 ⇒ NULL」）会误杀
  「coordinator 终态写 → scheduler 终态观察 release」之间的合法非 NULL 窗口；
  纯 epoch 不变量 `lease_expires_at IS NOT NULL ⇒ lease_epoch >= 1` 以
  SCH-16 反例兜底，保持 042 最小列形态。
- **partial index** ``ix_agent_purge_lease_active``：谓词
  ``lease_expires_at IS NOT NULL AND state NOT IN ('completed','cancelled')``，
  服务 tenant 并发上限计数（S5-SCH-8：只统计非终态且未到期的在租 operation）。
  042 落地时无并发写者（erase 入口不可达、scheduler 无生产调用方），普通
  ``CREATE INDEX`` 可接受、``CONCURRENTLY`` 非必需；既有行全 NULL 仍需一次性
  全表扫描，超大表迁移时长由 SCH-A 实现 PR 评估。

expand-only；downgrade 先 DROP INDEX 后 DROP COLUMN（无 reader 依赖——042 先于
任何 scheduler 代码合入），行数据不受影响。

**revision id 长度**：``042_purge_lease_carrier``（22 字符）≤ alembic 默认
``varchar(32)`` 版本表列宽。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "042_purge_lease_carrier"
down_revision: str | None = "041_run_event_ref_tombstone"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "metaedu"
_TABLE = "agent_conversation_purges"
_INDEX = "ix_agent_purge_lease_active"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        _INDEX,
        _TABLE,
        ["tenant_id", "lease_expires_at"],
        schema=_SCHEMA,
        postgresql_where=sa.text(
            "lease_expires_at IS NOT NULL "
            "AND state NOT IN ('completed', 'cancelled')"
        ),
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE, schema=_SCHEMA)
    op.drop_column(_TABLE, "lease_expires_at", schema=_SCHEMA)
