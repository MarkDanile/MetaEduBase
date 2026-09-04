"""R1-S6 S6-I3 具名 mutation kill 驱动（PR #589 stacked 续 PR #586，
# I3-C 故障矩阵完整批；14 行 F1..F14 + F10 契约冲突 skip）。

契约：Plan §R1-S6-5（14 行故障点冻结）。

用法（须独占 metaedu_test——并发验证进程的 autouse TRUNCATE 会互相破坏）：

    cd packages/server-python
    uv run python ../../scripts/s6i3_fault_matrix_mutation_kill.py

每项：内存字符串替换（**不裸 git restore**，避免抹掉本分支未提交源码）→ 跑映射
测试（期望 FAIL=红）→ try/finally 还原原文（**先保存 _BACKUPS[str(file)] = 原始
src**，最后 ``file.write_text(original)`` 严格字节还原）→ 再跑映射测试（期望
PASS=绿）。**所有 mutation 绝不 commit / push**。

F1-F14 映射（每行 1 个具名 mutation；F10 契约冲突 skip）：
- M-F13 takeover _TAKEOVER_SQL 跳过 lease_epoch CAS → F1/F13 撕裂
- M-F2 claim 不持 Conversation FOR UPDATE → F2 准备就绪门失效
  （Phase 2 修正：原 F2/F8 共享测试 → F2 单独判别载体 `test_mf2_lock_conversation_serializes_dual_claim`；
   F8 单独判别 → `test_mf8_top_operation_for_update_locks_existing_row`）
- M-F3 _ack_lost_repair 不写 ack_digest → F3 重放入口识别失效
- M-F4 external _write_erased_and_clear_ref 跳过 _clear_source_ref → F4 收口失
- M-F5 closeout _classify_input 跳过 checkpoint.state == 'erasing' → F5 ledger
  收敛失效
- M-F6 _find_event_gap count 比较改 true → F6 409 失效
- M-F7 retention prune 不置 event_log_complete=false → F7 410 失效
- M-F8 _select_top_purge_operation_for_update 去掉 FOR UPDATE → F8 重入撕裂
  （Phase 2 修正：F2/F8 共享断言拆分为 F2 单独判别 + F8 单独判别；F8 真红需 existing
   operation 行锁 + SET LOCAL lock_timeout `1s` + OperationalError `lock timeout` 断言——
   见 `test_mf8_top_operation_for_update_locks_existing_row`）
- M-F9 _load_verified_operation 跳过 hold_revision drift → F9 快照校验失效
- M-F11 settlement _verify_t2_tokens 跳过 checkpoint.state == 'erasing' 重验 →
  F11 fail closed 失效
- M-F12 retention _lock_run_row 不取 FOR UPDATE → F12 行锁串行失效
- M-F14 claim _lock_conversation 去掉 tenant_id 谓词 → F14 跨 tenant 命中

所有 mutation 都通过 memory-backup + try/finally 还原（不依赖 git restore）。
"""

import subprocess
import sys as _sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORKER = REPO / "packages/server-python/app/composition/retention_workers.py"
SETTLEMENT = REPO / "packages/server-python/app/composition/settlement.py"
CLAIM = REPO / "packages/server-python/app/composition/conversation_purge_scheduler.py"
EXTERNAL_PARTICIPANT = (
    REPO / "packages/server-python/app/composition/external_ref_erasure_participant.py"
)
ERASURE_PARTICIPANT = (
    REPO
    / "packages/server-python/app/contexts/agent_workspace/infrastructure/workspace_erasure_participant.py"
)
EXEC_REPO = (
    REPO
    / "packages/server-python/app/contexts/agent_execution/infrastructure/execution_query_repository.py"
)
TEST_DIR = REPO / "packages/server-python"


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
# MUTATIONS：每项 (name, file, old_anchor_with_sentinel, new_anchor, test_nodeid)
# 所有 anchor 用 sentinel（前后行）确保唯一。
# ---------------------------------------------------------------------------

MUTATIONS = [
    # --- F1/F13 takeover _TAKEOVER_SQL 跳过 lease_epoch CAS ---
    (
        "M-F13 takeover _TAKEOVER_SQL 跳过 lease_epoch CAS",
        CLAIM,
        # sentinel：前一行 `id = :op AND conversation_id = :cid` + 目标行
        'AND id = :op AND conversation_id = :cid "\n        "AND lease_epoch = :expected "\n',
        'AND id = :op AND conversation_id = :cid "\n        "AND true "\n',
        "tests/composition/test_s6i3_fault_scheduler.py::test_f13_process_kill_equivalence_lease_expiry_takeover_single_writer",
    ),
    # --- F2 claim 不持 Conversation FOR UPDATE ---
    (
        "M-F2 _lock_conversation 跳过 .with_for_update()",
        CLAIM,
        '                .where(\n                    ConversationModel.tenant_id == tenant_id,\n                    ConversationModel.id == conversation_id,\n                )\n                .with_for_update()',
        '                .where(\n                    ConversationModel.tenant_id == tenant_id,\n                    ConversationModel.id == conversation_id,\n                )\n                # mutation: skip FOR UPDATE',
        "tests/composition/test_s6i3_fault_mutation_evidence.py::test_mf2_lock_conversation_serializes_dual_claim",
    ),
    # --- F3 _ack_lost_repair 不写 ack_digest ---
    # Phase 0 契约审计修正：原映射 test_f3_lease_ack_lost_replay_no_fork（仅 raw SQL
    # seed + COUNT(*)断言，**不**调被变异 _ack_lost_repair helper）→ 改映射到
    # ``test_settlement_ack_lost_repair``（真实经 closeout_erasing → _classify_input
    # ("ack_lost") → _ack_lost_repair → 断言 ack_digest 字段）。
    (
        "M-F3 _ack_lost_repair 跳过 ack_digest 写入",
        SETTLEMENT,
        '        checkpoint.state = "acked"\n        checkpoint.ack_digest = ack_digest\n',
        '        checkpoint.state = "acked"\n        checkpoint.ack_digest = None  # mutation: skip\n',
        "tests/composition/test_s5_sch_d_settlement.py::test_settlement_ack_lost_repair",
    ),
    # --- F4 external 唯一清除路径跳过 source-ref 清除 ---
    # TD-106 方案 A（stacked impl PR）：participant Tx2 的清除逻辑已提取为模块级
    # 唯一写入路径 ``write_erased_and_clear_ref``（E-5-2 B2，settlement 收口共用），
    # 原 ``_write_erased_and_clear_ref`` 方法改为薄委托。锚点同步指向模块级实现
    # （4 空格缩进 + ``clear_external_source_ref``），不再匹配 reconcile 路径的
    # ``self._clear_source_ref`` 调用点。
    (
        "M-F4 external write_erased_and_clear_ref 跳过 clear_external_source_ref",
        EXTERNAL_PARTICIPANT,
        '    if current == ref.ref_value:\n        await clear_external_source_ref(session, tenant_id=tenant_id, ref=ref)',
        '    if False and current == ref.ref_value:  # mutation: skip clear_external_source_ref\n        await clear_external_source_ref(session, tenant_id=tenant_id, ref=ref)',
        "tests/composition/test_s6i3_fault_external.py::test_f4_single_owner_stepwise_ack_partial_ref_crash_replay",
    ),
    # --- F5 closeout _classify_input 跳过 checkpoint.state == 'erasing' 分支 ---
    # Phase 0 契约审计修正：原映射 test_f5_ack_after_operation_pre_aggregation_crash_takeover_safe
    # （仅 raw SQL + 4 owner acked seed，**不**调 _classify_input，且 seed 用 checkpoint=acked
    # 不进 mutated `erasing` 分支）→ 改映射到 ``test_external_multi_ref_per_ref_receipt``（真实
    # 经 closeout_erasing → _classify_input(fence=erasing, checkpoint=erasing) → mutated
    # 分支 → _t1_plan_recovery → adapter → ledger 写入路径）。
    (
        "M-F5 _classify_input 不分 'erasing'+'erasing'（接 eraser 后强制走 post_window_blocked）",
        SETTLEMENT,
        '            if checkpoint.state == "blocked":\n                return "post_window_blocked"\n            if checkpoint.state == "erasing":\n                return "window_erasing"',
        '            if checkpoint.state == "blocked":\n                return "post_window_blocked"\n            if False:  # mutation: collapse erasing into blocked\n                return "window_erasing"\n            if checkpoint.state == "erasing":\n                return "post_window_blocked"  # mutation: collapse',
        "tests/composition/test_s6_td106_settlement_ledger.py::test_external_multi_ref_per_ref_receipt",
    ),
    # --- F6 _find_event_gap count 比较改 true ---
    (
        "M-F6 _find_event_gap 顶部强制 return None（gap 永远不检出）",
        EXEC_REPO,
        '    async def _find_event_gap(\n        self,\n        *,\n        tenant_id: uuid.UUID,\n        run_id: uuid.UUID,\n        lower_bound: int,\n        upper_bound: int,\n    ) -> tuple[int, int | None] | None:\n        count, minimum, maximum = (',
        '    async def _find_event_gap(\n        self,\n        *,\n        tenant_id: uuid.UUID,\n        run_id: uuid.UUID,\n        lower_bound: int,\n        upper_bound: int,\n    ) -> tuple[int, int | None] | None:\n        if True:  # mutation: gap 永远不检出\n            return None\n        count, minimum, maximum = (',
        "tests/composition/test_s6i3_fault_events.py::test_f6_seq_gap_raw_delete_window_409_and_stale_410",
    ),
    # --- F7 retention prune 不置 event_log_complete=false ---
    (
        "M-F7 retention prune 不置 event_log_complete=false",
        WORKER,
        '            "SET first_available_event_seq = :first_available, "\n            "event_log_complete = false "\n',
        '            "SET first_available_event_seq = :first_available, "\n            "event_log_complete = true "\n',
        "tests/composition/test_s6i3_fault_events.py::test_f7_first_available_advance_sse_410_monotone_no_gap",
    ),
    # --- F8 _select_top_purge_operation_for_update 不取 FOR UPDATE ---
    # Phase 2 M-F8 单独判别载体（新增 test_mf8_top_operation_for_update_locks_existing_row）：
    # existing purge operation row 持锁 + SET LOCAL lock_timeout + OperationalError "lock timeout"/55P03 断言。
    # 移除 .with_for_update() 后 B 不会 lock-timeout → pytest.raises OperationalError 不触发 → assertion failure → KILLED。
    (
        "M-F8 _select_top_purge_operation_for_update 跳过 FOR UPDATE",
        CLAIM,
        '                .order_by(PurgeOperationModel.purge_revision.desc())\n                .limit(1)\n                .with_for_update()',
        '                .order_by(PurgeOperationModel.purge_revision.desc())\n                .limit(1)\n                # mutation: skip FOR UPDATE',
        "tests/composition/test_s6i3_fault_mutation_evidence.py::test_mf8_top_operation_for_update_locks_existing_row",
    ),
    # --- F9 _load_verified_operation 跳过 hold_revision drift ---
    (
        "M-F9 _load_verified_operation 跳过 hold_revision drift 校验",
        ERASURE_PARTICIPANT,
        '        if operation.hold_revision_snapshot != hold_revision:\n            raise ValueError(',
        '        if False:  # mutation: skip hold_revision drift\n            raise ValueError(',
        "tests/composition/test_s6i3_fault_hold.py::test_f9_create_before_entry_blocks_entry_fail_closed",
    ),
    # --- F11 settlement _verify_t2_tokens 跳过 checkpoint.state == 'erasing' 重验 ---
    (
        "M-F11 _verify_t2_tokens 跳过 checkpoint.state == 'erasing' 重验",
        SETTLEMENT,
        '        if checkpoint.state != "erasing":\n            raise ValueError(\n                f"T2 checkpoint state {checkpoint.state!r} != erasing; "',
        '        if False and checkpoint.state != "erasing":  # mutation: skip\n            raise ValueError(\n                f"T2 checkpoint state {checkpoint.state!r} != erasing; "',
        "tests/composition/test_s6i3_fault_external.py::test_f11_mutate_checkpoint_state_during_lookup_fail_closed",
    ),
    # --- F12 retention _lock_run_row 不取 FOR UPDATE ---
    (
        "M-F12 retention _lock_run_row 不取 FOR UPDATE",
        WORKER,
        '            "SELECT id, tenant_id, conversation_id, first_available_event_seq, "\n            "next_event_seq, event_log_complete "\n            "FROM metaedu.agent_runs "\n            "WHERE tenant_id = :tid AND id = :rid FOR UPDATE"',
        '            "SELECT id, tenant_id, conversation_id, first_available_event_seq, "\n            "next_event_seq, event_log_complete "\n            "FROM metaedu.agent_runs "\n            "WHERE tenant_id = :tid AND id = :rid"  # mutation: skip FOR UPDATE',
        "tests/composition/test_s6i3_fault_events.py::test_f12_retention_run_row_lock_serializes_writers",
    ),
    # --- F14 claim _lock_conversation 去掉 tenant_id 谓词 ---
    (
        "M-F14 _lock_conversation 去掉 tenant_id 谓词",
        CLAIM,
        '                .where(\n                    ConversationModel.tenant_id == tenant_id,\n                    ConversationModel.id == conversation_id,\n                )\n                .with_for_update()',
        '                .where(\n                    # mutation: drop tenant predicate\n                    ConversationModel.id == conversation_id,\n                )\n                .with_for_update()',
        "tests/composition/test_s6i3_fault_scheduler.py::test_f14_cross_tenant_claim_takeover_zero_write_fail_closed",
    ),
]


def main() -> int:
    results = []
    for name, path, old, new, test_id in MUTATIONS:
        apply(path, old, new)
        try:
            mutated = pytest_cmd(test_id)
        finally:
            # 中断/异常也保证还原（P3-1：try/finally 兜底，不遗留变异文件）。
            restore(path)
        kill = mutated.returncode != 0
        clean = pytest_cmd(test_id)
        ok = kill and clean.returncode == 0
        results.append(ok)
        print(
            f"{'KILLED' if ok else 'FAILED':8} "
            f"mutated={'red' if kill else 'NOT-RED'} "
            f"restored={'green' if clean.returncode == 0 else 'NOT-GREEN'} "
            f"{name}"
        )
    print(f"\n{sum(results)}/{len(results)} mutation kills passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    _sys.exit(main())