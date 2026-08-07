"""S3-C Writer fence：composition-owned fenced execution port。

契约注记（plan §R1-S3 S3 契约注记 round-1/round-2）：

- 所有 production 入口经此 port 调执行 writer；port 在 Guard + Conversation 行锁内
  做 fence 裁决（verdict）+ checkpoint 推进（advance）。
- 9 writer 入口：create_run_with_root / start_run / transition_run /
  mark_run_resume_required / resume_run / commit_terminal / append_event /
  ingest_runtime_event / CompatibilityOutputService.stage。
- advance 仅在 writer 返回 ``created=True``（真实新插入）时调用；
  IDEMPOTENT_REPLAY / 命中 existing 不推进计数器。
- 跨 owner source key fail closed（已在 erasure_repository 闭集校验）。
- **锁序**（round-3 P1-1 修正）：调用方必须先持 Guard + Conversation 行锁，
  再调 ``require_active_fence``（owner lock + fence FOR UPDATE）。
  ``dispatch_turn`` 中 ``consume_turn_event`` 已持 Guard + Conversation 行锁，
  port verdict 在其后调用。

本模块组合既有 ``AgentErasureRepository``（verdict/advance 原语）和
``RunCoordinator`` / ``CompatibilityOutputService``（writer 原语），不复制 fence/lock 逻辑。

**source key 语义**（round-3 P1-3/P1-4 修正）：
- ``run_context_body``：watermark = Run ``queue_seq``（create_run 推进）。
- ``run_output_body``：watermark = Run ``queue_seq``（commit_terminal 推进）。
- ``compatibility_output``：watermark = Run ``queue_seq``（stage 推进）。
- ``run_event_payload``：watermark = per-Conversation 单调递增计数器（每个新 event +1）。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.compatibility_output_service import (
    CompatibilityOutputService,
)
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_execution.domain import (
    RunConversationMismatchError,
    RuntimeIngestIdentityMismatchError,
)
from app.contexts.agent_workspace.domain.erasure import ErasureFenceState
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import ConversationModel

_EXECUTION_OWNER_KEY = "execution.core.v1"
_RUN_EVENT_SOURCE_KEY = "run_event_payload"


class FencedExecutionPort:
    """composition-owned fenced execution port（单一受控入口）。

    **锁序前置**：调用方必须先持 Guard + Conversation 行锁（Spec §6.1）。
    本 port 的 ``require_active_fence`` 在此前提下取 owner lock + fence FOR UPDATE。
    """

    EXECUTION_OWNER_KEY = _EXECUTION_OWNER_KEY
    RUN_EVENT_SOURCE_KEY = _RUN_EVENT_SOURCE_KEY

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._erasure = AgentErasureRepository(session)
        self._runs = RunCoordinator(session)
        self._compat = CompatibilityOutputService(session)

    # --- identity binding -------------------------------------------------

    async def _require_run_identity(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        queue_seq: int | None = None,
    ) -> None:
        """R1-S3-C round-7：caller 传 (tenant, conv, run, queue_seq) 必须与
        AgentRun 自身字段一致，防止 Conversation A 的 active fence 授权
        Conversation B 的 writer。

        ``queue_seq`` 仅 fenced_create_run / fenced_commit_terminal / fenced_stage
        涉及（其他 writer 不接收 queue_seq，调用方传 None 跳过校验）。
        """
        run = await self._runs.require_run(
            tenant_id=tenant_id, run_id=run_id
        )
        if run.conversation_id != conversation_id:
            raise RunConversationMismatchError(
                f"Run {run_id} belongs to conversation {run.conversation_id}, "
                f"not {conversation_id}"
            )
        if queue_seq is not None and run.queue_seq != queue_seq:
            raise RunConversationMismatchError(
                f"Run {run_id} queue_seq is {run.queue_seq}, "
                f"caller supplied {queue_seq}"
            )

    def _require_frame_identity(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        command,
    ) -> None:
        """R1-S3-C round-7：``fenced_ingest_runtime_event`` 的 frame 身份
        （``command.frame.tenant_id / frame.conversation_id / frame.run_id``）
        必须等于外层 ``tenant_id / conversation_id / run_id``，避免 Runtime 通道
        绕过 fenced port 校验（跨 Conversation 写）。
        """
        frame = command.frame
        if frame.tenant_id != tenant_id:
            raise RuntimeIngestIdentityMismatchError(
                f"Runtime frame tenant_id {frame.tenant_id} does not match "
                f"outer tenant_id {tenant_id}"
            )
        if frame.conversation_id != conversation_id:
            raise RuntimeIngestIdentityMismatchError(
                f"Runtime frame conversation_id {frame.conversation_id} does "
                f"not match outer conversation_id {conversation_id}"
            )
        if frame.run_id != run_id:
            raise RuntimeIngestIdentityMismatchError(
                f"Runtime frame run_id {frame.run_id} does not match "
                f"outer run_id {run_id}"
            )

    def _require_fence_identity(
        self,
        *,
        fence,
        conversation_id: uuid.UUID,
    ) -> None:
        """R1-S3-C round-7 commit-13：``advance_checkpoint`` 必须验证
        ``fence.conversation_id == conversation_id``，防止用 Conversation A
        的 active fence 快照推进 Conversation B 的 checkpoint（即使 caller
        已通过 ``_require_run_identity`` 校验 Run 归属，fence 本身仍是
        按 ``(tenant, conv, owner_key)`` 加载，跨 Conv 调用会让 fence
        状态错配）。
        """
        if fence.conversation_id != conversation_id:
            raise RunConversationMismatchError(
                f"Fence {fence.owner_key} belongs to conversation "
                f"{fence.conversation_id}, not {conversation_id}"
            )

    # --- verdict ---------------------------------------------------------

    async def require_active_fence(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ):
        """verdict：owner lock + fence FOR UPDATE，state=active 才放行。

        **前置**：调用方已持 Guard + Conversation 行锁（Spec §6.1 锁序）。
        """
        return await self._erasure.require_body_write_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=_EXECUTION_OWNER_KEY,
            now=None,
        )

    async def read_fence_state(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> ErasureFenceState:
        """R1-S4-C（S4-C R4）：**非抛**读取 execution fence 状态（epoch 分类用）。

        与 ``require_active_fence`` 不同：fence 非 active 时**不 raise**，返回
        真实状态供 ``classify_consume_epoch`` 判定 stale（fence erasing/erased
        才 stale，round-5 P1-1：stale 走 Tx1/Tx2 双事务而非 raise）。owner lock
        + fence FOR UPDATE 与 require 同序（Guard -> Conversation -> owner ->
        fence），缺 fence 按 registry 惰性建 active（与 require 同语义）。仅读
        状态不裁决、不推进 checkpoint。
        """
        from app.composition.agent_erasure_locks import acquire_owner_lock

        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=_EXECUTION_OWNER_KEY,
        )
        fence = await self._erasure.get_or_create_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=_EXECUTION_OWNER_KEY,
            now=None,
        )
        return fence.state

    async def conversation_purge_revision(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> int:
        """R1-S4-C（S4-C C1）：execution 侧 producer epoch 的真实来源。

        读取 ``Conversation.purge_revision`` 并**自持 Conversation 行锁
        （FOR UPDATE，round-1 P1-2 修订）**——不依赖调用方已持锁的隐式约定，
        R1 的「行锁内同事务读取」由本方法自身保证。**不得**用 fence CAS
        revision / fence ``purge_revision``（对齐值非快照）/ Conversation
        revision / 时间戳冒充（R1）。
        """
        value = (
            await self._session.execute(
                select(ConversationModel.purge_revision)
                .where(
                    ConversationModel.tenant_id == tenant_id,
                    ConversationModel.id == conversation_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if value is None:
            raise RunConversationMismatchError(
                f"conversation {conversation_id} not found for producer epoch"
            )
        return int(value)

    # --- advance 原语 ----------------------------------------------------

    async def advance_checkpoint(
        self,
        *,
        fence,
        conversation_id: uuid.UUID,
        source_key: str,
        watermark: int,
    ) -> None:
        """advance：按 ``source_key`` + ``watermark`` 推进 fence.ingress_checkpoint。

        - per-Run source key（``run_context_body`` / ``run_output_body`` /
          ``compatibility_output``）：watermark = Run ``queue_seq``。
        - ``run_event_payload``：watermark = per-Conversation 计数器（current + 1）。
        epoch 取自 ``fence.purge_revision``。
        """
        if source_key == _RUN_EVENT_SOURCE_KEY:
            sources = fence.ingress_checkpoint.get("sources", {})
            existing_entry = sources.get(_RUN_EVENT_SOURCE_KEY)
            current_watermark = (
                int(existing_entry.get("watermark", 0))
                if existing_entry is not None
                else 0
            )
            watermark = current_watermark + 1
        # R1-S3-C round-7 commit-13：fence.conversation_id 必须等于 caller 传
        # 的 conversation_id，防跨 Conv 推进 checkpoint。
        self._require_fence_identity(
            fence=fence, conversation_id=conversation_id
        )
        await self._erasure.advance_ingress_checkpoint_for_update(
            tenant_id=fence.tenant_id,
            conversation_id=conversation_id,
            owner_key=_EXECUTION_OWNER_KEY,
            source_key=source_key,
            watermark=watermark,
            epoch=fence.purge_revision,
        )

    # --- writer 包装 -----------------------------------------------------

    async def fenced_create_run(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        queue_seq: int,
    ) -> None:
        """create_run 后推进 ``run_context_body=queue_seq``。

        仅在 ``created=True``（真实新建）时由 caller 调用本方法。
        R1-S3-C round-7：校验 caller 传 (tenant, conv, queue_seq) 与刚
        创建的 Run 一致（防跨 Conversation 写 watermark）。
        """
        await self._require_run_identity(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
            queue_seq=queue_seq,
        )
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        await self.advance_checkpoint(
            fence=fence,
            conversation_id=conversation_id,
            source_key="run_context_body",
            watermark=queue_seq,
        )

    async def fenced_append_event(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        event,
    ):
        """append_event 后推进 ``run_event_payload`` 计数器 +1。

        R1-S3-C round-7 commit-4：保留原 writer 返回值 RunEvent（原
        RunCoordinator.append_event 直接返回 RunEvent）。
        """
        await self._require_run_identity(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
        )
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        run_event = await self._runs.append_event(
            tenant_id=tenant_id, run_id=run_id, event=event
        )
        await self.advance_checkpoint(
            fence=fence,
            conversation_id=conversation_id,
            source_key=_RUN_EVENT_SOURCE_KEY,
            watermark=0,  # advance_checkpoint 内部 +1
        )
        return run_event

    async def fenced_commit_terminal(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        queue_seq: int,
        expected_status,
        expected_revision: int,
        result,
        cancel_intent_revision: int | None = None,
    ):
        """commit_terminal 后推进 ``run_output_body=queue_seq`` + event 计数器。

        ``commit_terminal`` 返回 ``(run, event, terminal_digest_match)``；
        ``terminal_digest_match=True``（idempotent replay）不推进。
        R1-S3-C round-7 commit-10：透传 ``cancel_intent_revision`` 到
        RunCoordinator.commit_terminal（commit-11 在仓库层做 cancel intent
        CAS 校验 + status_revision 校验 + terminal 拒绝）。
        """
        await self._require_run_identity(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
            queue_seq=queue_seq,
        )
        # PR-A round-2 P2 认知（PR-B 批次1 落地）：producer epoch 读**前置**
        # require_active_fence——先取 Conversation 行锁再取 owner/fence，与
        # purge eraser（Conversation -> owner -> fence）同序。R1 的「行锁内同
        # 事务读取」由 conversation_purge_revision 自持 FOR UPDATE 保证，且锁
        # 序不再依赖调用方预持的隐式前置。
        producer_purge_revision = await self.conversation_purge_revision(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        run, event, terminal_digest_match = await self._runs.commit_terminal(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_status=expected_status,
            expected_revision=expected_revision,
            result=result,
            cancel_intent_revision=cancel_intent_revision,
            producer_purge_revision=producer_purge_revision,
        )
        if not terminal_digest_match:
            await self.advance_checkpoint(
                fence=fence,
                conversation_id=conversation_id,
                source_key="run_output_body",
                watermark=queue_seq,
            )
            await self.advance_checkpoint(
                fence=fence,
                conversation_id=conversation_id,
                source_key=_RUN_EVENT_SOURCE_KEY,
                watermark=0,  # +1
            )
        return run, event, terminal_digest_match

    async def fenced_stage(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        queue_seq: int,
        output_ref: str,
        reply: str,
        response_envelope: dict,
    ):
        """stage 后推进 ``compatibility_output=queue_seq``。

        ``stage`` 返回 ``(snapshot, created)``；``created=False`` 不推进。
        R1-S3-C round-7：caller 传 queue_seq 必须与 Run 一致。
        """
        await self._require_run_identity(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
            queue_seq=queue_seq,
        )
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        snapshot, created = await self._compat.stage_with_created(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
            output_ref=output_ref,
            reply=reply,
            response_envelope=response_envelope,
        )
        if created:
            await self.advance_checkpoint(
                fence=fence,
                conversation_id=conversation_id,
                source_key="compatibility_output",
                watermark=queue_seq,
            )
        return snapshot, created

    async def fenced_start_run(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_revision: int,
        start_barrier=None,
    ) -> tuple:
        """start_run 后推进 ``run_event_payload`` 计数器 +1。

        ``start_barrier`` 可选：workspace integration 注入
        ``WorkspaceRunStartBarrier``（actor_id 校验）。
        R1-S3-C round-7：caller 传 (tenant, conv, run_id) 必须与 Run 一致。
        """
        await self._require_run_identity(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
        )
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        runs = self._runs if start_barrier is None else RunCoordinator(
            self._session, start_barrier=start_barrier
        )
        run, event = await runs.start_run(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_revision=expected_revision,
        )
        await self.advance_checkpoint(
            fence=fence,
            conversation_id=conversation_id,
            source_key=_RUN_EVENT_SOURCE_KEY,
            watermark=0,  # +1
        )
        return run, event

    async def fenced_transition_run(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_status,
        expected_revision: int,
        target_status,
        summary: str,
        cancel_intent_revision: int | None = None,
    ) -> tuple:
        """transition_run 后推进 ``run_event_payload`` 计数器 +1。

        R1-S3-C round-7 commit-10：透传 ``cancel_intent_revision`` 到
        RunCoordinator.transition_run（commit-11 在仓库层做 cancel intent
        CAS 校验 + status_revision 校验 + terminal 拒绝）。
        R1-S3-C round-7 commit-3：caller 传 (tenant, conv, run_id) 必须与 Run 一致。
        """
        await self._require_run_identity(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
        )
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        run, event = await self._runs.transition_run(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_status=expected_status,
            expected_revision=expected_revision,
            target_status=target_status,
            summary=summary,
            cancel_intent_revision=cancel_intent_revision,
        )
        await self.advance_checkpoint(
            fence=fence,
            conversation_id=conversation_id,
            source_key=_RUN_EVENT_SOURCE_KEY,
            watermark=0,  # +1
        )
        return run, event

    async def fenced_mark_run_resume_required(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_status,
        expected_run_revision: int,
        expected_runtime_epoch: int,
        expected_binding_revision: int,
        summary: str,
    ) -> tuple:
        """mark_run_resume_required 后推进 ``run_event_payload`` 计数器 +1。

        R1-S3-C round-7 commit-4：保留原 writer 返回值
        ``(AgentRun, RunEvent, RuntimeSessionBinding)``（之前 round-6
        丢弃了 binding）。
        """
        await self._require_run_identity(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
        )
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        run, event, binding = await self._runs.mark_run_resume_required(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_status=expected_status,
            expected_run_revision=expected_run_revision,
            expected_runtime_epoch=expected_runtime_epoch,
            expected_binding_revision=expected_binding_revision,
            summary=summary,
        )
        await self.advance_checkpoint(
            fence=fence,
            conversation_id=conversation_id,
            source_key=_RUN_EVENT_SOURCE_KEY,
            watermark=0,  # +1
        )
        return run, event, binding

    async def fenced_resume_run(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        expected_run_revision: int,
        expected_runtime_epoch: int,
        expected_binding_revision: int,
        runtime_session_ref: str,
        summary: str,
    ) -> tuple:
        """resume_run 后推进 ``run_event_payload`` 计数器 +1。

        R1-S3-C round-7 commit-4：保留原 writer 返回值
        ``(AgentRun, RunEvent, RuntimeSessionBinding)``（之前 round-6
        丢弃了 binding）。
        """
        await self._require_run_identity(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
        )
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        run, event, binding = await self._runs.resume_run(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_run_revision=expected_run_revision,
            expected_runtime_epoch=expected_runtime_epoch,
            expected_binding_revision=expected_binding_revision,
            runtime_session_ref=runtime_session_ref,
            summary=summary,
        )
        await self.advance_checkpoint(
            fence=fence,
            conversation_id=conversation_id,
            source_key=_RUN_EVENT_SOURCE_KEY,
            watermark=0,  # +1
        )
        return run, event, binding

    async def fenced_ingest_runtime_event(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        command,
    ):
        """ingest_runtime_event 后推进 ``run_event_payload`` 计数器 +1。

        R1-S3-C round-7：校验 ``command.frame.tenant_id / frame.run_id``
        与外层一致（防止 Runtime 通道绕过 fenced port 校验）。
        Idempotent replay 不推进（writer 返回 ``idempotent_replay=True``）。
        """
        self._require_frame_identity(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
            command=command,
        )
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        result = await self._runs.ingest_runtime_event(command)
        if not result.idempotent_replay:
            await self.advance_checkpoint(
                fence=fence,
                conversation_id=conversation_id,
                source_key=_RUN_EVENT_SOURCE_KEY,
                watermark=0,  # +1
            )
        return result
