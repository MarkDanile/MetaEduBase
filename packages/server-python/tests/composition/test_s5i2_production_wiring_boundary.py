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


def test_six_erase_entries_unreachable_from_production_composition():
    app_root = Path(__file__).resolve().parents[3] / "app"
    violations: list[tuple[str, str]] = []
    for path in sorted(app_root.rglob("*.py")):
        if path.name in _DEFINING_FILES:
            continue
        content = path.read_text(encoding="utf-8")
        for name in _ENTRY_NAMES:
            if name in content:
                violations.append((str(path.relative_to(app_root)), name))
    assert violations == [], (
        "six participant erase entries must be unreachable from production "
        f"composition roots (S5-A-5); violations: {violations}"
    )
