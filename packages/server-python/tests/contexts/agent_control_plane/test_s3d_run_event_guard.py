"""R1-S3-D round-1 P1-2：migration 039 append-only 守卫放行矩阵 + 043 widening/DELETE。

migration 030 的 ``guard_agent_run_event_append_only()`` 无条件 RAISE，首次实现
用运行时 ``DROP TRIGGER -> UPDATE -> CREATE TRIGGER`` 绕过，有跨 Conversation
死锁（ACCESS SHARE -> ACCESS EXCLUSIVE 锁升级）与运行角色 DDL 权限两个缺陷。
migration 039 改为行级白名单：只放行受控 purge tombstone。migration 043 进一步
扩展（Plan §R1-S6-10 冻结矩阵 R1-S6-2/3）：

- 分支 1 widening：inline tombstone 的 ``NEW.payload_state`` 从 ``'redacted'`` 放宽为
  ``IN ('redacted','expired','archived')``（event retention 90 天到期 tombstone）。
- 分支 2（新增）：external 行 state-only 变化（``payload_ref`` 保留，仅
  ``payload_state`` 改为 tombstone 之一）合法——event retention external payload
  到期 tombstone（**不**经 external.payload.v1 清 ref）。
- 分支 4（新增 DELETE 放行）：``OLD.payload_state IN ('redacted','expired',
  'archived')`` 且 ``payload_inline IS NULL`` 且 ``payload_ref IS NULL``——仅
  payload 全清且状态为受控 tombstone 的行可删（event retention envelope prune）。

本模块直接对真实 PostgreSQL 断言守卫行为（不经 participant），锁定放行边界：

- 合法 purge tombstone（payload_inline 非空->NULL + payload_state ∈
  {redacted,expired,archived} + 其余列不变）-> 放行（039/043 branch 1 widening）。
- 合法 external state-only tombstone（external 行 inline=NULL、ref 保留，仅
  payload_state 改 tombstone 之一）-> 放行（043 branch 2 widening）。
- 合法 DELETE（payload 全清且 state ∈ {redacted,expired,archived}）-> 放行
  （043 branch 4）。
- 任一其他列变化（seq / payload_digest / payload_ref / classification /
  visibility / payload_size）-> 拒绝。**seq 不变是 Spec §7.2/§8 的身份不变量。**
- payload_inline 未真正清空（正文改写/复活）-> 拒绝。
- 普通 UPDATE（非 purge/state-only 形态）仍被拒 -> E1 append-only 语义不被削弱。
- 非法 state（写非 tombstone 集 ``'redacted'/'expired'/'archived'``）-> 拒绝。
- 任意 live DELETE（inline 非 NULL 或 ref 仍存在）-> 拒绝（043 branch 4 不开洞）。

变异验证：把 039/043 守卫的任一 AND 子句删除，对应「拒绝」用例即变红；把分支 2/4
widening 限制去掉，对应新放行用例变红。
"""

from __future__ import annotations

import asyncio

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


@pytest.mark.parametrize("new_state", ["redacted", "expired", "archived"])
async def test_guard_allows_controlled_purge_tombstone(db_session, new_state: str):
    """合法 purge tombstone（清 payload_inline + 转为 ``new_state`` ∈
    {redacted,expired,archived} + 其余列不变）-> 放行（039 存在理由 + 043 branch 1
    widening：event retention 90 天到期 tombstone 允许 expired/archived）。

    变异杀手：还原 030 无条件 RAISE -> 本测试变红；去掉 043 branch 1 的
    ``AND NEW.payload_state IN ('redacted','expired','archived')`` widening 子句
    -> expired/archived 用例变红。
    """
    event = await _seed_inline_event(db_session)
    event_id = event.id
    original_seq = event.seq
    original_digest = event.payload_digest

    await db_session.execute(
        text(
            f"UPDATE {_TABLE} SET payload_inline = NULL, "
            "payload_state = :new_state WHERE id = :eid"
        ),
        {"new_state": new_state, "eid": event_id},
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
    assert row.payload_state == new_state
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


async def test_guard_rejects_illegal_payload_state(db_session):
    """非法 payload_state（写非 tombstone 集 ``'redacted'/'expired'/'archived'``）-> 拒绝。

    inline 行 payload_state 改回 ``'inline'`` 不构成 043 branch 1 widening
    tombstone（branch 要求 NEW.payload_state IN (redacted,expired,archived)）；
    branch 2 要求 OLD.payload_state='external'（本行是 inline）-> 也失败。守卫
    任一放行分支不匹配 -> RAISE。保留为 widening 边界的「非法 state 拒绝」锚点。

    变异杀手：去掉 043 branch 1 的 ``AND NEW.payload_state IN ('redacted',
    'expired','archived')`` widening 限制 -> ``payload_state='inline'`` 被误放行。
    """
    event = await _seed_inline_event(db_session)
    await _expect_rejected(
        db_session,
        f"UPDATE {_TABLE} SET payload_inline = NULL, payload_state = 'inline' "
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


@pytest.mark.parametrize("new_state", ["redacted", "expired", "archived"])
async def test_guard_allows_external_state_only_tombstone(
    db_session, new_state: str
):
    """043 branch 2 widening（Plan §R1-S6-10 冻结矩阵）：external 行
    ``payload_inline=NULL`` + ``payload_ref`` 保留，仅 ``payload_state`` 改为
    {redacted,expired,archived} 之一 -> 放行（event retention external payload
    到期 tombstone；**不**经 external.payload.v1 清 ref，ref 清除唯一者 =
    external.payload.v1）。

    to_jsonb 差集豁免 ``payload_state``，ref 与 inline 保持不变；envelope 其余列
    强制不变。变异杀手：去掉分支 2 的
    ``AND (to_jsonb(OLD) - 'payload_state') = (to_jsonb(NEW) - 'payload_state')``
    差集子句 -> 本测试变红。
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
    event_id = event.id
    original_seq = event.seq
    original_digest = event.payload_digest
    original_ref = event.payload_ref

    await db_session.execute(
        text(
            f"UPDATE {_TABLE} SET payload_state = :new_state WHERE id = :eid"
        ),
        {"new_state": new_state, "eid": event_id},
    )
    await db_session.flush()

    row = (
        await db_session.execute(
            text(
                "SELECT payload_inline, payload_ref, payload_state, seq, "
                f"payload_digest FROM {_TABLE} WHERE id = :eid"
            ),
            {"eid": event_id},
        )
    ).one()
    assert row.payload_inline is None, "state-only 不得复活 inline"
    assert row.payload_ref == original_ref, "state-only 不得清 ref（唯一者 = external.payload.v1）"
    assert row.payload_state == new_state
    assert row.seq == original_seq, "envelope seq 强制不变（tombstone 不改身份）"
    assert row.payload_digest == original_digest, "envelope digest 强制不变"


async def test_guard_allows_delete_of_tombstoned_row(db_session):
    """043 branch 4（Plan §R1-S6-10 冻结矩阵）：``OLD.payload_state IN
    ('redacted','expired','archived')`` 且 ``payload_inline IS NULL`` 且
    ``payload_ref IS NULL`` -> DELETE 放行（event retention envelope prune）。

    inline 行先走 039/043 branch 1 写死为 redacted（清 inline + 转 redacted），
    然后 DELETE -> branch 4 匹配 -> 放行。变异杀手：去掉分支 4 的
    ``AND OLD.payload_ref IS NULL`` 限制 -> tombstoned 行被拒。
    """
    event = await _seed_inline_event(db_session)
    event_id = event.id
    await db_session.execute(
        text(
            f"UPDATE {_TABLE} SET payload_inline = NULL, "
            "payload_state = 'redacted' WHERE id = :eid"
        ),
        {"eid": event_id},
    )
    await db_session.flush()
    # 此刻行已 tombstoned（inline NULL + state='redacted'）。DELETE 放行。
    await db_session.execute(
        text(f"DELETE FROM {_TABLE} WHERE id = :eid"),
        {"eid": event_id},
    )
    await db_session.flush()
    row = (
        await db_session.execute(
            text(f"SELECT id FROM {_TABLE} WHERE id = :eid"),
            {"eid": event_id},
        )
    ).first()
    assert row is None, "tombstoned 行应被 branch 4 放行 DELETE"


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

    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory
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

    # 本测试只验证 039 守卫在 039<->038 间的切换（业务断言需库处于 039）。它用
    # 手动 UPDATE alembic_version 模拟 stamp——这只在「039 恰是 head」时安全。一旦
    # 后续迁移把 head 推进到 040+，结束时若仍 stamp 039，会留下「版本戳 039 但物理
    # 是 040 列/表」的脱节，后续 round-trip 会跳过 040 downgrade 而撞「列已存在」。
    # 故：测试体固定操作 039<->038，结束时**装回当前 head**（而非硬编码 039）。
    server_root = Path(__file__).resolve().parents[3]
    head_cfg = Config(str(server_root / "alembic.ini"))
    head_cfg.set_main_option("script_location", str(server_root / "alembic"))
    head_rev = ScriptDirectory.from_config(head_cfg).get_current_head()
    guard_home = "039_run_event_tombstone_guard"

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

    # 进入时把库对齐到守卫 home（039）：head > 039 时用真实 alembic 全链降级到 039
    # （040 downgrade 一律 fail-closed：本测试基线无 040 证据，全链降级安全放行；
    # 一旦有证据则 raise，须测试准备阶段清空），使后续 mig.downgrade/upgrade 的
    # 手动 stamp 与物理 schema 一致。结束 finally 用真实 upgrade 装回 head。
    from alembic import command as _alembic_command

    def _sync_db_url() -> str:
        return TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://", 1).replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )

    def _real_migrate(direction: str, rev: str) -> None:
        from app.config import settings as _settings

        original = _settings.database_url
        _settings.database_url = _sync_db_url()
        try:
            cfg = Config(str(server_root / "alembic.ini"))
            cfg.set_main_option("script_location", str(server_root / "alembic"))
            fn = (
                _alembic_command.upgrade
                if direction == "upgrade"
                else _alembic_command.downgrade
            )
            fn(cfg, rev)
        finally:
            _settings.database_url = original

    current = await _version()
    if current != guard_home:
        # head 已推进（如 040）：真实全链降级到守卫 home，再走 039<->038 验证。
        await asyncio.to_thread(_real_migrate, "downgrade", guard_home)

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
        await _run_migration(mig.upgrade, guard_home)
        assert await _version() == guard_home
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
        # 无论断言成败，结束时装回守卫并把库真实恢复到当前 head（而非硬编码 039），
        # 避免「版本戳 039 但物理是 040+」的脱节污染同库其它用例/迁移 round-trip。
        await db_session.rollback()
        await _run_migration(mig.upgrade, guard_home)
        await engine.dispose()
        if head_rev != guard_home:
            await asyncio.to_thread(_real_migrate, "upgrade", head_rev)


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
