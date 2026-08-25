"""R1-S6 TD-106 方案 A 具名 mutation kill 驱动（settlement SUCCESS ledger/binding 收口）。

契约：Plan §S6-15.5（TD-106 方案 A 裁决，2026-08-25）——settlement 态 1 SUCCESS
同事务逐 ref/binding 落 ledger/binding receipt + 清源 ref。

用法（须独占 metaedu_test——并发验证进程的 autouse TRUNCATE 会互相破坏）：

    cd packages/server-python
    uv run python ../../scripts/s6_td106_settlement_ledger_mutation_kill.py

每项：内存字符串替换（**不裸 git restore**——本分支 3 源文件均为未提交改动，git
restore 会抹掉实现；先保存 ``_BACKUPS[str(file)] = 原始 src``）→ 跑映射测试（期望
FAIL=红）→ try/finally 还原原文（``file.write_text(original)`` 严格字节还原）→ 再跑
映射测试（期望 PASS=绿）。**所有 mutation 绝不 commit / push**。

7 项具名 mutation（映射 §S6-15.5 方案 A 测试+mutation 证明矩阵）：
- M1 去掉 receipt 写（per-ref external receipt 占位化）→ test_external_single_ref_success_closure
- M2 去掉 source-ref 清除（write_erased_and_clear_ref 跳过 clear_external_source_ref）
  → test_external_single_ref_success_closure
- M3 改为聚合 receipt（_aggregate_window 丢 ref_closures per-ref 清单 → 收口 fail closed）
  → test_external_multi_ref_per_ref_receipt
- M4 移除单写 CAS（ledger UPDATE 去 registered+receipt NULL 谓词）
  → test_concurrent_settlement_single_writer_external
- M5 放宽缺 receipt 的成功路径（_aggregate_window 去空 evidence fail-closed 守卫）
  → test_missing_evidence_no_false_success_external
- M6 绕过 B2 唯一清除者 / E-1 source identity 重验（binding 冲突不再 fail closed）
  → test_source_mismatch_atomic_rollback_external
- M7 去掉关键 token 重验（_verify_t2_tokens 去 checkpoint.state == 'erasing'）
  → test_s6i3_fault_external.py::test_f11_mutate_checkpoint_state_during_lookup_fail_closed
  （判别载体为 F11 mutate-during-lookup；token 重验非本 PR 新增行为，TD-106 套件
   无 T1→T2 窗口内 mutation 用例）

所有 mutation 都通过 memory-backup + try/finally 还原（不依赖 git restore）。
NOT-RED 如实登记（说明原因），不计入 kill 分母。
"""

import subprocess
import sys as _sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SETTLEMENT = REPO / "packages/server-python/app/composition/settlement.py"
EXTERNAL_PARTICIPANT = (
    REPO / "packages/server-python/app/composition/external_ref_erasure_participant.py"
)
TEST_DIR = REPO / "packages/server-python"

TD106 = "tests/composition/test_s6_td106_settlement_ledger.py"


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=TEST_DIR)


def pytest_cmd(test_id: str) -> subprocess.CompletedProcess:
    return run(["uv", "run", "pytest", test_id, "-q", "--tb=line"])


_BACKUPS: dict[str, str] = {}


def apply(file: Path, old: str, new: str) -> None:
    src = file.read_text()
    assert old in src, f"anchor not found in {file}: {old[:80]!r}"
    _BACKUPS[str(file)] = src
    file.write_text(src.replace(old, new, 1))


def restore(file: Path) -> None:
    original = _BACKUPS.pop(str(file), None)
    if original is not None:
        file.write_text(original)


# ---------------------------------------------------------------------------
# MUTATIONS：每项 (name, file, old_anchor, new_anchor, test_nodeid)
# ---------------------------------------------------------------------------

MUTATIONS = [
    # --- M1 去掉 receipt 写：per-ref external receipt 占位化为固定串 ---
    (
        "M1 去掉 receipt 写（per-ref external receipt 占位化）",
        SETTLEMENT,
        "                receipt_digest = external_erase_receipt_digest(\n",
        '                receipt_digest = "a" * 64  # mutation: 去掉真实 receipt 写\n'
        "                _discard = external_erase_receipt_digest(\n",
        f"{TD106}::test_external_single_ref_success_closure",
    ),
    # --- M2 去掉 source-ref 清除 ---
    (
        "M2 去掉 source-ref 清除（write_erased_and_clear_ref 跳过 clear_external_source_ref）",
        EXTERNAL_PARTICIPANT,
        "    if current == ref.ref_value:\n"
        "        await clear_external_source_ref(session, tenant_id=tenant_id, ref=ref)\n",
        "    if False and current == ref.ref_value:  # mutation: 去掉 source-ref 清除\n"
        "        await clear_external_source_ref(session, tenant_id=tenant_id, ref=ref)\n",
        f"{TD106}::test_external_single_ref_success_closure",
    ),
    # --- M3 改为聚合 receipt：丢 per-ref closure 清单 ---
    (
        "M3 改为聚合 receipt（_aggregate_window 丢 ref_closures → 收口 fail closed）",
        SETTLEMENT,
        "        return _WindowOutcome(OutputState.SUCCESS, ack_digest=ack, ref_closures=closures)\n",
        "        return _WindowOutcome(OutputState.SUCCESS, ack_digest=ack)  # mutation: 聚合丢 per-ref\n",
        f"{TD106}::test_external_multi_ref_per_ref_receipt",
    ),
    # --- M4 移除单写 CAS ---
    (
        "M4 移除单写 CAS（ledger UPDATE 去 registered+receipt NULL 谓词）",
        EXTERNAL_PARTICIPANT,
        '            "AND erase_state = \'registered\' AND receipt_digest IS NULL"\n',
        '            "AND true"  # mutation: 移除单写 CAS\n',
        f"{TD106}::test_ledger_write_cas_idempotent_guard_external",
    ),
    # --- M5 放宽缺 receipt 的成功路径 ---
    (
        "M5 放宽缺 receipt 成功路径（去空 evidence fail-closed 守卫）",
        SETTLEMENT,
        '        if any(not (o.ack_evidence or "").strip() for o in ref_outcomes):\n',
        '        if False and any(not (o.ack_evidence or "").strip() for o in ref_outcomes):  # mutation\n',
        f"{TD106}::test_missing_evidence_no_false_success_external",
    ),
    # --- M6 绕过 B2 唯一清除者 / E-1 source identity 重验 ---
    (
        "M6 绕过 B2 唯一清除者 / E-1 source identity 重验（binding 冲突不 fail closed）",
        EXTERNAL_PARTICIPANT,
        "    if current is not None and current != ref.ref_value:\n",
        "    if False and current is not None and current != ref.ref_value:  # mutation: 绕过 E-1/B2\n",
        f"{TD106}::test_source_mismatch_atomic_rollback_external",
    ),
    # --- M7 去掉关键 token 重验（checkpoint.state == 'erasing'）---
    (
        "M7 去掉关键 token 重验（_verify_t2_tokens 去 checkpoint.state == 'erasing'）",
        SETTLEMENT,
        '        if checkpoint.state != "erasing":\n'
        "            raise ValueError(\n"
        '                f"T2 checkpoint state {checkpoint.state!r} != erasing; "',
        '        if False and checkpoint.state != "erasing":  # mutation: 去 token 重验\n'
        "            raise ValueError(\n"
        '                f"T2 checkpoint state {checkpoint.state!r} != erasing; "',
        "tests/composition/test_s6i3_fault_external.py::test_f11_mutate_checkpoint_state_during_lookup_fail_closed",
    ),
]


def main() -> int:
    results = []
    kills = 0
    for name, path, old, new, test_id in MUTATIONS:
        apply(path, old, new)
        try:
            mutated = pytest_cmd(test_id)
        finally:
            # 中断/异常也保证还原（try/finally 兜底，不遗留变异文件）。
            restore(path)
        kill = mutated.returncode != 0
        clean = pytest_cmd(test_id)
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
            print("    ^ NOT-RED：如实登记，不计入 kill 分母（见 PR body 矩阵）")
    print(f"\n{kills}/{len(results)} mutation kills passed（NOT-RED 已登记，不计入分母）")
    return 0 if all(results) else 1


if __name__ == "__main__":
    _sys.exit(main())
