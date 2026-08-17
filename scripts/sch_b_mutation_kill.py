"""R1-S5 SCH-B 10 项具名 mutation kill 驱动（可复现证据链）。

用法（须独占 metaedu_test）：

    cd packages/server-python
    uv run python ../../scripts/sch_b_mutation_kill.py

每项：应用变异 → 跑映射测试（期望红）→ git restore → 跑映射测试（期望绿）。
变异绝不提交。
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ORCH = (
    REPO
    / "packages/server-python/app/composition/owner_execution_orchestrator.py"
)
TEST_DIR = REPO / "packages/server-python"
TEST = "tests/composition/test_s5_sch_b_orchestrator.py"

MUTATIONS = [
    (
        "M-SCH-B-owner-order 未按字典序",
        ["        for owner_key in (str(o[\"owner_key\"]) for o in registry_snapshot()):"],
        ["        for owner_key in reversed([str(o[\"owner_key\"]) for o in registry_snapshot()]):  # M"],
        f"{TEST}::test_owner_lexicographic_order_and_per_owner_coordinator",
    ),
    (
        "M-SCH-B-coordinator 漏聚合",
        ["                await self._aggregate(tenant_id, conversation_id, purge_operation_id)\n"
         "                aggregations += 1"],
        ["                aggregations += 1  # M：跳过聚合"],
        f"{TEST}::test_owner_lexicographic_order_and_per_owner_coordinator",
    ),
    (
        "M-SCH-B-erasing 直接 entry",
        ["            if state == \"erasing\":"],
        ["            if False:  # M：erasing 不交 settlement 而直接 entry"],
        f"{TEST}::test_erasing_delegates_to_settlement_port",
    ),
    (
        "M-SCH-B-reject 拒绝域仍 entry",
        ["                if reason is not None and not is_retryable_reason(reason):\n"
         "                    return \"skipped\"  # 拒绝域：reconcile-only，不重开"],
        ["                if False:\n"
         "                    return \"skipped\"  # M：拒绝域放行"],
        f"{TEST}::test_blocked_whitelist_vs_reject",
    ),
    (
        "M-SCH-B-budget-reason failed 丢 reason",
        ['                "state = \'failed\', reason_code = :reason "'],
        ['                "state = \'failed\', reason_code = NULL "  # M：丢 reason'],
        f"{TEST}::test_budget_exhaustion_writes_failed",
    ),
    (
        "M-SCH-B-pre-window 计入预算",
        ["                    and not is_pre_window_gate(reason)\n"
         "                    and attempt >= RETRY_BUDGET"],
        ["                    and attempt >= RETRY_BUDGET  # M：pre-window 计预算"],
        f"{TEST}::test_pre_window_gate_exempts_budget",
    ),
    (
        "M-SCH-B-skip-acked 重跑 acked",
        ['            if state in ("acked", "failed"):'],
        ['            if state == "failed":  # M：acked 不跳过'],
        f"{TEST}::test_skips_acked_and_failed",
    ),
    (
        "M-SCH-B-tenant 裸 id 谓词（verify 双查询去 tenant）",
        ["                        ConversationModel.tenant_id == tenant_id,\n"
         "                        ConversationModel.id == conversation_id,",
         "                        PurgeOperationModel.tenant_id == tenant_id,\n"
         "                        PurgeOperationModel.id == purge_operation_id,"],
        ["                        ConversationModel.id == conversation_id,  # M\n",
         "                        PurgeOperationModel.id == purge_operation_id,  # M\n"],
        f"{TEST}::test_cross_tenant_zero_entry",
    ),
    (
        "M-SCH-B-old-token 过期租约不 fail-closed",
        ["            if operation.lease_expires_at is None or operation.lease_expires_at <= now:"],
        ["            if False:  # M：过期租约放行"],
        f"{TEST}::test_expired_lease_fails_closed",
    ),
    (
        "M-SCH-B-tick 漏候选",
        ['                    "AND lease_expires_at IS NOT NULL "'],
        ['                    "AND lease_expires_at IS NULL "  # M：反谓词漏候选'],
        f"{TEST}::test_tick_forces_aggregation",
    ),
]


def apply(olds: list[str], news: list[str]) -> None:
    src = ORCH.read_text()
    for old, new in zip(olds, news):
        assert old in src, f"anchor not found: {old[:60]!r}"
        src = src.replace(old, new, 1)
    ORCH.write_text(src)



def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=TEST_DIR)


def restore() -> None:
    run(["git", "restore", "--", str(ORCH)])


def pytest_cmd(test_id: str) -> subprocess.CompletedProcess:
    return run(["uv", "run", "pytest", test_id, "-q", "--tb=line"])


def main() -> int:
    results = []
    for name, olds, news, test_id in MUTATIONS:
        apply(olds, news)
        mutated = pytest_cmd(test_id)
        kill = mutated.returncode != 0
        restore()
        clean = pytest_cmd(test_id)
        ok = kill and clean.returncode == 0
        results.append(ok)
        print(
            f"{'KILLED' if ok else 'FAILED':8} "
            f"mutated={'red' if kill else 'NOT-RED'} "
            f"restored={'green' if clean.returncode == 0 else 'NOT-GREEN'} {name}"
        )
    print(f"\n{sum(results)}/{len(results)} mutation kills passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
