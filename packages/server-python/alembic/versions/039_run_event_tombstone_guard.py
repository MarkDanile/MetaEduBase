"""S3-D: agent_run_events append-only 守卫放行受控 purge tombstone。

Revision ID: 039_run_event_tombstone_guard
Revises: 038_execution_actor_tombstone
Create Date: 2026-08-03

R1-S3-D round-1 复审 P1-2：migration 030 的
``guard_agent_run_event_append_only()`` 无条件 RAISE，而 Spec §7.2 要求 R1 purge
把 ``RunEvent.payload_inline`` 墓碑化。首次实现绕过守卫的做法是在运行时事务内
``DROP TRIGGER -> UPDATE -> CREATE TRIGGER``，有两个缺陷：

1. ``DROP TRIGGER`` 需表级 ``ACCESS EXCLUSIVE``，而同事务早前的 event scan 已持
   ``ACCESS SHARE``；两个并发 eraser（不同 Conversation）互相等待锁升级 -> 死锁。
2. 普通运行角色未必有该表 DDL 权限，部署即失败。

故「不新增 migration」与「RunEvent payload tombstone」不可兼得。本迁移把守卫从
无条件 RAISE 改为**行级白名单**：仅放行受控 purge tombstone 形态，其余 UPDATE 与
全部 DELETE 仍 RAISE，保持 E1 append-only 语义与 §1「seq 不可变」不变量。

**放行谓词**（三者同时成立）：

- ``OLD.payload_inline IS NOT NULL AND NEW.payload_inline IS NULL``（正文真的被清）
- ``NEW.payload_state = 'redacted'``（投影受控 tombstone 状态）
- **其余所有列不变**：用 ``to_jsonb(OLD) - 'payload_inline' - 'payload_state'``
  与 NEW 的同款投影相等判定。相较枚举 26 列，该写法对未来新增列**默认收紧**
  （新列若被改动会自动落入「其余列变化」而被拒），不会随 schema 演进悄悄开洞。

expand-only，不改表结构。

**downgrade 边界**：还原 030 的无条件 RAISE 版本。守卫是 ``BEFORE UPDATE OR
DELETE`` 触发器，只作用于**新写**，已产生的 tombstone 行不受影响，故 downgrade
**无条件可逆**——与 038「已 redacted 行 fail closed」的不可逆边界不同，测试须明确
区分两者，不可套用 038 的断言。
"""

from collections.abc import Sequence

from alembic import op

revision: str = "039_run_event_tombstone_guard"
down_revision: str | None = "038_execution_actor_tombstone"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 受控 purge tombstone 放行谓词。除 payload_inline/payload_state 外任一列变化
# （含 seq/payload_digest/payload_ref/provenance）都不满足，落到 RAISE 分支。
#
# ``TG_OP = 'UPDATE'`` 是**防御性冗余**（已由真实 PostgreSQL 变异验证确认为
# equivalent mutant）：DELETE 触发时 PL/pgSQL 的 ``NEW`` 是未赋值记录，
# ``NEW.payload_state = 'redacted'`` 求值为 NULL 而非 true，IF 判定为假即落到
# RAISE，故删除该子句 DELETE 仍被拒。保留它是为显式表达「只放行 UPDATE」的意图，
# 避免后续改写其余子句时无意开洞（与 S2-D/E round-6 对 timing-only 存活变异的
# 处理同规格：存活但有据可依，不据此删除防御）。
_GUARD_WITH_PURGE_TOMBSTONE = """
CREATE OR REPLACE FUNCTION metaedu.guard_agent_run_event_append_only()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE'
        AND OLD.payload_inline IS NOT NULL
        AND NEW.payload_inline IS NULL
        AND NEW.payload_state = 'redacted'
        AND (to_jsonb(OLD) - 'payload_inline' - 'payload_state')
            = (to_jsonb(NEW) - 'payload_inline' - 'payload_state')
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'agent_run_events is append-only in E1'
        USING ERRCODE = '55000';
END;
$$
"""

# migration 030 的原始无条件 RAISE 版本（downgrade 目标）。
_GUARD_UNCONDITIONAL = """
CREATE OR REPLACE FUNCTION metaedu.guard_agent_run_event_append_only()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'agent_run_events is append-only in E1'
        USING ERRCODE = '55000';
END;
$$
"""


def upgrade() -> None:
    # CREATE OR REPLACE 保留既有 trigger 绑定（触发器引用函数名，不需重建触发器，
    # 因此升级路径不做任何表级 DDL，无 ACCESS EXCLUSIVE 需求）。
    op.execute(_GUARD_WITH_PURGE_TOMBSTONE)


def downgrade() -> None:
    op.execute(_GUARD_UNCONDITIONAL)
