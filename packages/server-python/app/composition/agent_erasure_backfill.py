"""R1-S1 baseline fence backfill（可恢复、幂等、分批、tenant 限流）。

为既有 Conversation 补当前已安装 owner 的 baseline ``active`` fence。设计约束：

- 不做单一全表大事务：每个 Conversation 一个短事务，崩溃/重启后从下一个
  Conversation 继续（幂等 INSERT ... ON CONFLICT DO NOTHING）。
- 幂等：同一 fence 重复写入不报错、不重复。
- 分批 + tenant 限流：调用方传 ``tenant_id``、``batch_size``、``max_conversations``
  控制单批规模；批间由调用方决定是否停顿。
- fail closed：owner registry 必须能解析全部 6 个固定 owner；任何无法可靠处理的
  Conversation 计入 ``failed``，不静默跳过。

R1-S1 只补 fence；不建立 purge operation、不改 Conversation purge_state、不清正文。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_registry import owner_registry, registry_digest
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    ErasureFenceModel,
)
from app.shared.schemas.canonical_json import canonical_digest


def _empty_ingress_digest() -> str:
    return canonical_digest({"ingress": {}, "schema_version": 1})


@dataclass(slots=True)
class BackfillReport:
    tenants_processed: int = 0
    conversations_scanned: int = 0
    fences_created: int = 0
    fences_already_present: int = 0
    failed_conversations: list[uuid.UUID] = field(default_factory=list)
    registry_digest: str = ""

    @property
    def ok(self) -> bool:
        return not self.failed_conversations


async def _select_conversation_batch(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    after_id: uuid.UUID | None,
    batch_size: int,
) -> list[uuid.UUID]:
    statement = (
        select(ConversationModel.id)
        .where(ConversationModel.tenant_id == tenant_id)
        .order_by(ConversationModel.id)
        .limit(batch_size)
    )
    if after_id is not None:
        statement = statement.where(ConversationModel.id > after_id)
    result = await session.execute(statement)
    return [row[0] for row in result.all()]


async def _backfill_conversation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> tuple[int, int]:
    """为单个 Conversation 幂等补全部 owner 的 fence。

    返回 (created, already_present)。调用方在独立事务中调用本函数。
    """
    created = 0
    already = 0
    ingress_digest = _empty_ingress_digest()
    for owner in owner_registry():
        statement = (
            insert(ErasureFenceModel)
            .values(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=owner.owner_key,
                owner_version=owner.owner_version,
                state="active",
                ingress_checkpoint={},
                ingress_digest=ingress_digest,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "conversation_id", "owner_key"]
            )
        )
        result = await session.execute(statement)
        rowcount = (
            result.rowcount if isinstance(result, CursorResult) else 0
        )
        if rowcount > 0:
            created += 1
        else:
            already += 1
    return created, already


async def backfill_baseline_fences(
    session_factory,
    *,
    tenant_id: uuid.UUID,
    batch_size: int = 100,
    max_conversations: int | None = None,
) -> BackfillReport:
    """为指定 tenant 的既有 Conversation 幂等补 baseline fence。

    每个 Conversation 在独立短事务中处理；任一失败计入 ``failed_conversations``
    并继续（fail closed 由 report.ok 体现，不静默通过）。
    """
    report = BackfillReport(registry_digest=registry_digest())
    # 触发 registry 解析；任何 owner 缺失会在首个 Conversation 前 fail closed。
    owner_registry()

    after_id: uuid.UUID | None = None
    processed = 0
    while True:
        async with session_factory() as session, session.begin():
            batch = await _select_conversation_batch(
                session,
                tenant_id=tenant_id,
                after_id=after_id,
                batch_size=batch_size,
            )
        if not batch:
            break
        for conversation_id in batch:
            if max_conversations is not None and processed >= max_conversations:
                return report
            try:
                async with session_factory() as session, session.begin():
                    created, already = await _backfill_conversation(
                        session,
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                    )
                report.fences_created += created
                report.fences_already_present += already
                report.conversations_scanned += 1
            except Exception:
                report.failed_conversations.append(conversation_id)
            processed += 1
            after_id = conversation_id
        # 终止条件：本批已处理完，且要么达到 max_conversations、要么本批
        # 已空/不足 batch_size（说明没有更多 Conversation）。达到
        # max_conversations 时不能因整批返回而误判为“还有更多”。
        if max_conversations is not None and processed >= max_conversations:
            break
        if len(batch) < batch_size:
            break
    report.tenants_processed = 1
    return report


async def count_conversations(session: AsyncSession, *, tenant_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(ConversationModel)
        .where(ConversationModel.tenant_id == tenant_id)
    )
    return int(result.scalar_one())
