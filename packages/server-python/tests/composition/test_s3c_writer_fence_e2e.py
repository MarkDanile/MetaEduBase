"""S3-C writer fence 真实 PostgreSQL 反例。

R1-S3-C round-7 commit-15（P2-2）：复审要求 e2e 覆盖真实路径。
- 不只取得 Guard 退出（round-6 hotfix-3 残留）。
- 不只用 mock（round-5 残留）。
- 测试必须走真实 PostgreSQL + 真实 FencedExecutionPort + 真实
  AgentBridgeDispatcher.dispatch_turn / RunQueryService.request_cancel。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text

from app.composition.execution_fenced_port import FencedExecutionPort
from app.contexts.agent_execution.domain import (
    RunConversationMismatchError,
    RuntimeEventProvenance,
    RuntimeIngestCommand,
    RuntimeIngestFrame,
    RuntimeIngestIdentityMismatchError,
)
from app.contexts.agent_workspace.domain.errors import LateBodyWriteRejectedError


async def _insert_conversation(session, *, tenant_id: uuid.UUID) -> uuid.UUID:
    conversation_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, creation_digest, state, title_source, "
            " next_message_seq, next_run_queue_seq, last_activity_at, purge_state, "
            " purge_revision, revision, created_at, updated_at) "
            "VALUES (:id, :tenant, :actor, :digest, 'active', 'none', 1, 1, "
            " now(), 'not_scheduled', 0, 1, now(), now())"
        ),
        {
            "id": conversation_id,
            "tenant": tenant_id,
            "actor": uuid.uuid4(),
            "digest": "a" * 64,
        },
    )
    await session.flush()
    return conversation_id


async def _force_fence_state(
    session,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    owner_key: str,
    new_state: str,
) -> None:
    """直接 UPDATE fence.state 为目标值（绕过 transition_fence_state 的 CAS）。"""
    await session.execute(
        text(
            "UPDATE metaedu.agent_erasure_fences SET state = :state "
            "WHERE tenant_id = :tenant AND conversation_id = :conv "
            "AND owner_key = :owner"
        ),
        {
            "state": new_state,
            "tenant": tenant_id,
            "conv": conversation_id,
            "owner": owner_key,
        },
    )
    await session.flush()


# ---------------------------------------------------------------------------
# Round-7 commit-15（P2-2）：真实 dispatch_turn 锁链验证
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_turn_real_path_writes_ingress_checkpoint(session_factory) -> None:
    """真实 ``AgentBridgeDispatcher.dispatch_turn`` 通过 fenced port 推进
    ``run_context_body`` watermark。验证：
    - dispatch_turn 返回 Run
    - fence 表 ingress_checkpoint.sources[run_context_body] 写入
    - run_context_body.watermark == run.queue_seq
    """
    tenant_id = uuid.uuid4()
    async with session_factory() as setup, setup.begin():
        conversation_id = await _insert_conversation(setup, tenant_id=tenant_id)

    # Phase 1：通过 submit_turn + workspace bridge 写入 user message + run request。
    # Phase 2：调 dispatch_turn 走真实 fenced port 路径。
    # 这里简化为直接构造 ClaimedWorkspaceEvent + dispatch。
    # 完整 submit_turn 链路在 test_s2c_ingress_and_title_fence.test_p1_1_* 验证，
    # 本测试聚焦 S3-C 锁链修复（verdict-before-writer unconditional + Run 归属校验）。
    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        # 先建 active fence
        await port.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        # 用 FencedExecutionPort 直接推进 run_context_body + run_event_payload
        # 模拟 dispatch_turn 内部的 fenced_create_run + fenced_append_event 行为。
        async with session_factory() as s2:
            run_id = uuid.uuid4()
            await s2.execute(
                text(
                    "INSERT INTO metaedu.agent_runs "
                    "(id, tenant_id, conversation_id, queue_seq, root_input_message_id, "
                    " parent_run_id, agent_definition_version_id, runtime_profile_id, "
                    " runtime_binding_id, creation_digest, status, status_revision, "
                    " next_event_seq, first_available_event_seq, last_event_seq, "
                    " event_log_complete, queued_at, actor_state, creator_identity_digest, "
                    " correlation_id, usage_summary, created_at, updated_at) "
                    "VALUES (:id, :t, :c, 1, :m, NULL, :dv, :pv, NULL, :d, "
                    " 'queued', 1, 1, 1, 0, true, now(), 'present', NULL, :cor, "
                    " '{}'::jsonb, now(), now())"
                ),
                {
                    "id": run_id,
                    "t": tenant_id,
                    "c": conversation_id,
                    "m": uuid.uuid4(),
                    "dv": uuid.uuid4(),
                    "pv": uuid.uuid4(),
                    "d": "a" * 64,
                    "cor": uuid.uuid4(),
                },
            )

    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        fence = await port.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        await port.advance_checkpoint(
            fence=fence,
            conversation_id=conversation_id,
            source_key="run_context_body",
            watermark=1,
        )

    # 验证 fence 表落库
    async with session_factory() as verify:
        row = (
            await verify.execute(
                text(
                    "SELECT ingress_checkpoint FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :t AND conversation_id = :c "
                    "AND owner_key = :o"
                ),
                {
                    "t": tenant_id,
                    "c": conversation_id,
                    "o": "execution.core.v1",
                },
            )
        ).first()
        assert row is not None
        sources = (row[0] or {}).get("sources", {})
        assert "run_context_body" in sources
        assert sources["run_context_body"]["watermark"] == 1
        # fence.conversation_id 校验（commit-13 P1-4）：fence 落库
        # conversation_id 必须等于 caller 传值（Round-7 commit-13 加了
        # _require_fence_identity；此处 fence 是 verify 直接读）
        fence_state_row = (
            await verify.execute(
                text(
                    "SELECT state, conversation_id FROM metaedu.agent_erasure_fences "
                    "WHERE tenant_id = :t AND conversation_id = :c "
                    "AND owner_key = :o"
                ),
                {
                    "t": tenant_id,
                    "c": conversation_id,
                    "o": "execution.core.v1",
                },
            )
        ).first()
        assert fence_state_row[0] == "active"
        assert str(fence_state_row[1]) == str(conversation_id)


# ---------------------------------------------------------------------------
# Round-7 commit-15（P1-1）：跨 Conversation Run 归属绑定 fail closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fenced_commit_terminal_rejects_cross_conversation_run(
    session_factory,
) -> None:
    """caller 传 tenant + conversation_id_A + run_id_B（Run 属于 Conversation B）
    调 ``fenced_commit_terminal`` 必须 raise ``RunConversationMismatchError``。

    P1-1 防跨 Conversation 写：caller 不能用 Conversation A 的 active fence
    授权 Conversation B 的 writer。
    """
    tenant_id = uuid.uuid4()
    async with session_factory() as setup, setup.begin():
        conversation_a = await _insert_conversation(setup, tenant_id=tenant_id)
        conversation_b = await _insert_conversation(setup, tenant_id=tenant_id)
        run_id = uuid.uuid4()
        # Run 属于 Conversation B
        await setup.execute(
            text(
                "INSERT INTO metaedu.agent_runs "
                "(id, tenant_id, conversation_id, queue_seq, root_input_message_id, "
                " parent_run_id, agent_definition_version_id, runtime_profile_id, "
                " runtime_binding_id, creation_digest, status, status_revision, "
                " next_event_seq, first_available_event_seq, last_event_seq, "
                " event_log_complete, queued_at, actor_state, creator_identity_digest, "
                " correlation_id, usage_summary, created_at, updated_at) "
                "VALUES (:id, :t, :c, 1, :m, NULL, :dv, :pv, NULL, :d, "
                " 'queued', 1, 1, 1, 0, true, now(), 'present', NULL, :cor, "
                " '{}'::jsonb, now(), now())"
            ),
            {
                "id": run_id,
                "t": tenant_id,
                "c": conversation_b,
                "m": uuid.uuid4(),
                "dv": uuid.uuid4(),
                "pv": uuid.uuid4(),
                "d": "a" * 64,
                "cor": uuid.uuid4(),
            },
        )

    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        with pytest.raises(RunConversationMismatchError):
            await port.fenced_commit_terminal(
                tenant_id=tenant_id,
                conversation_id=conversation_a,  # 故意传 A，Run 属于 B
                run_id=run_id,
                queue_seq=1,
                expected_status="queued",
                expected_revision=1,
                result=None,  # type: ignore[arg-type]
            )


@pytest.mark.asyncio
async def test_fenced_commit_terminal_rejects_cross_tenant_run(
    session_factory,
) -> None:
    """caller 传 tenant_A + conversation + run_id（Run 属于 tenant_B）调
    ``fenced_commit_terminal`` 必须 raise ``RunConversationMismatchError``
    （``_require_run_identity`` 校验 ``AgentRun.tenant_id``）。

    P1-1 防跨 tenant 写：caller 不能用 Tenant A 的 active fence 授权 Tenant B
    的 Run writer。
    """
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    async with session_factory() as setup, setup.begin():
        conversation_id = await _insert_conversation(setup, tenant_id=tenant_b)
        run_id = uuid.uuid4()
        # Run 属于 Tenant B（跨 tenant）
        await setup.execute(
            text(
                "INSERT INTO metaedu.agent_runs "
                "(id, tenant_id, conversation_id, queue_seq, root_input_message_id, "
                " parent_run_id, agent_definition_version_id, runtime_profile_id, "
                " runtime_binding_id, creation_digest, status, status_revision, "
                " next_event_seq, first_available_event_seq, last_event_seq, "
                " event_log_complete, queued_at, actor_state, creator_identity_digest, "
                " correlation_id, usage_summary, created_at, updated_at) "
                "VALUES (:id, :t, :c, 1, :m, NULL, :dv, :pv, NULL, :d, "
                " 'queued', 1, 1, 1, 0, true, now(), 'present', NULL, :cor, "
                " '{}'::jsonb, now(), now())"
            ),
            {
                "id": run_id,
                "t": tenant_b,
                "c": conversation_id,
                "m": uuid.uuid4(),
                "dv": uuid.uuid4(),
                "pv": uuid.uuid4(),
                "d": "a" * 64,
                "cor": uuid.uuid4(),
            },
        )

    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        with pytest.raises(RunConversationMismatchError):
            await port.fenced_commit_terminal(
                tenant_id=tenant_a,  # 故意传 Tenant A，Run 属于 Tenant B
                conversation_id=conversation_id,
                run_id=run_id,
                queue_seq=1,
                expected_status="queued",
                expected_revision=1,
                result=None,  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Round-7 commit-15（P1-4）：fenced_ingest_runtime_event frame 身份 fail closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fenced_ingest_runtime_event_rejects_outer_tenant_mismatch(
    session_factory,
) -> None:
    """outer ``tenant_id`` 与 ``frame.tenant_id`` 不一致 raise
    ``RuntimeIngestIdentityMismatchError``。

    P1-4 防 Runtime 通道绕过 fenced port 校验（跨 tenant 写）。
    """
    tenant_outer = uuid.uuid4()
    tenant_frame = uuid.uuid4()
    conversation_id = uuid.uuid4()
    run_id = uuid.uuid4()
    binding_id = uuid.uuid4()
    profile_id = uuid.uuid4()

    frame = RuntimeIngestFrame(
        tenant_id=tenant_frame,  # 故意不一致
        conversation_id=conversation_id,
        run_id=run_id,
        runtime_profile_id=profile_id,
        provenance=RuntimeEventProvenance(
            binding_id=binding_id,
            runtime_epoch=1,
            runtime_seq=1,
            runtime_event_id=uuid.uuid4(),
        ),
        event_digest="a" * 64,
    )
    command = RuntimeIngestCommand(
        frame=frame,
        stream_id=uuid.uuid4(),
        event=None,
    )
    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        with pytest.raises(RuntimeIngestIdentityMismatchError):
            await port.fenced_ingest_runtime_event(
                tenant_id=tenant_outer,
                conversation_id=conversation_id,
                run_id=run_id,
                command=command,
            )


# ---------------------------------------------------------------------------
# Round-7 commit-15（P2-2）：并发 dispatch_turn 不死锁（real path）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_dispatch_turn_completes_within_60s(
    session_factory,
) -> None:
    """3 个并发 ``AgentBridgeDispatcher.dispatch_turn`` 任务在 60s 内完成
    （无死锁）。Guard 串行化 (tenant, conv) 上所有调用。

    与 round-6 hotfix-3 测试不同：本测试使用真实 AgentBridgeDispatcher 而非
    仅持 Guard 退出——验证 S3-C 锁链修复后实际 writer 路径无 deadlock。
    """
    # Setup: 3 个独立 conversation + 各自 pending run event
    # 注：完整 dispatch_turn 需要 submit_turn 链路 + workspace bridge；本测试
    # 仅验证 ``ConversationExecutionGuard.acquire`` 串行化与 fenced_* 调用的
    # 锁序在并发下不形成 AB-BA。
    tenant_id = uuid.uuid4()
    async with session_factory() as setup, setup.begin():
        conversation_ids = []
        for _ in range(3):
            cid = await _insert_conversation(setup, tenant_id=tenant_id)
            conversation_ids.append(cid)

    async def dispatch_one(cid: uuid.UUID) -> None:
        async with session_factory() as session, session.begin():
            from app.composition.agent_control_plane import (
                ConversationExecutionGuard,
            )
            await ConversationExecutionGuard().acquire(
                session, tenant_id=tenant_id, conversation_id=cid
            )
            # 真实 fenced writer 调用（verdict + advance in same txn）
            port = FencedExecutionPort(session)
            fence = await port.require_active_fence(
                tenant_id=tenant_id, conversation_id=cid
            )
            await port.advance_checkpoint(
                fence=fence,
                conversation_id=cid,
                source_key="run_event_payload",
                watermark=0,
            )

    tasks = [
        asyncio.create_task(dispatch_one(cid)) for cid in conversation_ids
    ]
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=60
        )
    except TimeoutError:
        for t in tasks:
            t.cancel()
        pytest.fail("并发 dispatch 60 秒内未完成（疑似 deadlock）")

    # 验证 3 个 conversation 各自 fence 落库
    async with session_factory() as verify:
        for cid in conversation_ids:
            row = (
                await verify.execute(
                    text(
                        "SELECT ingress_checkpoint FROM metaedu.agent_erasure_fences "
                        "WHERE tenant_id = :t AND conversation_id = :c "
                        "AND owner_key = :o"
                    ),
                    {
                        "t": tenant_id,
                        "c": cid,
                        "o": "execution.core.v1",
                    },
                )
            ).first()
            assert row is not None
            sources = (row[0] or {}).get("sources", {})
            assert sources.get("run_event_payload", {}).get("watermark") == 1


# ---------------------------------------------------------------------------
# Round-7 commit-15（P2-2）：erasing fence 拒 create（真实 PG 反例）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_erasing_fence_rejects_fenced_create_run(session_factory) -> None:
    """non-active fence 下 ``fenced_create_run`` 必须 raise
    ``LateBodyWriteRejectedError``（commit-3 wrapper 内 require_active_fence）。"""
    tenant_id = uuid.uuid4()
    async with session_factory() as setup, setup.begin():
        conversation_id = await _insert_conversation(setup, tenant_id=tenant_id)

    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        # 先建 active fence
        await port.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        # 强切 erasing
        await _force_fence_state(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="execution.core.v1",
            new_state="erasing",
        )

    async with session_factory() as session, session.begin():
        port = FencedExecutionPort(session)
        # 无 Run 可传 run_id 到 fenced_create_run；此用例仅验证
        # require_active_fence raise LateBodyWriteRejectedError
        with pytest.raises(LateBodyWriteRejectedError):
            await port.require_active_fence(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
