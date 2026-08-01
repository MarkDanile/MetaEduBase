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

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.compatibility_output_service import (
    CompatibilityOutputService,
)
from app.contexts.agent_execution.application.run_coordinator import RunCoordinator
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)

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
        queue_seq: int,
    ) -> None:
        """create_run 后推进 ``run_context_body=queue_seq``（round-3 P1-3）。

        create_run 写 Run context + root TurnInput，不写 RunEvent。
        仅在 ``created=True``（真实新建）时由调用方调用本方法。
        """
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
    ) -> None:
        """append_event 后推进 ``run_event_payload`` 计数器 +1。"""
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        await self._runs.append_event(
            tenant_id=tenant_id, run_id=run_id, event=event
        )
        await self.advance_checkpoint(
            fence=fence,
            conversation_id=conversation_id,
            source_key=_RUN_EVENT_SOURCE_KEY,
            watermark=0,  # advance_checkpoint 内部 +1
        )

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
    ):
        """commit_terminal 后推进 ``run_output_body=queue_seq`` + event 计数器。

        commit_terminal 返回 (run, event, terminal_digest_match)；
        terminal_digest_match=True（idempotent replay）不推进。
        """
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        run, event, terminal_digest_match = await self._runs.commit_terminal(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_status=expected_status,
            expected_revision=expected_revision,
            result=result,
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

        round-3 P2-1：``stage`` 直接返回 ``created`` 标志（不二次探测）。
        """
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
        ``WorkspaceRunStartBarrier``（actor_id 校验）。默认 None 时 RunCoordinator
        使用 ``FailClosedRunStartBarrier``。
        """
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
    ) -> tuple:
        """transition_run 后推进 ``run_event_payload`` 计数器 +1。"""
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

        R1-S3-C round-6：plan §S3-C 9 writer 矩阵剩余 3 个 wrapper 之一。
        当前 production 无调用点（S3-E 接入），wrapper 与单测先就位。
        """
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        run, event, _binding = await self._runs.mark_run_resume_required(
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
        return run, event

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

        R1-S3-C round-6：plan §S3-C 9 writer 矩阵剩余 3 个 wrapper 之一。
        当前 production 无调用点（S3-E 接入），wrapper 与单测先就位。
        """
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        run, event, _binding = await self._runs.resume_run(
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
        return run, event

    async def fenced_ingest_runtime_event(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        command,
    ):
        """ingest_runtime_event 后推进 ``run_event_payload`` 计数器 +1。

        R1-S3-C round-6：plan §S3-C 9 writer 矩阵剩余 3 个 wrapper 之一。
        Runtime adapter 推迟到 S4 接入，本 wrapper 形态先就位。
        Idempotent replay 不推进（writer 返回 ``idempotent_replay=True``）。
        """
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
