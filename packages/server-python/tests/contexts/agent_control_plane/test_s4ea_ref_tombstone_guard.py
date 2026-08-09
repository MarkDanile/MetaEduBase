"""R1-S4-E-A：migration 041 append-only 守卫扩展放行矩阵。

migration 039 只放行 inline purge tombstone（``payload_inline`` 非空->NULL +
``payload_state='redacted'`` + 其余列含 ``payload_ref`` 全不变）——S4-E-B2 取得
external receipt 后无法清 ``RunEvent.payload_ref``。migration 041 扩展守卫为
**两个放行分支**（Plan §R1-S4-E B5/E-0 冻结形态）：

- 分支 1（039 原有）：inline purge tombstone。
- 分支 2（041 新增）：external ref 严格 tombstone——``OLD.payload_inline IS NULL
  AND NEW.payload_inline IS NULL AND OLD.payload_ref IS NOT NULL AND NEW.payload_ref
  IS NULL AND NEW.payload_state='redacted'``，且 ``to_jsonb`` 差集在原豁免列基础上
  仅再豁免 ``payload_ref``/``payload_state``（其余 envelope 列强制不变）。

本模块直接对真实 PostgreSQL 断言守卫行为（不经 participant），锁定放行边界：

- 合法 ref tombstone（持 ref 旧状态 -> redacted 无 ref，inline 两端均 NULL，
  其余列不变）-> 放行。
- 清 ref 同时复活 inline（``NEW.payload_inline`` 非 NULL）-> 拒绝（变异杀手：
  删 ``NEW.payload_inline IS NULL`` 子句）。
- 清 ref 但旧行已有 inline（``OLD.payload_inline`` 非 NULL）-> 拒绝（变异杀手：
  删 ``OLD.payload_inline IS NULL`` 子句）。
- 清 ref 但 payload_state 不转 redacted -> 拒绝。
- 清 ref 同时改其他 envelope 列（seq/digest/classification/visibility/size）-> 拒绝。
- ref 未真正清（NEW.payload_ref 仍非空）-> 拒绝。
- 任意 DELETE -> 拒绝（E1 append-only 不变）。
- 039 分支 1（inline tombstone）仍放行（041 不得削弱既有白名单）。

变异验证：把 041 守卫分支 2 的任一 AND 子句删除，对应「拒绝」用例即变红。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.contexts.agent_control_plane import s3d_helpers as h

pytestmark = pytest.mark.asyncio

_TABLE = "metaedu.agent_run_events"

_APPEND_ONLY_ERROR = "append-only"

# migration 041 文件路径（revision id 以数字开头，无法作为包名 import）。
_MIG_041 = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "041_run_event_external_ref_tombstone.py"
)


def _load_mig():
    spec = importlib.util.spec_from_file_location("mig_041", _MIG_041)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    return mig


async def _seed_external_event(db_session, *, payload_state: str = "external"):
    """建 completed Run + 一个 external/持 ref 的 RunEvent，返回 event。"""
    conversation_id, identity, _ = await h.seed_purgeable(db_session)
    run = await h.seed_completed_run(
        db_session, conversation_id=conversation_id, identity=identity
    )
    event = await h.seed_run_event(
        db_session,
        run=run,
        payload_inline=None,
        payload_ref="external://object/1",
        payload_state=payload_state,
    )
    await db_session.flush()
    return event


async def _seed_inline_event(db_session):
    """建 completed Run + 一个 inline payload event，返回 event（039 分支验证用）。"""
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
# 放行分支：external ref 严格 tombstone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "old_state",
    ["external", "redacted", "expired", "archived"],
)
async def test_guard_allows_ref_tombstone(db_session, old_state: str):
    """持 ref 旧状态（external/redacted/expired/archived）-> redacted 无 ref 放行。

    041 存在的唯一理由：S4-E-B2 取得 external receipt 后清 RunEvent.payload_ref。
    变异杀手：还原 039 白名单（去掉分支 2）-> 本测试变红。
    """
    event = await _seed_external_event(db_session, payload_state=old_state)
    event_id = event.id
    original_seq = event.seq
    original_digest = event.payload_digest

    await db_session.execute(
        text(
            f"UPDATE {_TABLE} SET payload_ref = NULL, "
            "payload_state = 'redacted' WHERE id = :eid"
        ),
        {"eid": event_id},
    )
    await db_session.flush()

    row = (
        await db_session.execute(
            text(
                "SELECT payload_inline, payload_ref, payload_state, seq, "
                "payload_digest FROM metaedu.agent_run_events WHERE id = :eid"
            ),
            {"eid": event_id},
        )
    ).one()
    assert row.payload_inline is None, "清 ref 不得复活 inline"
    assert row.payload_ref is None, "ref 应被清"
    assert row.payload_state == "redacted"
    assert row.seq == original_seq
    assert row.payload_digest == original_digest


async def test_guard_keeps_039_inline_branch_allowed(db_session):
    """041 不得削弱 039 白名单：inline purge tombstone 仍放行。"""
    event = await _seed_inline_event(db_session)
    await db_session.execute(
        text(
            f"UPDATE {_TABLE} SET payload_inline = NULL, "
            "payload_state = 'redacted' WHERE id = :eid"
        ),
        {"eid": event.id},
    )
    await db_session.flush()
    row = (
        await db_session.execute(
            text(
                "SELECT payload_inline, payload_state FROM "
                "metaedu.agent_run_events WHERE id = :eid"
            ),
            {"eid": event.id},
        )
    ).one()
    assert row.payload_inline is None
    assert row.payload_state == "redacted"


# ---------------------------------------------------------------------------
# 拒绝分支：清 ref 的非法形态
# ---------------------------------------------------------------------------


async def test_guard_rejects_ref_tombstone_with_inline_revive(db_session):
    """清 ref 同时复活 inline（NEW.payload_inline 非 NULL）-> 拒绝。

    变异杀手：删守卫分支 2 的 ``NEW.payload_inline IS NULL`` 子句 -> 本测试变红。
    """
    event = await _seed_external_event(db_session)
    await _expect_rejected(
        db_session,
        "UPDATE metaedu.agent_run_events SET payload_ref = NULL, "
        "payload_state = 'redacted', payload_inline = '{\"x\": 1}'::jsonb "
        "WHERE id = :eid",
        event.id,
    )


async def test_guard_rejects_ref_tombstone_with_inline_on_old(db_session):
    """清 ref 但旧行已有 inline（OLD.payload_inline 非 NULL）-> 拒绝。

    分支 2 的 ``OLD.payload_inline IS NULL`` 子句是**防御性**（equivalent-mutant
    先例，与 039 的 ``TG_OP='UPDATE'`` 同规格）：``ck_agent_run_event_payload``
    强制 inline/ref 恰一非空，不存在「旧行 inline+ref 并存」的合法行，无法构造
    直接击杀该子句的输入——保留它是为显式表达「ref tombstone 只允许 external/
    redacted 等无 inline 旧状态」，避免未来 schema 演进（CHECK 放宽）时无意开洞。

    本用例验证「inline 旧行上的任何 ref 变化都被拒」（两条分支都不放行：分支 1
    要求其余列不变、分支 2 要求 OLD inline 为 NULL）——不作为该子句的击杀证据。
    """
    event = await _seed_inline_event(db_session)
    await _expect_rejected(
        db_session,
        f"UPDATE {_TABLE} SET payload_ref = 'external://leaked', "
        "payload_state = 'redacted' WHERE id = :eid",
        event.id,
    )


async def test_guard_rejects_ref_tombstone_not_redacted(db_session):
    """清 ref 但 payload_state 不转 redacted -> 拒绝。

    变异杀手：删分支 2 的 ``NEW.payload_state = 'redacted'`` 子句 -> 本测试变红。
    """
    event = await _seed_external_event(db_session)
    await _expect_rejected(
        db_session,
        f"UPDATE {_TABLE} SET payload_ref = NULL, payload_state = 'expired' "
        "WHERE id = :eid",
        event.id,
    )


@pytest.mark.parametrize(
    ("label", "extra_set"),
    [
        ("seq", "seq = 999"),
        ("payload_digest", "payload_digest = repeat('b', 64)"),
        ("classification", "classification = 'public'"),
        ("visibility", "visibility = 'system'"),
        ("payload_size", "payload_size = 999"),
        ("event_type", "event_type = 'run.tampered'"),
    ],
)
async def test_guard_rejects_ref_tombstone_with_other_column_change(
    db_session, label: str, extra_set: str
):
    """ref tombstone 形态但同时改其他列 -> 拒绝（to_jsonb 差集判定）。

    变异杀手：删分支 2 的 to_jsonb 相等子句 -> 全部 6 个用例变红。
    """
    event = await _seed_external_event(db_session)
    await _expect_rejected(
        db_session,
        f"UPDATE {_TABLE} SET payload_ref = NULL, payload_state = 'redacted', "
        f"{extra_set} WHERE id = :eid",
        event.id,
    )


async def test_guard_rejects_ref_not_cleared(db_session):
    """ref 未真正清（NEW.payload_ref 仍非空，只改 state）-> 拒绝。

    变异杀手：删分支 2 的 ``NEW.payload_ref IS NULL`` 子句 -> 本测试变红。
    """
    event = await _seed_external_event(db_session)
    await _expect_rejected(
        db_session,
        f"UPDATE {_TABLE} SET payload_state = 'redacted' WHERE id = :eid",
        event.id,
    )


async def test_guard_rejects_ref_tombstone_delete(db_session):
    """任意 DELETE 仍被拒（041 只放行 UPDATE 的 tombstone 分支）。

    变异杀手：把分支 2 的 ``TG_OP = 'UPDATE'`` 子句删除 -> 本测试变红。
    """
    event = await _seed_external_event(db_session)
    await _expect_rejected(
        db_session, f"DELETE FROM {_TABLE} WHERE id = :eid", event.id
    )


# ---------------------------------------------------------------------------
# migration 041 roundtrip：upgrade/downgrade 切换守卫行为
# ---------------------------------------------------------------------------


async def test_migration_041_roundtrip_restores_039_on_downgrade(db_session):
    """真实调用迁移入口 ``downgrade()``/``upgrade()`` 跑 041 -> 039 -> 041
    roundtrip，验证守卫行为随之切换。

    - ``downgrade()`` 后：ref tombstone 被拒（039 白名单还原，只放行 inline
      tombstone），inline tombstone 仍放行。
    - ``upgrade()`` 后：ref tombstone 重新放行（分支 2 恢复）。

    守卫只作用于**新写**，已产生的 tombstone 行不受影响，故 roundtrip 无条件可逆
    （区别于 038 的不可逆边界）。try/finally 结束时把库装回当前 head（不硬编码
    041），避免「版本戳 041 但物理 schema 是后续 head」的脱节。
    """
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory
    from sqlalchemy import text as _text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from tests.conftest import TEST_DB_URL

    mig = _load_mig()

    server_root = Path(__file__).resolve().parents[3]
    head_cfg = Config(str(server_root / "alembic.ini"))
    head_cfg.set_main_option("script_location", str(server_root / "alembic"))
    head_rev = ScriptDirectory.from_config(head_cfg).get_current_head()
    guard_home = "041_run_event_external_ref_tombstone"

    event = await _seed_external_event(db_session)
    event_id = event.id
    await db_session.commit()  # 提交基线，后续 guard 切换的 rollback 不丢失 event。

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)

    async def _run_migration(fn, to_rev: str) -> None:
        def _do(sync_conn) -> None:
            mig_ctx = MigrationContext.configure(sync_conn)
            Operations(mig_ctx)._install_proxy()
            fn()

        async with engine.begin() as conn:
            await conn.run_sync(_do)
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

    # 进入时把库对齐到守卫 home（041）：head > 041 时用真实 alembic 全链降级。
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
        await _run_migration(mig.upgrade, guard_home)

    try:
        # --- 真实 downgrade() -> 039：ref tombstone 拒绝，inline tombstone 放行 ---
        await _run_migration(mig.downgrade, "040_transport_external_scope")
        assert await _version() == "040_transport_external_scope"

        e1 = await _seed_external_event(db_session)
        await _expect_rejected(
            db_session,
            f"UPDATE {_TABLE} SET payload_ref = NULL, payload_state = 'redacted' "
            "WHERE id = :eid",
            e1.id,
        )

        # --- 真实 upgrade() -> 041：ref tombstone 放行 + 版本戳 041 ---
        await _run_migration(mig.upgrade, guard_home)
        assert await _version() == guard_home
        await db_session.execute(
            text(
                f"UPDATE {_TABLE} SET payload_ref = NULL, "
                "payload_state = 'redacted' WHERE id = :eid"
            ),
            {"eid": event_id},
        )
        await db_session.flush()
        row = (
            await db_session.execute(
                text(
                    f"SELECT payload_state, payload_ref FROM {_TABLE} "
                    "WHERE id = :eid"
                ),
                {"eid": event_id},
            )
        ).one()
        assert row.payload_state == "redacted", "upgrade 后 ref tombstone 应放行"
        assert row.payload_ref is None
    finally:
        await db_session.rollback()
        await _run_migration(mig.upgrade, guard_home)
        await engine.dispose()
        if head_rev != guard_home:
            import asyncio

            await asyncio.to_thread(_real_migrate, "upgrade", head_rev)
