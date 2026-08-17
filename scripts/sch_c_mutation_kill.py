"""R1-S5 SCH-C 反例矩阵完整性收口批次 mutation kill 驱动（可复现证据链）。

用法（须独占 metaedu_test）：

    cd packages/server-python
    uv run python ../../scripts/sch_c_mutation_kill.py

每项：应用变异 → 跑映射测试（期望红）→ git restore → 跑映射测试（期望绿）。
变异绝不提交。主体靶 SCH-C 新代码（purge_rebuild.py / predecessor_lineage.py /
projection_calculator.py）；行 31 靶 SCH-B 编排器白名单、行 21 靶 I2 family-B
门禁（均为**临时变异回归验证**——若当前源码暴露 SCH-B/I2 缺陷即停，不在 SCH-C
偷改上层实现）。
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REBUILD = REPO / "packages/server-python/app/composition/purge_rebuild.py"
LINEAGE = REPO / "packages/server-python/app/composition/predecessor_lineage.py"
CALC = REPO / "packages/server-python/app/composition/projection_calculator.py"
ORCH = REPO / "packages/server-python/app/composition/owner_execution_orchestrator.py"
WS_PARTICIPANT = (
    REPO
    / "packages/server-python/app/contexts/agent_workspace/infrastructure/workspace_erasure_participant.py"
)
EX_PARTICIPANT = (
    REPO
    / "packages/server-python/app/contexts/agent_execution/infrastructure/execution_erasure_participant.py"
)
TEST_DIR = REPO / "packages/server-python"
TEST = "tests/composition/test_s5_sch_c_rebuild_seeding.py"

# 反例矩阵完整性收口批次新增测试集合（部分 mutation 多测试共享）。
_T = f"{TEST}::"

# (name, file, [olds], [news], [tests])
MUTATIONS = [
    (
        "M-SCH-C-drift-gate 无 drift 也 rebuild",
        REBUILD,
        ['        if top.state != "blocked" or top.failure_code not in _G1_G2_FAILURE_CODES:'],
        ['        if False:  # M：无 drift 也 rebuild'],
        [
            f"{_T}test_rebuild_idempotent_no_drift",
        ],
    ),
    (
        "M-SCH-C-quiesce erasing 未挡 rebuild",
        REBUILD,
        ["        if self._has_erasing(predecessor_checkpoints, predecessor_fences):\n            return RebuildOutcome(RebuildKind.QUIESCE)"],
        ["        if False:  # M：erasing 放行"],
        [
            f"{_T}test_rebuild_quiesce_erasing",
        ],
    ),
    (
        "M-SCH-C-deleted restore 未挡 rebuild",
        REBUILD,
        ['        if conversation.state != "deleted":\n            return RebuildOutcome(RebuildKind.NOT_DUE)'],
        ['        if False:  # M：restore 放行'],
        [
            f"{_T}test_rebuild_restore_active_zero_rows",
        ],
    ),
    (
        "M-SCH-C-lineage-conflict 阶段 1 失败不回滚",
        REBUILD,
        ["        if any(f.lineage_status == \"conflict\" for f in lineage.values()):\n            raise ValueError(\"lineage stage-1 verification failed; rollback rebuild\")"],
        ["        if False:  # M：lineage 失败放行"],
        [
            f"{_T}test_rebuild_seeding_lineage_fail_rolls_back",
        ],
    ),
    (
        "M-SCH-C-removed removed unfinished 放行",
        REBUILD,
        ["        if self._removed_unfinished(diff, predecessor_checkpoints, predecessor_fences):\n            raise ValueError(\n                \"removed owner with unfinished obligation; rebuild fail closed\"\n            )"],
        ["        if False:  # M：removed unfinished 放行"],
        [
            f"{_T}test_rebuild_removed_unfinished_fail_closed",
        ],
    ),
    (
        "M-SCH-C-carry 3/5/6 被重开 pending",
        LINEAGE,
        ['def _is_carry_reason(reason: str) -> bool:\n    return reason.endswith(_CARRY_REASON_SUFFIXES)'],
        ['def _is_carry_reason(reason: str) -> bool:\n    return False  # M：carry 重开'],
        [
            f"{_T}test_rebuild_outcome_unknown_carry",
            f"{_T}test_rebuild_partial_ack_mixed_obligations",
            f"{_T}test_rebuild_re_added_reason_family_parametrized[3-5-6-outcome-unknown]",
            f"{_T}test_rebuild_version_changed_reason_family_parametrized[3-outcome-unknown]",
            f"{_T}test_rebuild_version_changed_reason_family_parametrized[5-deadline-expired]",
            f"{_T}test_rebuild_version_changed_reason_family_parametrized[6-adapter-unresolvable]",
        ],
    ),
    (
        "M-SCH-C-lease rebuild 未 acquire lease",
        REBUILD,
        ['        token_row = (await self._session.execute(\n            self._ACQUIRE_SQL,'],
        ['        token_row = None  # M：未 acquire\n        _unused = (await self._session.execute(\n            self._ACQUIRE_SQL,'],
        [
            f"{_T}test_rebuild_g2_creates_new_revision_and_acquires_lease",
        ],
    ),
    (
        "M-SCH-C-writeback purge_revision 未写回",
        REBUILD,
        ['        await self._session.execute(\n            text(\n                "UPDATE metaedu.agent_conversations SET purge_revision = :r "\n                "WHERE tenant_id = :tid AND id = :cid"\n            ),\n            {"r": new_revision, "tid": tenant_id, "cid": conversation_id},\n        )'],
        ['        # M：未写回 conversation.purge_revision'],
        [
            f"{_T}test_rebuild_g2_creates_new_revision_and_acquires_lease",
        ],
    ),
    (
        "M-SCH-C-null-reason NULL 重开 pending",
        LINEAGE,
        ['        if reason is None:\n            # NULL reason 不得落入通用 pending 分支（S5-B-2 硬约束④）。\n            return LineageFact(entry.owner_key, "conflict", "native_pending")'],
        ['        if reason is None:\n            return LineageFact(entry.owner_key, "not_applicable", "native_pending")  # M'],
        [
            f"{_T}test_rebuild_blocked_null_reason_rolls_back",
            f"{_T}test_rebuild_re_added_reason_family_parametrized[null-dirty-data]",
        ],
    ),
    (
        "M-SCH-C-ack-lost blocked×erased 放行",
        LINEAGE,
        ['        if fence == "erased":\n            # blocked × erased = S5-C-1 ACK-lost 输入态，非 rebuild 可判义务，dirty-data。\n            return LineageFact(entry.owner_key, "conflict", "native_pending")'],
        ['        if False:  # M：ACK-lost 放行'],
        [
            f"{_T}test_rebuild_blocked_erased_fence_conflict",
        ],
    ),
    (
        "M-SCH-C-re-added 缺 cp 非 erased 未重开 pending",
        LINEAGE,
        ['        # 缺 cp 且 fence 非 erased → 义务重开 pending（缺行不视为已完成）。\n        return LineageFact(entry.owner_key, "not_applicable", "native_pending")'],
        ['        # 缺 cp 且 fence 非 erased → M：误判 conflict\n        return LineageFact(entry.owner_key, "conflict", "native_pending")'],
        [
            f"{_T}test_rebuild_re_added_missing_cp_reopens",
        ],
    ),
    (
        "M-SCH-C-six-item lineage 六项恒真（逐跳重验）",
        LINEAGE,
        ["    if fact.checkpoint_state != \"acked\":\n        return False  # 六项 2"],
        ["    return True  # M：六项恒真\n    if fact.checkpoint_state != \"acked\":\n        return False  # 六项 2"],
        [
            f"{_T}test_rebuild_forged_ack_digest_rolls_back",
            f"{_T}test_coordinator_double_chain_tamper_g4",
            f"{_T}test_coordinator_stage2_fence_tamper_g4",
        ],
    ),
    # ---- 反例矩阵完整性收口批次新增 mutation ----
    (
        "M-SCH-C-caseE-migrate active fence 未迁移",
        REBUILD,
        ['        for key in diff.version_changed:\n            fence = predecessor_fences.get(key)\n            if fence is not None and fence.state == "active":'],
        ['        for key in diff.version_changed:\n            fence = predecessor_fences.get(key)\n            if False:  # M：active fence 未迁移'],
        [
            f"{_T}test_rebuild_case_e_active_fence_migrates",
        ],
    ),
    (
        "M-SCH-C-caseE-erased erased fence 放行 seed",
        LINEAGE,
        ['    if fact.fence_state == "erased":\n        return LineageFact(entry.owner_key, "conflict", "native_pending")'],
        ['    if fact.fence_state == "erased":\n        return LineageFact(entry.owner_key, "not_applicable", "native_pending")  # M'],
        [
            f"{_T}test_rebuild_case_e_erased_fence_fail_closed",
            f"{_T}test_rebuild_version_changed_reason_family_parametrized[output-4-erased-fence]",
        ],
    ),
    (
        "M-SCH-C-batch-seed 分批提交 seed",
        REBUILD,
        ['        for entry in current_snapshot:\n            await self._seed_checkpoint(\n                tenant_id=tenant_id,\n                purge_operation_id=operation.id,\n                entry=entry,\n                lineage=lineage[entry.owner_key],\n                predecessor_fact=facts.get(entry.owner_key),\n                diff=diff,\n            )'],
        ['        for entry in current_snapshot:\n            await self._seed_checkpoint(\n                tenant_id=tenant_id,\n                purge_operation_id=operation.id,\n                entry=entry,\n                lineage=lineage[entry.owner_key],\n                predecessor_fact=facts.get(entry.owner_key),\n                diff=diff,\n            )\n        await self._session.commit()  # M：分批提交 seed'],
        [
            f"{_T}test_rebuild_seeding_crash_atomic_rollback",
        ],
    ),
    (
        "M-SCH-C-revision-collision revision 不复用（对 superseded op 继续写）",
        REBUILD,
        ['        new_revision = conversation.purge_revision + 1'],
        ['        new_revision = conversation.purge_revision  # M：revision 不复用'],
        [
            f"{_T}test_rebuild_double_drift_chain",
            f"{_T}test_sch3_hold_create_quiesce_release_rebuild_full_sequence",
        ],
    ),
    (
        "M-SCH-C-tenant-scope lineage 定位去掉 tenant 维度",
        REBUILD,
        ['                select(PurgeOwnerCheckpointModel).where(\n                    PurgeOwnerCheckpointModel.tenant_id == tenant_id,\n                    PurgeOwnerCheckpointModel.purge_operation_id == purge_operation_id,'],
        ['                select(PurgeOwnerCheckpointModel).where(\n                    PurgeOwnerCheckpointModel.purge_operation_id == purge_operation_id,'],
        [
            f"{_T}test_rebuild_cross_tenant_predecessor_forgery",
        ],
    ),
    (
        "M-SCH-C-re-added-pending re-added 按新增建 pending",
        LINEAGE,
        ['    if fact is None:\n        return LineageFact(entry.owner_key, "not_applicable", "native_pending")'],
        ['    return LineageFact(entry.owner_key, "not_applicable", "native_pending")  # M：按新增建 pending\n    if fact is None:\n        return LineageFact(entry.owner_key, "not_applicable", "native_pending")'],
        [
            f"{_T}test_rebuild_re_added_erased_native_anchor",
        ],
    ),
    (
        "M-SCH-C-hold-gate active hold 期间 eager rebuild",
        REBUILD,
        ['        if await self._repo.has_active_legal_hold(\n            tenant_id=tenant_id, conversation_id=conversation_id\n        ):\n            return RebuildOutcome(RebuildKind.HOLD_GATED)'],
        ['        if False:  # M：active hold 期间 eager rebuild'],
        [
            f"{_T}test_rebuild_active_hold_defers",
        ],
    ),
    (
        "M-SCH-C-snapshot-set 只取旧 snapshot owner 集",
        REBUILD,
        ['        for entry in current_snapshot:\n            await self._seed_checkpoint('],
        ['        for entry in old_snapshot:  # M：只取旧 snapshot owner 集\n            await self._seed_checkpoint('],
        [
            f"{_T}test_rebuild_added_owner_pending",
            f"{_T}test_rebuild_removed_completed_skips",
        ],
    ),
    (
        "M-SCH-C-idempotent 并发二建不幂等",
        REBUILD,
        ['                return RebuildOutcome(\n                    RebuildKind.IDEMPOTENT,\n                    purge_operation_id=top.id,\n                    purge_revision=top.purge_revision,\n                )'],
        ['                return RebuildOutcome(RebuildKind.NOT_DUE)  # M：不幂等'],
        [
            f"{_T}test_rebuild_concurrent_single_revision",
        ],
    ),
    (
        "M-SCH-C-inherited-ack inherited ACK 不计入全 acked",
        CALC,
        ['    elif fence_row.purge_revision < operation_purge_revision:\n        # inherited 例外（回填自 S5-B-8 第 1 项）：lineage 六项全过（lineage_status\n        # == valid）才记入「全 owner acked」；否则矛盾 fail closed。\n        if lineage_status != "valid":\n            return False'],
        ['    elif fence_row.purge_revision < operation_purge_revision:\n        return False  # M：inherited ACK 不计入全 acked'],
        [
            f"{_T}test_coordinator_inherited_ack_counts_completed",
        ],
    ),
    (
        "M-SCH-C-missing-row-native 缺行按 native_pending 判 running",
        CALC,
        ['    for owner_key in missing_owners:\n        if lineage_of(owner_key).expected_obligation_kind != "native_pending":'],
        ['    for owner_key in missing_owners:\n        if False:  # M：缺行按 native_pending 判 running'],
        [
            f"{_T}test_seeded_missing_row_g4_conflict",
        ],
    ),
    (
        "M-SCH-C-whitelist-356 SCH-B 白名单含 3/5/6（临时变异 SCH-B 编排器）",
        ORCH,
        ['_RETRYABLE_SUFFIXES = ("_erase_timeout", "_adapter_unavailable", "_scan_nonzero")'],
        ['_RETRYABLE_SUFFIXES = (\n    "_erase_timeout",\n    "_adapter_unavailable",\n    "_scan_nonzero",\n    "_outcome_unknown",\n    "_settlement_deadline_expired",\n    "_adapter_unresolvable",\n)  # M：白名单含 3/5/6'],
        [
            f"{_T}test_schb_retry_whitelist_3_5_6_zero_side_effects",
        ],
    ),
    (
        "M-SCH-C-first-lock 移除 Conversation 首锁",
        REBUILD,
        ['                select(ConversationModel)\n                .where(\n                    ConversationModel.tenant_id == tenant_id,\n                    ConversationModel.id == conversation_id,\n                )\n                .with_for_update()\n            )'],
        ['                select(ConversationModel)\n                .where(\n                    ConversationModel.tenant_id == tenant_id,\n                    ConversationModel.id == conversation_id,\n                )\n                # M：移除 Conversation 首锁\n            )'],
        [
            f"{_T}test_rebuild_stage2_read_consistency_first_lock",
        ],
    ),
    (
        "M-SCH-C-familyB-workspace workspace core 门禁放行（I2 回归验证，临时）",
        WS_PARTICIPANT,
        ['            if fence.purge_revision != purge_revision:'],
        ['            if False:  # M：workspace core family-B 门禁放行'],
        [
            "tests/composition/test_s5i2_six_owner_shared_write_removal.py::"
            "test_workspace_core_erased_fence_cross_revision_gate_fail_closed",
        ],
    ),
    (
        "M-SCH-C-familyB-execution execution core 门禁放行（I2 回归验证，临时）",
        EX_PARTICIPANT,
        ['            if fence.purge_revision != purge_revision:'],
        ['            if False:  # M：execution core family-B 门禁放行'],
        [
            "tests/composition/test_s5i2_six_owner_shared_write_removal.py::"
            "test_execution_core_erased_fence_cross_revision_gate_fail_closed",
        ],
    ),
]


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=TEST_DIR)


def apply(path: Path, olds: list[str], news: list[str]) -> None:
    src = path.read_text()
    for old, new in zip(olds, news, strict=True):
        assert old in src, f"anchor not found in {path.name}: {old[:60]!r}"
        src = src.replace(old, new, 1)
    path.write_text(src)


def restore(path: Path) -> None:
    run(["git", "restore", "--", str(path)])


def main() -> int:
    results = []
    for name, path, olds, news, tests in MUTATIONS:
        apply(path, olds, news)
        mutated = all(
            run(["uv", "run", "pytest", test_id, "-q", "--tb=line"]).returncode != 0
            for test_id in tests
        )
        restore(path)
        clean = all(
            run(["uv", "run", "pytest", test_id, "-q", "--tb=line"]).returncode == 0
            for test_id in tests
        )
        ok = mutated and clean
        results.append(ok)
        print(
            f"{'KILLED' if ok else 'FAILED':8} "
            f"mutated={'red' if mutated else 'NOT-RED'} "
            f"restored={'green' if clean else 'NOT-GREEN'} {name}"
        )
    print(f"\n{sum(results)}/{len(results)} mutation kills passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
