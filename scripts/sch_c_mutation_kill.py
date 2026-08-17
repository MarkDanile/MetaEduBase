"""R1-S5 SCH-C 9 项具名 mutation kill 驱动（可复现证据链）。

用法（须独占 metaedu_test）：

    cd packages/server-python
    uv run python ../../scripts/sch_c_mutation_kill.py

每项：应用变异 → 跑映射测试（期望红）→ git restore → 跑映射测试（期望绿）。
变异绝不提交。仅靶 SCH-C 新代码（purge_rebuild.py / predecessor_lineage.py）。
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REBUILD = REPO / "packages/server-python/app/composition/purge_rebuild.py"
LINEAGE = REPO / "packages/server-python/app/composition/predecessor_lineage.py"
TEST_DIR = REPO / "packages/server-python"
TEST = "tests/composition/test_s5_sch_c_rebuild_seeding.py"

MUTATIONS = [
    # (name, file, [olds], [news], test)
    (
        "M-SCH-C-drift-gate 无 drift 也 rebuild",
        REBUILD,
        ['        if top.state != "blocked" or top.failure_code not in _G1_G2_FAILURE_CODES:'],
        ['        if False:  # M：无 drift 也 rebuild'],
        f"{TEST}::test_rebuild_idempotent_no_drift",
    ),
    (
        "M-SCH-C-quiesce erasing 未挡 rebuild",
        REBUILD,
        ["        if self._has_erasing(predecessor_checkpoints, predecessor_fences):\n            return RebuildOutcome(RebuildKind.QUIESCE)"],
        ["        if False:  # M：erasing 放行"],
        f"{TEST}::test_rebuild_quiesce_erasing",
    ),
    (
        "M-SCH-C-deleted restore 未挡 rebuild",
        REBUILD,
        ['        if conversation.state != "deleted":\n            return RebuildOutcome(RebuildKind.NOT_DUE)'],
        ['        if False:  # M：restore 放行'],
        f"{TEST}::test_rebuild_restore_active_zero_rows",
    ),
    (
        "M-SCH-C-lineage-conflict 阶段 1 失败不回滚",
        REBUILD,
        ["        if any(f.lineage_status == \"conflict\" for f in lineage.values()):\n            raise ValueError(\"lineage stage-1 verification failed; rollback rebuild\")"],
        ["        if False:  # M：lineage 失败放行"],
        f"{TEST}::test_rebuild_seeding_lineage_fail_rolls_back",
    ),
    (
        "M-SCH-C-removed removed unfinished 放行",
        REBUILD,
        ["        if self._removed_unfinished(diff, predecessor_checkpoints, predecessor_fences):\n            raise ValueError(\n                \"removed owner with unfinished obligation; rebuild fail closed\"\n            )"],
        ["        if False:  # M：removed unfinished 放行"],
        f"{TEST}::test_rebuild_removed_unfinished_fail_closed",
    ),
    (
        "M-SCH-C-carry outcome_unknown 被重开 pending",
        LINEAGE,
        ['def _is_carry_reason(reason: str) -> bool:\n    return reason.endswith(_CARRY_REASON_SUFFIXES)'],
        ['def _is_carry_reason(reason: str) -> bool:\n    return False  # M：carry 重开'],
        f"{TEST}::test_rebuild_outcome_unknown_carry",
    ),
    (
        "M-SCH-C-lease rebuild 未 acquire lease",
        REBUILD,
        ['        token_row = (await self._session.execute(\n            self._ACQUIRE_SQL,'],
        ['        token_row = None  # M：未 acquire\n        _unused = (await self._session.execute(\n            self._ACQUIRE_SQL,'],
        f"{TEST}::test_rebuild_g2_creates_new_revision_and_acquires_lease",
    ),
    (
        "M-SCH-C-writeback purge_revision 未写回",
        REBUILD,
        ['        await self._session.execute(\n            text(\n                "UPDATE metaedu.agent_conversations SET purge_revision = :r "\n                "WHERE tenant_id = :tid AND id = :cid"\n            ),\n            {"r": new_revision, "tid": tenant_id, "cid": conversation_id},\n        )'],
        ['        # M：未写回 conversation.purge_revision'],
        f"{TEST}::test_rebuild_g2_creates_new_revision_and_acquires_lease",
    ),
    (
        "M-SCH-C-six-item lineage 六项恒真",
        LINEAGE,
        ["    if fact.fence_state != \"erased\":\n        return False  # 六项 3"],
        ["    if fact.fence_state != \"erased\" and False:\n        return False  # M：六项 3 放行"],
        f"{TEST}::test_rebuild_seeding_lineage_fail_rolls_back",
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
    for name, path, olds, news, test_id in MUTATIONS:
        apply(path, olds, news)
        mutated = run(["uv", "run", "pytest", test_id, "-q", "--tb=line"])
        kill = mutated.returncode != 0
        restore(path)
        clean = run(["uv", "run", "pytest", test_id, "-q", "--tb=line"])
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
