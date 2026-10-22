"""TD-114 CLI `agent-identity` 子命令的真实 PostgreSQL contract tests。

契约验收归属（§10-A 组，A-8）：

- dry-run 零写（两表行数不变）
- `--tenant` 选择范围（只动指定 tenant）
- 失败统计与退出码（conflict → exit 1；全绿 → exit 0）
- 重跑幂等（全 skipped，零新增）
- `--actor` 缺失或不存在即报错不执行（零写入）
- created 归属由 RETURNING 判定（不缺 skipped/created 倒挂）

测试直验数据库最终状态；真实 PostgreSQL。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_identity_bootstrap import (
    actor_exists,
    backfill_agent_identity,
    list_all_tenant_ids,
)

pytestmark = pytest.mark.asyncio


async def _make_tenant(session: AsyncSession, *, with_user: bool = False) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    await session.execute(
        text(
            "INSERT INTO metaedu.tenants "
            "(id, name, school_name, isolation, is_active, created_at, updated_at) "
            "VALUES (:id, :name, :school, 'shared', true, :now, :now)"
        ),
        {"id": tenant_id, "name": f"cli-{tenant_id.hex[:8]}", "school": "TD-114", "now": now},
    )
    if with_user:
        await session.execute(
            text(
                "INSERT INTO metaedu.users "
                "(id, tenant_id, username, email, password_hash, role, "
                " clearance_level, is_active, created_at, updated_at) "
                "VALUES (:id, :tid, :uname, :email, 'x', 'teacher', 0, true, "
                "        :now, :now)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "uname": f"ops_{tenant_id.hex[:12]}",
                "email": None,
                "now": now,
            },
        )
    await session.commit()
    return tenant_id


async def _make_actor(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """在指定 tenant 下建一个真实 user 作为 --actor。"""
    now = datetime.now(UTC).replace(tzinfo=None)
    actor_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.users "
            "(id, tenant_id, username, email, password_hash, role, "
            " clearance_level, is_active, created_at, updated_at) "
            "VALUES (:id, :tid, :uname, NULL, 'x', 'teacher', 0, true, :now, :now)"
        ),
        {"id": actor_id, "tid": tenant_id, "uname": f"ops_{actor_id.hex[:12]}", "now": now},
    )
    await session.commit()
    return actor_id


async def _cleanup(session: AsyncSession, *tenant_ids: uuid.UUID) -> None:
    for tid in tenant_ids:
        for statement in (
            "DELETE FROM metaedu.users WHERE tenant_id = :tid",
            "DELETE FROM metaedu.agent_runtime_profiles WHERE tenant_id = :tid",
            "DELETE FROM metaedu.agent_definition_versions WHERE tenant_id = :tid",
            "DELETE FROM metaedu.tenants WHERE id = :tid",
        ):
            await session.execute(text(statement), {"tid": tid})
    await session.commit()


async def _counts(session: AsyncSession, tenant_id: uuid.UUID) -> tuple[int, int]:
    definitions = (
        await session.execute(
            text("SELECT count(*) FROM metaedu.agent_definition_versions WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
    ).scalar_one()
    profiles = (
        await session.execute(
            text("SELECT count(*) FROM metaedu.agent_runtime_profiles WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
    ).scalar_one()
    return definitions, profiles


async def test_actor_must_exist(db_session, session_factory):
    """契约 §8：--actor 不存在于 metaedu.users -> 拒绝执行（零写入）。"""
    ghost = uuid.uuid4()
    assert await actor_exists(db_session, ghost) is False


async def test_dry_run_writes_nothing(db_session, session_factory):
    """A-8：dry-run 零写入，分类与预测计数正确。"""
    t_missing = await _make_tenant(db_session)
    actor = await _make_actor(db_session, t_missing)
    try:
        before = await _counts(db_session, t_missing)
        report = await backfill_agent_identity(
            session_factory,
            tenant_ids=[t_missing],
            actor_id=actor,
            dry_run=True,
        )
        assert report.dry_run is True
        assert report.exit_code == 0
        assert len(report.tenants) == 1
        scan = report.tenants[0]
        assert scan.classification == "missing"
        assert scan.would_create == 2
        assert scan.created == 0
        assert await _counts(db_session, t_missing) == before == (0, 0)
    finally:
        await _cleanup(db_session, t_missing)


async def test_real_run_creates_then_rerun_skips(db_session, session_factory):
    """A-8：实写创建 → 重跑全 skipped 零新增；created 由 RETURNING 判定。"""
    t1 = await _make_tenant(db_session)
    actor = await _make_actor(db_session, t1)
    try:
        report = await backfill_agent_identity(
            session_factory, tenant_ids=[t1], actor_id=actor, dry_run=False
        )
        assert report.exit_code == 0
        assert report.tenants[0].classification == "complete"
        assert report.tenants[0].created == 2
        assert await _counts(db_session, t1) == (1, 1)

        rerun = await backfill_agent_identity(
            session_factory, tenant_ids=[t1], actor_id=actor, dry_run=False
        )
        assert rerun.exit_code == 0
        assert rerun.tenants[0].classification == "complete"
        assert rerun.tenants[0].created == 0
        assert rerun.tenants[0].skipped == 2
        assert await _counts(db_session, t1) == (1, 1)
    finally:
        await _cleanup(db_session, t1)


async def test_tenant_scoping_only_touches_target(db_session, session_factory):
    """A-8：tenant_ids 只动指定 tenant。"""
    t_target = await _make_tenant(db_session)
    t_untouched = await _make_tenant(db_session)
    actor = await _make_actor(db_session, t_target)
    try:
        report = await backfill_agent_identity(
            session_factory,
            tenant_ids=[t_target],
            actor_id=actor,
            dry_run=False,
        )
        assert report.exit_code == 0
        assert await _counts(db_session, t_target) == (1, 1)
        assert await _counts(db_session, t_untouched) == (0, 0)
    finally:
        await _cleanup(db_session, t_target, t_untouched)


async def test_conflict_tenant_reports_and_exit_1(db_session, session_factory):
    """A-8：conflict tenant 如实报告且退出码为 1；不覆盖受控记录。"""
    t_ok = await _make_tenant(db_session)
    t_conflict = await _make_tenant(db_session)
    actor = await _make_actor(db_session, t_ok)
    try:
        # 预置漂移 definition（digest 不符）
        await db_session.execute(
            text(
                "INSERT INTO metaedu.agent_definition_versions "
                "(id, tenant_id, definition_key, version, status, "
                " definition_digest, created_by, created_at) "
                "VALUES (:id, :tid, 'system.direct_rag', 1, 'published', "
                "        :digest, :actor, now())"
            ),
            {"id": uuid.uuid4(), "tid": t_conflict, "digest": "f" * 64, "actor": actor},
        )
        await db_session.commit()

        report = await backfill_agent_identity(
            session_factory,
            tenant_ids=[t_ok, t_conflict],
            actor_id=actor,
            dry_run=False,
        )
        assert report.exit_code == 1
        by_tenant = {t.tenant_id: t for t in report.tenants}
        assert by_tenant[t_ok].classification == "complete"
        assert by_tenant[t_conflict].classification == "conflict"
        assert by_tenant[t_conflict].error is not None
        # 冲突 tenant 零写入（profile 未建；漂移 definition 未覆盖）
        assert await _counts(db_session, t_conflict) == (1, 0)
        assert await _counts(db_session, t_ok) == (1, 1)
    finally:
        await _cleanup(db_session, t_ok, t_conflict)


async def test_disabled_tenant_reported_not_reenabled(db_session, session_factory):
    """A-8：disabled tenant 如实报告、不重启用、exit 0（disabled 不计失败）。"""
    t1 = await _make_tenant(db_session)
    actor = await _make_actor(db_session, t1)
    try:
        await backfill_agent_identity(
            session_factory, tenant_ids=[t1], actor_id=actor, dry_run=False
        )
        await db_session.execute(
            text(
                "UPDATE metaedu.agent_runtime_profiles SET enabled = false WHERE tenant_id = :tid"
            ),
            {"tid": t1},
        )
        await db_session.commit()

        report = await backfill_agent_identity(
            session_factory, tenant_ids=[t1], actor_id=actor, dry_run=False
        )
        assert report.exit_code == 0
        assert report.tenants[0].classification == "disabled"
        assert report.tenants[0].created == 0
        enabled = (
            await db_session.execute(
                text("SELECT enabled FROM metaedu.agent_runtime_profiles WHERE tenant_id = :tid"),
                {"tid": t1},
            )
        ).scalar_one()
        assert enabled is False
    finally:
        await _cleanup(db_session, t1)


async def test_list_all_tenant_ids_scans_tenants_table(db_session):
    """选择条件 = metaedu.tenants 全量（契约 §7）。"""
    t1 = await _make_tenant(db_session)
    try:
        ids = await list_all_tenant_ids(db_session)
        assert t1 in ids
    finally:
        await _cleanup(db_session, t1)


async def test_failure_samples_bounded_beyond_cap(db_session, session_factory):
    """P2：超过样本上限时——总失败/冲突计数完整、明细样本有界、
    其余 tenant 仍全部处理。"""
    from app.composition.agent_identity_bootstrap import _MAX_FAILURE_SAMPLES

    n = _MAX_FAILURE_SAMPLES + 2  # 18 个冲突 tenant
    tenants = [await _make_tenant(db_session) for _ in range(n)]
    actor = await _make_actor(db_session, tenants[0])
    try:
        for tid in tenants:
            await db_session.execute(
                text(
                    "INSERT INTO metaedu.agent_definition_versions "
                    "(id, tenant_id, definition_key, version, status, "
                    " definition_digest, created_by, created_at) "
                    "VALUES (:id, :tid, 'system.direct_rag', 1, 'published', "
                    "        :digest, :actor, now())"
                ),
                {"id": uuid.uuid4(), "tid": tid, "digest": "f" * 64, "actor": actor},
            )
        await db_session.commit()

        report = await backfill_agent_identity(
            session_factory, tenant_ids=tenants, actor_id=actor, dry_run=False
        )
        # 全部 tenant 仍被处理（分类完整）
        assert len(report.tenants) == n
        assert all(t.classification == "conflict" for t in report.tenants)
        # 总需介入数完整累计（分类计数），退出码为 1
        assert report.exit_code == 1
        # 明细样本有界
        assert len(report.failure_samples) == _MAX_FAILURE_SAMPLES
        retained = sum(1 for t in report.tenants if t.error is not None)
        assert retained == _MAX_FAILURE_SAMPLES
        # 冲突行零写入（抽样验证首尾各一）
        assert await _counts(db_session, tenants[0]) == (1, 0)
        assert await _counts(db_session, tenants[-1]) == (1, 0)
    finally:
        await _cleanup(db_session, *tenants)


async def test_cli_entry_missing_actor_fails_without_writes(db_session, session_factory):
    """P2：真实 CLI 入口——缺 --actor 立即报错，零写入。"""
    from app.cli.backfill import _run_agent_identity

    t1 = await _make_tenant(db_session)
    try:
        with pytest.raises(SystemExit):
            await _run_agent_identity(session_factory, str(t1), True, None)
        assert await _counts(db_session, t1) == (0, 0)
    finally:
        await _cleanup(db_session, t1)


async def test_cli_entry_invalid_actor_uuid_fails_without_writes(db_session, session_factory):
    """P2：真实 CLI 入口——非法 UUID 报错，零写入。"""
    from app.cli.backfill import _run_agent_identity

    t1 = await _make_tenant(db_session)
    try:
        with pytest.raises(SystemExit):
            await _run_agent_identity(session_factory, str(t1), True, "not-a-uuid")
        assert await _counts(db_session, t1) == (0, 0)
    finally:
        await _cleanup(db_session, t1)


async def test_cli_entry_nonexistent_actor_fails_without_writes(db_session, session_factory):
    """P2：真实 CLI 入口——actor 不存在于 metaedu.users 报错，零写入。"""
    from app.cli.backfill import _run_agent_identity

    t1 = await _make_tenant(db_session)
    try:
        with pytest.raises(SystemExit):
            await _run_agent_identity(session_factory, str(t1), True, str(uuid.uuid4()))
        assert await _counts(db_session, t1) == (0, 0)
    finally:
        await _cleanup(db_session, t1)


async def test_cli_entry_valid_actor_returns_payload_and_exit_code(db_session, session_factory):
    """P2：真实 CLI 入口——合法 actor 可执行，返回 JSON 可序列化 payload + 退出码。"""
    import json

    from app.cli.backfill import _run_agent_identity

    t1 = await _make_tenant(db_session)
    actor = await _make_actor(db_session, t1)
    try:
        payload, exit_code = await _run_agent_identity(session_factory, str(t1), False, str(actor))
        assert exit_code == 0
        assert payload["subcommand"] == "agent-identity"
        assert payload["failed"] == 0
        assert payload["tenants"][0]["classification"] == "complete"
        json.dumps(payload)  # JSON 可序列化
        assert await _counts(db_session, t1) == (1, 1)
    finally:
        await _cleanup(db_session, t1)
