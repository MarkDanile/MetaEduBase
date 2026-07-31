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
``ExecutionRepository``（writer 原语），不复制 fence/lock 逻辑。

M1a（本 commit）只注入 ``create_run_with_root``（M1b 注入其余 8 个 writer）。
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

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

    async def require_active_fence(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, source_key: str
    ):
        """verdict：owner lock + fence FOR UPDATE，state=active 才放行。

        实际是 ``AgentErasureRepository.require_body_write_fence_for_update`` 的薄
        包装，统一 fenced port 入口语义。advance 由 ``advance_run_event_checkpoint`` 负责。
        """
        return await self._erasure.require_body_write_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=self.EXECUTION_OWNER_KEY,
            now=None,
        )

    async def advance_run_event_checkpoint(
        self,
        *,
        fence,
        conversation_id: uuid.UUID,
        epoch: int,
    ) -> None:
        """advance：run_event_payload 计数器 ``+1``（仅 caller 持有 created=True 时调）。

        watermark 暂取 ``0`` 占位（per-Conversation 真实基数在 M1b 由各 writer
        注入时传入）。Advance 持久化于 fence.ingress_checkpoint，IDEMPOTENT_REPLAY
        / 命中 existing 不调用本方法（无 created 标志）。
        """
        await self._erasure.advance_ingress_checkpoint_for_update(
            tenant_id=fence.tenant_id,
            conversation_id=conversation_id,
            owner_key=self.EXECUTION_OWNER_KEY,
            source_key=self.RUN_EVENT_SOURCE_KEY,
            watermark=0,
            epoch=epoch,
        )
