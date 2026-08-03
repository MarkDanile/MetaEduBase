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


# ---------------------------------------------------------------------------
# codex round-2 P2-4：migration 039 验收闭环
# ---------------------------------------------------------------------------


async def test_migration_039_roundtrip_downgrade_restores_unconditional_guard(
    db_session,
):
    """codex P2-4：039 downgrade -> 038（守卫还原为无条件 RAISE）-> upgrade -> 039
    （守卫再放行 tombstone）的 roundtrip。

    迁移的 ``upgrade()``/``downgrade()`` 就是 ``op.execute(<守卫函数 SQL>)``
    （``CREATE OR REPLACE FUNCTION``，无表级 DDL、无 ACCESS EXCLUSIVE）。本测试直接
    取迁移模块里的两段守卫 SQL 文本经当前会话执行，等价于 ``op.execute`` 的效果，
    依次断言：

    - 应用 038 守卫（无条件 RAISE）后：合法 tombstone 也被拒（030 行为还原）。
    - 应用 039 守卫（白名单）后：合法 tombstone 重新放行。

    守卫只作用于**新写**，已产生的 tombstone 行不受影响，故 roundtrip 无条件可逆
    （区别于 038 的不可逆边界）。try/finally 保证结束时守卫回到 039 版本，不污染
    同库其他用例。
    """
    import importlib.util
    from pathlib import Path

    from sqlalchemy import text as _text

    # 按文件路径加载迁移模块（revision id 以数字开头，无法作为包名 import）。
    mig_path = (
        Path(__file__).resolve().parents[3]
        / "alembic"
        / "versions"
        / "039_run_event_tombstone_guard.py"
    )
    spec = importlib.util.spec_from_file_location("mig_039", mig_path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    event = await _seed_inline_event(db_session)
    event_id = event.id
    run_id = event.run_id
    await db_session.commit()  # 提交基线，后续 guard 切换的 rollback 不丢失 event。

    async def _apply(sql: str) -> None:
        await db_session.execute(_text(sql))
        await db_session.flush()

    async def _seed_fresh_event() -> object:
        # 在新事务内 seed 一个 inline event（_expect_rejected 的 rollback 只回滚本
        # 事务，不丢已提交的基线 run/conversation）。
        run = await h.run_model(db_session, run_id)
        fresh = await h.seed_run_event(db_session, run=run, seq=100)
        await db_session.flush()
        return fresh

    try:
        # --- downgrade -> 038：守卫还原为无条件 RAISE ---
        await _apply(mig._GUARD_UNCONDITIONAL)
        await db_session.commit()  # 持久化 038 守卫（guard 切换不被后续 rollback 回退）。

        # 038 守卫下：合法 tombstone 也被无条件 RAISE 拒绝。
        e1 = await _seed_fresh_event()
        await _expect_rejected(
            db_session,
            f"UPDATE {_TABLE} SET payload_inline = NULL, payload_state = 'redacted' "
            "WHERE id = :eid",
            e1.id,
        )

        # --- upgrade -> 039：白名单恢复，合法 tombstone 重新放行 ---
        await _apply(mig._GUARD_WITH_PURGE_TOMBSTONE)
        await db_session.commit()
        await db_session.execute(
            _text(
                f"UPDATE {_TABLE} SET payload_inline = NULL, "
                "payload_state = 'redacted' WHERE id = :eid"
            ),
            {"eid": event_id},
        )
        await db_session.flush()
        row = (
            await db_session.execute(
                _text(f"SELECT payload_state FROM {_TABLE} WHERE id = :eid"),
                {"eid": event_id},
            )
        ).one()
        assert row.payload_state == "redacted", "upgrade 后 tombstone 应重新放行"
    finally:
        # 无论断言成败，结束时把守卫恢复到 039 版本，避免污染同库其他用例。
        await db_session.rollback()
        await _apply(mig._GUARD_WITH_PURGE_TOMBSTONE)
        await db_session.commit()


async def test_erase_path_emits_no_ddl(db_session, session_factory):
    """codex P2-4（restricted runtime role 的可表达等价物）：erase 全程**不发任何
    DDL**（无 DROP/CREATE TRIGGER/FUNCTION）——这是 039 消除运行时 DDL 的设计目标。

    测试环境角色是 superuser（``pg_roles.rolsuper``），**基于权限的** restricted-role
    测试在本环境无法表达（superuser 绕过一切权限检查）。但「erase 不需 DDL 权限」的
    可证等价物是「erase 根本不发 DDL」：若 erase 路径不含任何 DDL 语句，则任意无
    DDL 权限的角色都能跑通。本测试用 AST 提取 participant 模块里**实际执行**的全部
    字符串字面量（剔除 docstring/注释），断言其中不含任何 DDL 关键字；再以一次真实
    erase 在真实 PG 跑通佐证（行为不因角色有无 DDL 权限而不同）。
    """
    import ast
    import inspect

    from app.contexts.agent_execution.infrastructure import (
        execution_erasure_participant as mod,
    )

    # 取模块中所有作为表达式/调用实参的字符串字面量（ast 自动排除 docstring——
    # docstring 是 Expr(value=Constant) 且不作为 SQL 执行；真正的 SQL 出现在
    # ``text(...)``/``execute(...)`` 调用实参中）。
    tree = ast.parse(inspect.getsource(mod))
    executed_strings: list[str] = []
    for node in ast.walk(tree):
        # 只收集出现在调用实参里的字符串（SQL 都经 text()/execute() 传入）。
        if isinstance(node, ast.Call):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    executed_strings.append(arg.value)
    joined = "\n".join(executed_strings).upper()
    for ddl in ("DROP TRIGGER", "CREATE TRIGGER", "CREATE OR REPLACE FUNCTION",
                "ALTER TABLE", "DROP FUNCTION"):
        assert ddl not in joined, (
            f"erase 路径不得含运行时 DDL {ddl!r}（039 的目标即消除它）"
        )

    # 真实 erase 在 superuser 下也应成功（行为不因角色有无 DDL 权限而不同）。
    ctx = await h.seed_purgeable_with_run(db_session)
    out = await h.participant(db_session).erase_execution_body(
        tenant_id=h.TENANT_ID,
        conversation_id=ctx["conversation_id"],
        purge_revision=ctx["purge_revision"],
        purge_operation_id=ctx["operation_id"],
        expected_operation_revision=ctx["op_revision"],
    )
    await db_session.commit()
    assert out.erased


async def test_concurrent_erase_two_conversations_no_deadlock(
    db_session, session_factory
):
    """codex P2-4：两个**不同 Conversation** 并发 erase -> 双方各自成功、无死锁、
    无锁升级等待（039 的核心动机：行级守卫放行替代运行时 DROP TRIGGER 的
    ACCESS SHARE -> ACCESS EXCLUSIVE 锁升级死锁）。

    双方在**各自独立会话**并发跑**真实 participant**；行级守卫不做表级 DDL，故两个
    eraser 只各自持自己 Conversation 的行锁 + owner advisory + fence/operation 行锁，
    互不阻塞。``asyncio.gather`` 双方都应返回 erased，无 ``DeadlockDetectedError``。
    """
    import asyncio

    ctx_a = await h.seed_purgeable_with_run(db_session, title="conv A")
    ctx_b = await h.seed_purgeable_with_run(db_session, title="conv B")
    await db_session.commit()

    async def erase_in_own_session(ctx):
        async with session_factory() as session:
            out = await h.participant(session).erase_execution_body(
                tenant_id=h.TENANT_ID,
                conversation_id=ctx["conversation_id"],
                purge_revision=ctx["purge_revision"],
                purge_operation_id=ctx["operation_id"],
                expected_operation_revision=ctx["op_revision"],
            )
            await session.commit()
            return out

    results = await asyncio.gather(
        erase_in_own_session(ctx_a),
        erase_in_own_session(ctx_b),
        return_exceptions=True,
    )
    assert all(not isinstance(r, Exception) for r in results), (
        f"both concurrent erases should succeed without deadlock, got {results!r}"
    )
    assert all(r.erased for r in results), (
        f"both conversations should reach erased fence, got {results!r}"
    )
