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
    """codex round-3 P2-2：真实调用迁移入口 ``downgrade()``/``upgrade()`` 跑
    039 -> 038 -> 039 roundtrip，并验证守卫行为随之切换。

    round-2 的实现只直接执行迁移模块里的 SQL 常量（``_GUARD_UNCONDITIONAL`` /
    ``_GUARD_WITH_PURGE_TOMBSTONE``），交换、清空 ``upgrade()``/``downgrade()``
    函数体后测试仍绿——迁移入口本身是死代码。本测试改为：把 alembic ``op`` 通过
    ``MigrationContext.configure`` 绑定到当前真实连接，然后**真实调用**
    ``mig.downgrade()`` 与 ``mig.upgrade()``（其内部的 ``op.execute`` 即对真实 PG
    执行），依次断言：

    - ``downgrade()`` 后：合法 tombstone 被无条件 RAISE 拒绝（030/038 行为还原）。
    - ``upgrade()`` 后：合法 tombstone 重新放行（白名单恢复）。

    守卫只作用于**新写**，已产生的 tombstone 行不受影响，故 roundtrip 无条件可逆
    （区别于 038 的不可逆边界）。try/finally 结束时再调一次 ``upgrade()`` 把守卫
    恢复到 039 版本，不污染同库其他用例。
    """
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text as _text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from tests.conftest import TEST_DB_URL

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

    # 真实迁移入口在**专用 engine 连接**上执行（避免与 db_session 在同一连接上
    # 叠加两个事务）。迁移模块内的 ``op.execute`` 经 ``_install_proxy`` 注入的
    # alembic.op 模块级 ``_proxy`` 解析到该连接的 Operations，即真实对 PG 执行。
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)

    async def _run_migration(fn, to_rev: str) -> None:
        def _do(sync_conn) -> None:
            mig_ctx = MigrationContext.configure(sync_conn)
            Operations(mig_ctx)._install_proxy()
            fn()

        # 真实迁移入口（CREATE OR REPLACE FUNCTION）。
        async with engine.begin() as conn:
            await conn.run_sync(_do)
        # 真实 alembic 在迁移后 stamp version_num；039 守卫迁移的 upgrade/downgrade
        # 本身不写版本表（纯函数重定义），故测试用显式 UPDATE 模拟 alembic 的 stamp
        # 步骤，使 roundtrip 每一步都能断言 alembic_version（codex round-3 P2-2）。
        async with engine.begin() as conn:
            await conn.execute(
                _text("UPDATE metaedu.alembic_version SET version_num = :v"),
                {"v": to_rev},
            )

    async def _version() -> str:
        async with engine.connect() as conn:
            return (
                await conn.execute(
                    _text("SELECT version_num FROM metaedu.alembic_version")
                )
            ).scalar_one()

    async def _seed_fresh_event() -> object:
        # 在新事务内 seed 一个 inline event（_expect_rejected 的 rollback 只回滚本
        # 事务，不丢已提交的基线 run/conversation）。
        run = await h.run_model(db_session, run_id)
        fresh = await h.seed_run_event(db_session, run=run, seq=100)
        await db_session.flush()
        return fresh

    try:
        # --- 真实 downgrade() -> 038：守卫还原为无条件 RAISE + 版本戳 038 ---
        await _run_migration(mig.downgrade, "038_execution_actor_tombstone")
        assert await _version() == "038_execution_actor_tombstone"

        e1 = await _seed_fresh_event()
        await _expect_rejected(
            db_session,
            f"UPDATE {_TABLE} SET payload_inline = NULL, payload_state = 'redacted' "
            "WHERE id = :eid",
            e1.id,
        )

        # --- 真实 upgrade() -> 039：白名单恢复 + 版本戳 039，tombstone 重新放行 ---
        await _run_migration(mig.upgrade, "039_run_event_tombstone_guard")
        assert await _version() == "039_run_event_tombstone_guard"
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
        # 无论断言成败，结束时装回 039 守卫 + 版本戳，避免污染同库其他用例。
        await db_session.rollback()
        await _run_migration(mig.upgrade, "039_run_event_tombstone_guard")
        await engine.dispose()


async def test_erase_path_emits_no_ddl(db_session):
    """codex round-3 P2-3：erase 全程**实际发出**的 SQL 不含任何 DDL——这是 039
    消除运行时 DDL 的设计目标，也是 restricted runtime role 的可表达等价物。

    测试环境角色是 superuser（``pg_roles.rolsuper``），基于权限的 restricted-role
    测试在本环境无法表达（superuser 绕过一切权限检查）。可证等价物是「erase 根本
    不发 DDL」：若 erase 实际执行的语句里没有任何 DDL，则任意无 DDL 权限的角色都
    能跑通。

    **执行轨迹（非 AST 静态扫描）**：round-2 的 AST 扫描只覆盖直接作为调用实参的
    字符串常量，变量 SQL、动态拼接及 helper 发出的 SQL 都能绕过。本测试在独立
    engine 上挂 ``before_cursor_execute`` 事件监听器，捕获一次**真实 erase** 实际
    发给 PG 的全部语句，断言无 DDL 关键字。变量/拼接/helper SQL 都逃不掉——它们
    最终都要过 cursor execute。
    """
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    from tests.conftest import TEST_DB_URL

    # 先用常规会话 seed（事件监听只挂在 erase 用的独立 engine 上）。
    ctx = await h.seed_purgeable_with_run(db_session)
    await db_session.commit()

    statements: list[str] = []
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    try:
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as session:
            out = await h.participant(session).erase_execution_body(
                tenant_id=h.TENANT_ID,
                conversation_id=ctx["conversation_id"],
                purge_revision=ctx["purge_revision"],
                purge_operation_id=ctx["operation_id"],
                expected_operation_revision=ctx["op_revision"],
            )
            await session.commit()
        assert out.erased
    finally:
        await engine.dispose()

    assert statements, "erase 应实际发出 SQL（监听未失效）"
    joined = "\n".join(statements).upper()
    for ddl in (
        "DROP TRIGGER",
        "CREATE TRIGGER",
        "CREATE OR REPLACE FUNCTION",
        "CREATE FUNCTION",
        "ALTER TABLE",
        "DROP FUNCTION",
        "ALTER TRIGGER",
    ):
        assert ddl not in joined, (
            f"erase 实际执行轨迹含运行时 DDL {ddl!r}（039 的目标即消除它）：\n"
            + "\n".join(s for s in statements if ddl in s.upper())
        )


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
