"""R1-S6 S6-I1: agent_run_events append-only 守卫扩展——retention tombstone + 前缀删除白名单。

Revision ID: 043_run_event_retention_guard
Revises: 042_purge_lease_carrier
Create Date: 2026-08-19

Plan §R1-S6-10「migration 043 冻结需求」（P0-1 评审裁决；契约冻结经 PR #581
并入 main `01524667`）：append-only 守卫（039/041）白名单扩展——(a) UPDATE
tombstone 放行 ``NEW.payload_state IN ('redacted','expired','archived')``
（inline 清除分支；ref 分支保持 redacted-only，retention 禁清 ref）；(b) DELETE
仅限已 tombstone 行（``OLD.payload_state IN (redacted/expired/archived) AND
payload_inline IS NULL AND payload_ref IS NULL``）；其余 UPDATE/DELETE 维持
RAISE。expand-only、downgrade 可逆（还原 041 行为）。

**043 放行分支（四分支，全部 BEFORE UPDATE OR DELETE）**：

- **分支 1（039 原有，widened）**：inline purge/retention tombstone——
  ``OLD.payload_inline IS NOT NULL AND NEW.payload_inline IS NULL AND
  NEW.payload_state IN ('redacted','expired','archived')``，其余列不变。
  039/041 原要求 ``NEW.payload_state='redacted'``；S6 的 payload expiry 写
  ``payload_state='expired'``，erasure 仍写 ``'redacted'``，archived 为业务
  tombstone 状态——三者同为「payload_inline 已清 + 受控 tombstone 状态」。
- **分支 2（S6 新增）**：external 行**仅 state 变化** tombstone——
  ``OLD.payload_state='external' AND OLD.payload_inline IS NULL AND
  NEW.payload_inline IS NULL AND NEW.payload_state IN ('redacted','expired',
  'archived')``，其余列（**含 payload_ref**）不变。retention 的 external
  payload expiry 只转 state、**不得清 payload_ref**（ref 清除唯一者 =
  external.payload.v1，S4-E-B2）。external 行必有 payload_ref（CHECK
  ck_agent_run_event_payload），state 变化即满足 retention 到期写。
- **分支 3（041 原有，保持 redacted-only）**：external ref 严格 tombstone——
  ref 被清 + 两端均无 inline + 转 ``redacted``。retention 禁清 ref，故 S6 不
  宽化本分支；ref 清除仍仅 external participant（S4-E-B2）。
- **分支 4（S6 新增 DELETE）**：仅放行已 tombstone 行的 DELETE——
  ``OLD.payload_state IN ('redacted','expired','archived') AND
  OLD.payload_inline IS NULL AND OLD.payload_ref IS NULL``（envelope prune 只删
  连续前缀里已 tombstone 且 payload 全清的行；ref-bearing 行 payload_ref 未清
  不满足 → 仍 RAISE）。guard 不得对 live 行开 DELETE 洞。

**downgrade 边界**：还原 041 白名单（分支 1 恢复 ``redacted``-only + 分支 3）。
守卫是 ``BEFORE UPDATE OR DELETE`` 触发器，只作用于**新写**，已产生的
expired/archived 行与已删前缀不受影响，故 downgrade **无条件可逆**——与 038
的不可逆边界不同（测试套用 039/041 的可逆断言模式）。

expand-only，不改业务表结构；CREATE OR REPLACE FUNCTION 保留既有 trigger 绑定
（无表级 DDL、无 ACCESS EXCLUSIVE、不引入运行时 DDL）。
"""

from collections.abc import Sequence

from alembic import op

revision: str = "043_run_event_retention_guard"
down_revision: str | None = "042_purge_lease_carrier"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 041 白名单（downgrade 目标）：分支 1（inline purge tombstone，redacted-only）
# + 分支 3（external ref 严格 tombstone）。
_GUARD_041 = """
CREATE OR REPLACE FUNCTION metaedu.guard_agent_run_event_append_only()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- 分支 1（039 原有）：inline purge tombstone。
    IF TG_OP = 'UPDATE'
        AND OLD.payload_inline IS NOT NULL
        AND NEW.payload_inline IS NULL
        AND NEW.payload_state = 'redacted'
        AND (to_jsonb(OLD) - 'payload_inline' - 'payload_state')
            = (to_jsonb(NEW) - 'payload_inline' - 'payload_state')
    THEN
        RETURN NEW;
    END IF;
    -- 分支 3（041 新增）：external ref 严格 tombstone——OLD/NEW 均无 inline、
    -- ref 被清、转 redacted、其余 envelope 列不变。
    IF TG_OP = 'UPDATE'
        AND OLD.payload_inline IS NULL
        AND NEW.payload_inline IS NULL
        AND OLD.payload_ref IS NOT NULL
        AND NEW.payload_ref IS NULL
        AND NEW.payload_state = 'redacted'
        AND (to_jsonb(OLD) - 'payload_inline' - 'payload_state' - 'payload_ref')
            = (to_jsonb(NEW) - 'payload_inline' - 'payload_state' - 'payload_ref')
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'agent_run_events is append-only in E1'
        USING ERRCODE = '55000';
END;
$$
"""

# 043 白名单：四分支。TG_OP='UPDATE'/'DELETE' 防御子句显式表达意图——DELETE 触发
# 时 PL/pgSQL 的 NEW 是未赋值记录（分支 1/2/3 天然落到 RAISE），分支 4 显式
# 放行已 tombstone 行的删除；保留防御子句避免后续改写时无意开洞（与 039/041
# 同规格）。to_jsonb 差集按分支精确豁免：分支 1 豁免 inline+state、分支 2 豁免
# state、分支 3 豁免 inline+state+ref。
_GUARD_043 = """
CREATE OR REPLACE FUNCTION metaedu.guard_agent_run_event_append_only()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- 分支 1（039 原有，widened）：inline payload 清除 -> 任一受控 tombstone。
    IF TG_OP = 'UPDATE'
        AND OLD.payload_inline IS NOT NULL
        AND NEW.payload_inline IS NULL
        AND NEW.payload_state IN ('redacted', 'expired', 'archived')
        AND (to_jsonb(OLD) - 'payload_inline' - 'payload_state')
            = (to_jsonb(NEW) - 'payload_inline' - 'payload_state')
    THEN
        RETURN NEW;
    END IF;
    -- 分支 2（043 新增）：external 行仅 state 变化 tombstone——payload_ref 保留
    -- （ref 清除唯一者 = external.payload.v1），其余列不变。
    IF TG_OP = 'UPDATE'
        AND OLD.payload_state = 'external'
        AND OLD.payload_inline IS NULL
        AND NEW.payload_inline IS NULL
        AND NEW.payload_state IN ('redacted', 'expired', 'archived')
        AND (to_jsonb(OLD) - 'payload_state')
            = (to_jsonb(NEW) - 'payload_state')
    THEN
        RETURN NEW;
    END IF;
    -- 分支 3（041 原有，保持 redacted-only）：external ref 严格 tombstone。
    IF TG_OP = 'UPDATE'
        AND OLD.payload_inline IS NULL
        AND NEW.payload_inline IS NULL
        AND OLD.payload_ref IS NOT NULL
        AND NEW.payload_ref IS NULL
        AND NEW.payload_state = 'redacted'
        AND (to_jsonb(OLD) - 'payload_inline' - 'payload_state' - 'payload_ref')
            = (to_jsonb(NEW) - 'payload_inline' - 'payload_state' - 'payload_ref')
    THEN
        RETURN NEW;
    END IF;
    -- 分支 4（043 新增 DELETE）：仅放行已 tombstone 行的删除——payload 全清
    -- （inline/ref 均 NULL）且状态为受控 tombstone。live 行 DELETE 仍 RAISE。
    IF TG_OP = 'DELETE'
        AND OLD.payload_state IN ('redacted', 'expired', 'archived')
        AND OLD.payload_inline IS NULL
        AND OLD.payload_ref IS NULL
    THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'agent_run_events is append-only in E1'
        USING ERRCODE = '55000';
END;
$$
"""


def upgrade() -> None:
    # CREATE OR REPLACE 保留既有 trigger 绑定（触发器引用函数名，不需重建触发器，
    # 因此升级路径不做任何表级 DDL，无 ACCESS EXCLUSIVE 需求）。
    op.execute(_GUARD_043)


def downgrade() -> None:
    op.execute(_GUARD_041)
