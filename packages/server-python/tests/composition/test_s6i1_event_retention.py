"""R1-S6 S6-I1: ``run_event_retention`` 真实 PG 验收。

契约：Plan §R1-S6-2（S6-2.1 谓词 / S6-2.2 payload expiry / S6-2.3 连续前缀
prune + ``first_available_event_seq`` 推进 + ``event_log_complete=False`` /
S6-2.4 锁域 裁决三 / S6-2.5 计数）+ S6-1 item 1（DB clock）+ S6-1 item 3 裁决一
（hold 到期读侧谓词宽化）+ S6-1 item 5（SSE 410/409）+ migration 043 冻结需求
（S6-10）。mutation 驱动 = ``scripts/s6i1_retention_mutation_kill.py``。

反例映射（每项具名 mutation 对应，见 mutation kill 脚本 docstring）：

- S6-RET-1 inline payload expiry：清 payload_inline + 转 ``expired``，八元保留
- S6-RET-2 external payload expiry：仅 state 变化，payload_ref 保留（043(a) 分支 2）
- S6-RET-3 连续前缀 prune 推进 first_available_event_seq + event_log_complete=False
- S6-RET-4 prune 遇未 tombstone 行停止前缀
- S6-RET-5 prune 遇 external ref 行停止（ref 未清不满足 043(b) 白名单）
- S6-RET-6 active hold 阻塞 expiry + prune
- S6-RET-7 过期 hold 不阻塞（裁决一，R1-AC7）
- S6-RET-8 tenant scope 隔离
- S6-RET-9 幂等重入
- S6-RET-10 推进后 SSE 早于窗口稳定 410；event_log_complete=True 时 409
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.composition.retention_workers import run_event_retention
from app.contexts.agent_execution.application.ports import (
    ConversationAccessDecision,
    EventVisibility,
)
from app.contexts.agent_execution.application.run_query_service import RunQueryService
from app.contexts.agent_execution.domain import (
    EventGapDetectedError,
    EventHistoryExpiredError,
)
from app.contexts.agent_execution.domain.event import RunEventPayload
from app.contexts.agent_execution.domain.snapshots import snapshot_digest

pytestmark = pytest.mark.asyncio

_DIGEST = "a" * 64


# ---------------------------------------------------------------------------
# 种子 helpers（与 db_session 同事务；teardown 由 composition autouse clean 兜底）
# ---------------------------------------------------------------------------


async def _seed_conversation(session, *, tid=None, cid=None) -> tuple[uuid.UUID, uuid.UUID]:
    tid = tid or uuid.uuid4()
    cid = cid or uuid.uuid4()
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
    session,
    *,
    tid,
    cid,
    run_id=None,
    first_available: int = 1,
    last_seq: int = 0,
    event_log_complete: bool = True,
) -> uuid.UUID:
    """非终态（queued）run——避免 terminal envelope CHECK；事件 retention 对 run
    状态不敏感。``next_event_seq = last_seq + 1`` 满足 ck_agent_run_sequences。
    snapshot 列满足 ``to_run``（RuntimeCapabilitySnapshot 等）pydantic 校验。"""
    run_id = run_id or uuid.uuid4()
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
    session,
    *,
    tid,
    cid,
    run_id,
    seq: int,
    event_type: str = "tool.completed",
    payload_state: str = "inline",
    payload_ref: str | None = None,
    persisted_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> None:
    """插入 agent_run_events 行（满足 ck_agent_run_event_payload）。

    - inline：payload_inline 非空 + ref NULL + classification 非 restricted。
    - external：inline NULL + ref 非空。
    - redacted/expired/archived：inline NULL；ref 由调用方控制（默认 NULL）。
    """
    classification = "public"
    payload_inline: dict | None = None
    size = 1
    digest = _DIGEST
    if payload_state == "inline":
        payload_inline = {"summary": f"evt-{seq}"}
        model = RunEventPayload(summary=f"evt-{seq}").model_dump(mode="json")
        # to_event 校验 payload_size == 序列化长度 + payload_digest == snapshot_digest。
        size = len(
            json.dumps(
                model,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        digest = snapshot_digest(model)
    elif payload_state == "external":
        classification = "internal"
        payload_ref = payload_ref or f"ref-{run_id}-{seq}"
    else:
        classification = "public"
        payload_ref = payload_ref if payload_ref is not None else None
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_run_events "
            "(id, tenant_id, conversation_id, run_id, seq, event_type, schema_version, "
            "occurred_at, persisted_at, visibility, classification, payload_inline, "
            "payload_ref, payload_state, payload_digest, payload_size, media_type, "
            "expires_at, correlation_id, causation_id) "
            "VALUES (gen_random_uuid(), :tid, :cid, :rid, :seq, :etype, 1, "
            ":persisted_at, :persisted_at, 'user', :class, cast(:inline as jsonb), :ref, "
            ":state, :digest, :size, 'application/json', :expires_at, :rid, NULL)"
        ),
        {
            "tid": tid, "cid": cid, "rid": run_id, "seq": seq, "etype": event_type,
            "persisted_at": persisted_at or datetime.now(UTC),
            "class": classification,
            "inline": (
                json.dumps(payload_inline)
                if payload_inline is not None
                else None
            ),
            "ref": payload_ref,
            "state": payload_state, "digest": digest, "size": size,
            "expires_at": expires_at,
        },
    )


async def _seed_hold(
    session, *, tid, cid, expires_at: datetime | None = None, state: str = "active"
) -> None:
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversation_legal_holds "
            "(id, tenant_id, conversation_id, reason_code, purpose, actor_id, state, "
            "expires_at, revision, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :tid, :cid, 'retention_test', 'test', :tid, "
            ":state, :expires_at, 1, now(), now())"
        ),
        {"tid": tid, "cid": cid, "state": state, "expires_at": expires_at},
    )


async def _event_state(session, *, tid, run_id, seq) -> tuple[str, dict | None, str | None]:
    row = await session.execute(
        text(
            "SELECT payload_state, payload_inline, payload_ref, payload_digest, "
            "payload_size, media_type, classification "
            "FROM metaedu.agent_run_events "
            "WHERE tenant_id = :tid AND run_id = :rid AND seq = :seq"
        ),
        {"tid": tid, "rid": run_id, "seq": seq},
    )
    mapping = row.mappings().first()
    return (
        mapping["payload_state"],
        mapping["payload_inline"],
        mapping["payload_ref"],
    )


async def _run_window(session, *, tid, run_id) -> tuple[int, bool]:
    row = await session.execute(
        text(
            "SELECT first_available_event_seq, event_log_complete "
            "FROM metaedu.agent_runs WHERE tenant_id = :tid AND id = :rid"
        ),
        {"tid": tid, "rid": run_id},
    )
    mapping = row.mappings().first()
    return mapping["first_available_event_seq"], mapping["event_log_complete"]


class _AllowRead:
    async def resolve(self, **_kwargs):
        return ConversationAccessDecision(
            audience_key="owner",
            visible_event_scopes=frozenset({EventVisibility.USER}),
            can_cancel=True,
        )


class _NeverUsed:
    pass


def _build_query_service(session: object) -> RunQueryService:
    """read_event_batch 只依赖 conversation_access；其余 Protocol 以占位注入。"""
    return RunQueryService(
        session,
        conversation_access=_AllowRead(),
        workspace_read=_NeverUsed(),
        guard=_NeverUsed(),
        fenced_writer=_NeverUsed(),
    )


# ---------------------------------------------------------------------------
# S6-RET-1/2 payload expiry
# ---------------------------------------------------------------------------


async def test_inline_payload_expiry_clears_body_keeps_envelope(session_factory):
    """S6-RET-1：inline 到期行清 payload_inline + 转 expired；envelope 行保留
    （expires_at 提前到期但 persisted_at 未到 90 天——不触发 prune）。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_id = await _seed_run(seed, tid=tid, cid=cid)
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_id, seq=1,
            persisted_at=datetime.now(UTC) - timedelta(days=10),
            expires_at=datetime.now(UTC) - timedelta(days=100),
        )

    result = await run_event_retention(session_factory)

    assert result.payloads_expired == 1
    assert result.envelopes_pruned == 0, "envelope 未到期（persisted_at 10d）"
    assert result.first_available_event_seq_advanced == 0
    assert result.runs_processed == 1
    async with session_factory() as verify:
        state, inline, ref = await _event_state(
            verify, tid=tid, run_id=run_id, seq=1
        )
        assert state == "expired"
        assert inline is None
        assert ref is None
        # 行仍存在（envelope 保留）
        row = await verify.execute(
            text(
                "SELECT seq, event_type, payload_digest, payload_size, media_type, "
                "classification FROM metaedu.agent_run_events "
                "WHERE tenant_id = :tid AND run_id = :rid AND seq = 1"
            ),
            {"tid": tid, "rid": run_id},
        )
        assert row.mappings().first()["seq"] == 1


async def test_external_payload_expiry_state_only_preserves_ref(session_factory):
    """S6-RET-2：external 到期行仅 state 转 expired，payload_ref 保留
    （043(a) 分支 2；ref 清除唯一者 = external.payload.v1）。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_id = await _seed_run(seed, tid=tid, cid=cid)
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_id, seq=1,
            payload_state="external", payload_ref="ref-ext-1",
            persisted_at=datetime.now(UTC) - timedelta(days=10),
            expires_at=datetime.now(UTC) - timedelta(days=100),
        )

    result = await run_event_retention(session_factory)

    assert result.payloads_expired == 1
    async with session_factory() as verify:
        state, inline, ref = await _event_state(
            verify, tid=tid, run_id=run_id, seq=1
        )
        assert state == "expired"
        assert inline is None
        assert ref == "ref-ext-1", "payload_ref 必须保留（external.payload.v1 唯一清除者）"


# ---------------------------------------------------------------------------
# S6-RET-3/4/5 envelope prune
# ---------------------------------------------------------------------------


async def test_continuous_prefix_prune_advances_first_available(session_factory):
    """S6-RET-3：连续前缀全部到期 + tombstone → 删除 + 同事务推进
    first_available_event_seq + event_log_complete=False。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_id = await _seed_run(seed, tid=tid, cid=cid, last_seq=3)
        for seq in (1, 2, 3):
            await _seed_event(
                seed, tid=tid, cid=cid, run_id=run_id, seq=seq,
                persisted_at=datetime.now(UTC) - timedelta(days=100),
            )

    result = await run_event_retention(session_factory)

    assert result.payloads_expired == 3
    assert result.envelopes_pruned == 3
    assert result.first_available_event_seq_advanced == 1
    async with session_factory() as verify:
        count = await verify.scalar(
            text(
                "SELECT count(*) FROM metaedu.agent_run_events "
                "WHERE tenant_id = :tid AND run_id = :rid"
            ),
            {"tid": tid, "rid": run_id},
        )
        assert count == 0, "全部前缀已删"
        first_avail, complete = await _run_window(verify, tid=tid, run_id=run_id)
        assert first_avail == 4, "推进到删除末行 seq+1"
        assert complete is False, "历史已过期显式标记"


async def test_prune_stops_at_live_row_in_prefix(session_factory):
    """S6-RET-4：前缀内出现未 tombstone（live）行 → 立即停止前缀推进，不制造
    内部 gap。"""
    now = datetime.now(UTC)
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_id = await _seed_run(seed, tid=tid, cid=cid, last_seq=2)
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_id, seq=1,
            persisted_at=now - timedelta(days=100),
        )
        # seq2 仍是 live inline（persisted_at 10d 未到期）→ 停止前缀。
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_id, seq=2,
            persisted_at=now - timedelta(days=10),
        )

    result = await run_event_retention(session_factory)

    assert result.payloads_expired == 1
    assert result.envelopes_pruned == 1, "只删 seq1"
    assert result.first_available_event_seq_advanced == 1
    async with session_factory() as verify:
        first_avail, complete = await _run_window(verify, tid=tid, run_id=run_id)
        assert first_avail == 2
        assert complete is False
        state, inline, _ = await _event_state(verify, tid=tid, run_id=run_id, seq=2)
        assert state == "inline", "seq2 live 行保留正文"
        assert inline is not None


async def test_prune_stops_at_external_ref_row(session_factory):
    """S6-RET-5：前缀内出现 external ref 行 → expiry 后 ref 未清，不满足 043(b)
    DELETE 白名单（payload_ref IS NULL）→ 停止前缀。"""
    now = datetime.now(UTC)
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_id = await _seed_run(seed, tid=tid, cid=cid, last_seq=2)
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_id, seq=1,
            persisted_at=now - timedelta(days=100),
        )
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_id, seq=2,
            payload_state="external", payload_ref="ref-ext-2",
            persisted_at=now - timedelta(days=100),
        )

    result = await run_event_retention(session_factory)

    assert result.payloads_expired == 2, "两个 payload 都 expiry"
    assert result.envelopes_pruned == 1, "external 行 envelope 保留（ref 未清）"
    assert result.first_available_event_seq_advanced == 1
    async with session_factory() as verify:
        first_avail, _ = await _run_window(verify, tid=tid, run_id=run_id)
        assert first_avail == 2
        state, inline, ref = await _event_state(verify, tid=tid, run_id=run_id, seq=2)
        assert state == "expired"
        assert inline is None
        assert ref == "ref-ext-2", "external 行 envelope 未删（payload_ref 仍持有）"


# ---------------------------------------------------------------------------
# S6-RET-6/7 hold 语义（裁决一）
# ---------------------------------------------------------------------------


async def test_active_hold_blocks_expiry_and_prune(session_factory):
    """S6-RET-6：Conversation 存在 active hold（expires_at NULL）→ 该 run 不进入
    retention 范围（payload expiry 与 prune 全部跳过，事件保持 inline）。"""
    now = datetime.now(UTC)
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        await _seed_hold(seed, tid=tid, cid=cid, expires_at=None)
        run_id = await _seed_run(seed, tid=tid, cid=cid, last_seq=1)
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_id, seq=1,
            persisted_at=now - timedelta(days=100),
        )

    result = await run_event_retention(session_factory)

    assert result.payloads_expired == 0
    assert result.envelopes_pruned == 0
    async with session_factory() as verify:
        state, inline, _ = await _event_state(verify, tid=tid, run_id=run_id, seq=1)
        assert state == "inline", "active hold 阻塞 payload expiry"
        assert inline is not None


async def test_expired_hold_does_not_block(session_factory):
    """S6-RET-7（裁决一，R1-AC7）：``expires_at`` 已过期的 active hold 不再是
    active → 不阻塞 expiry/prune。未过期 hold 行为不变由 S6-RET-6 覆盖。"""
    now = datetime.now(UTC)
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        await _seed_hold(
            seed, tid=tid, cid=cid, expires_at=now - timedelta(days=30)
        )
        run_id = await _seed_run(seed, tid=tid, cid=cid, last_seq=1)
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_id, seq=1,
            persisted_at=now - timedelta(days=100),
        )

    result = await run_event_retention(session_factory)

    assert result.payloads_expired == 1
    assert result.envelopes_pruned == 1, "过期 hold 不阻塞 prune"
    assert result.first_available_event_seq_advanced == 1
    async with session_factory() as verify:
        first_avail, complete = await _run_window(verify, tid=tid, run_id=run_id)
        assert first_avail == 2
        assert complete is False


async def test_expires_at_null_still_active(session_factory):
    """裁决一：``expires_at IS NULL`` 的 active hold 仍 active（阻塞）。"""
    now = datetime.now(UTC)
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        await _seed_hold(seed, tid=tid, cid=cid, expires_at=None)
        run_id = await _seed_run(seed, tid=tid, cid=cid, last_seq=1)
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_id, seq=1,
            persisted_at=now - timedelta(days=100),
        )

    result = await run_event_retention(session_factory)
    assert result.payloads_expired == 0
    assert result.envelopes_pruned == 0


# ---------------------------------------------------------------------------
# S6-RET-8/9 tenant scope + 幂等
# ---------------------------------------------------------------------------


async def test_tenant_scope_hold_isolation(session_factory):
    """S6-RET-8：hold 判定 tenant-scoped——tenant A 的 hold 不影响 tenant B 的
    run；B 处理、A 跳过。"""
    now = datetime.now(UTC)
    async with session_factory() as seed, seed.begin():
        tid_a, cid_a = await _seed_conversation(seed)
        await _seed_hold(seed, tid=tid_a, cid=cid_a, expires_at=None)
        run_a = await _seed_run(seed, tid=tid_a, cid=cid_a, last_seq=1)
        await _seed_event(
            seed, tid=tid_a, cid=cid_a, run_id=run_a, seq=1,
            persisted_at=now - timedelta(days=100),
        )
        tid_b, cid_b = await _seed_conversation(seed)
        run_b = await _seed_run(seed, tid=tid_b, cid=cid_b, last_seq=1)
        await _seed_event(
            seed, tid=tid_b, cid=cid_b, run_id=run_b, seq=1,
            persisted_at=now - timedelta(days=100),
        )

    result = await run_event_retention(session_factory)

    assert result.payloads_expired == 1
    async with session_factory() as verify:
        state_a, inline_a, _ = await _event_state(verify, tid=tid_a, run_id=run_a, seq=1)
        assert state_a == "inline", "A 的 hold 阻塞 A"
        assert inline_a is not None
        # B 无 hold：expiry + prune 都发生（事件已删，first_available 推进到 2）。
        first_avail_b, complete_b = await _run_window(verify, tid=tid_b, run_id=run_b)
        assert first_avail_b == 2
        assert complete_b is False


async def test_idempotent_rerun(session_factory):
    """S6-RET-9：重入不命中已处理行——第二次运行全零计数。"""
    now = datetime.now(UTC)
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_id = await _seed_run(seed, tid=tid, cid=cid, last_seq=2)
        for seq in (1, 2):
            await _seed_event(
                seed, tid=tid, cid=cid, run_id=run_id, seq=seq,
                persisted_at=now - timedelta(days=100),
            )

    first = await run_event_retention(session_factory)
    assert first.payloads_expired == 2
    assert first.envelopes_pruned == 2

    second = await run_event_retention(session_factory)
    assert second.payloads_expired == 0
    assert second.envelopes_pruned == 0
    assert second.first_available_event_seq_advanced == 0


# ---------------------------------------------------------------------------
# S6-RET-10 SSE 稳定 410/409（S6-1 item 5 承接）
# ---------------------------------------------------------------------------


async def test_sse_410_after_prune(session_factory):
    """推进后早于窗口的 SSE 请求返回稳定 410 ``event_history_expired``
    （event_log_complete=False 分支）。"""
    now = datetime.now(UTC)
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_id = await _seed_run(seed, tid=tid, cid=cid, last_seq=2)
        for seq in (1, 2):
            await _seed_event(
                seed, tid=tid, cid=cid, run_id=run_id, seq=seq,
                persisted_at=now - timedelta(days=100),
            )
    await run_event_retention(session_factory)

    async with session_factory() as verify:
        service = _build_query_service(verify)
        with pytest.raises(EventHistoryExpiredError):
            await service.read_event_batch(
                tenant_id=tid, actor_id=tid, run_id=run_id, after_seq=0
            )


async def test_sse_409_when_event_log_complete_true(session_factory):
    """``event_log_complete=True`` 且窗口早于请求 → 409 ``event_gap_detected``
    （既有分支冻结；与 410 判别 = event_log_complete）。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        # first_available=4 + event_log_complete=True + 事件从 seq4 起（seq1-3 缺失）。
        run_id = await _seed_run(
            seed, tid=tid, cid=cid, first_available=4, last_seq=6,
            event_log_complete=True,
        )
        for seq in (4, 5, 6):
            await _seed_event(
                seed, tid=tid, cid=cid, run_id=run_id, seq=seq,
                persisted_at=datetime.now(UTC) - timedelta(days=10),
            )

    async with session_factory() as verify:
        service = _build_query_service(verify)
        with pytest.raises(EventGapDetectedError):
            await service.read_event_batch(
                tenant_id=tid, actor_id=tid, run_id=run_id, after_seq=0
            )


async def test_event_write_hold_reverify_blocks(session_factory):
    """F-2 判别：payload expiry / prune 的 UPDATE/DELETE WHERE 并入语句级 hold
    EXISTS——hold 在写时点存在 → 0 行写入（防御候选↔写窗口竞态）。"""
    from app.composition.retention_workers import (
        _expire_expired_payloads,
        _prune_expired_prefix,
    )

    now_dt = datetime.now(UTC)
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_id = await _seed_run(seed, tid=tid, cid=cid, last_seq=1)
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_id, seq=1,
            persisted_at=now_dt - timedelta(days=100),
        )
        await _seed_hold(seed, tid=tid, cid=cid, expires_at=None)

    async with session_factory() as worker, worker.begin():
        expired = await _expire_expired_payloads(
            worker,
            tenant_id=tid,
            run_id=run_id,
            conversation_id=cid,
            now=now_dt,
        )
        assert expired == 0, "hold EXISTS 阻断 payload expiry 写"
        pruned, advanced = await _prune_expired_prefix(
            worker,
            tenant_id=tid,
            run_id=run_id,
            conversation_id=cid,
            now=now_dt,
            first_available_event_seq=1,
        )
        assert pruned == 0 and advanced == 0, "hold EXISTS 阻断 prune 写"
    async with session_factory() as verify:
        state, inline, _ = await _event_state(verify, tid=tid, run_id=run_id, seq=1)
        assert state == "inline", "写时点 hold 重验：正文未清"
