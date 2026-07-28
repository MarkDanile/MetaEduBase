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


@dataclass(frozen=True, slots=True)
class BackfillFailure:
    """单个 Conversation 回填失败的稳定诊断信息（不持久化正文）。"""

    conversation_id: uuid.UUID
    reason_code: str
    error_type: str


@dataclass(slots=True)
class BackfillReport:
    tenants_processed: int = 0
    conversations_scanned: int = 0
    fences_created: int = 0
    fences_already_present: int = 0
    # 失败明细：稳定 reason_code + conversation_id + 异常类型（生产排障用，
    # 不持久化正文）。仅失败条目入列，条数远小于会话总数，内存有界。
    failures: list[BackfillFailure] = field(default_factory=list)
    # 下次调用的起始游标（最后一个已扫描 Conversation id）；处理完全部后为
    # 最后一个 id，调用方据此判断是否继续。
    next_after_id: uuid.UUID | None = None
    # True 表示本次在达到 max_conversations 前已扫描完 tenant 内全部
    # Conversation（即没有更多可处理）；``ok`` 只表示无失败，不代表已扫完。
    completed: bool = False
    registry_digest: str = ""

    @property
    def failed_conversations(self) -> list[uuid.UUID]:
        """失败 Conversation id 列表（向后兼容视图，源自 ``failures``）。"""
        return [failure.conversation_id for failure in self.failures]

    @property
    def ok(self) -> bool:
        """本次运行无失败。注意：``ok=True`` 不等于已处理完全部——
        需同时看 ``completed`` 或反复以 ``next_after_id`` 续跑到 completed。"""
        return not self.failures


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
    after_id: uuid.UUID | None = None,
) -> BackfillReport:
    """为指定 tenant 的既有 Conversation 幂等补 baseline fence。

    每个 Conversation 在独立短事务中处理；任一失败计入 ``failed_conversations``
    并继续（fail closed 由 report.ok 体现，不静默通过）。

    游标：``after_id`` 为 keyset 起始（只处理 id > after_id 的 Conversation）；
    报告带回 ``next_after_id`` 供下次续跑。bounded（``max_conversations``）调用
    必须串联该游标才能持续推进，否则会反复处理同一批头部 Conversation。
    """
    # 参数守卫（fail closed）：非法规模会产生“处理 0 个却 completed”的虚假结果。
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")
    if max_conversations is not None and max_conversations < 1:
        raise ValueError(
            f"max_conversations must be None or >= 1, got {max_conversations}"
        )

    report = BackfillReport(registry_digest=registry_digest())
    # 触发 registry 解析；任何 owner 缺失会在首个 Conversation 前 fail closed。
    owner_registry()

    processed = 0
    exhausted = False
    while True:
        async with session_factory() as session, session.begin():
            batch = await _select_conversation_batch(
                session,
                tenant_id=tenant_id,
                after_id=after_id,
                batch_size=batch_size,
            )
        if not batch:
            exhausted = True
            break
        for conversation_id in batch:
            if max_conversations is not None and processed >= max_conversations:
                report.next_after_id = after_id
                report.tenants_processed = 1
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
            except Exception as exc:
                report.failures.append(
                    BackfillFailure(
                        conversation_id=conversation_id,
                        reason_code="fence_insert_failed",
                        error_type=type(exc).__name__,
                    )
                )
            processed += 1
            after_id = conversation_id
        # 终止条件：达到 max_conversations，或本批不足 batch_size（没有更多）。
        if max_conversations is not None and processed >= max_conversations:
            break
        if len(batch) < batch_size:
            exhausted = True
            break
    report.next_after_id = after_id
    report.completed = exhausted
    report.tenants_processed = 1
    return report


async def count_conversations(session: AsyncSession, *, tenant_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(ConversationModel)
        .where(ConversationModel.tenant_id == tenant_id)
    )
    return int(result.scalar_one())


# ---------------------------------------------------------------------------
# 可执行入口（运维命令）：python -m app.composition.agent_erasure_backfill
#
# 退出码契约（自动化调用）：
#   0 = 全部完成且无失败；
#   1 = 有失败（report.failures 含稳定 reason_code）；
#   2 = 未完成（达到 --max-conversations 但未扫完），须以输出的 next_after_id
#       作为 --after-id 续跑直到 exit 0。
# ---------------------------------------------------------------------------


def _make_session_factory():
    """构造生产 session factory（独立可注入以便测试替换）。

    使用方负责在结束后 dispose 引擎；此处返回 (session_factory, engine)。
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings

    engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory, engine


async def _run_cli(args: object) -> int:
    factory, engine = _make_session_factory()
    try:
        after_id = uuid.UUID(args.after_id) if args.after_id else None  # type: ignore[attr-defined]
        report = await backfill_baseline_fences(
            factory,
            tenant_id=uuid.UUID(args.tenant_id),  # type: ignore[attr-defined]
            batch_size=args.batch_size,  # type: ignore[attr-defined]
            max_conversations=args.max_conversations,  # type: ignore[attr-defined]
            after_id=after_id,
        )
    finally:
        await engine.dispose()
    print(  # noqa: T201
        "backfill report: "
        f"scanned={report.conversations_scanned} "
        f"created={report.fences_created} "
        f"already_present={report.fences_already_present} "
        f"failed={len(report.failed_conversations)} "
        f"completed={report.completed} "
        f"next_after_id={report.next_after_id}"
    )
    # 退出码契约（自动化调用）：0=全部完成且无失败；1=有失败；2=未完成
    # （达到 max_conversations 但未扫完，须以 next_after_id 续跑）。
    if report.failed_conversations:
        for failure in report.failures:
            print(  # noqa: T201
                f"failed conversation: {failure.conversation_id} "
                f"reason={failure.reason_code} error={failure.error_type}"
            )
        return 1
    if not report.completed:
        print(  # noqa: T201
            f"incomplete: resume with --after-id {report.next_after_id}"
        )
        return 2
    return 0


def main() -> int:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(
        prog="python -m app.composition.agent_erasure_backfill",
        description="为既有 Conversation 幂等补 baseline erasure fence（可恢复/分批）。",
    )
    parser.add_argument("--tenant-id", required=True, help="目标 tenant UUID")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--max-conversations",
        type=int,
        default=None,
        help="单次最多处理的 Conversation 数（有界分批）；达到后由 next_after_id 续跑",
    )
    parser.add_argument(
        "--after-id",
        default=None,
        help="续跑游标：只处理 id 大于该值的 Conversation（上次报告的 next_after_id）",
    )
    return asyncio.run(_run_cli(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
