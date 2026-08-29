"""R1-S5-I2 S5-A-5 滚动发布前提测试门禁：六 participant erase 入口在生产组合根
不可达（仅测试可构造）。

冻结契约（S5-A-5）：切换安全性依赖「切换时生产无 purge 执行路径在网」；I2 落地
一条测试门禁——六 participant 的 erase_* 入口在生产组合根不可达。本测试静态扫描
生产源码：erase 入口名只允许出现在各自的 participant 定义文件中；任何生产模块
引用（组合根接线、scheduler 前接线）→ 红。后续 S5 scheduler slice 只能在单写者
coordinator 落地后接线。

变异：在生产模块（app/ 下非定义文件）挂任一 erase 入口调用 → 本测试红。
"""

from __future__ import annotations

from pathlib import Path

_ENTRY_NAMES = {
    "erase_conversation_body",
    "erase_execution_body",
    "erase_transport_owner",
    "erase_external_payload",
    "erase_runtime_session",
}

# erase 入口的合法定义文件（participant 本体；其 docstring 引述入口名属正常）。
_DEFINING_FILES = {
    "workspace_erasure_participant.py",
    "execution_erasure_participant.py",
    "transport_erasure_participant.py",
    "external_ref_erasure_participant.py",
    "runtime_erasure_participant.py",
}

# S5-SCH-3 组合根启用门禁（联合 merged-boundary）：scheduler_composition.py 是
# scheduler 组合根的唯一生产装配点——仅当 B/C/D 三 slice 全部元素齐备且含
# CompositionNotReadyError 门禁时，六 owner erase 入口引用被放行；否则视为
# 违规引用（partial wiring 不得使 erase 入口可达）。
_COMPOSITION_ROOT = "scheduler_composition.py"

# M 类维护路径（M-class；S6-8.3 冻结）：restore_replay.py 作为 replay executor 维护
# 路径是 D2 的主入口（用户裁决 A 方案；Plan §S6-8.3）。M 类不属于生产组合根（与
# S5-A-5 切换安全保证无关）——六 owner erase 入口可达是 M 类维护路径的契约事实。
# 本文件 allowlist 让 S5-A-5 静态扫描放行 M 类入口调用，同时保留生产组合根禁线。
_MAINTENANCE_FILES = {
    "restore_replay.py",
}


def test_six_erase_entries_unreachable_from_production_composition():
    # 本文件位于 packages/server-python/tests/composition/ →
    # parents[2] = packages/server-python → app/。
    app_root = Path(__file__).resolve().parents[2] / "app"
    assert app_root.is_dir(), f"app root not found: {app_root}"
    violations: list[tuple[str, str]] = []
    for path in sorted(app_root.rglob("*.py")):
        if path.name in _DEFINING_FILES:
            continue
        if path.name == _COMPOSITION_ROOT:
            continue  # 联合边界：单独门禁断言覆盖
        if path.name in _MAINTENANCE_FILES:
            # M 类维护路径 allowlist：restore_replay.py（D2 M-class executor）
            # 是 S6-8.3 冻结 M 类入口调用者；不属于 S5-A-5 生产组合根禁线。
            continue
        content = path.read_text(encoding="utf-8")
        for name in _ENTRY_NAMES:
            if name in content:
                violations.append((str(path.relative_to(app_root)), name))
    assert violations == [], (
        "six participant erase entries must be unreachable from production "
        f"composition roots (S5-A-5); violations: {violations}"
    )
    # 联合边界必须含启用门禁（B/C/D 全元素 + fail closed），否则挂引用视为违规。
    composition = (app_root / "composition" / _COMPOSITION_ROOT).read_text(
        encoding="utf-8"
    )
    for required in (
        "CompositionNotReadyError",  # 门禁：partial wiring fail closed
        "OwnerExecutionOrchestrator",  # SCH-B
        "build_owner_entries",  # participant map
        "build_settlement_port",  # SCH-D concrete SettlementPort
        "PurgeRebuildService",  # SCH-C
        "coordinator_scan_providers",  # coordinator
        "ConversationPurgeScheduler",  # SCH-A claim/lease
    ):
        assert required in composition, (
            f"composition root {_COMPOSITION_ROOT} missing joint-wiring gate "
            f"element {required!r}; erase entry reference not sanctioned"
        )
