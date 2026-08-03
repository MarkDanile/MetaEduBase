"""R1-S3-D round-1 P1-2：migration 039 append-only 守卫放行矩阵。

migration 030 的 ``guard_agent_run_event_append_only()`` 无条件 RAISE，首次实现
用运行时 ``DROP TRIGGER -> UPDATE -> CREATE TRIGGER`` 绕过，有跨 Conversation
死锁（ACCESS SHARE -> ACCESS EXCLUSIVE 锁升级）与运行角色 DDL 权限两个缺陷。
migration 039 改为行级白名单：只放行受控 purge tombstone 形态。

本模块直接对真实 PostgreSQL 断言守卫行为（不经 participant），锁定放行边界：

- 合法 purge tombstone（payload_inline 非空->NULL + payload_state=redacted +
  其余列不变）-> 放行。
- 任一其他列变化（seq / payload_digest / payload_ref / classification /
  visibility / payload_size）-> 拒绝。**seq 不变是 Spec §7.2/§8 的身份不变量。**
- payload_state 不转 redacted、payload_inline 未真正清空 -> 拒绝。
- 任意 DELETE -> 拒绝（E1 append-only 不变）。

变异验证：把 039 守卫的任一 AND 子句删除，对应「拒绝」用例即变红。
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.contexts.agent_control_plane import s3d_helpers as h

pytestmark = pytest.mark.asyncio

_TABLE = "metaedu.agent_run_events"

# 守卫是 BEFORE UPDATE OR DELETE 触发器，RAISE 使用 ERRCODE 55000。
_APPEND_ONLY_ERROR = "append-only"


async def _seed_inline_event(db_session):
    """建 completed Run + 一个 inline payload event，返回 event。"""
    conversation_id, identity, _ = await h.seed_purgeable(db_session)
    run = await h.seed_completed_run(
        db_session, conversation_id=conversation_id, identity=identity
    )
    event = await h.seed_run_event(db_session, run=run)
    await db_session.flush()
    return event


async def _expect_rejected(db_session, sql: str, event_id) -> None:
    """执行 SQL 并断言被 append-only 守卫拒绝。"""
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 - 驱动异常类型由 DB 决定
        await db_session.execute(text(sql), {"eid": event_id})
        await db_session.flush()
    assert _APPEND_ONLY_ERROR in str(excinfo.value), (
        f"expected append-only guard rejection, got: {excinfo.value}"
    )
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 放行分支：受控 purge tombstone
# ---------------------------------------------------------------------------


async def test_guard_allows_controlled_purge_tombstone(db_session):
    """合法 purge tombstone（清 payload_inline + 转 redacted，其余列不变）-> 放行。

    这是 039 存在的唯一理由：participant 的 RunEvent tombstone 不再需要运行时 DDL。
    变异杀手：还原 030 无条件 RAISE -> 本测试变红。
    """
    event = await _seed_inline_event(db_session)
    event_id = event.id
    original_seq = event.seq
    original_digest = event.payload_digest

    await db_session.execute(
        text(
            f"UPDATE {_TABLE} SET payload_inline = NULL, "
            "payload_state = 'redacted' WHERE id = :eid"
        ),
        {"eid": event_id},
    )
    await db_session.flush()

    row = (
        await db_session.execute(
            text(
                "SELECT payload_inline, payload_state, seq, payload_digest "
                f"FROM {_TABLE} WHERE id = :eid"
            ),
            {"eid": event_id},
        )
    ).one()
    assert row.payload_inline is None, "payload_inline should be cleared"
    assert row.payload_state == "redacted"
    # seq 与 digest 是身份/审计事实，tombstone 不得改动（Spec §7.2/§8）。
    assert row.seq == original_seq
    assert row.payload_digest == original_digest


# ---------------------------------------------------------------------------
# 拒绝分支：任一其他列变化（守卫的 to_jsonb 差集判定）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "extra_set"),
    [
        ("seq", "seq = 999"),
        ("payload_digest", "payload_digest = repeat('b', 64)"),
        ("payload_ref", "payload_ref = 'external://leaked'"),
        ("classification", "classification = 'public'"),
        ("visibility", "visibility = 'system'"),
        ("payload_size", "payload_size = 0"),
        ("event_type", "event_type = 'run.tampered'"),
    ],
)
async def test_guard_rejects_tombstone_with_other_column_change(
    db_session, label: str, extra_set: str
):
    """tombstone 形态但同时改其他列 -> 拒绝（守卫 to_jsonb 差集判定）。

    ``seq`` 用例锁定 Spec §7.2/§8「tombstone 不改 seq」不变量；``payload_ref``
    用例锁定「external payload 归 external.payload.v1，execution 不得顺手清除」
    的 owner 边界（§1/§5）。
    变异杀手：删守卫的 to_jsonb 相等子句 -> 全部 7 个用例变红。
    """
    event = await _seed_inline_event(db_session)
    await _expect_rejected(
        db_session,
        f"UPDATE {_TABLE} SET payload_inline = NULL, payload_state = 'redacted', "
        f"{extra_set} WHERE id = :eid",
        event.id,
    )


# ---------------------------------------------------------------------------
# 拒绝分支：非受控 tombstone 形态
# ---------------------------------------------------------------------------


async def test_guard_rejects_non_redacted_payload_state(db_session):
    """清 payload_inline 但 payload_state 不转 redacted -> 拒绝。

    变异杀手：删守卫的 ``NEW.payload_state = 'redacted'`` 子句 -> 本测试变红。
    """
    event = await _seed_inline_event(db_session)
    await _expect_rejected(
        db_session,
        f"UPDATE {_TABLE} SET payload_inline = NULL, payload_state = 'expired' "
        "WHERE id = :eid",
        event.id,
    )


async def test_guard_rejects_payload_rewrite(db_session):
    """payload_inline 未清空而是被改写（正文替换）-> 拒绝。

    变异杀手：删守卫的 ``NEW.payload_inline IS NULL`` 子句 -> 本测试变红。
    """
    event = await _seed_inline_event(db_session)
    await _expect_rejected(
        db_session,
        f"UPDATE {_TABLE} SET payload_inline = '{{\"x\": 1}}'::jsonb, "
        "payload_state = 'redacted' WHERE id = :eid",
        event.id,
    )


async def test_guard_rejects_plain_update(db_session):
    """普通 UPDATE（非 purge 形态）仍被拒 -> E1 append-only 语义不被 039 削弱。"""
    event = await _seed_inline_event(db_session)
    await _expect_rejected(
        db_session,
        f"UPDATE {_TABLE} SET visibility = 'system' WHERE id = :eid",
        event.id,
    )


async def test_guard_rejects_delete(db_session):
    """任意 DELETE 仍被拒（039 只放行 UPDATE 的 tombstone 分支）。

    变异杀手：把守卫的 ``TG_OP = 'UPDATE'`` 子句删除 -> 本测试变红。
    """
    event = await _seed_inline_event(db_session)
    await _expect_rejected(
        db_session, f"DELETE FROM {_TABLE} WHERE id = :eid", event.id
    )


async def test_guard_rejects_tombstone_on_already_null_payload(db_session):
    """payload_inline 本就为 NULL（external 事件）-> 拒绝。

    守卫要求 ``OLD.payload_inline IS NOT NULL``：没有正文可清的行不构成 purge
    tombstone，放行等于给 external 事件开了一条无谓的可写路径。
    变异杀手：删 ``OLD.payload_inline IS NOT NULL`` 子句 -> 本测试变红。
    """
    conversation_id, identity, _ = await h.seed_purgeable(db_session)
    run = await h.seed_completed_run(
        db_session, conversation_id=conversation_id, identity=identity
    )
    event = await h.seed_run_event(
        db_session,
        run=run,
        payload_inline=None,
        payload_ref="external://object/1",
        payload_state="external",
    )
    await db_session.flush()
    await _expect_rejected(
        db_session,
        f"UPDATE {_TABLE} SET payload_inline = NULL, payload_state = 'redacted' "
        "WHERE id = :eid",
        event.id,
    )
