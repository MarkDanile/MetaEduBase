"""R1-S5 SCH-D Settlement 具名 mutation kill 驱动（可复现证据链）。

用法（须独占 metaedu_test）：

    cd packages/server-python
    uv run python ../../scripts/sch_d_mutation_kill.py

每项：应用变异 → 跑映射测试（期望红）→ git restore → 跑映射测试（期望绿）。
变异绝不提交。仅靶 SCH-D 新代码（settlement.py / erasure_repository.py
settlement fence 路径）；靶向 S5-C-8 反例矩阵判别点。
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SETTLEMENT = REPO / "packages/server-python/app/composition/settlement.py"
REPO_FENCE = (
    REPO
    / "packages/server-python/app/contexts/agent_workspace/infrastructure/erasure_repository.py"
)
TEST_DIR = REPO / "packages/server-python"
TEST = "tests/composition/test_s5_sch_d_settlement.py"

_T = f"{TEST}::"

MUTATIONS = [
    (
        "M-SCH-D-drift-equality drift 用已安装 registry/hold 等值校验",
        SETTLEMENT,
        ["        if operation.hold_revision_snapshot > conversation.hold_revision:"],
        ["        if operation.hold_revision_snapshot != conversation.hold_revision:  # M"],
        [f"{_T}test_settlement_drift_frozen_snapshot"],
    ),
    (
        "M-SCH-D-fence-write 删 settlement fence erasing→blocked 写",
        SETTLEMENT,
        ['        await self._repo.transition_fence_state_settlement(\n            tenant_id=tenant_id,\n            conversation_id=conversation_id,\n            owner_key=fence.owner_key,\n            expected_state=ErasureFenceState.ERASING,\n            expected_revision=fence.revision,\n            new_state=ErasureFenceState.BLOCKED,\n            expected_owner_version=frozen.owner_version,\n            purge_revision=frozen.purge_revision,\n            hold_revision=hold_revision,\n            now=await self._database_now(),\n        )'],
        ["        if False:  # M：删 settlement fence 写"],
        [
            f"{_T}test_settlement_post_window_blocked_converges",
            f"{_T}test_settlement_lookup_none_unknown",
        ],
    ),
    (
        "M-SCH-D-ack-lost repair 清 operation failure_code / 写 purge_state",
        SETTLEMENT,
        ['        checkpoint.state = "acked"\n        checkpoint.ack_digest = ack_digest\n        checkpoint.checkpoint_digest = scan_digest\n        checkpoint.reason_code = None\n        checkpoint.updated_at = await self._database_now()\n        await self._session.flush()'],
        ['        checkpoint.state = "acked"\n        checkpoint.ack_digest = ack_digest\n        checkpoint.checkpoint_digest = scan_digest\n        checkpoint.reason_code = None\n        checkpoint.updated_at = await self._database_now()\n        # M：repair 清 operation failure_code\n        await self._session.execute(\n            text("UPDATE metaedu.agent_conversation_purges SET failure_code=NULL")\n        )\n        await self._session.flush()'],
        [f"{_T}test_settlement_ack_lost_repair"],
    ),
    (
        "M-SCH-D-lookup-none-delete None 视为未执行再次 delete",
        SETTLEMENT,
        ["            if supports_replay and descriptor.dedup_window >= descriptor.settlement_deadline:"],
        ["            if True:  # M：None 视为未执行再次 delete"],
        [f"{_T}test_settlement_lookup_none_unknown"],
    ),
    (
        "M-SCH-D-replay-window 窗口不足仍 replay",
        SETTLEMENT,
        ["            if descriptor.dedup_window >= descriptor.settlement_deadline:\n                replay_outcome = await self._replay_adapter("],
        ["            if True:  # M：窗口不足仍 replay\n                replay_outcome = await self._replay_adapter("],
        [f"{_T}test_settlement_replay_window_insufficient"],
    ),
    (
        "M-SCH-D-deadline 过期仍自动 replay/lookup",
        SETTLEMENT,
        ["            if now > checkpoint.updated_at + descriptor.settlement_deadline:"],
        ["            if False:  # M：过期仍自动 replay/lookup"],
        [f"{_T}test_settlement_deadline_expired"],
    ),
    (
        "M-SCH-D-unresolvable fallback 当前 adapter",
        SETTLEMENT,
        ['        try:\n            raw_adapter = self._adapter_resolver(\n                owner_key=owner_key, owner_version=frozen.owner_version\n            )\n        except AdapterUnresolvableError:\n            return _WindowOutcome(\n                OutputState.ADAPTER_UNRESOLVABLE,\n                reason=_unresolvable_reason(owner_key),\n            )'],
        ['        try:\n            raw_adapter = self._adapter_resolver(\n                owner_key=owner_key, owner_version=frozen.owner_version\n            )\n        except AdapterUnresolvableError:\n            raise  # M：fallback 当前 adapter（不 fail closed）'],
        [f"{_T}test_settlement_adapter_unresolvable"],
    ),
    (
        "M-SCH-D-token 删除精确 attempt/intent token 重验",
        SETTLEMENT,
        ['            and (checkpoint.attempt < 1 or checkpoint.checkpoint_digest is None)\n        ):\n            raise ValueError(\n                "erasing checkpoint lacks attempt/intent token; new Tx1 "\n                "rejected by settlement channel"\n            )'],
        ['            and (checkpoint.attempt < 1 or checkpoint.checkpoint_digest is None)\n        ):\n            if False:  # M：token 校验放宽\n                raise ValueError(\n                    "erasing checkpoint lacks attempt/intent token; new Tx1 "\n                    "rejected by settlement channel"\n                )'],
        [f"{_T}test_settlement_erasing_without_token_rejected"],
    ),
    (
        "M-SCH-D-reason-shared 3/5/6 共用同一 code",
        SETTLEMENT,
        ['def _outcome_unknown_reason(owner_key: str) -> str:\n    return (\n        _REASON_OUTCOME_UNKNOWN_EXTERNAL\n        if owner_key == "external.payload.v1"\n        else _REASON_OUTCOME_UNKNOWN_RUNTIME\n    )'],
        ['def _outcome_unknown_reason(owner_key: str) -> str:\n    return _REASON_OUTCOME_UNKNOWN_EXTERNAL  # M：共用 code'],
        [f"{_T}test_settlement_reasons_distinct"],
    ),
    (
        "M-SCH-D-idempotent 重放跳过已收口 fence 白名单判定",
        SETTLEMENT,
        ['        return None  # active/blocked fence → 无 settlement 输入态'],
        ['        return "window_erasing"  # M：已 blocked fence 仍重收'],
        [f"{_T}test_settlement_idempotent_replay"],
    ),
    (
        "M-SCH-D-reconcile-exception 删例外映射（fence 写失败不收敛）",
        SETTLEMENT,
        ['        try:\n            await self._repo.transition_fence_state_settlement(\n                tenant_id=tenant_id,\n                conversation_id=conversation_id,\n                owner_key=fence.owner_key,\n                expected_state=ErasureFenceState.ERASING,\n                expected_revision=fence.revision,\n                new_state=ErasureFenceState.BLOCKED,\n                expected_owner_version=frozen.owner_version,\n                purge_revision=frozen.purge_revision,\n                hold_revision=hold_revision,\n                now=await self._database_now(),\n            )\n        except ValueError:\n            # S5-C-1 例外条款：fence 写失败 → 具名 reconcile（checkpoint 已落账\n            # 输出态 reason），零自动重试。\n            return'],
        ['        try:\n            await self._repo.transition_fence_state_settlement(\n                tenant_id=tenant_id,\n                conversation_id=conversation_id,\n                owner_key=fence.owner_key,\n                expected_state=ErasureFenceState.ERASING,\n                expected_revision=fence.revision,\n                new_state=ErasureFenceState.BLOCKED,\n                expected_owner_version=frozen.owner_version,\n                purge_revision=frozen.purge_revision,\n                hold_revision=hold_revision,\n                now=await self._database_now(),\n            )\n        except ValueError:\n            raise  # M：删例外映射（fence 写失败崩溃）'],
        [f"{_T}test_settlement_fence_write_failure_reconcile"],
    ),
    (
        "M-SCH-D-lookup-nofork 去 CAS（重放不写 checkpoint）",
        SETTLEMENT,
        ['            if checkpoint is not None and checkpoint.state != "acked":\n                checkpoint.state = "acked"\n                checkpoint.ack_digest = ack'],
        ['            if False:  # M：去 CAS（重放不收敛 checkpoint）\n                checkpoint.state = "acked"\n                checkpoint.ack_digest = ack'],
        [f"{_T}test_settlement_lookup_crash_replay_no_fork"],
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
