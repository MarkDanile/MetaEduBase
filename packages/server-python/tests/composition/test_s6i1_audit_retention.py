"""R1-S6 S6-I1: ``run_audit_retention`` 真实 PG 验收。

契约：Plan §R1-S6-3（S6-3.1 谓词与 blocked 清单 / S6-3.2 删除集合 children-first /
S6-3.3 锁域 裁决三 / S6-3.4 hold 联动）+ S6-1 item 1（DB clock）+ S6-1 item 3
裁决一（hold 到期谓词宽化）。mutation 驱动 =
``scripts/s6i1_retention_mutation_kill.py``。

反例映射（每项具名 mutation 对应）：

- S6-AUD-1 终态 + 365 天到期 run 被 prune（children-first：turn_inputs →
  run_events → compat_outputs → run）
- S6-AUD-2 非终态 / 未到期 run 不候选
- S6-AUD-3 events payload 未全 tombstone → blocked 零写
- S6-AUD-4 outcome_unknown 未解决 → blocked；解决后可删
- S6-AUD-5 approval.requested 未解决 → blocked；解决后可删
- S6-AUD-6 projection reconcile 未完成（output_publish_state / outbox / inbox）→ blocked
- S6-AUD-7 存活子 run → blocked；子 run 删除后可删
- S6-AUD-8 active hold 阻塞；过期 hold（裁决一）不阻塞
- S6-AUD-9 tenant scope 隔离
- S6-AUD-10 幂等重入
- S6-AUD-11 已 purge conversation 短路（events 已 tombstone → 可删）
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.composition.retention_workers import run_audit_retention

pytestmark = pytest.mark.asyncio

_DIGEST = "a" * 64


async def _seed_conversation(session, *, tid=None, cid=None, purged: bool = False):
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
            "'deleted', now() - interval '1 day', 'completed', 1, :purged_at, 0, 1, "
            "1, 1, now(), now(), now())"
        ),
        {
            "cid": cid, "tid": tid, "digest": _DIGEST,
            "purged_at": datetime.now(UTC) if purged else None,
        },
    )
    return tid, cid


async def _seed_catalog(session, *, tid):
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


async def _seed_terminal_run(
    session,
    *,
    tid,
    cid,
    status: str = "failed",
    ended_days_ago: int = 400,
    output_publish_state: str = "not_required",
    parent_run_id: uuid.UUID | None = None,
    queue_seq: int = 1,
):
    """终态 run（默认 failed，非 completed 简化 terminal output envelope）。
    同一 conversation 内多个 run 必须传不同 ``queue_seq``（uq_agent_run_queue_seq）。"""
    run_id = uuid.uuid4()
    def_id, prof_id = await _seed_catalog(session, tid=tid)
    ended_at = datetime.now(UTC) - timedelta(days=ended_days_ago)
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_runs "
            "(id, tenant_id, conversation_id, queue_seq, root_input_message_id, "
            "agent_definition_version_id, runtime_profile_id, creation_digest, status, "
            "status_revision, next_event_seq, first_available_event_seq, last_event_seq, "
            "event_log_complete, queued_at, ended_at, terminal_code, terminal_reason, "
            "terminal_result_digest, output_publish_state, created_by, actor_state, "
            "actor_identity_digest, correlation_id, runtime_capability_snapshot, "
            "run_config_snapshot, budget_snapshot, usage_summary, parent_run_id, "
            "created_at, updated_at) "
            "VALUES (:rid, :tid, :cid, :qseq, :rid, :def_id, :prof_id, :digest, :status, "
            "1, 2, 1, 1, true, now() - interval '400 days', :ended_at, 'fail', "
            "'test failure', :digest, :opstate, :tid, 'present', NULL, :rid, "
            "'{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, :parent, "
            "now() - interval '400 days', now() - interval '400 days')"
        ),
        {
            "rid": run_id, "tid": tid, "cid": cid, "qseq": queue_seq,
            "def_id": def_id, "prof_id": prof_id,
            "digest": _DIGEST, "status": status, "ended_at": ended_at,
            "opstate": output_publish_state, "parent": parent_run_id,
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
    event_type: str = "run.failed",
    payload_state: str = "redacted",
    payload_ref: str | None = None,
    persisted_at: datetime | None = None,
):
    classification = "public"
    payload_inline: dict | None = None
    if payload_state == "inline":
        payload_inline = {"summary": f"evt-{seq}"}
    elif payload_state == "external":
        classification = "internal"
        payload_ref = payload_ref or f"ref-{run_id}-{seq}"
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_run_events "
            "(id, tenant_id, conversation_id, run_id, seq, event_type, schema_version, "
            "occurred_at, persisted_at, visibility, classification, payload_inline, "
            "payload_ref, payload_state, payload_digest, payload_size, media_type, "
            "expires_at, correlation_id, causation_id) "
            "VALUES (gen_random_uuid(), :tid, :cid, :rid, :seq, :etype, 1, "
            ":persisted_at, :persisted_at, 'user', :class, cast(:inline as jsonb), :ref, "
            ":state, :digest, 1, 'application/json', NULL, :rid, NULL)"
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
            "state": payload_state, "digest": _DIGEST,
        },
    )


async def _seed_turn_input(session, *, tid, run_id):
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_turn_inputs "
            "(id, tenant_id, run_id, ordinal, input_kind, message_id, request_id, "
            "expected_runtime_epoch, context_digest, created_by, actor_state, "
            "actor_identity_digest, created_at) "
            "VALUES (gen_random_uuid(), :tid, :rid, 0, 'root', gen_random_uuid(), "
            "gen_random_uuid(), NULL, :digest, :tid, 'present', NULL, now())"
        ),
        {"tid": tid, "rid": run_id, "digest": _DIGEST},
    )


async def _seed_compat_output(session, *, tid, cid, run_id):
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_compatibility_outputs "
            "(id, tenant_id, conversation_id, run_id, output_ref, output_digest, "
            "response_digest, reply_text, response_envelope, payload_state, "
            "media_type, classification, created_at) "
            "VALUES (gen_random_uuid(), :tid, :cid, :rid, 'out-ref', :digest, "
            ":digest, 'reply', '{}'::jsonb, 'present', 'text/markdown', 'internal', "
            "now())"
        ),
        {"tid": tid, "cid": cid, "rid": run_id, "digest": _DIGEST},
    )


async def _seed_hold(session, *, tid, cid, expires_at=None, state="active"):
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


async def _seed_outbox(session, *, tid, cid, run_id, status="pending"):
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_execution_outbox "
            "(id, tenant_id, event_type, schema_version, aggregate_id, aggregate_type, "
            "payload_inline, payload_ref, payload_digest, correlation_id, causation_id, "
            "status, attempt_count, next_attempt_at, created_at, conversation_id, "
            "producer_purge_revision) "
            "VALUES (gen_random_uuid(), :tid, 'assistant_message.publish_requested.v1', "
            "1, :rid, 'agent_run', '{}'::jsonb, NULL, :digest, gen_random_uuid(), NULL, "
            ":status, 0, now(), now(), :cid, 1)"
        ),
        {"tid": tid, "cid": cid, "rid": run_id, "digest": _DIGEST, "status": status},
    )


async def _run_exists(session, *, tid, run_id) -> bool:
    return (
        await session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM metaedu.agent_runs "
                "WHERE tenant_id = :tid AND id = :rid)"
            ),
            {"tid": tid, "rid": run_id},
        )
    ) is True


# ---------------------------------------------------------------------------
# S6-AUD-1/2 基础 prune
# ---------------------------------------------------------------------------


async def test_terminal_run_pruned_children_first(session_factory):
    """S6-AUD-1：终态 + 365 天到期 run 被 prune；turn_inputs/events/compat_outputs
    全部随 run 删除（children-first 显式顺序）。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_id = await _seed_terminal_run(seed, tid=tid, cid=cid)
        await _seed_event(seed, tid=tid, cid=cid, run_id=run_id, seq=1, event_type="run.failed")
        await _seed_turn_input(seed, tid=tid, run_id=run_id)
        await _seed_compat_output(seed, tid=tid, cid=cid, run_id=run_id)

    result = await run_audit_retention(session_factory)

    assert result.runs_pruned == 1
    assert result.runs_blocked == 0
    async with session_factory() as verify:
        assert await _run_exists(verify, tid=tid, run_id=run_id) is False
        for table in ("agent_turn_inputs", "agent_run_events", "agent_compatibility_outputs"):
            count = await verify.scalar(
                text(
                    f"SELECT count(*) FROM metaedu.{table} "
                    "WHERE tenant_id = :tid AND run_id = :rid"
                ),
                {"tid": tid, "rid": run_id},
            )
            assert count == 0, f"{table} 应随 run 删除"


async def test_non_terminal_and_young_runs_not_candidates(session_factory):
    """S6-AUD-2：非终态（ended_at NULL）与未到期（<365 天）run 不候选，零 prune。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        old = await _seed_terminal_run(seed, tid=tid, cid=cid, ended_days_ago=400, queue_seq=1)
        young = await _seed_terminal_run(seed, tid=tid, cid=cid, ended_days_ago=100, queue_seq=2)
        # 非终态：running + ended_at NULL（复用 terminal run 然后改状态会违反 CHECK；
        # 直接种 running run）。
        run_running = uuid.uuid4()
        def_id, prof_id = await _seed_catalog(seed, tid=tid)
        await seed.execute(
            text(
                "INSERT INTO metaedu.agent_runs "
                "(id, tenant_id, conversation_id, queue_seq, root_input_message_id, "
                "agent_definition_version_id, runtime_profile_id, creation_digest, status, "
                "status_revision, next_event_seq, first_available_event_seq, last_event_seq, "
                "event_log_complete, queued_at, output_publish_state, created_by, actor_state, "
                "actor_identity_digest, correlation_id, runtime_capability_snapshot, "
                "run_config_snapshot, budget_snapshot, usage_summary, created_at, updated_at) "
                "VALUES (:rid, :tid, :cid, 3, :rid, :def_id, :prof_id, :digest, 'running', "
                "1, 2, 1, 1, true, now(), 'not_required', :tid, 'present', NULL, :rid, "
                "'{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, now(), now())"
            ),
            {
                "rid": run_running, "tid": tid, "cid": cid, "def_id": def_id,
                "prof_id": prof_id, "digest": _DIGEST,
            },
        )

    result = await run_audit_retention(session_factory)

    assert result.runs_pruned == 1
    async with session_factory() as verify:
        assert await _run_exists(verify, tid=tid, run_id=old) is False
        assert await _run_exists(verify, tid=tid, run_id=young) is True
        assert await _run_exists(verify, tid=tid, run_id=run_running) is True


# ---------------------------------------------------------------------------
# S6-AUD-3..7 blocked 前置
# ---------------------------------------------------------------------------


async def test_blocked_when_events_not_tombstoned(session_factory):
    """S6-AUD-3：events payload 未全 tombstone → blocked 零写（audit 不越权清
    payload；90 天 event retention 先行）。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_id = await _seed_terminal_run(seed, tid=tid, cid=cid)
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_id, seq=1,
            event_type="run.failed", payload_state="inline",
        )

    result = await run_audit_retention(session_factory)

    assert result.runs_blocked == 1
    assert result.blocked_reasons["events_payload_not_tombstoned"] == 1
    async with session_factory() as verify:
        assert await _run_exists(verify, tid=tid, run_id=run_id) is True


async def test_blocked_on_outcome_unknown_then_resolved(session_factory):
    """S6-AUD-4：``tool.outcome_unknown`` 无后续 tool resolve → blocked 零写；
    存在后续 tool resolve（tool.completed）→ 可删。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_blocked = await _seed_terminal_run(seed, tid=tid, cid=cid, queue_seq=1)
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_blocked, seq=1,
            event_type="tool.outcome_unknown",
        )
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_blocked, seq=2, event_type="run.failed",
        )
        run_resolved = await _seed_terminal_run(seed, tid=tid, cid=cid, queue_seq=2)
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_resolved, seq=1,
            event_type="tool.outcome_unknown",
        )
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_resolved, seq=2,
            event_type="tool.completed",
        )
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_resolved, seq=3, event_type="run.failed",
        )

    result = await run_audit_retention(session_factory)

    assert result.runs_blocked == 1
    assert result.blocked_reasons["outcome_unknown"] == 1
    assert result.runs_pruned == 1
    async with session_factory() as verify:
        assert await _run_exists(verify, tid=tid, run_id=run_blocked) is True
        assert await _run_exists(verify, tid=tid, run_id=run_resolved) is False


async def test_blocked_on_unresolved_approval_then_resolved(session_factory):
    """S6-AUD-5：``approval.requested`` 无对应 resolved/expired → blocked；存在
    ``approval.resolved`` → 可删。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_blocked = await _seed_terminal_run(seed, tid=tid, cid=cid, queue_seq=1)
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_blocked, seq=1,
            event_type="approval.requested",
        )
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_blocked, seq=2, event_type="run.failed",
        )
        run_resolved = await _seed_terminal_run(seed, tid=tid, cid=cid, queue_seq=2)
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_resolved, seq=1,
            event_type="approval.requested",
        )
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_resolved, seq=2,
            event_type="approval.resolved",
        )
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_resolved, seq=3, event_type="run.failed",
        )

    result = await run_audit_retention(session_factory)

    assert result.runs_blocked == 1
    assert result.blocked_reasons["unresolved_approval"] == 1
    assert result.runs_pruned == 1
    async with session_factory() as verify:
        assert await _run_exists(verify, tid=tid, run_id=run_blocked) is True
        assert await _run_exists(verify, tid=tid, run_id=run_resolved) is False


async def test_blocked_on_projection_pending_outbox_and_inbox(session_factory):
    """S6-AUD-6：projection reconcile 未完成——outbox 非终态行（pending）→ blocked；
    清 outbox 后 inbox processing 仍 blocked；全清后可删。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_id = await _seed_terminal_run(seed, tid=tid, cid=cid)
        await _seed_event(seed, tid=tid, cid=cid, run_id=run_id, seq=1, event_type="run.failed")
        await _seed_outbox(seed, tid=tid, cid=cid, run_id=run_id, status="pending")

    result = await run_audit_retention(session_factory)
    assert result.runs_blocked == 1
    assert result.blocked_reasons["projection_reconcile_incomplete"] == 1

    # 清 outbox → 仍 blocked（种 inbox processing receipt 行）。
    async with session_factory() as fix, fix.begin():
        await fix.execute(
            text(
                "DELETE FROM metaedu.agent_execution_outbox WHERE tenant_id = :tid"
            ),
            {"tid": tid},
        )
        await fix.execute(
            text(
                "INSERT INTO metaedu.agent_execution_inbox "
                "(id, tenant_id, consumer_name, event_id, event_type, schema_version, "
                "payload_digest, correlation_id, causation_id, status, created_at, "
                "conversation_id, producer_purge_revision) "
                "VALUES (gen_random_uuid(), :tid, 'dispatcher', gen_random_uuid(), "
                "'assistant_message.published.v1', 1, :digest, gen_random_uuid(), NULL, "
                "'processing', now(), :cid, 1)"
            ),
            {"tid": tid, "cid": cid, "digest": _DIGEST},
        )

    second = await run_audit_retention(session_factory)
    assert second.runs_blocked == 1
    assert second.blocked_reasons["projection_reconcile_incomplete"] == 1

    # 清 inbox → 可删。
    async with session_factory() as fix2, fix2.begin():
        await fix2.execute(
            text(
                "DELETE FROM metaedu.agent_execution_inbox WHERE tenant_id = :tid"
            ),
            {"tid": tid},
        )
    third = await run_audit_retention(session_factory)
    assert third.runs_pruned == 1


async def test_blocked_on_surviving_child_run(session_factory):
    """S6-AUD-7：父 run 存在**未到期**存活子 run（parent_run_id FK）→ blocked
    零写；子 run 到期（从账上移除）后父 run 可删。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        parent = await _seed_terminal_run(seed, tid=tid, cid=cid, queue_seq=1)
        await _seed_event(seed, tid=tid, cid=cid, run_id=parent, seq=1, event_type="run.failed")
        # 子 run 未到期（100 天 < 365 天）→ 存活子 run 阻塞父 run。
        child = await _seed_terminal_run(
            seed, tid=tid, cid=cid, parent_run_id=parent, queue_seq=2, ended_days_ago=100
        )
        await _seed_event(seed, tid=tid, cid=cid, run_id=child, seq=1, event_type="run.failed")

    result = await run_audit_retention(session_factory)
    assert result.runs_blocked == 1
    assert result.blocked_reasons["surviving_child_run"] == 1
    async with session_factory() as verify:
        assert await _run_exists(verify, tid=tid, run_id=parent) is True
        assert await _run_exists(verify, tid=tid, run_id=child) is True

    # 子 run 到期移除后，父 run 可删。
    async with session_factory() as fix, fix.begin():
        await fix.execute(
            text(
                "DELETE FROM metaedu.agent_run_events WHERE tenant_id = :tid AND run_id = :rid"
            ),
            {"tid": tid, "rid": child},
        )
        await fix.execute(
            text("DELETE FROM metaedu.agent_runs WHERE tenant_id = :tid AND id = :rid"),
            {"tid": tid, "rid": child},
        )
    second = await run_audit_retention(session_factory)
    assert second.runs_pruned == 1
    async with session_factory() as verify:
        assert await _run_exists(verify, tid=tid, run_id=parent) is False


# ---------------------------------------------------------------------------
# S6-AUD-8/9/10 hold + tenant scope + 幂等
# ---------------------------------------------------------------------------


async def test_hold_blocks_audit_prune(session_factory):
    """S6-AUD-8：active hold（expires_at NULL）阻塞 audit prune；过期 hold
    （裁决一）不阻塞。"""
    now = datetime.now(UTC)
    async with session_factory() as seed, seed.begin():
        tid_held, cid_held = await _seed_conversation(seed)
        await _seed_hold(seed, tid=tid_held, cid=cid_held, expires_at=None)
        held_run = await _seed_terminal_run(seed, tid=tid_held, cid=cid_held)
        await _seed_event(
            seed, tid=tid_held, cid=cid_held, run_id=held_run, seq=1,
            event_type="run.failed",
        )
        tid_expired, cid_expired = await _seed_conversation(seed)
        await _seed_hold(
            seed, tid=tid_expired, cid=cid_expired, expires_at=now - timedelta(days=30)
        )
        expired_run = await _seed_terminal_run(seed, tid=tid_expired, cid=cid_expired)
        await _seed_event(
            seed, tid=tid_expired, cid=cid_expired, run_id=expired_run, seq=1,
            event_type="run.failed",
        )

    result = await run_audit_retention(session_factory)

    assert result.runs_pruned == 1
    async with session_factory() as verify:
        assert await _run_exists(verify, tid=tid_held, run_id=held_run) is True
        assert await _run_exists(verify, tid=tid_expired, run_id=expired_run) is False


async def test_tenant_scope_isolation(session_factory):
    """S6-AUD-9：tenant A 的 hold 不影响 tenant B 的 run prune。"""
    async with session_factory() as seed, seed.begin():
        tid_a, cid_a = await _seed_conversation(seed)
        await _seed_hold(seed, tid=tid_a, cid=cid_a, expires_at=None)
        run_a = await _seed_terminal_run(seed, tid=tid_a, cid=cid_a)
        await _seed_event(seed, tid=tid_a, cid=cid_a, run_id=run_a, seq=1, event_type="run.failed")
        tid_b, cid_b = await _seed_conversation(seed)
        run_b = await _seed_terminal_run(seed, tid=tid_b, cid=cid_b)
        await _seed_event(seed, tid=tid_b, cid=cid_b, run_id=run_b, seq=1, event_type="run.failed")

    result = await run_audit_retention(session_factory)

    assert result.runs_pruned == 1
    async with session_factory() as verify:
        assert await _run_exists(verify, tid=tid_a, run_id=run_a) is True
        assert await _run_exists(verify, tid=tid_b, run_id=run_b) is False


async def test_idempotent_rerun(session_factory):
    """S6-AUD-10：重入不命中已删行——第二次运行零 prune。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed)
        run_id = await _seed_terminal_run(seed, tid=tid, cid=cid)
        await _seed_event(seed, tid=tid, cid=cid, run_id=run_id, seq=1, event_type="run.failed")

    first = await run_audit_retention(session_factory)
    assert first.runs_pruned == 1
    second = await run_audit_retention(session_factory)
    assert second.runs_pruned == 0


async def test_purged_conversation_shortcut(session_factory):
    """S6-AUD-11：conversation 已 purge（purged_at 非空）→ events payload 已被
    purge 全部 redacted → 前置自动满足，run 可删。"""
    async with session_factory() as seed, seed.begin():
        tid, cid = await _seed_conversation(seed, purged=True)
        run_id = await _seed_terminal_run(seed, tid=tid, cid=cid)
        await _seed_event(
            seed, tid=tid, cid=cid, run_id=run_id, seq=1,
            event_type="run.failed", payload_state="redacted",
        )

    result = await run_audit_retention(session_factory)
    assert result.runs_pruned == 1
    async with session_factory() as verify:
        assert await _run_exists(verify, tid=tid, run_id=run_id) is False
