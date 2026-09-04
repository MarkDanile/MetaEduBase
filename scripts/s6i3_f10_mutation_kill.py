"""R1-S6-I3 F10 故障矩阵具名 mutation kill（TD-105 承接，settlement T1/T2 hold 推进）。

契约：Plan §S6-15.3 (TD-105) — F10 settlement 读法锁定（裁决二 supersede S5-SCH-2
T2 token 清单 hold snapshot 项）。8 项具名 mutation 与判别载体映射：

| M# | 标题                                                | 锚点 / 落值                                              | 判别载体（test id）                                          |
|----|-----------------------------------------------------|----------------------------------------------------------|------------------------------------------------------------|
| M1 | hold 推进被错误判为 fail-closed                     | settlement.py:887 ``>`` → ``>=``（让 advance 也 fail）    | test_f10_t1_then_advance_hold_t2_completes                 |
| M2 | hold 回退未 fail-closed                              | settlement.py:887 ``hold_revision_snapshot > conversation hold_revision`` 整段 raise 注释跳过 | test_f10_t2_unidirectional_regression_fails_closed |
| M3 | fence/checkpoint 状态写错（fence 落 `erased`→`blocked`） | settlement.py `_apply_window_outcome` fenced `ERASED` → `BLOCKED` 写错 | test_f10_t1_then_advance_hold_t2_completes（assert fence=erased）|
| M4 | G2 `blocked_hold_revision_changed` 缺失              | projection_calculator.py:319 `if inputs.hold_drift:` → `if False:` | test_f10_projection_g2_blocked_hold_revision_changed_no_completed |
| M5 | rebuild 未进入 HOLD_GATED                            | purge_rebuild.py:157 `return RebuildOutcome(RebuildKind.HOLD_GATED)` → `return RebuildOutcome(RebuildKind.REBUILT, ...)` 跳过 HOLD_GATED | test_f10_rebuild_hold_gated_with_active_hold |
| M6 | completed 绕过最终扫描                               | projection_calculator.py:491-507 nonzero scan check 注释跳过 | test_f10_projection_g2_blocked_hold_revision_changed_no_completed（completed 路径）/ F10 chain 通过 held hold 释放后 G3 cleared 后 scan non-zero 仍 completed |
| M7 | 重复 adapter 调用（重放阶段调 adapter）              | settlement.py `_apply_window_outcome` SUCCESS 路径加 `_noop_adapter_resolver` 注入触发（mock-style stub）| test_f10_no_body_resurrection_no_repeated_adapter_replay_idempotent |
| M8 | ledger/binding per-ref receipt 丢失或 source 未清    | settlement.py `_close_window_ledger` 外部 `write_erased_and_clear_ref` 替换为仅 UPDATE `erase_state='erased'`（B2 唯一清除者越权）| test_f10_td106_per_ref_receipt_and_source_clear（合并入 test_f10_t1_then_advance_hold_t2_completes 的 TD-106 断言） |

所有 mutation 都通过 memory-backup + try/finally 还原（不依赖 git restore）。NOT-RED
如实登记（说明原因），不计入 kill 分母。

用法（须独占 metaedu_test——并发验证进程的 autouse TRUNCATE 会互相破坏）：

    cd packages/server-python
    uv run python ../../scripts/s6i3_f10_mutation_kill.py
"""

import subprocess
import sys as _sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SETTLEMENT = REPO / "packages/server-python/app/composition/settlement.py"
PROJECTION = REPO / "packages/server-python/app/composition/projection_calculator.py"
PURGE_REBUILD = REPO / "packages/server-python/app/composition/purge_rebuild.py"
TEST_DIR = REPO / "packages/server-python"

F10_TEST = "tests/composition/test_s6i3_fault_f10.py"


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=TEST_DIR)


def pytest_cmd(test_ids: list[str]) -> subprocess.CompletedProcess:
    return run(["uv", "run", "pytest", *test_ids, "-q", "--tb=line"])


_BACKUPS: dict[str, str] = {}


def apply(file: Path, old: str, new: str) -> None:
    src = file.read_text()
    assert old in src, f"anchor not found in {file}: {old[:80]!r}"
    # 同文件多 edit 仅在首次 touch 时备份原始 src（否则后次备份覆盖原始）。
    if str(file) not in _BACKUPS:
        _BACKUPS[str(file)] = src
    file.write_text(src.replace(old, new, 1))


def restore(file: Path) -> None:
    original = _BACKUPS.pop(str(file), None)
    if original is not None:
        file.write_text(original)


# ---------------------------------------------------------------------------
# MUTATIONS：每项 (name, edits=[(file, old_anchor, new_anchor), ...],
#              tests=[nodeid, ...])
# 所有 anchor 用足够上下文确保唯一；kill = 全部映射测试转红且还原后全绿。
# ---------------------------------------------------------------------------

MUTATIONS = [
    # --- M1 hold 推进被错误判为 fail-closed ---
    # 把 settlement frozen-snapshot 第 4  条 hold 检查的 ``>`` 改为 ``>=``（advance
    # 也 fail），settlement 永远 fail-closed → T2 永远不落账 → F10 核心四环不再闭合。
    (
        "M1 hold 推进被错误判为 fail-closed（frozen-snapshot `>` 改 `>=`）",
        [
            (
                SETTLEMENT,
                "        if operation.hold_revision_snapshot > conversation.hold_revision:",
                "        if operation.hold_revision_snapshot >= conversation.hold_revision:  # mutation M1",
            )
        ],
        [f"{F10_TEST}::test_f10_t1_then_advance_hold_t2_completes"],
    ),
    # --- M2 hold 回退未 fail-closed ---
    # 注释掉 frozen-snapshot 第 4  条 hold 整段 raise → regression 不再 fail-closed。
    (
        "M2 hold 回退未 fail-closed（frozen-snapshot hold 整段 raise skip）",
        [
            (
                SETTLEMENT,
                "        if operation.hold_revision_snapshot > conversation.hold_revision:\n"
                "            raise ValueError(\n"
                "                \"operation hold_revision_snapshot > conversation hold_revision; \"\n"
                "                \"hold regression, settlement fail closed\"\n"
                "            )",
                "        if False and operation.hold_revision_snapshot > conversation.hold_revision:  # mutation M2\n"
                "            raise ValueError(\n"
                "                \"operation hold_revision_snapshot > conversation hold_revision; \"\n"
                "                \"hold regression, settlement fail closed\"\n"
                "            )",
            )
        ],
        [f"{F10_TEST}::test_f10_t2_unidirectional_regression_fails_closed"],
    ),
    # --- M3 fence/checkpoint 状态写错（fence 写 `erased` 误为 `blocked`） ---
    # settlement._apply_window_outcome SUCCESS 路径 fence CAS 的 new_state 写错；
    # 测试断言 fence=erased 必红。
    (
        "M3 fence 状态写错（_apply_window_outcome SUCCESS fence new_state=ERASED 改 BLOCKED）",
        [
            (
                SETTLEMENT,
                "                new_state=ErasureFenceState.ERASED,",
                "                new_state=ErasureFenceState.BLOCKED,  # mutation M3",
            )
        ],
        [f"{F10_TEST}::test_f10_t1_then_advance_hold_t2_completes"],
    ),
    # --- M4 G2 blocked_hold_revision_changed 缺失 ---
    (
        "M4 G2 blocked_hold_revision_changed 缺失（projection calculator hold_drift if False）",
        [
            (
                PROJECTION,
                "    if inputs.hold_drift:\n"
                "        return ProjectionResult(\n"
                "            state=\"blocked\",\n"
                "            failure_code=\"blocked_hold_revision_changed\",\n"
                "            purge_state=\"blocked\",\n"
                "            completed=False,\n"
                "            purged=False,\n"
                "        )",
                "    if False and inputs.hold_drift:  # mutation M4\n"
                "        return ProjectionResult(\n"
                "            state=\"blocked\",\n"
                "            failure_code=\"blocked_hold_revision_changed\",\n"
                "            purge_state=\"blocked\",\n"
                "            completed=False,\n"
                "            purged=False,\n"
                "        )",
            )
        ],
        [f"{F10_TEST}::test_f10_projection_g2_blocked_hold_revision_changed_no_completed"],
    ),
    # --- M5 rebuild 未进入 HOLD_GATED ---
    # purge_rebuild 探测到 active hold 时不返回 HOLD_GATED，伪装 IDEMPOTENT——但实际
    # operation 还在 G2-blocked，测试断言 HOLD_GATED 必红。
    (
        "M5 rebuild 未进入 HOLD_GATED（HOLD_GATED 改 IDEMPOTENT 提前返回）",
        [
            (
                PURGE_REBUILD,
                "            return RebuildOutcome(RebuildKind.HOLD_GATED)",
                "            return RebuildOutcome(RebuildKind.IDEMPOTENT)  # mutation M5",
            )
        ],
        [f"{F10_TEST}::test_f10_rebuild_hold_gated_with_active_hold"],
    ),
    # --- M6 completed 绕过最终扫描 ---
    # projection_calculator nonzero scan 检查整段 skip → 即使 scan 非零也判 completed。
    # Phase 1 解除 NOT-RED 登记：M6 判别载体已迁移到独立 test
    # ``test_f10_m6_completed_bypass_scan_check_blocked``（新增
    # ``tests/composition/s6i3_fault_f10.py::test_f10_m6_completed_bypass_scan_check_blocked``）——
    # 真实 PG 路径：closeout_erasing → aggregate_projection；构造 G1/G2/G3 cleared
    # + 6 owner acked + workspace.core.v1 final scan nonzero（actor_state='present'）→
    # priority-3 scan 唯一可达。control 断言 state=blocked + failure_code=
    # workspace_body_scan_nonzero；mutant（M6 priority-3 折叠）允许 completed →
    # 测试转红。本测试**不**走 hold-drift 场景（F10 既有测试集 G2 提前 return
    # 不可达 priority-3），用 5-party 全 pass + scan nonzero 唯一触发 priority-3。
    (
        "M6 completed 绕过最终扫描（projection nonzero scan check skip）",
        [
            (
                PROJECTION,
                "    nonzero_scans = [\n"
                "        (owner_key, scans_by_owner.get(owner_key, 0))\n"
                "        for owner_key in snapshot_order\n"
                "        if scans_by_owner.get(owner_key, 0) != 0\n"
                "    ]\n"
                "    if nonzero_scans:",
                "    nonzero_scans = []  # mutation M6: bypass final scan\n"
                "    if False and nonzero_scans:  # mutation M6\n",
            )
        ],
        [f"{F10_TEST}::test_f10_m6_completed_bypass_scan_check_blocked"],
    ),
    # --- M7 重复 adapter 调用 ---
    # settlement._apply_window_outcome SUCCESS 路径在 fence/checkpoint 落账前强制再调
    # adapter → 测试断言 `lookup_calls` 不变必红。
    (
        "M7 重复 adapter 调用（_apply_window_outcome SUCCESS 路径多调 receipt_lookup）",
        [
            (
                SETTLEMENT,
                "        await self._close_window_ledger(session, t1, outcome)",
                "        # mutation M7: 多调一次 receipt_lookup（重放应不触发 adapter）\n"
                "        await self._recover_outside_locks(t1)\n"
                "        await self._close_window_ledger(session, t1, outcome)",
            )
        ],
        [f"{F10_TEST}::test_f10_no_body_resurrection_no_repeated_adapter_replay_idempotent"],
    ),
    # --- M8 ledger/binding per-ref receipt 丢失或 source 未清 ---
    # settlement._close_window_ledger 外部 ``write_erased_and_clear_ref`` 改为裸 UPDATE
    # erase_state='erased'（B2 唯一清除者越权 + 跳 receipt + 跳 source clear）。
    (
        "M8 ledger/binding per-ref receipt 丢失或 source 未清（B2 越权裸 UPDATE）",
        [
            (
                SETTLEMENT,
                "                await write_erased_and_clear_ref(\n"
                "                    session,\n"
                "                    ref=ref,\n"
                "                    receipt_digest=receipt_digest,\n"
                "                    tenant_id=t1.tenant_id,\n"
                "                )",
                "                # mutation M8: B2 越权裸 UPDATE（无 receipt、无 source clear）\n"
                "                await session.execute(\n"
                "                    text(\n"
                "                        \"UPDATE metaedu.agent_external_object_refs \"\n"
                "                        \"SET erase_state = 'erased' \"\n"
                "                        \"WHERE id = :id AND erase_state = 'registered'\"\n"
                "                    ),\n"
                "                    {\"id\": ref.id},\n"
                "                )",
            )
        ],
        [f"{F10_TEST}::test_f10_t1_then_advance_hold_t2_completes"],
    ),
]


def main() -> int:
    results = []
    kills = 0
    for name, edits, test_ids in MUTATIONS:
        files = []
        try:
            for f, old, new in edits:
                apply(f, old, new)
                if f not in files:
                    files.append(f)
            mutated = pytest_cmd(test_ids)
        finally:
            # 中断/异常也保证还原（try/finally 兜底，不遗留变异文件）。
            for f in files:
                restore(f)
        kill = mutated.returncode != 0
        clean = pytest_cmd(test_ids)
        ok = kill and clean.returncode == 0
        results.append(ok)
        kills += int(ok)
        print(
            f"{'KILLED' if ok else 'FAILED':8} "
            f"mutated={'red' if kill else 'NOT-RED'} "
            f"restored={'green' if clean.returncode == 0 else 'NOT-GREEN'} "
            f"{name}"
        )
        if not kill:
            print(
                "    ^ NOT-RED：如实登记，不计入 kill 分母（见 PR body 矩阵）"
            )
    print(
        f"\n{kills}/{len(results)} mutation kills passed（NOT-RED 已登记，不计入分母）"
    )
    return 0 if all(results) else 1


if __name__ == "__main__":
    _sys.exit(main())