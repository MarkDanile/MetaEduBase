"""S3-C Writer fence：composition-owned fenced execution port。

契约注记（plan §R1-S3 S3 契约注记 round-1/round-2）：

- 所有 production 入口经此 port 调执行 writer；port 在 Guard + Conversation 行锁内
  做 fence 裁决（verdict）+ checkpoint 推进（advance）。
- 9 writer 入口：create_run_with_root / start_run / transition_run /
  mark_run_resume_required / resume_run / commit_terminal / append_event /
  ingest_runtime_event / CompatibilityOutputService.stage。
- advance 仅在 writer 返回 ``created=True``（真实新插入）时调用 ``+1``；
  IDEMPOTENT_REPLAY / 命中 existing 不推进计数器。
- 跨 owner source key fail closed（已在 erasure_repository 闭集校验）。

本模块组合既有 ``AgentErasureRepository``（verdict/advance 原语）和
``RunCoordinator`` / ``CompatibilityOutputService``（writer 原语），不复制 fence/lock 逻辑。
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


class FencedExecutionPort:
    """composition-owned fenced execution port（单一受控入口）。"""

    EXECUTION_OWNER_KEY = "execution.core.v1"
    RUN_EVENT_SOURCE_KEY = "run_event_payload"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._erasure = AgentErasureRepository(session)
        self._runs = RunCoordinator(session)
        self._compat = CompatibilityOutputService(session)

    async def require_active_fence(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ):
        """verdict：owner lock + fence FOR UPDATE，state=active 才放行。"""
        return await self._erasure.require_body_write_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=self.EXECUTION_OWNER_KEY,
            now=None,
        )

    async def advance_run_event_checkpoint(
        self, *, fence, conversation_id: uuid.UUID, epoch: int
    ) -> None:
        """advance：run_event_payload 计数器 ``+1``（仅 created=True 时调）。"""
        await self._erasure.advance_ingress_checkpoint_for_update(
            tenant_id=fence.tenant_id,
            conversation_id=conversation_id,
            owner_key=self.EXECUTION_OWNER_KEY,
            source_key=self.RUN_EVENT_SOURCE_KEY,
            watermark=0,
            epoch=epoch,
        )

    async def fenced_append_event(
        self, *, tenant_id, conversation_id, run_id, event, epoch
    ) -> None:
        """fenced append_event：verdict + append + advance（append 总是新插入 -> created=True）。"""
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        await self._runs.append_event(
            tenant_id=tenant_id, run_id=run_id, event=event
        )
        await self.advance_run_event_checkpoint(
            fence=fence, conversation_id=conversation_id, epoch=epoch
        )

    async def fenced_commit_terminal(
        self, *, tenant_id, conversation_id, run_id, expected_status,
        expected_revision, result, epoch
    ):
        """fenced commit_terminal：verdict + commit + advance。

        commit_terminal 返回 (run, event, terminal_digest_match)；
        terminal_digest_match=True 表示 idempotent replay（terminal digest 命中），
        不推进计数器。
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
            await self.advance_run_event_checkpoint(
                fence=fence, conversation_id=conversation_id, epoch=epoch
            )
        return run, event, terminal_digest_match

    async def fenced_stage(
        self, *, tenant_id, conversation_id, run_id, output_ref, reply,
        response_envelope, epoch
    ):
        """fenced CompatibilityOutputService.stage：verdict + stage + advance（created=True 时）。

        stage 返回 snapshot（无 created 标志）；本方法通过 get_by_run 二次检查判断
        是否新插入（created=True）。round-2 P2-1 要求 writer 返回 created 标志禁止
        二次探测--但 stage 当前不支持，M1b 暂用二次检查（M2 改 stage 返回 created）。
        """
        fence = await self.require_active_fence(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        # 检查 existing（判断 created）
        existing = await self._compat._repository.get_by_run(
            tenant_id=tenant_id, run_id=run_id
        )
        snapshot = await self._compat.stage(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
            output_ref=output_ref,
            reply=reply,
            response_envelope=response_envelope,
        )
        created = existing is None
        if created:
            await self.advance_run_event_checkpoint(
                fence=fence, conversation_id=conversation_id, epoch=epoch
            )
        return snapshot, created
