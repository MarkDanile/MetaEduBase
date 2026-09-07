"""R1-S6 PR-E release drill 五阶段 fail-closed canary contract（pure test harness）。

契约锚点：Plan §S6-7（发布迁移流程）/ §S6-8（备份恢复门禁）/ §S6-9（R1-AC1..12，
重点是 AC11 旧 Writer 在线 fail-closed + AC12 restore 重放降级声明）/ §S6-10（边界
与停止条件）/ §S6-14 item 4（PR-E = release drill 五阶段 fail-closed 判别 + canary
测试环境限定）+ Spec §10（expand/backfill/enforce/enable 顺序）/ §11（AC11/AC12）。

本文件是**纯测试 harness**（用户裁决）：不新增 thin composition / production
orchestrator；只复用 main 已有入口——migration 043 事实、registry /
conformance（``run_writer_conformance_static``）、fence backfill
（``backfill_baseline_fences``）、transport backfill（``backfill_transport_scope``）、
六类巡检（``verify_inspection``）、reconcile gate（``tenant_scope_gate_hits``）、
scheduler 组合根门禁（``build_scheduler_composition`` /
``CompositionNotReadyError``）、静态生产 wiring 守卫
（``test_six_erase_entries_unreachable_from_production_composition``）、M-class
maintenance lock（``acquire_maintenance_shared_lock`` /
``acquire_maintenance_exclusive_lock``）、restore-before-open gate
（``evaluate_restore_before_open``）。

五阶段映射与证据层级（冻结声明）：

1. **expand**（真实 PG）：head=043 + append-only guard 四分支 frozen；live 行
   UPDATE/DELETE fail closed。
2. **writer capability**（静态 + 真实 PG）：registry snapshot/digest 一致；
   owner_version/digest 漂移、未知 owner、缺 erase capability 全部 fail closed。
3. **batched backfill**（真实 PG）：fence backfill 分批/续跑/幂等；版本漂移 fail
   closed 不静默跳过；transport 无法映射行 → 具名 reconcile + gate 阻断。
4. **verify**（真实 PG）：六类巡检 exit 0/1/2；发现 → reconcile 登记 + gate
   fail closed；不自动 resolve。
5. **canary enable**（静态守卫 + 真实 PG）：三重 fail-closed（registry False +
   静态 wiring 守卫 + 组合根门禁）；旧 writer 变体注入 fail closed；M-class
   锁互斥不被绕过。

**生产门禁（未执行，不冒充已验证）**：真实 pg_dump / restore / 流量切换、多实例
滚动 canary、旧 writer 真实进程部署——本仓库无该基础设施（Plan §S6-8.6 /
R1-AC12 字面降级）。旧 writer「在线」仅以测试内注入 stale owner_version /
stale registry digest / 未 resolved reconcile 模拟（AC11：conformance suite 只能
断言本进程代码，判别点必须在 drill 内）。

**边界（本文件全程遵守）**：不翻转 ``erase_available``；不接 scheduler production
caller；不使六 erase 入口生产可达；「canary enable」仅断言测试环境 tenant 级
fail-closed gate 行为，**不是**真实生产启用；不改锁序 / 事务边界 / 写者矩阵；
不修复 runbook §6.4 历史文档漂移（restore_replay_executor 已 registered=FENCE_M，
正确现状由 ``test_s6i2_pending_writers_empty_after_d2_registered`` 钉住）；测试库
仅 metaedu_test。
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.composition.agent_erasure_backfill import backfill_baseline_fences
from app.composition.agent_erasure_locks import (
    acquire_maintenance_exclusive_lock,
    acquire_maintenance_shared_lock,
)
from app.composition.agent_erasure_registry import (
    OwnerCapabilityUnavailableError,
    OwnerRegistryChangedError,
    UnknownOwnerError,
    assert_snapshot_current,
    owner_registry,
    registry_digest,
    registry_snapshot,
    require_capability,
    require_owner,
    require_owner_version,
    snapshot_digest,
)
from app.composition.agent_transport_backfill import backfill_transport_scope
from app.composition.agent_transport_ledger_service import tenant_scope_gate_hits
from app.composition.restore_replay import (
    RestoreReplayReport,
    evaluate_restore_before_open,
)
from app.composition.s6i2_orphan_inspection import (
    run_writer_conformance_static,
    verify_inspection,
)
from app.composition.scheduler_composition import (
    CompositionNotReadyError,
    build_scheduler_composition,
)
from tests.composition.test_s5i2_production_wiring_boundary import (
    test_six_erase_entries_unreachable_from_production_composition as _static_guard,
)
from tests.composition.test_s6i2_orphan_inspection import (
    _seed_conversation,
    _seed_event,
    _seed_run,
    _seed_tenant,
)

pytestmark = pytest.mark.asyncio

_DIGEST = "a" * 64


# ---------------------------------------------------------------------------
# 本地 seed helpers（仅本 drill 需要的最小形态；跨测试复用走 import 惯例）
# ---------------------------------------------------------------------------


async def _insert_conversation(session, *, tenant_id: uuid.UUID) -> uuid.UUID:
    """与 test_agent_erasure_schema._insert_conversation 同形态的最小 Conversation。"""
    cid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, creation_digest, state, title_source, "
            " next_message_seq, next_run_queue_seq, last_activity_at, purge_state, "
            " purge_revision, revision, created_at, updated_at) "
            "VALUES (:id, :tenant, :actor, :digest, 'active', 'none', 1, 1, "
            " now(), 'not_scheduled', 0, 1, now(), now())"
        ),
        {"id": cid, "tenant": tenant_id, "actor": uuid.uuid4(), "digest": _DIGEST},
    )
    await session.flush()
    return cid


async def _seed_drifted_fence(
    session, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, owner_version: int
) -> None:
    """种一条 owner_version 漂移的 active fence（模拟旧 writer 写出的非基线行）。"""
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_erasure_fences "
            "(tenant_id, conversation_id, owner_key, owner_version, state, "
            " purge_revision, hold_revision, ingress_checkpoint, ingress_digest, "
            " revision, created_at, updated_at) "
            "VALUES (:t, :c, 'workspace.core.v1', :ov, 'active', 0, 0, "
            " '{}'::jsonb, :digest, 1, now(), now())"
        ),
        {
            "t": tenant_id,
            "c": conversation_id,
            "ov": owner_version,
            "digest": _DIGEST,
        },
    )


async def _seed_phantom_ws_outbox(session, *, tenant_id: uuid.UUID) -> uuid.UUID:
    """种一条 aggregate_id 指向不存在 Message 的 workspace outbox（scope 不可映射）。"""
    oid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_workspace_outbox "
            "(id, tenant_id, event_type, schema_version, aggregate_id, "
            " aggregate_type, payload_inline, payload_ref, payload_digest, "
            " correlation_id, status, attempt_count, next_attempt_at, created_at) "
            "VALUES (:id, :tid, 'turn.requested.v1', 1, :agg, 'workspace.message', "
            " '{}'::jsonb, NULL, :digest, :corr, 'pending', 0, "
            " clock_timestamp(), clock_timestamp())"
        ),
        {
            "id": oid,
            "tid": tenant_id,
            "agg": uuid.uuid4(),  # phantom Message——不存在
            "digest": _DIGEST,
            "corr": uuid.uuid4(),
        },
    )
    return oid


async def _seed_tenant_scope_reconcile_open(session, *, tenant_id: uuid.UUID) -> None:
    """种一条未 resolved 的 tenant_scope reconcile（epoch_unresolvable 合法组合）。

    组合与 ``_register_ledger_issue`` 对 event_gap 的登记完全一致（migration 040
    CHECK 合法矩阵内）：owner=execution.transport.v1 / source=agent_run_events /
    class=tenant_scope / conversation_id=NULL。
    """
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_transport_scope_reconcile "
            "(id, tenant_id, owner_key, source_table, source_row_id, "
            " conversation_id, reconcile_class, issue_code, state, revision, "
            " created_at, resolved_at) "
            "VALUES (:id, :t, 'execution.transport.v1', 'agent_run_events', :rid, "
            " NULL, 'tenant_scope', 'epoch_unresolvable', 'open', 1, "
            " clock_timestamp(), NULL)"
        ),
        {"id": uuid.uuid4(), "t": tenant_id, "rid": uuid.uuid4()},
    )


# ---------------------------------------------------------------------------
# Stage 1 — expand（migrations 034-043 expand-only 基线）
# ---------------------------------------------------------------------------


async def test_stage1_expand_baseline_head_043_and_guard_active(session_factory):
    """expand 阶段：alembic head=043 + append-only guard 函数与 trigger 在网。

    真实 PG 断言 expand 序列已落到冻结基线（head = 043_run_event_retention_guard），
    且 039/041/043 的 append-only guard（``guard_agent_run_event_append_only`` +
    ``trg_agent_run_event_append_only`` on ``agent_run_events``）处于激活状态。
    本测试不新增/放宽任何 schema——只读 pg_catalog。
    """
    async with session_factory() as s, s.begin():
        head = (
            await s.execute(text("SELECT version_num FROM metaedu.alembic_version"))
        ).scalar_one()
        assert head == "043_run_event_retention_guard", (
            f"expand 基线必须为 043（S6-10 冻结）；实际 {head}"
        )
        guard_fn = (
            await s.execute(
                text(
                    "SELECT count(*) FROM pg_proc p "
                    "JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = 'metaedu' "
                    "AND p.proname = 'guard_agent_run_event_append_only'"
                )
            )
        ).scalar_one()
        assert guard_fn == 1, "append-only guard 函数必须在网"
        trigger = (
            await s.execute(
                text(
                    "SELECT count(*) FROM pg_trigger t "
                    "JOIN pg_class c ON c.oid = t.tgrelid "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'metaedu' "
                    "AND t.tgname = 'trg_agent_run_event_append_only' "
                    "AND c.relname = 'agent_run_events' AND NOT t.tgisinternal"
                )
            )
        ).scalar_one()
        assert trigger == 1, "append-only trigger 必须绑定 agent_run_events"


async def test_stage1_expand_guard_fail_closed_on_live_row_write(session_factory):
    """expand 阶段 fail-closed：guard 对 live 行 UPDATE/DELETE 维持 RAISE。

    证明 043 四分支白名单处于 frozen 状态（expand 没有松约束）：
    - live 行非 tombstone UPDATE（改 media_type）→ RAISE（55000）；
    - live 行 DELETE → RAISE（分支 4 只放行已 tombstone 行）；
    - 正向控制：分支 1 tombstone UPDATE（payload_inline→NULL + state→expired）
      必须放行——guard 存在但不是「全拒」，白名单语义精确。
    """
    async with session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        rid, corr = await _seed_run(s, tid=tid, cid=cid, state="failed")
        await _seed_event(s, tid=tid, rid=rid, cid=cid, corr=corr, seq=1)
        event_id = (
            await s.execute(
                text(
                    "SELECT id FROM metaedu.agent_run_events "
                    "WHERE tenant_id = :t AND run_id = :r AND seq = 1"
                ),
                {"t": tid, "r": rid},
            )
        ).scalar_one()

    # 负例 1：live 行非 tombstone UPDATE → guard RAISE
    async with session_factory() as s:
        with pytest.raises(Exception) as exc_update:
            async with s.begin():
                await s.execute(
                    text(
                        "UPDATE metaedu.agent_run_events SET media_type = 'text/plain' "
                        "WHERE tenant_id = :t AND id = :e"
                    ),
                    {"t": tid, "e": event_id},
                )
        assert "append-only" in str(exc_update.value), (
            f"live 行 UPDATE 必须被 guard 拒绝；实际异常: {exc_update.value!r}"
        )

    # 负例 2：live 行 DELETE → guard RAISE（分支 4 只放行已 tombstone 行）
    async with session_factory() as s:
        with pytest.raises(Exception) as exc_delete:
            async with s.begin():
                await s.execute(
                    text(
                        "DELETE FROM metaedu.agent_run_events "
                        "WHERE tenant_id = :t AND id = :e"
                    ),
                    {"t": tid, "e": event_id},
                )
        assert "append-only" in str(exc_delete.value), (
            f"live 行 DELETE 必须被 guard 拒绝；实际异常: {exc_delete.value!r}"
        )

    # 正向控制：分支 1 tombstone UPDATE 放行（043 widened 白名单在 frozen 状态）
    async with session_factory() as s, s.begin():
        await s.execute(
            text(
                "UPDATE metaedu.agent_run_events "
                "SET payload_inline = NULL, payload_state = 'expired' "
                "WHERE tenant_id = :t AND id = :e"
            ),
            {"t": tid, "e": event_id},
        )
        state, inline = (
            await s.execute(
                text(
                    "SELECT payload_state, payload_inline "
                    "FROM metaedu.agent_run_events WHERE tenant_id = :t AND id = :e"
                ),
                {"t": tid, "e": event_id},
            )
        ).one()
        assert state == "expired" and inline is None


# ---------------------------------------------------------------------------
# Stage 2 — writer capability（registry owner_version / capability digest）
# ---------------------------------------------------------------------------


async def test_stage2_capability_registry_snapshot_and_conformance_consistent():
    """capability 阶段（正常路径）：registry snapshot 内部一致 + conformance 全过。

    - ``snapshot_digest(registry_snapshot()) == registry_digest()``（持久化 snapshot
      与 digest 内部一致）；
    - ``run_writer_conformance_static()``：writer 集合 == registry owner 集合、无
      unknown key、无 capability 漂移、stage_with_created 调用方全 fenced。
    """
    assert snapshot_digest(registry_snapshot()) == registry_digest()
    result = run_writer_conformance_static()
    assert result.writers_failed == (), f"writer 漂移: {result.writers_failed}"
    assert result.registry_unknown_keys == ()
    assert result.capability_drift_keys == ()
    assert result.stage_with_created_callers_unfenced == ()
    assert result.writers_passed == result.writers_total


async def test_stage2_capability_owner_version_mismatch_fail_closed():
    """capability 阶段 fail-closed：owner_version / registry digest 漂移被拒。

    覆盖 AC11 旧 writer 变体的两个判别点（测试内注入，不改 registry）：
    - stale owner_version（旧 writer 上报的版本 ≠ 安装版本）→
      ``OwnerRegistryChangedError``；
    - stale registry digest（旧 writer 持有的 snapshot digest ≠ 当前 registry）→
      ``OwnerRegistryChangedError``（``assert_snapshot_current``）。
    均为纯函数 fail closed，不产生任何越权写入。
    """
    ws_installed = require_owner("workspace.core.v1").owner_version
    exec_installed = require_owner("execution.core.v1").owner_version
    with pytest.raises(OwnerRegistryChangedError):
        require_owner_version("workspace.core.v1", ws_installed + 1)
    with pytest.raises(OwnerRegistryChangedError):
        require_owner_version("execution.core.v1", exec_installed + 1)
    with pytest.raises(OwnerRegistryChangedError):
        assert_snapshot_current("0" * 64)
    # 正向控制：当前版本 + 当前 digest 放行
    require_owner_version("workspace.core.v1", ws_installed)
    require_owner_version("execution.core.v1", exec_installed)
    assert_snapshot_current(registry_digest())


async def test_stage2_capability_unknown_owner_and_missing_erase_fail_closed():
    """capability 阶段 fail-closed：未知 owner + 缺 erase capability。

    - 未知 owner key（旧/伪造 writer 上报）→ ``UnknownOwnerError``；
    - external/runtime ``erase_available=False``（canary 不得翻转）→
      ``require_capability(..., "erase")`` 抛 ``OwnerCapabilityUnavailableError``。
    """
    with pytest.raises(UnknownOwnerError):
        require_owner("legacy.owner.v0")
    for owner_key in ("external.payload.v1", "runtime.private.v1"):
        owner = require_owner(owner_key)
        assert owner.erase_available is False, (
            f"{owner_key} erase_available 必须保持 False（禁止 capability flip）"
        )
        with pytest.raises(OwnerCapabilityUnavailableError):
            require_capability(owner_key, "erase")


# ---------------------------------------------------------------------------
# Stage 3 — batched backfill（fence backfill + transport scope backfill）
# ---------------------------------------------------------------------------


async def test_stage3_fence_backfill_batched_resumable_idempotent(session_factory):
    """backfill 阶段（fence）：分批 + 游标续跑 + 幂等。

    3 个 Conversation、batch_size=2、max_conversations=2：第一批 completed=False
    且带回 next_after_id；以该游标续跑完成剩余 1 个；全程重跑后 fences_created=0
    （幂等，不重复创建）。
    """
    owners = len(owner_registry())
    async with session_factory() as s, s.begin():
        tid = uuid.uuid4()
        for _ in range(3):
            await _insert_conversation(s, tenant_id=tid)

    first = await backfill_baseline_fences(
        session_factory, tenant_id=tid, batch_size=2, max_conversations=2
    )
    assert first.ok and first.conversations_succeeded == 2
    assert first.completed is False and first.next_after_id is not None

    resumed = await backfill_baseline_fences(
        session_factory, tenant_id=tid, batch_size=2, after_id=first.next_after_id
    )
    assert resumed.ok and resumed.conversations_succeeded == 1
    assert resumed.completed is True

    again = await backfill_baseline_fences(session_factory, tenant_id=tid)
    assert again.ok
    assert again.fences_created == 0
    assert again.fences_already_present == 3 * owners

    async with session_factory() as s:
        count = (
            await s.execute(
                text(
                    "SELECT count(*) FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :t"
                ),
                {"t": tid},
            )
        ).scalar_one()
    assert count == 3 * owners


async def test_stage3_fence_backfill_version_drift_fail_closed_not_skipped(
    session_factory,
):
    """backfill 阶段 fail-closed：版本漂移 fence 不静默覆盖、不静默跳过。

    模拟「无法可靠回填的行」（AC11）：Conversation 已有一条 owner_version=999 的
    非基线 fence（旧 writer 写出版本漂移）→ backfill 计入 failure_count
    （``OwnerRegistryChangedError``），``report.ok`` 为 False，且漂移行**保持
    原样不被覆盖**；同事务已建的其余 owner fence 随失败回滚（不产生半提交）。
    """
    async with session_factory() as s, s.begin():
        tid = uuid.uuid4()
        cid = await _insert_conversation(s, tenant_id=tid)
        await _seed_drifted_fence(
            s, tenant_id=tid, conversation_id=cid, owner_version=999
        )

    report = await backfill_baseline_fences(session_factory, tenant_id=tid)
    assert not report.ok, "漂移行必须使 report.ok=False（fail closed 不静默通过）"
    assert report.failure_count == 1
    assert report.failures[0].reason_code == "fence_insert_failed"
    assert report.failures[0].error_type == "OwnerRegistryChangedError"

    async with session_factory() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT owner_key, owner_version FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :t AND conversation_id = :c"
                ),
                {"t": tid, "c": cid},
            )
        ).all()
    assert len(rows) == 1, "失败事务必须整体回滚，不留半提交 fence"
    assert rows[0][0] == "workspace.core.v1" and rows[0][1] == 999, (
        "漂移 fence 必须保持原样（不静默覆盖清除路径上的非基线行）"
    )


async def test_stage3_transport_backfill_unmappable_named_reconcile_blocks(
    session_factory,
):
    """backfill 阶段 fail-closed（transport）：不可映射行 → 具名 reconcile + gate 阻断。

    workspace outbox 的 aggregate_id 指向不存在的 Message → 不回填 conversation_id
    （不盲 join、不静默跳过），登记 ``source_message_missing`` / ``tenant_scope`` /
    ``state='open'`` 具名 reconcile；随后 ``tenant_scope_gate_hits`` 命中——
    scheduler/canary enable 对该 tenant fail closed。
    """
    async with session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
        outbox_id = await _seed_phantom_ws_outbox(s, tenant_id=tid)

    report = await backfill_transport_scope(session_factory, tenant_id=tid)
    assert report.ok, f"{report.failures} / {report.verify_detail}"
    assert report.reconcile_issues_registered >= 1

    async with session_factory() as s, s.begin():
        issue = (
            await s.execute(
                text(
                    "SELECT reconcile_class, issue_code, conversation_id, state "
                    "FROM metaedu.agent_transport_scope_reconcile "
                    "WHERE tenant_id = :t AND source_row_id = :o "
                    "AND issue_code = 'source_message_missing'"
                ),
                {"t": tid, "o": outbox_id},
            )
        ).one()
        assert issue[0] == "tenant_scope"
        assert issue[2] is None and issue[3] == "open"
        # 不静默跳过：scope 未回填，行内投影 pending
        conv, proj = (
            await s.execute(
                text(
                    "SELECT conversation_id, scope_reconcile_state "
                    "FROM metaedu.agent_workspace_outbox WHERE id = :o"
                ),
                {"o": outbox_id},
            )
        ).one()
        assert conv is None and proj == "pending"
        # 具名 reconcile 未 resolved → gate 阻断（fail closed）
        assert await tenant_scope_gate_hits(s, tenant_id=tid) is True


# ---------------------------------------------------------------------------
# Stage 4 — verify（六类巡检 + reconcile gate fail closed）
# ---------------------------------------------------------------------------


async def test_stage4_verify_clean_tenant_exit_zero(session_factory):
    """verify 阶段（正常路径）：干净 tenant → exit 0 / 零发现 / conformance 全过。"""
    async with session_factory() as s, s.begin():
        tid = await _seed_tenant(s)

    report = await verify_inspection(
        session_factory, tenant_id=tid, persist_event_gap=False
    )
    assert report.exit_code == 0
    assert report.total_findings == 0
    assert report.indeterminate is False
    assert report.conformance.writers_failed == ()


async def test_stage4_verify_finding_gate_fail_closed_no_autoresolve(session_factory):
    """verify 阶段 fail-closed：event gap 发现 → 登记 + gate 阻断，不自动 resolve。

    event gap（terminal run 缺 seq 2）→ ``verify_inspection(persist_event_gap=True)``
    exit 1：置 ``event_log_complete=False``（唯一写路径）+ 登记
    ``epoch_unresolvable`` / ``tenant_scope`` / ``state='open'`` reconcile；随后
    ``tenant_scope_gate_hits`` 命中（scheduler-enable 对该 tenant fail closed）；
    reconcile 保持 ``open``——verify 不得自动伪造 resolve。
    """
    async with session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
        cid = await _seed_conversation(s, tid=tid)
        rid, corr = await _seed_run(s, tid=tid, cid=cid, state="failed")
        await _seed_event(s, tid=tid, rid=rid, cid=cid, corr=corr, seq=1)
        await _seed_event(s, tid=tid, rid=rid, cid=cid, corr=corr, seq=3)

    report = await verify_inspection(
        session_factory,
        tenant_id=tid,
        persist_event_gap=True,
        inspections=("event_gap",),
    )
    assert report.exit_code == 1
    assert report.total_event_log_complete_writes == 1

    async with session_factory() as s, s.begin():
        complete = (
            await s.execute(
                text(
                    "SELECT event_log_complete FROM metaedu.agent_runs "
                    "WHERE tenant_id = :t AND id = :r"
                ),
                {"t": tid, "r": rid},
            )
        ).scalar_one()
        assert complete is False, "event gap 检出必须置 event_log_complete=False"
        state = (
            await s.execute(
                text(
                    "SELECT state FROM metaedu.agent_transport_scope_reconcile "
                    "WHERE tenant_id = :t AND source_table = 'agent_run_events' "
                    "AND issue_code = 'epoch_unresolvable'"
                ),
                {"t": tid},
            )
        ).scalar_one()
        assert state == "open", "verify 不得自动 resolve（fail closed 等人工处置）"
        assert await tenant_scope_gate_hits(s, tenant_id=tid) is True


async def test_stage4_verify_indeterminate_exit_two(session_factory):
    """verify 阶段：不可判定（未知巡检名）→ exit 2 / indeterminate。"""
    async with session_factory() as s, s.begin():
        tid = await _seed_tenant(s)

    report = await verify_inspection(
        session_factory,
        tenant_id=tid,
        persist_event_gap=False,
        inspections=("no_such_inspection",),
    )
    assert report.exit_code == 2
    assert report.indeterminate is True


# ---------------------------------------------------------------------------
# Stage 5 — canary enable（测试环境 tenant 级 fail-closed；≠ 生产启用）
# ---------------------------------------------------------------------------


async def test_stage5_canary_triple_fail_closed_boundary_holds(session_factory):
    """canary 阶段：三重 fail-closed 边界仍然成立（不启用真实生产 canary）。

    1. registry：external/runtime ``erase_available=False`` + ``require_capability``
       fail closed；
    2. 静态守卫：六 erase 入口在生产组合根不可达（复用 S5-I2 源码扫描门禁——
       本调用即该门禁本体，任何生产模块挂 erase 入口引用 → 红）；
    3. 组合根门禁：partial wiring（缺 claim / 缺 owner entries）→
       ``CompositionNotReadyError`` fail closed。
    """
    # (1) registry False
    for owner_key in ("external.payload.v1", "runtime.private.v1"):
        with pytest.raises(OwnerCapabilityUnavailableError):
            require_capability(owner_key, "erase")

    # (2) 静态生产 wiring 守卫（跨测试 import 复用既有门禁，别名避免 pytest 双收集）
    _static_guard()

    # (3) 组合根启用门禁：partial wiring fail closed
    with pytest.raises(CompositionNotReadyError):
        build_scheduler_composition(session_factory=session_factory, claim=None)
    with pytest.raises(CompositionNotReadyError):
        build_scheduler_composition(session_factory=session_factory, owner_entries={})


async def test_stage5_canary_old_writer_variant_fail_closed(session_factory):
    """canary 阶段（AC11 判别点）：旧 writer 在线变体注入 → 每处 gate fail closed。

    旧 writer「在线」以测试内注入模拟（conformance 只能断言本进程代码，真实远程
    旧进程部署属生产门禁）：
    - stale owner_version → ``OwnerRegistryChangedError``；
    - stale registry digest → ``OwnerRegistryChangedError``；
    - 未 resolved tenant_scope reconcile → ``tenant_scope_gate_hits`` 命中，
      scheduler/canary enable 对该 tenant fail closed；
    - 全程 ``erase_available`` 不翻转（canary enable ≠ capability flip）。
    """
    with pytest.raises(OwnerRegistryChangedError):
        require_owner_version("workspace.core.v1", 999)
    with pytest.raises(OwnerRegistryChangedError):
        assert_snapshot_current("f" * 64)

    async with session_factory() as s, s.begin():
        tid = await _seed_tenant(s)
        await _seed_tenant_scope_reconcile_open(s, tenant_id=tid)
        assert await tenant_scope_gate_hits(s, tenant_id=tid) is True

    for owner in owner_registry():
        if owner.owner_key in ("external.payload.v1", "runtime.private.v1"):
            assert owner.erase_available is False


async def test_stage5_m_class_lock_mutual_exclusion_enforced(session_factory):
    """M-class 维护锁互斥不被测试绕过（retention/audit shared vs replay exclusive）。

    - Session A 持 exclusive（replay 形态）→ Session B ``lock_timeout='1s'`` 申请
      shared（retention/audit 形态）→ 锁等待超时（55P03）；
    - 反向：A 持 shared → B 申请 exclusive → 同样超时；
    - A 持 exclusive → 第二 replay 实例申请 exclusive → 同样超时（V1 多 replay
      串行约束，runbook §6.2）；
    - 释放后 B 可正常获取（正向控制，证明超时确由互斥而非锁不可用）。
    """
    # A exclusive → B shared 超时
    async with session_factory() as a, a.begin():
        await acquire_maintenance_exclusive_lock(a)
        async with session_factory() as b, b.begin():
            await b.execute(text("SET LOCAL lock_timeout = '1s'"))
            with pytest.raises(Exception) as exc_shared:
                await acquire_maintenance_shared_lock(b)
            err = str(exc_shared.value).lower()
            assert "lock timeout" in err or "55p03" in err, (
                f"exclusive 持锁期间 shared 必须锁等待超时；实际: {exc_shared.value!r}"
            )
        await a.rollback()

    # A shared → B exclusive 超时
    async with session_factory() as a, a.begin():
        await acquire_maintenance_shared_lock(a)
        async with session_factory() as b, b.begin():
            await b.execute(text("SET LOCAL lock_timeout = '1s'"))
            with pytest.raises(Exception) as exc_excl:
                await acquire_maintenance_exclusive_lock(b)
            err = str(exc_excl.value).lower()
            assert "lock timeout" in err or "55p03" in err, (
                f"shared 持锁期间 exclusive 必须锁等待超时；实际: {exc_excl.value!r}"
            )
        await a.rollback()

    # A exclusive → 第二 replay 实例 exclusive 超时（多 replay 串行）
    async with session_factory() as a, a.begin():
        await acquire_maintenance_exclusive_lock(a)
        async with session_factory() as b, b.begin():
            await b.execute(text("SET LOCAL lock_timeout = '1s'"))
            with pytest.raises(Exception) as exc_replay:
                await acquire_maintenance_exclusive_lock(b)
            err = str(exc_replay.value).lower()
            assert "lock timeout" in err or "55p03" in err, (
                "exclusive 持锁期间第二 replay 实例 exclusive 必须锁等待超时"
                f"（多 replay 串行）；实际: {exc_replay.value!r}"
            )
        await a.rollback()

    # 正向控制：锁已释放，两种级别都可立即获取
    async with session_factory() as c, c.begin():
        await acquire_maintenance_shared_lock(c)
    async with session_factory() as d, d.begin():
        await acquire_maintenance_exclusive_lock(d)


# ---------------------------------------------------------------------------
# restore-before-open 顺序（S6-8：服务关闭 → ledger replay → scan 零 → 才放行 gate）
# ---------------------------------------------------------------------------


async def test_restore_before_open_order_gate_fail_closed_until_replay_clean(
    session_factory,
):
    """restore-before-open 顺序：replay 未干净前 gate 保持 closed，干净后才放行。

    - blocking replay report（error）→ ``open_allowed=False`` 且 blocked_reasons
      具名（replay_error:*）；
    - ``runtime_proof_c_present=True``（caller 显式传入）→ 即使 replay 干净也
      强制 closed（不可绕 0/False）；
    - replay 干净 + runtime_proof_c_present=False + 空 tenant（六 owner scan 零 +
      S6-6 巡检零）→ ``open_allowed=True``——顺序链尾：replay 干净、scan 为零
      之后才允许测试环境 gate。本断言是 contract-tested 级别，**不**冒充真实
      pg_dump/restore/流量切换 drill（生产门禁，未执行）。
    """
    async with session_factory() as s, s.begin():
        tid = await _seed_tenant(s)

    blocking = RestoreReplayReport(error="archive_read_failed")
    assert blocking.has_blocking_finding() is True
    report_blocked = await evaluate_restore_before_open(
        session_factory,
        tenant_id=tid,
        replay_report=blocking,
        runtime_proof_c_present=False,
    )
    assert report_blocked.open_allowed is False
    assert any(r.startswith("replay_error:") for r in report_blocked.blocked_reasons)

    clean = RestoreReplayReport()
    assert clean.has_blocking_finding() is False
    report_proof_c = await evaluate_restore_before_open(
        session_factory,
        tenant_id=tid,
        replay_report=clean,
        runtime_proof_c_present=True,
    )
    assert report_proof_c.open_allowed is False
    assert any(
        r.startswith("RUNTIME_BINDING_EVIDENCE_UNPROVABLE:")
        for r in report_proof_c.blocked_reasons
    )

    report_open = await evaluate_restore_before_open(
        session_factory,
        tenant_id=tid,
        replay_report=clean,
        runtime_proof_c_present=False,
    )
    assert report_open.open_allowed is True
    assert report_open.blocked_reasons == ()
    # 六 owner scan + S6-6 巡检全部执行且残量为零（scan 为零才放行，非跳过扫描）
    assert len(report_open.owner_scan_findings) == 6
    assert all(total == 0 for _, total in report_open.owner_scan_findings)
    assert all(total == 0 for _, total in report_open.s6_6_findings)
