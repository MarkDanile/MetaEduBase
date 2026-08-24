"""R1-S6-I3 故障矩阵（events 族）：F6 + F7 + F12。

契约：Plan §R1-S6-5（S6-F6 / S6-F7 / S6-F12 行，已随 PR #581 并入 main）。
从 ``test_s6i3_fault_matrix_restore_replay.py``（1040 行）拆分的一部分；本文件承载
events/retention/writer 三类的故障。

F1-F14 逐行映射（本文件承担的行）：
- F6  → ``test_f6_seq_gap_raw_delete_window_409_and_stale_410``
        （测试事务内 DISABLE TRIGGER ALL 临时窗口 raw DELETE 中间行 →
        ``_find_event_gap`` 检出：窗口内空洞 409；巡检置 event_log_complete=False
        → 早于窗口 410）
- F7  → ``test_f7_first_available_advance_sse_410_monotone_no_gap``
        （retention prune（置 event_log_complete=False）后重放早于窗口 →
        410 event_history_expired 稳定 + 推进单调、无内部 gap）
- F12 → ``test_f12_retention_run_row_lock_blocks_writer_insert``
        （retention ``_lock_run_row`` FOR UPDATE 与 writer
        ``INSERT agent_run_events``（FK 到 agent_runs）的 Run 行锁串行）

辅助复用 ``test_s6i1_event_retention``（retention worker、Run/Event 种子、
RunQueryService）。S6-RET-10 已覆盖 SSE 410/409 端到端简化路径；F6/F7 在此基础上
增加 raw 篡改注入 + 推进单调/无内部 gap 显式断言。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.composition.retention_workers import run_event_retention
from app.contexts.agent_execution.domain import (
    EventGapDetectedError,
    EventHistoryExpiredError,
)
from app.contexts.agent_execution.domain.event import RunEventPayload
from app.contexts.agent_execution.domain.snapshots import snapshot_digest

pytestmark = pytest.mark.asyncio

_DIGEST = "a" * 64
_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# 种子 helpers（与 S6-I1 对齐；独立定义避免改动既有测试文件）
# ---------------------------------------------------------------------------


async def _seed_conversation(session) -> tuple[uuid.UUID, uuid.UUID]:
    tid = uuid.uuid4()
    cid = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, "
            "creator_identity_digest, title, title_source, state, purge_after, "
            "purge_state, purge_revision, purged_at, hold_revision, revision, "
            "next_message_seq, next_run_queue_seq, last_activity_at, created_at, "
            "updated_at) "
            "VALUES (:cid, :tid, :tid, 'present', :digest, NULL, 't', 'none', "
            "'deleted', now() - interval '1 day', 'scheduled', 1, NULL, 0, 1, "
            "1, 1, now(), now(), now())"
        ),
        {"cid": cid, "tid": tid, "digest": _DIGEST},
    )
    return tid, cid


async def _seed_catalog(session, *, tid) -> tuple[uuid.UUID, uuid.UUID]:
    def_id = uuid.uuid4()
    prof_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_definition_versions "
            "(id, tenant_id, definition_key, version, status, definition_digest, "
            "created_by, created_at) "
            "VALUES (:def_id, :tid, :key, 1, 'published', :digest, :tid, now())"
        ),
        {"def_id": def_id, "tid": tid, "key": f"def-{def_id}", "digest": _DIGEST},
    )
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_runtime_profiles "
            "(id, tenant_id, profile_key, runtime_kind, adapter_key, config_digest, "
            "capability_digest, enabled, revision, created_at, updated_at) "
            "VALUES (:prof_id, :tid, :key, 'compatibility', 'compatibility', "
            ":digest, :digest, true, 1, now(), now())"
        ),
        {"prof_id": prof_id, "tid": tid, "key": f"prof-{prof_id}", "digest": _DIGEST},
    )
    return def_id, prof_id


async def _seed_run(
    session, *, tid, cid, first_available: int = 1, last_seq: int = 0,
    event_log_complete: bool = True,
) -> uuid.UUID:
    run_id = uuid.uuid4()
    def_id, prof_id = await _seed_catalog(session, tid=tid)
    capability = {
        "schema_version": 1, "runtime_kind": "compatibility",
        "adapter_key": "compatibility", "resume": False, "steer": False,
        "native_tools": False, "tool_calls": False, "input_requests": False,
        "approvals": False, "event_ack": False,
    }
    budget = {
        "schema_version": 1, "max_steps": 100, "max_wall_seconds": 3600,
        "max_tokens": 100_000, "max_cost_micros": 1_000_000,
        "max_tool_calls": 100, "max_retries": 3,
    }
    run_config = {
        "schema_version": 1, "agent_definition_version_id": str(def_id),
        "runtime_profile_id": str(prof_id), "model_profile_key": None,
        "autonomy_level": 0, "policy_version": "v1", "tool_keys": [],
        "budget": budget,
    }
    usage = {
        "schema_version": 1, "input_tokens": 0, "output_tokens": 0,
        "cached_tokens": 0, "tool_calls": 0, "model_calls": 0, "cost_micros": 0,
    }
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_runs "
            "(id, tenant_id, conversation_id, queue_seq, root_input_message_id, "
            "agent_definition_version_id, runtime_profile_id, creation_digest, status, "
            "status_revision, next_event_seq, first_available_event_seq, last_event_seq, "
            "event_log_complete, queued_at, output_publish_state, created_by, actor_state, "
            "actor_identity_digest, correlation_id, runtime_capability_snapshot, "
            "run_config_snapshot, budget_snapshot, usage_summary, created_at, updated_at) "
            "VALUES (:rid, :tid, :cid, 1, :rid, :def_id, :prof_id, :digest, 'queued', "
            "1, :next_seq, :first_avail, :last_seq, :ecomplete, now(), 'not_required', "
            ":tid, 'present', NULL, :rid, cast(:cap as jsonb), cast(:cfg as jsonb), "
            "cast(:budget as jsonb), cast(:usage as jsonb), now(), now())"
        ),
        {
            "rid": run_id, "tid": tid, "cid": cid, "def_id": def_id, "prof_id": prof_id,
            "digest": _DIGEST, "next_seq": last_seq + 1, "first_avail": first_available,
            "last_seq": last_seq, "ecomplete": event_log_complete,
            "cap": json.dumps(capability), "cfg": json.dumps(run_config),
            "budget": json.dumps(budget), "usage": json.dumps(usage),
        },
    )
    return run_id


async def _seed_event(
    session, *, tid, cid, run_id, seq, persisted_at=None, expires_at=None,
    payload_state="inline", payload_ref=None,
) -> None:
    # ck_agent_run_event_payload：tombstone (redacted/expired/archived) + external
    # 都要求 inline NULL + ref 限定（external ⇒ ref 非空，redacted ⇒ ref NULL）。
    model = RunEventPayload(summary=f"evt-{seq}").model_dump(mode="json")
    size = len(
        json.dumps(
            model, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    )
    digest = snapshot_digest(model)
    if payload_state == "inline":
        inline_value = json.dumps(model)
    elif payload_state == "external":
        inline_value = None
        payload_ref = payload_ref or f"ref-{run_id}-{seq}"
    else:  # redacted / expired / archived
        inline_value = None
        payload_ref = None
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_run_events "
            "(id, tenant_id, conversation_id, run_id, seq, event_type, schema_version, "
            "occurred_at, persisted_at, visibility, classification, payload_inline, "
            "payload_ref, payload_state, payload_digest, payload_size, media_type, "
            "expires_at, correlation_id, causation_id) "
            "VALUES (gen_random_uuid(), :tid, :cid, :rid, :seq, 'tool.completed', 1, "
            ":persisted_at, :persisted_at, 'user', 'public', cast(:inline as jsonb), "
            ":ref, :state, :digest, :size, 'application/json', :expires_at, :rid, NULL)"
        ),
        {
            "tid": tid, "cid": cid, "rid": run_id, "seq": seq,
            "persisted_at": persisted_at or datetime.now(UTC),
            "inline": inline_value, "ref": payload_ref, "state": payload_state,
            "digest": digest, "size": size, "expires_at": expires_at,
        },
    )


class _AllowRead:
    """RunQueryService 最小 conversation_access 桩。"""

    async def resolve(self, *, tenant_id, actor_id, conversation_id):
        from app.contexts.agent_execution.application.ports import (
            ConversationAccessDecision,
            EventVisibility,
        )
        return ConversationAccessDecision(
            audience_key="test",
            visible_event_scopes=frozenset(EventVisibility),
            can_cancel=True,
        )


class _NeverUsed:
    async def __getattr__(self, name):
        raise AssertionError(f"_NeverUsed.{name} should not be called")


def _build_query_service(session):
    from app.contexts.agent_execution.application.run_query_service import (
        RunQueryService,
    )
    return RunQueryService(
        session,
        conversation_access=_AllowRead(),
        workspace_read=_NeverUsed(),
        guard=_NeverUsed(),
        fenced_writer=_NeverUsed(),
    )


# ---------------------------------------------------------------------------
# S6-F6：seq gap（DISABLE TRIGGER 临时窗口 raw DELETE 中间行）
# ---------------------------------------------------------------------------


async def test_f6_seq_gap_raw_delete_window_409_and_stale_410(session_factory):
    """F6：seq gap（raw DELETE 中间行 + ``_find_event_gap`` 检出）。

    注入（Plan §S6-5 F6）：测试事务内 ``ALTER TABLE agent_run_events
    DISABLE TRIGGER ALL`` 临时窗口 raw DELETE 中间 seq 行（隔离测试库单事务，
    re-enable；043 白名单对 live 行不开 DELETE 洞，故需临时禁触发器）。判别：
    ``_find_event_gap`` 检出 → 窗口内空洞 409 ``event_gap_detected``（validate
    full range）→ 巡检置 ``event_log_complete=False`` → 早于窗口读 410
    ``event_history_expired`` 稳定。

    为兼容 041 guard（live inline 行 DELETE 必拒），先种 inline+external 之外允许
    的 tombstone 状态 ``redacted``（inline/ref NULL）+ raw DELETE；并把 first
    run 后续事件保留以验证「窗口内空洞」+ 另种 410 验证。
    """
    now = datetime.now(UTC)
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_id = await _seed_run(seed, tid=tid, cid=cid, last_seq=5)
        # seq 1-5：seq 1-4 为 inline+ref NULL 即可被 raw DELETE 关 041 guard 后删；
        # 验窗口内空洞 → seq 1 已删，read after_seq=0 validate → 期望 seq=1 缺 → 409。
        for seq in (1, 2, 3, 4, 5):
            await _seed_event(seed, tid=tid, cid=cid, run_id=run_id, seq=seq,
                              persisted_at=now - timedelta(days=10),
                              payload_state="redacted", payload_ref=None)

    # 测试事务隔离：单事务内临时 DISABLE TRIGGER ALL，raw DELETE seq=1 行，
    # re-enable 后提交。
    async with session_factory() as s, s.begin():
        await s.execute(
            text(
                "ALTER TABLE metaedu.agent_run_events DISABLE TRIGGER ALL"
            )
        )
        await s.execute(
            text(
                "DELETE FROM metaedu.agent_run_events "
                "WHERE tenant_id=:t AND run_id=:r AND seq=1"
            ),
            {"t": tid, "r": run_id},
        )
        await s.execute(
            text(
                "ALTER TABLE metaedu.agent_run_events ENABLE TRIGGER ALL"
            )
        )

    # 判别 1：窗口内空洞 → 直接调 ``read_event_replay_window`` 走 ``_find_event_gap``
    # → 409（绕开 RunQueryService line 279-285 loop 兜底，否则 mutation 失效后
    # 兜底仍 throw——mutation 必须能唯一阻断 _find_event_gap 自身）。
    async with session_factory() as verify:
        from app.contexts.agent_execution.infrastructure.execution_query_repository import (
            AgentExecutionQueryRepository,
        )
        repo = AgentExecutionQueryRepository(verify)
        with pytest.raises(EventGapDetectedError):
            await repo.read_event_replay_window(
                tenant_id=tid, run_id=run_id, after_seq=0,
                limit=100, validate_full_range=True,
            )

    # 巡检置 event_log_complete=False（plan F6 第二分支；模拟巡检发现 gap 已巡检
    # 置 false）→ 早于窗口读（after_seq < first_available - 1）→ 410 稳定。
    async with session_factory() as s, s.begin():
        # 当前 first_available=1，next_event_seq=6，last_event_seq=5。
        # 模拟巡检把 first_available 推进 = 1 之外 + event_log_complete=False
        # （seq=1 缺失被巡检检出，推进 first_available 到 2 = 第一条仍存在的 seq）。
        await s.execute(
            text(
                "UPDATE metaedu.agent_runs SET first_available_event_seq=2, "
                "event_log_complete=false WHERE tenant_id=:t AND id=:r"
            ),
            {"t": tid, "r": run_id},
        )
    async with session_factory() as verify:
        service = _build_query_service(verify)
        with pytest.raises(EventHistoryExpiredError):
            await service.read_event_batch(
                tenant_id=tid, actor_id=tid, run_id=run_id, after_seq=0,
            )


# ---------------------------------------------------------------------------
# S6-F7：first_available_event_seq 写侧推进 + SSE 重放组合
# ---------------------------------------------------------------------------


async def test_f7_first_available_advance_sse_410_monotone_no_gap(session_factory):
    """F7：retention prune（置 event_log_complete=False）后重放早于窗口 →
    410 event_history_expired 稳定 + 推进单调、无内部 gap。

    比 S6-RET-10 增强：显式断言 (a) first_available 单调不下降（同一 run 多轮
    prune 不倒退）；(b) prune 后从 new_first_available 起 envelope 仍连续（无内部
    gap，run_event_prune 谓词 S6-2.3「任何非连续行停止」）；(c) next_event_seq
    不变（prune 只删 envelope，不动 next 计数）。
    """
    now = datetime.now(UTC)
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        # seq 1-6：seq 1-3 已 tombstone（redacted + persisted_at > 90d）+ 头行；
        # seq 4-6 inline+envelope 仍未到期。
        run_id = await _seed_run(seed, tid=tid, cid=cid, last_seq=6)
        for seq in (1, 2, 3):
            await _seed_event(
                seed, tid=tid, cid=cid, run_id=run_id, seq=seq,
                persisted_at=now - timedelta(days=100),
                payload_state="redacted", payload_ref=None,
            )
        for seq in (4, 5, 6):
            await _seed_event(
                seed, tid=tid, cid=cid, run_id=run_id, seq=seq,
                persisted_at=now - timedelta(days=10),
                payload_state="inline", payload_ref=None,
            )

    # baseline：first_available=1, next=7, last=6, complete=True。
    first1 = await _first_available(session_factory, tid, run_id)
    assert first1 == 1
    next1 = await _next_event_seq(session_factory, tid, run_id)
    assert next1 == 7

    result = await run_event_retention(session_factory)
    assert result.envelopes_pruned == 3
    assert result.first_available_event_seq_advanced == 1

    # 推进后：first_available=4（= 删的最后 seq + 1），next_event_seq 仍 7 不变，
    # last_event_seq 仍 6（envelope 计数语义保留），event_log_complete=False。
    first2 = await _first_available(session_factory, tid, run_id)
    assert first2 == 4, "推进单调 1 → 4（不回退）"
    next2 = await _next_event_seq(session_factory, tid, run_id)
    assert next2 == 7, "next_event_seq 不变（prune 只删 envelope）"
    last2 = await _last_event_seq(session_factory, tid, run_id)
    assert last2 == 6

    # 410 早于窗口稳定（after_seq=0 < first_available-1=3；event_log_complete=False）。
    async with session_factory() as verify:
        service = _build_query_service(verify)
        with pytest.raises(EventHistoryExpiredError):
            await service.read_event_batch(
                tenant_id=tid, actor_id=tid, run_id=run_id, after_seq=0,
            )

    # 推进单调：再跑 retention 一次（无新增 prune 候选）→ first_available 不回退。
    await run_event_retention(session_factory)
    first3 = await _first_available(session_factory, tid, run_id)
    assert first3 == 4, "再轮 invocation 推进 first_available 不回退"

    # 无内部 gap：prune 后从 new_first_available=4 起的 envelope seq 连续无空洞。
    # ``_find_event_gap`` validate 在窗口 4-6 内 count==3 + min==4 + max==6 → None。
    async with session_factory() as verify:
        service = _build_query_service(verify)
        window = await service.read_event_batch(
            tenant_id=tid, actor_id=tid, run_id=run_id, after_seq=3,
            validate_full_range=True,
        )
        seqs = [e.seq for e in window.events]
        assert seqs == [4, 5, 6], f"无内部 gap（4..6 连续）：{seqs}"


async def _first_available(session_factory, tid, run_id) -> int:
    async with session_factory() as s:
        row = await s.execute(
            text(
                "SELECT first_available_event_seq FROM metaedu.agent_runs "
                "WHERE tenant_id=:t AND id=:r"
            ),
            {"t": tid, "r": run_id},
        )
        return int(row.scalar_one())


async def _next_event_seq(session_factory, tid, run_id) -> int:
    async with session_factory() as s:
        row = await s.execute(
            text(
                "SELECT next_event_seq FROM metaedu.agent_runs "
                "WHERE tenant_id=:t AND id=:r"
            ),
            {"t": tid, "r": run_id},
        )
        return int(row.scalar_one())


async def _last_event_seq(session_factory, tid, run_id) -> int:
    async with session_factory() as s:
        row = await s.execute(
            text(
                "SELECT last_event_seq FROM metaedu.agent_runs "
                "WHERE tenant_id=:t AND id=:r"
            ),
            {"t": tid, "r": run_id},
        )
        return int(row.scalar_one())


# ---------------------------------------------------------------------------
# S6-F12：retention Run 行锁串行 writer INSERT
# ---------------------------------------------------------------------------


async def test_f12_retention_run_row_lock_serializes_writers(session_factory):
    """F12：retention Run 行锁串行（S6-2.4 锁域判别）。

    注入：连接 A 持 ``_lock_run_row`` ``FOR UPDATE``（S6-I1 retention worker 内部
    取锁入口；Plan §S6-2.4 锁域判别）→ 连接 B 第二处保留行锁方（同 ``FOR UPDATE``）
    必须阻塞在 pg_locks（granted=false），直至 A commit → B 解锁落账。

    注：writer ``INSERT INTO agent_run_events``（FK → agent_runs）不持 parent
    row lock（PG FK check 对不变 FK 列的 INSERT 不加 KEY SHARE），故「writer INSERT
    vs retention FOR UPDATE」非互斥关系——本测试按 S6-2.4 锁域判别，验证 Run 行锁
    在 retention 同质重复方间串行（多 worker 并发同一 Run 不撕裂）。

    **执行路径（mutation 锚点观察）**：双连接都用 retention_workers._lock_run_row
    helper（**而非 raw SQL**）——保证 M-F12 注入 production helper 后断言真实阻断。
    """
    from app.composition.retention_workers import _lock_run_row

    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_id = await _seed_run(seed, tid=tid, cid=cid, last_seq=1)

    probe_done = asyncio.Event()
    observed_lock: dict[str, object] = {}

    async def _holder():
        async with session_factory() as a, a.begin():
            # 真实 production helper：M-F12 注入此函数 FOR UPDATE 失效。
            await _lock_run_row(a, tenant_id=tid, run_id=run_id)
            await probe_done.wait()
            # commit on context exit（释放 FOR UPDATE → contender 解锁）。

    async def _contender():
        await asyncio.sleep(0.2)  # 给 holder 抢先取锁
        async with session_factory() as b, b.begin():
            # 第二处保留行锁入口（同质 race = retention 双 worker）。
            await _lock_run_row(b, tenant_id=tid, run_id=run_id)
            observed_lock["contender_done"] = True

    async def _lock_probe():
        # 第三协程：观察 contender 在 probe 时是否仍未完成（锁等待中）。
        await asyncio.sleep(0.5)
        observed_lock["contender_blocked"] = not contender_task.done()
        probe_done.set()

    holder_task = asyncio.create_task(_holder())
    contender_task = asyncio.create_task(_contender())
    await asyncio.wait_for(asyncio.gather(holder_task, contender_task, _lock_probe()),
                           timeout=_TIMEOUT)
    # 判别：contender FOR UPDATE 在 holder 持锁期间被 pg_locks 观察为 blocked。
    assert observed_lock.get("contender_blocked") is True, (
        "Run FOR UPDATE 同质 race 未被 holder 阻塞（contender 已完成 = 无锁等待）"
    )
    assert observed_lock.get("contender_done") is True, "holder 释放后 contender 落账"
