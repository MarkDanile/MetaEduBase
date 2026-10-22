"""TD-114 Agent identity 显式初始化编排（composition adapter + CLI 支撑）。

契约：docs/02-delivery-plans/01-specs/2026-10-19-td-114-agent-identity-bootstrap-contract.md
实施计划：docs/02-delivery-plans/02-plans/2026-10-19-td-114-agent-identity-bootstrap-plan.md

本模块是 TD-114 的唯一装配点：workspace 侧消费 ``AgentIdentityBootstrapPort``
声明的中性 ``BootstrapOutcome``，execution 侧的 ORM / 仓储 / 领域枚举 /
V1 冻结常量只在本模块出现（TD-085 依赖方向不变）。

V1 内容常量（payload 形状 + digest 输入）必须与
``ExecutionIdentityService.bootstrap_direct_rag``
（``execution_identity_service.py``）逐字一致；漂移由
``tests/composition/test_agent_identity_bootstrap.py`` 的等价钉住测试兜底
（直接比对本模块计算值与 bootstrap_direct_rag 实际写库值）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.execution_identity_service import (
    DIRECT_RAG_CAPABILITIES,
    DIRECT_RAG_DEFINITION_KEY,
    DIRECT_RAG_DEFINITION_VERSION,
    DIRECT_RAG_PROFILE_KEY,
)
from app.contexts.agent_execution.domain import (
    AgentDefinitionStatus,
    snapshot_digest,
)
from app.contexts.agent_execution.infrastructure.repository import (
    AgentExecutionIdentityRepository,
)
from app.contexts.agent_workspace.application.ports import (
    AgentIdentityBootstrapPort,
    BootstrapOutcome,
)
from app.contexts.identity.infrastructure.models import (
    TenantModel,
    UserModel,
)

# V1 冻结内容（与 bootstrap_direct_rag 的 payload 逐字一致；等价性由测试钉住）。
_V1_DEFINITION_DIGEST_PAYLOAD = {
    "definition_key": DIRECT_RAG_DEFINITION_KEY,
    "execution_mode": "compatibility",
    "schema_version": 1,
    "version": DIRECT_RAG_DEFINITION_VERSION,
}
_V1_PROFILE_CONFIG_PAYLOAD = {
    "adapter_key": "direct_rag",
    "profile_key": DIRECT_RAG_PROFILE_KEY,
    "runtime_kind": "compatibility",
    "schema_version": 1,
}
_V1_DEFINITION_DIGEST = snapshot_digest(_V1_DEFINITION_DIGEST_PAYLOAD)
_V1_PROFILE_CONFIG_DIGEST = snapshot_digest(_V1_PROFILE_CONFIG_PAYLOAD)
_V1_CAPABILITY_DIGEST = snapshot_digest(DIRECT_RAG_CAPABILITIES)
_V1_RUNTIME_KIND = "compatibility"
_V1_ADAPTER_KEY = "direct_rag"


class BootstrapIndeterminateError(Exception):
    """契约 §5 回读后仍无法确认目标行状态（显式失败，不静默）。"""


@dataclass(frozen=True, slots=True)
class TenantIdentityScan:
    """单个 tenant 的初始化执行/预测事实（CLI 统计口径）。"""

    tenant_id: uuid.UUID
    # 分类：missing（全缺失或部分缺失）/ complete / disabled / conflict / failed
    classification: str
    # 实写结果计数（dry-run 下恒 0）：created = 本事务实际插入行数（RETURNING 判定）
    created: int = 0
    skipped: int = 0
    # dry-run 下为预测将创建的行数；实写下恒 0
    would_create: int = 0
    # 失败/冲突说明（无则 None）；**有界**：仅前 ``_MAX_FAILURE_SAMPLES`` 个
    # failed/conflict tenant 保留 error 明细，超上限者 error=None（明细见
    # ``BackfillReport.failure_samples``，总数经 ``failed`` / 分类计数完整累计）。
    error: str | None = None


# 失败样本上限：超过后只累计计数，不再保留明细（内存有界）。
# 沿用 agent_erasure_backfill 的 _MAX_FAILURE_SAMPLES 模式（值对齐 16）。
_MAX_FAILURE_SAMPLES = 16


@dataclass(frozen=True, slots=True)
class BackfillFailureSample:
    """有界失败/冲突明细样本（仅前 ``_MAX_FAILURE_SAMPLES`` 个）。"""

    tenant_id: uuid.UUID
    classification: str
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class BackfillReport:
    """agent-identity backfill 的汇总报告（CLI JSON 输出形状）。"""

    dry_run: bool
    tenants: tuple[TenantIdentityScan, ...] = ()
    # 总失败数：完整累计，不受样本上限影响。
    failed: int = 0
    # 失败/冲突明细样本（有界，最多 _MAX_FAILURE_SAMPLES 条）。
    failure_samples: tuple[BackfillFailureSample, ...] = ()

    @property
    def exit_code(self) -> int:
        """契约 §7：任何 failed 或 conflict 非零 -> exit 1。"""
        has_conflict = any(t.classification == "conflict" for t in self.tenants)
        return 1 if (self.failed > 0 or has_conflict) else 0


@dataclass(frozen=True, slots=True)
class _BootstrapDetail:
    """bootstrap 的内部结果（含创建归属计数；仅供 CLI 统计，不进 API 响应）。"""

    outcome: BootstrapOutcome
    created: int


class ExecutionIdentityBootstrapAdapter(AgentIdentityBootstrapPort):
    """``AgentIdentityBootstrapPort`` 的 execution 侧默认实现。

    显式继承 port：port 面扩张而 adapter 未跟进时构造期即 fail-closed。
    每个调用方 session 新建一个实例；事务边界归调用方（route / CLI 逐 tenant）。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._identity = AgentExecutionIdentityRepository(session)

    async def bootstrap_v1_identity(
        self, *, tenant_id: uuid.UUID, actor_id: uuid.UUID
    ) -> BootstrapOutcome:
        """契约 §2：API 响应面只含终态（不携带 created 计数）。"""
        return (await self._bootstrap(tenant_id=tenant_id, actor_id=actor_id)).outcome

    async def bootstrap_v1_identity_with_stats(
        self, *, tenant_id: uuid.UUID, actor_id: uuid.UUID
    ) -> _BootstrapDetail:
        """CLI 统计面：created 计数由仓储 RETURNING 实际插入归属（契约 §5）。"""
        return await self._bootstrap(tenant_id=tenant_id, actor_id=actor_id)

    async def _bootstrap(self, *, tenant_id: uuid.UUID, actor_id: uuid.UUID) -> _BootstrapDetail:
        """按契约 §4 状态矩阵分流；两表写入同事务（契约 §5）。

        契约 §4：409 分支零写入——draft/retired/digest/身份冲突在写前分流。
        契约 §5：insert 未插入（RETURNING 空）时必须同事务回读并重新分流，
        不得直接当作「已存在」。
        """
        created = 0
        definition = await self._identity.get_agent_definition_version_by_key(
            tenant_id=tenant_id,
            definition_key=DIRECT_RAG_DEFINITION_KEY,
            version=DIRECT_RAG_DEFINITION_VERSION,
        )
        profile = await self._identity.get_runtime_profile_by_key(
            tenant_id=tenant_id,
            profile_key=DIRECT_RAG_PROFILE_KEY,
        )

        # §4 写前分流：受控记录与冲突一律零写入。
        conflict = self._classify_conflict(definition, profile)
        if conflict is not None:
            return _BootstrapDetail(
                outcome=BootstrapOutcome(
                    initialized=False,
                    disabled_existing=False,
                    conflict=True,
                    conflict_reason=conflict,
                ),
                created=0,
            )

        if definition is None:
            inserted_id = await self._identity.insert_agent_definition_version_if_absent(
                tenant_id=tenant_id,
                definition_key=DIRECT_RAG_DEFINITION_KEY,
                version=DIRECT_RAG_DEFINITION_VERSION,
                definition_digest=_V1_DEFINITION_DIGEST,
                created_by=actor_id,
            )
            if inserted_id is not None:
                created += 1
            else:
                # §5：并发落败或既有行；同事务回读并按 §4 重新分流。
                definition = await self._identity.get_agent_definition_version_by_key(
                    tenant_id=tenant_id,
                    definition_key=DIRECT_RAG_DEFINITION_KEY,
                    version=DIRECT_RAG_DEFINITION_VERSION,
                )
                if definition is None:
                    raise BootstrapIndeterminateError(
                        "definition insert was not persisted and re-read found no row"
                    )
                conflict = self._classify_definition_conflict(definition)
                if conflict is not None:
                    return _BootstrapDetail(
                        outcome=BootstrapOutcome(
                            initialized=False,
                            disabled_existing=False,
                            conflict=True,
                            conflict_reason=conflict,
                        ),
                        created=0,
                    )

        if profile is None:
            inserted_id = await self._identity.insert_runtime_profile_if_absent(
                tenant_id=tenant_id,
                profile_key=DIRECT_RAG_PROFILE_KEY,
                runtime_kind=_V1_RUNTIME_KIND,
                adapter_key=_V1_ADAPTER_KEY,
                config_digest=_V1_PROFILE_CONFIG_DIGEST,
                capability_digest=_V1_CAPABILITY_DIGEST,
                enabled=True,
            )
            if inserted_id is not None:
                created += 1
            else:
                profile = await self._identity.get_runtime_profile_by_key(
                    tenant_id=tenant_id,
                    profile_key=DIRECT_RAG_PROFILE_KEY,
                )
                if profile is None:
                    raise BootstrapIndeterminateError(
                        "profile insert was not persisted and re-read found no row"
                    )
                conflict = self._classify_profile_conflict(profile)
                if conflict is not None:
                    return _BootstrapDetail(
                        outcome=BootstrapOutcome(
                            initialized=False,
                            disabled_existing=False,
                            conflict=True,
                            conflict_reason=conflict,
                        ),
                        created=0,
                    )

        if profile is None:
            # 本事务刚由我方插入（enabled=True）；回读拿权威行（含并发仲裁后的
            # 真实落库状态），不回读不得声称最终状态。
            profile = await self._identity.get_runtime_profile_by_key(
                tenant_id=tenant_id,
                profile_key=DIRECT_RAG_PROFILE_KEY,
            )
        assert profile is not None
        # §3：disabled profile 不自动启用；initialized 与 servable 分离。
        return _BootstrapDetail(
            outcome=BootstrapOutcome(
                initialized=True,
                disabled_existing=not profile.enabled,
                conflict=False,
            ),
            created=created,
        )

    def _classify_conflict(self, definition, profile) -> str | None:
        """§4 写前分流：任一冲突返回原因，否则 None。"""
        return self._classify_definition_conflict(definition) or self._classify_profile_conflict(
            profile
        )

    @staticmethod
    def _classify_definition_conflict(definition) -> str | None:
        if definition is None:
            return None
        if definition.status is not AgentDefinitionStatus.PUBLISHED:
            return (
                "agent definition system.direct_rag v1 exists in non-published "
                f"state ({definition.status.value}); refusing to re-publish"
            )
        if definition.definition_digest != _V1_DEFINITION_DIGEST:
            return (
                "agent definition system.direct_rag v1 has different content "
                "digest; refusing to overwrite"
            )
        return None

    @staticmethod
    def _classify_profile_conflict(profile) -> str | None:
        if profile is None:
            return None
        if (
            profile.runtime_kind != _V1_RUNTIME_KIND
            or profile.adapter_key != _V1_ADAPTER_KEY
            or profile.config_digest != _V1_PROFILE_CONFIG_DIGEST
            or profile.capability_digest != _V1_CAPABILITY_DIGEST
        ):
            return (
                "runtime profile compat.direct_rag.v1 has different immutable "
                "identity; refusing to overwrite"
            )
        return None


def build_agent_identity_bootstrap(session: AsyncSession) -> ExecutionIdentityBootstrapAdapter:
    """composition 装配入口：bootstrap route 的依赖来源。"""
    return ExecutionIdentityBootstrapAdapter(session)


# --- CLI 存量补齐（契约 §7） -------------------------------------------------


async def list_all_tenant_ids(session: AsyncSession) -> list[uuid.UUID]:
    """存量补齐的选择条件：metaedu.tenants 全量扫描（契约 §7）。"""
    rows = await session.execute(select(TenantModel.id).order_by(TenantModel.id))
    return [row[0] for row in rows.all()]


async def actor_exists(session: AsyncSession, actor_id: uuid.UUID) -> bool:
    """契约 §8：--actor 必须存在于 metaedu.users（不存在即报错不执行）。"""
    row = await session.execute(select(UserModel.id).where(UserModel.id == actor_id).limit(1))
    return row.scalar_one_or_none() is not None


async def classify_tenant_identity(
    session: AsyncSession, tenant_id: uuid.UUID
) -> TenantIdentityScan:
    """dry-run 的只读分类（无并发写，只读判定合法——契约 §7）。"""
    identity = AgentExecutionIdentityRepository(session)
    definition = await identity.get_agent_definition_version_by_key(
        tenant_id=tenant_id,
        definition_key=DIRECT_RAG_DEFINITION_KEY,
        version=DIRECT_RAG_DEFINITION_VERSION,
    )
    profile = await identity.get_runtime_profile_by_key(
        tenant_id=tenant_id, profile_key=DIRECT_RAG_PROFILE_KEY
    )
    adapter = ExecutionIdentityBootstrapAdapter(session)
    conflict = adapter._classify_conflict(definition, profile)
    if conflict is not None:
        return TenantIdentityScan(tenant_id=tenant_id, classification="conflict", error=conflict)
    if definition is not None and profile is not None:
        if not profile.enabled:
            return TenantIdentityScan(tenant_id=tenant_id, classification="disabled")
        return TenantIdentityScan(tenant_id=tenant_id, classification="complete")
    missing = int(definition is None) + int(profile is None)
    return TenantIdentityScan(tenant_id=tenant_id, classification="missing", would_create=missing)


async def backfill_agent_identity(
    session_factory,
    *,
    tenant_ids: list[uuid.UUID],
    actor_id: uuid.UUID,
    dry_run: bool,
) -> BackfillReport:
    """逐 tenant 独立短事务的存量补齐（契约 §7）。

    - dry-run：只读分类，零写入；
    - 实写：per-tenant commit/rollback 互不影响；
    - 失败/冲突如实计数并载明细，不静默跳过；
    - created 归属由仓储 RETURNING 的实际插入结果给出（契约 §5），
      不凭写前查询推断。
    """
    scans: list[TenantIdentityScan] = []
    failed = 0
    samples: list[BackfillFailureSample] = []

    def _sample(tenant_id: uuid.UUID, classification: str, error: str) -> str | None:
        """保留有界失败明细；返回该 tenant 行上应保留的 error（超上限为 None）。"""
        if len(samples) < _MAX_FAILURE_SAMPLES:
            samples.append(
                BackfillFailureSample(
                    tenant_id=tenant_id,
                    classification=classification,
                    error_type=classification,
                    message=error[:200],
                )
            )
            return error[:200]
        return None

    for tenant_id in tenant_ids:
        async with session_factory() as session:
            try:
                if dry_run:
                    scans.append(await classify_tenant_identity(session, tenant_id))
                    continue
                scan = await classify_tenant_identity(session, tenant_id)
                if scan.classification in {"complete", "disabled"}:
                    scans.append(
                        TenantIdentityScan(
                            tenant_id=tenant_id,
                            classification=scan.classification,
                            skipped=2,
                        )
                    )
                    await session.commit()
                    continue
                if scan.classification == "conflict":
                    scans.append(
                        TenantIdentityScan(
                            tenant_id=tenant_id,
                            classification="conflict",
                            error=_sample(tenant_id, "conflict", scan.error or ""),
                        )
                    )
                    await session.commit()
                    continue
                detail = await build_agent_identity_bootstrap(
                    session
                ).bootstrap_v1_identity_with_stats(tenant_id=tenant_id, actor_id=actor_id)
                if detail.outcome.conflict:
                    scans.append(
                        TenantIdentityScan(
                            tenant_id=tenant_id,
                            classification="conflict",
                            error=_sample(
                                tenant_id,
                                "conflict",
                                detail.outcome.conflict_reason or "",
                            ),
                        )
                    )
                    await session.rollback()
                    continue
                scans.append(
                    TenantIdentityScan(
                        tenant_id=tenant_id,
                        classification="disabled"
                        if detail.outcome.disabled_existing
                        else "complete",
                        created=detail.created,
                    )
                )
                await session.commit()
            except Exception as exc:  # noqa: BLE001 - CLI 失败如实计数不静默
                await session.rollback()
                failed += 1
                scans.append(
                    TenantIdentityScan(
                        tenant_id=tenant_id,
                        classification="failed",
                        error=_sample(tenant_id, "failed", f"{type(exc).__name__}: {exc}"),
                    )
                )
    return BackfillReport(
        dry_run=dry_run,
        tenants=tuple(scans),
        failed=failed,
        failure_samples=tuple(samples),
    )


__all__ = [
    "BackfillFailureSample",
    "BackfillReport",
    "BootstrapIndeterminateError",
    "ExecutionIdentityBootstrapAdapter",
    "TenantIdentityScan",
    "_MAX_FAILURE_SAMPLES",
    "actor_exists",
    "backfill_agent_identity",
    "build_agent_identity_bootstrap",
    "classify_tenant_identity",
    "list_all_tenant_ids",
]
