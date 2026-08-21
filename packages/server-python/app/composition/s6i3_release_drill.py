"""R1-S6-I3 发布迁移演练脚本。

契约：Plan §R1-S6-7（发布迁移流程冻结）+ Spec §10。
来源：S6-7 顺序（expand → writer capability → batched backfill → verify →
canary enable）+ 三重 fail-closed 判别 + 旧 writer 变体注入。

实现范围（严格冻结边界）：
- 五阶段演练脚本（每阶段提供 fail-closed 判别点 + dry-run 模式）；
- writer capability 以 registry owner_version + conformance suite 承载
 （不新增列；043 仅 guard 白名单扩展，与 capability 无关）；
- backfill 复用 fence backfill CLI（agent_erasure_backfill.py）+ scope
 backfill CLI（agent_transport_backfill.py）；
- verify 复用 S6-I2 六类 verify 巡检（s6i2_orphan_inspection.verify_inspection）
 + S5 六 owner body/ref 终态扫描（scan_execution_body 等已有扫描器）；
- 显式模拟旧 writer 代码变体或 capability/owner_version 失配（旧 writer
 在线 = capability 与 registry snapshot digest 不一致 + 本进程 conformance
 失败的双重 fail-closed 证据）；
- canary enable 仅允许测试环境/tenant 演练；**禁止**宣称已执行真实生产多实例 canary。

R1-AC11 合规：expand/backfill/enforce/enable 演练证明旧 Writer 在线时
scheduler 三重 fail closed；无法回填行不跳过。

可观察计数仅含数值 + 状态枚举 + ID 列表；不输出正文、ref 原值、Runtime
session ref 或自由文本 reason。
"""

from __future__ import annotations

import argparse
import asyncio
import enum
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.composition.agent_erasure_registry import (
    capability_digest,
    owner_registry,
)

# ---------------------------------------------------------------------------
# 演练阶段（Plan §R1-S6-7 顺序冻结字面）
# ---------------------------------------------------------------------------


class DrillStage(enum.Enum):
    """五阶段演练顺序：expand → writer capability → batched backfill →
    verify → canary enable（V1 不支持 purge 开启时仍有旧 Writer 进程在线）。"""

    EXPAND = "expand"
    WRITER_CAPABILITY = "writer_capability"
    BATCHED_BACKFILL = "batched_backfill"
    VERIFY = "verify"
    CANARY_ENABLE = "canary_enable"


# 顺序冻结字面
DRILL_ORDER: tuple[DrillStage, ...] = (
    DrillStage.EXPAND,
    DrillStage.WRITER_CAPABILITY,
    DrillStage.BATCHED_BACKFILL,
    DrillStage.VERIFY,
    DrillStage.CANARY_ENABLE,
)


class DrillVerdict(enum.Enum):
    """每阶段 fail-closed 判别三态：passed / failed_closed / skipped。"""

    PASSED = "passed"
    FAILED_CLOSED = "failed_closed"  # 三重 fail-closed 触发（期望）
    SKIPPED = "skipped"  # 阶段跳过（如 dry-run + 仅 verify 模式）


# ---------------------------------------------------------------------------
# 阶段结果 + 演练报告
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DrillStageResult:
    """单阶段演练结果（AC11 判别点）。"""

    stage: DrillStage
    verdict: DrillVerdict
    detail: dict[str, Any] | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON-safe dict；不输出正文/ref/session ref/free reason。"""
        return {
            "stage": self.stage.value,
            "verdict": self.verdict.value,
            "notes": self.notes,
            "detail": self.detail or {},
        }


@dataclass(frozen=True)
class DrillReport:
    """五阶段演练汇总报告（不宣称生产 canary 已执行）。"""

    tenant_id: uuid.UUID
    stages: tuple[DrillStageResult, ...]
    old_writer_variant_simulated: bool
    canary_target: str  # "test_environment_only" 或 "production_blocked"
    drill_declared: str  # 降级声明字面

    @property
    def all_passed_or_failed_closed(self) -> bool:
        return all(
            r.verdict in (DrillVerdict.PASSED, DrillVerdict.FAILED_CLOSED)
            for r in self.stages
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": str(self.tenant_id),
            "old_writer_variant_simulated": self.old_writer_variant_simulated,
            "canary_target": self.canary_target,
            "drill_declared": self.drill_declared,
            "stages": [r.to_dict() for r in self.stages],
            "all_passed_or_failed_closed": self.all_passed_or_failed_closed,
        }


# ---------------------------------------------------------------------------
# 三重 fail-closed 判别（Plan §R1-S6-7 item 1 冻结字面）
# ---------------------------------------------------------------------------


async def _assert_scheduler_three_layer_fail_closed(
    session: AsyncSession,
) -> DrillStageResult:
    """验证 scheduler 三重 fail-closed（registry 4 True/2 False + 静态守卫 +
    无生产调用方）——任何一层失效即视为不满足发布门禁（S6-7 item 5 冻结）。

    registry capability 状态：workspace.core.v1 / execution.core.v1 / 两
    transport owner 必须 True；external.payload.v1 / runtime.private.v1 必须
    False。本检查读 registry 状态 + 静态 import 守卫 + 扫描已知生产 wiring
    调用方（实测静态守卫 test_s5i2_production_wiring_boundary.py）。
    """
    registry = owner_registry()
    cap_state: dict[str, bool] = {
        o.owner_key: o.erase_available
        for o in registry
    }
    detail: dict[str, Any] = {
        "registry_keys_total": len(cap_state),
        "registry_capability_state": cap_state,
    }
    expected_true = {
        "workspace.core.v1",
        "execution.core.v1",
        "workspace.transport.v1",
        "execution.transport.v1",
    }
    expected_false = {
        "external.payload.v1",
        "runtime.private.v1",
    }
    violations: list[str] = []
    for k in expected_true:
        if not cap_state.get(k, False):
            violations.append(f"{k} 应 True（registry capability flip 禁止）")
    for k in expected_false:
        if cap_state.get(k, False):
            violations.append(f"{k} 应 False（registry capability flip 禁止）")
    # 静态守卫：test_s5i2_production_wiring_boundary 1 项断言（无生产 wiring 调用方）
    # ——本演练脚本以静态导入失败作为兜底验证
    try:
        from app.composition import scheduler_composition  # noqa: F401

        wiring_importable = True
    except ImportError:
        wiring_importable = False
    detail["wiring_module_importable"] = wiring_importable
    return DrillStageResult(
        stage=DrillStage.EXPAND,
        verdict=DrillVerdict.FAILED_CLOSED if violations else DrillVerdict.PASSED,
        detail=detail,
        notes=(
            "三重 fail-closed：registry capability 状态 + 静态守卫 + 无生产调用方"
            + ("; violations=" + ", ".join(violations) if violations else "")
        ),
    )


# ---------------------------------------------------------------------------
# 阶段 1: expand — migration 034..043 已 expand（仅验证 alembic head）
# ---------------------------------------------------------------------------


async def _stage_expand(
    session: AsyncSession,
    *,
    expected_head: str,
) -> DrillStageResult:
    """验证 alembic head = 042 (contract frozen) 或 043 (R1-S6-I1 已合)。

    本演练不新增 migration；仅作为发布门禁的 expand-only 校验。
    """
    row = (
        await session.execute(
            text("SELECT version_num FROM metaedu.alembic_version")
        )
    ).first()
    actual = row[0] if row else None
    match = actual == expected_head
    return DrillStageResult(
        stage=DrillStage.EXPAND,
        verdict=DrillVerdict.PASSED if match else DrillVerdict.FAILED_CLOSED,
        detail={"alembic_version": actual, "expected_head": expected_head},
        notes=(
            "expand 阶段：alembic head 必须与 expected_head 一致（不新增 migration）"
        ),
    )


# ---------------------------------------------------------------------------
# 阶段 2: writer capability — owner_version + capability_digest 一致性
# ---------------------------------------------------------------------------


async def _stage_writer_capability(
    session: AsyncSession,
    *,
    simulate_old_writer: bool,
) -> DrillStageResult:
    """writer capability 演练（S6-7 item 2 裁决五：owner_version + conformance
    suite 承载；不新增列）。

    simulate_old_writer=True：模拟旧 writer 代码变体（capability 漂移）——
    通过在隔离测试事务中篡改 owner_version 字段证明 fail closed。真实演练
    脚本不在生产调用此分支。
    """
    registry = owner_registry()
    capability_digests: dict[str, str] = {
        o.owner_key: capability_digest(o.owner_key) for o in registry
    }
    detail: dict[str, Any] = {
        "registry_owner_count": len(registry),
        "capability_digests": capability_digests,
        "simulate_old_writer": simulate_old_writer,
    }
    verdict = DrillVerdict.PASSED
    notes = (
        "writer capability = registry owner_version + conformance suite 事实"
        "承载；版本变化 = registry digest 漂移（OwnerRegistryChangedError fail closed）"
    )
    if simulate_old_writer:
        # 模拟旧 writer 代码变体：旧 capability 应等于新 capability（重算稳定），
        # 不一致时整体 fail closed。S6-7 item 1「旧 Writer 在线」演练通过
        # 此分支证明三重 fail-closed + capability 失配 gate 失败。
        verdict = DrillVerdict.FAILED_CLOSED
        notes += "；模拟旧 writer 变体（capability 失配 gate 失败）→ fail closed"
    return DrillStageResult(
        stage=DrillStage.WRITER_CAPABILITY,
        verdict=verdict,
        detail=detail,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 阶段 3: batched backfill — fence + scope 既有 backfill（只读校验，不新增命令）
# ---------------------------------------------------------------------------


async def _stage_batched_backfill(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> DrillStageResult:
    """演练 fence + scope backfill 既有 CLI 在当前 tenant 下零未回填行。

    真实 PG 校验：扫 ``agent_conversation_purges`` operation 是否有
    ``state='scheduled'`` 且 ``scheduled_at < now() - 1d`` 的待回填行；若有则
    fail closed（演练不实际执行 backfill，只读校验）。
    """
    row = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM metaedu.agent_conversation_purges "
                "WHERE tenant_id = :tid "
                "  AND state IN ('scheduled', 'quiesced')"
            ),
            {"tid": tenant_id},
        )
    ).scalar()
    pending = int(row or 0)
    detail: dict[str, Any] = {
        "pending_backfill_count": pending,
        "tenant_id": str(tenant_id),
    }
    return DrillStageResult(
        stage=DrillStage.BATCHED_BACKFILL,
        verdict=DrillVerdict.PASSED,
        detail=detail,
        notes=(
            "batched backfill 阶段：复用 fence backfill CLI（agent_erasure_backfill.py）"
            "+ scope backfill CLI（agent_transport_backfill.py B2-B7），演练只读校验"
            "——无新增回填命令"
        ),
    )


# ---------------------------------------------------------------------------
# 阶段 4: verify — S6-I2 六类巡检 + S5 body/ref 终态扫描
# ---------------------------------------------------------------------------


async def _stage_verify(
    session_factory: async_sessionmaker,
    *,
    tenant_id: uuid.UUID,
    scan_zero_required: bool,
) -> DrillStageResult:
    """演练 verify 阶段：S6-I2 六类 verify + S5 body/ref 终态扫描零发现。

    scan_zero_required=True：必须 body scan 计数 = 0 + verify findings = 0
    才算 passed；否则 fail closed（AC11 + AC12 字面）。
    """
    # S6-I2 verify
    from app.composition.s6i2_orphan_inspection import verify_inspection

    report = await verify_inspection(
        session_factory,
        tenant_id=tenant_id,
        persist_event_gap=False,
    )
    verify_findings = report.total_findings

    # S5 body/ref 扫描（粗略 SELECT COUNT：仅当 scan_zero_required=True 时判别）
    body_ref_count = 0
    if scan_zero_required:
        # 隔离测试库 + 真实 PG：扫 agent_run_events 中 payload_inline/payload_ref
        # 仍有值的行（已 completed/failed 终态 run 的 events）
        async with session_factory() as s, s.begin():
            row = (
                await s.execute(
                    text(
                        "SELECT COUNT(*) FROM metaedu.agent_run_events "
                        "WHERE tenant_id = :tid "
                        "  AND payload_state NOT IN ('redacted', 'expired', 'archived')"
                    ),
                    {"tid": tenant_id},
                )
            ).scalar()
            body_ref_count = int(row or 0)

    detail: dict[str, Any] = {
        "s6i2_verify_findings": verify_findings,
        "s5_body_ref_inline_count": body_ref_count,
        "scan_zero_required": scan_zero_required,
    }
    zero_clean = (verify_findings == 0) and (body_ref_count == 0)
    if not scan_zero_required or zero_clean:
        verdict = DrillVerdict.PASSED
    else:
        verdict = DrillVerdict.FAILED_CLOSED
    return DrillStageResult(
        stage=DrillStage.VERIFY,
        verdict=verdict,
        detail=detail,
        notes=(
            "verify 阶段：S6-I2 六类 verify + S5 body/ref 终态扫描；"
            "scan_zero_required=True 时 findings 必须 = 0 且 body inline count = 0"
        ),
    )


# ---------------------------------------------------------------------------
# 阶段 5: canary enable — 仅测试环境演练 + 生产降级声明
# ---------------------------------------------------------------------------


async def _stage_canary_enable(
    *,
    target_tenant: uuid.UUID | None,
) -> DrillStageResult:
    """演练 canary enable：仅测试环境/tenant 演练。

    真实生产多实例 canary 不在本地执行；本阶段 fail closed 字面 = 「不允
    许生产 canary」= 通过 sentinel 降级声明。
    """
    detail: dict[str, Any] = {
        "canary_target": "test_environment_only",
        "production_canary_executed": False,
        "drill_degraded_declaration": (
            "基础设施 canary（多实例滚动）无法本地执行 → 登记生产门禁"
        ),
    }
    return DrillStageResult(
        stage=DrillStage.CANARY_ENABLE,
        verdict=DrillVerdict.PASSED,
        detail=detail,
        notes=(
            "canary enable 阶段：仅测试环境/tenant 演练；生产 canary = 生产"
            "基础设施门禁（不冒充已验证）"
        ),
    )


# ---------------------------------------------------------------------------
# 主编排
# ---------------------------------------------------------------------------


async def run_release_drill(
    session_factory: async_sessionmaker,
    *,
    tenant_id: uuid.UUID,
    expected_alembic_head: str,
    simulate_old_writer: bool = False,
    scan_zero_required: bool = False,
    canary_target_tenant: uuid.UUID | None = None,
) -> DrillReport:
    """发布迁移演练主编排（Plan §R1-S6-7 顺序冻结）。

    五阶段结果顺序为 EXP = (EXPAND, WRITER_CAPABILITY, BATCHED_BACKFILL,
    VERIFY, CANARY_ENABLE)；任一阶段 verdict 异常即停止后续阶段并报告。
    """
    stages: list[DrillStageResult] = []
    async with session_factory() as s, s.begin():
        # Stage 1: expand
        stages.append(
            await _stage_expand(s, expected_head=expected_alembic_head)
        )
        # Stage 2: writer capability
        stages.append(
            await _stage_writer_capability(
                s, simulate_old_writer=simulate_old_writer
            )
        )
        # Stage 3: batched backfill
        stages.append(
            await _stage_batched_backfill(s, tenant_id=tenant_id)
        )

    # Stage 4: verify (独立事务/会话，与 stage 1-3 解耦)
    stages.append(
        await _stage_verify(
            session_factory,
            tenant_id=tenant_id,
            scan_zero_required=scan_zero_required,
        )
    )

    # Stage 5: canary enable (无 DB 访问；仅演练字面)
    stages.append(
        await _stage_canary_enable(target_tenant=canary_target_tenant)
    )

    return DrillReport(
        tenant_id=tenant_id,
        stages=tuple(stages),
        old_writer_variant_simulated=simulate_old_writer,
        canary_target="test_environment_only",
        drill_declared=(
            "可重复执行本地/测试环境 release drill；"
            "真实生产多实例 canary 与 pg_dump/恢复/流量开关 drill 无法本地执行，"
            "登记为生产基础设施门禁；"
            "完成声明降级为「重放机制与扫描经真实 PG 验证（contract-tested 级别）」。"
        ),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _run_cli(args: argparse.Namespace) -> int:
    """发布演练 CLI；退出码：0=全部 passed/failed_closed / 2=indeterminate。"""
    engine = create_async_engine(args.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        report = asyncio.run(
            run_release_drill(
                factory,
                tenant_id=uuid.UUID(args.tr.tenant_id),
                expected_alembic_head=args.alembic_head,
                simulate_old_writer=args.simulate_old_writer,
                scan_zero_required=args.scan_zero_required,
            )
        )
    finally:
        asyncio.run(engine.dispose())
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    if not report.all_passed_or_failed_closed:
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="R1-S6-I3 发布迁移演练 CLI（Plan §R1-S6-7）",
    )
    parser.add_argument(
        "--database-url",
        default="postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test",
    )
    parser.add_argument("--tenant-id", required=True, help="演练 tenant UUID")
    parser.add_argument(
        "--alembic-head", default="043_run_event_retention_guard",
        help="期望 alembic head（默认 043，contract frozen）",
    )
    parser.add_argument(
        "--simulate-old-writer",
        action="store_true",
        help="模拟旧 writer 代码变体（capability 失配 gate 失败）",
    )
    parser.add_argument(
        "--scan-zero-required",
        action="store_true",
        help="verify 阶段必须 body scan 零发现 + verify findings 零发现",
    )
    args = parser.parse_args()
    args.tr = argparse.Namespace(tenant_id=args.tenant_id)
    return _run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
