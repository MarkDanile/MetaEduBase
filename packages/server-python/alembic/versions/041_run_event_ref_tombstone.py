"""S4-E-A: agent_run_events append-only 守卫扩展——放行 external ref 严格 tombstone。

Revision ID: 041_run_event_ref_tombstone
Revises: 040_transport_external_scope
Create Date: 2026-08-10

R1-S4-E E-0/E-1b：`RunEvent.payload_ref` 归 `external.payload.v1`（S4-E-B2）清除，
migration 039 的守卫白名单只放行 `payload_inline`/`payload_state` 变化，
``to_jsonb(OLD) - 'payload_inline' - 'payload_state'`` 强制**其余列含 payload_ref 全
不变**——S4-E-B2 取得 external receipt 后无法清 RunEvent.payload_ref。本迁移把守卫
扩展为**两个放行分支**：

**分支 1（039 原有）**：inline purge tombstone——``OLD.payload_inline IS NOT NULL
AND NEW.payload_inline IS NULL AND NEW.payload_state='redacted'``，其余列（含
payload_ref）不变。

**分支 2（041 新增）**：external ref tombstone（Plan §R1-S4-E B5/E-0 冻结形态）——
- ``OLD.payload_ref IS NOT NULL AND NEW.payload_ref IS NULL``（ref 真的被清）；
- ``NEW.payload_state = 'redacted'``（投影受控 tombstone 状态）；
- ``NEW.payload_inline IS NULL`` **且 ``OLD.payload_inline IS NULL``**（清 ref 不同时
  复活 inline——`payload_inline` 两端均 NULL，禁止「清 ref 顺带写 inline」）。
- ``OLD.payload_state`` 可为 ``external``/``redacted``/``expired``/``archived`` 任一
  （持 ref 的旧状态——「非 external 但残留 ref」正是 final scan 必须处理的历史矛盾
  形态，见 ck_agent_run_event_payload）；``to_jsonb`` 差集在原豁免列
  （payload_inline/payload_state）基础上**仅再豁免 payload_ref**，其余 envelope 列
  强制不变。
- ``TG_OP = 'UPDATE'`` 防御子句与分支 1 对齐：DELETE 触发时 PL/pgSQL 的 ``NEW``
  是未赋值记录，``NEW.payload_state = 'redacted'`` 求值为 NULL 而非 true，IF 判定为
  假即落到 RAISE，故删除该子句 DELETE 仍被拒——保留是为显式表达「只放行 UPDATE」
  的意图，避免后续改写分支 2 时无意开洞（与 039 对分支 1 的 ``TG_OP='UPDATE'``
  防御性冗余同规格，039 docstring L49-54）。

expand-only，不改业务表结构；沿 039 行级白名单（非 DDL，CREATE OR REPLACE FUNCTION
保留既有 trigger 绑定，无 ACCESS EXCLUSIVE 需求，不引入运行时 DDL）。

**revision id 长度**：``041_run_event_ref_tombstone``（27 字符）≤ alembic 默认
``varchar(32)`` 版本表列宽，无需加宽 ``metaedu.alembic_version``——revision id 保持
≤32 字符是本迁移的约束（Plan §R1-S4-E B5 具名 migration 的缩短形式；原始冻结名
``041_run_event_external_ref_tombstone`` 36 字符溢出列宽，三面首轮 P1 后缩短并同步
plan file/revision 映射）。

**downgrade 边界**：还原 039 的白名单（仅分支 1）。守卫是 ``BEFORE UPDATE OR
DELETE`` 触发器，只作用于**新写**，已产生的 ref-tombstone 行不受影响，故 downgrade
**无条件可逆**（无任何 schema/元数据残留——版本表宽度不变）——与 038 的不可逆边界
不同，测试须明确区分，不可套用 038 断言。
"""

from collections.abc import Sequence

from alembic import op

revision: str = "041_run_event_ref_tombstone"
down_revision: str | None = "040_transport_external_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 039 白名单（downgrade 目标）：仅放行 inline purge tombstone。
_GUARD_039 = """
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

# 041 白名单：两个放行分支。分支 2（ref tombstone）的 to_jsonb 差集额外豁免
# payload_ref；payload_inline 必须 OLD/NEW 均 NULL（清 ref 不得复活 inline）；
# TG_OP='UPDATE' 与分支 1 对齐（防御性冗余，DELETE 仍被拒）。
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
    -- 分支 2（041 新增）：external ref 严格 tombstone——OLD/NEW 均无 inline、
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


def upgrade() -> None:
    # CREATE OR REPLACE 保留既有 trigger 绑定（触发器引用函数名，不需重建触发器，
    # 因此升级路径不做任何表级 DDL，无 ACCESS EXCLUSIVE 需求）。
    op.execute(_GUARD_041)


def downgrade() -> None:
    op.execute(_GUARD_039)
