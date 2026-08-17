"""R1-S5 SCH-A 13 项具名 mutation kill 驱动（可复现证据链）。

用法（须独占 metaedu_test——并发验证进程的 autouse TRUNCATE 会互相破坏）：

    cd packages/server-python
    uv run python ../../scripts/sch_a_mutation_kill.py

每项：应用变异（内存字符串替换）→ 跑映射测试（期望 FAIL=红）→
git restore 生产文件 → 跑映射测试（期望 PASS=绿）。变异绝不提交。
13 项与 `tests/composition/test_s5_sch_a_claim_lease.py` 头部反例映射表
一一对应（SCH-1/2/5/6/7 + SCH-9..16）。
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCHEDULER = (
    REPO
    / "packages/server-python/app/composition/conversation_purge_scheduler.py"
)
MIGRATION = (
    REPO
    / "packages/server-python/alembic/versions/042_purge_lease_carrier.py"
)
TEST_DIR = REPO / "packages/server-python"

MUTATIONS = [
    # (name, file, old, new, mapped test)
    (
        "M-SCH-1 claim 对过期行跳过 takeover",
        SCHEDULER,
        "        if expires_at is not None:\n"
        "            # 已过期：claim 走 takeover（含强制聚合）。",
        "        if False:\n"
        "            # M-SCH-1：跳过过期 takeover（claim 改走 fresh）。",
        "tests/composition/test_s5_sch_a_claim_lease.py::test_claim_path_takes_over_expired_lease",
    ),
    (
        "M-SCH-2 全 owner checkpoint 建行不完整",
        SCHEDULER,
        "        for owner in operation.registry_snapshot:",
        "        for owner in operation.registry_snapshot[:1]:  # M-SCH-2",
        "tests/composition/test_s5_sch_a_claim_lease.py::test_first_claim_creates_operation_full_checkpoints_and_lease",
    ),
    (
        "M-SCH-5 takeover 缺 epoch CAS",
        SCHEDULER,
        '        "AND lease_epoch = :expected "\n'
        "        \"AND state NOT IN ('completed', 'cancelled') \"",
        '        "AND state NOT IN (\'completed\', \'cancelled\') "  # M-SCH-5',
        "tests/composition/test_s5_sch_a_claim_lease.py::test_stale_epoch_zero_write_on_renew_takeover_release",
    ),
    (
        "M-SCH-6 Conversation 锁裸 id 谓词",
        SCHEDULER,
        "                .where(\n"
        "                    ConversationModel.tenant_id == tenant_id,\n"
        "                    ConversationModel.id == conversation_id,\n"
        "                )\n"
        "                .with_for_update()\n"
        "            )\n"
        "        ).scalar_one_or_none()",
        "                .where(\n"
        "                    ConversationModel.id == conversation_id,  # M-SCH-6\n"
        "                )\n"
        "                .with_for_update()\n"
        "            )\n"
        "        ).scalar_one_or_none()",
        "tests/composition/test_s5_sch_a_claim_lease.py::test_cross_tenant_zero_write",
    ),
    (
        "M-SCH-7 release 不校验 epoch",
        SCHEDULER,
        '        "AND lease_epoch = :expected AND lease_expires_at IS NOT NULL "',
        '        "AND lease_expires_at IS NOT NULL "  # M-SCH-7',
        "tests/composition/test_s5_sch_a_claim_lease.py::test_stale_epoch_zero_write_on_renew_takeover_release",
    ),
    (
        "M-SCH-9 renew 谓词改用 updated_at",
        SCHEDULER,
        '        "AND lease_expires_at > clock_timestamp() "',
        '        "AND updated_at > clock_timestamp() - make_interval(secs => :ttl) "  # M-SCH-9',
        "tests/composition/test_s5_sch_a_claim_lease.py::test_updated_at_change_does_not_renew",
    ),
    (
        "M-SCH-10 renew 缺到期检查",
        SCHEDULER,
        '        "AND lease_epoch = :expected "\n'
        '        "AND lease_expires_at > clock_timestamp() "',
        '        "AND lease_epoch = :expected "  # M-SCH-10',
        "tests/composition/test_s5_sch_a_claim_lease.py::test_expired_token_cannot_renew",
    ),
    (
        "M-SCH-11 takeover 缺在租检查",
        SCHEDULER,
        '        "AND (lease_expires_at IS NULL OR lease_expires_at <= clock_timestamp()) "\n',
        '        "AND true "  # M-SCH-11\n',
        "tests/composition/test_s5_sch_a_claim_lease.py::test_takeover_live_lease_rejected_in_lease",
    ),
    (
        "M-SCH-12 release 不推进 epoch",
        SCHEDULER,
        '        "lease_epoch = lease_epoch + 1, lease_expires_at = NULL "',
        '        "lease_expires_at = NULL "  # M-SCH-12',
        "tests/composition/test_s5_sch_a_claim_lease.py::test_release_clears_expiry_and_invalidates_old_token",
    ),
    (
        "M-SCH-13 计数含终态行",
        SCHEDULER,
        '                    "AND state NOT IN (\'completed\', \'cancelled\') "',
        '                    "AND true "  # M-SCH-13',
        "tests/composition/test_s5_sch_a_claim_lease.py::test_tenant_cap_four_and_slot_counting",
    ),
    (
        "M-SCH-14 migration 042 伪造 backfill",
        MIGRATION,
        "    op.create_index(",
        '    op.execute(\n'
        '        "UPDATE metaedu.agent_conversation_purges "\n'
        '        "SET lease_expires_at = clock_timestamp()"  # M-SCH-14\n'
        "    )\n"
        "    op.create_index(",
        "tests/composition/test_agent_erasure_migration_roundtrip.py::test_042_lease_carrier_downgrade_upgrade_round_trip",
    ),
    (
        "M-SCH-15 claim 跳过 NULL 态 acquire",
        SCHEDULER,
        "        token = await self._acquire_cas(\n"
        "            tenant_id, conversation_id, op_id, epoch\n"
        "        )",
        "        token = None  # M-SCH-15：跳过 NULL 态 acquire",
        "tests/composition/test_s5_sch_a_claim_lease.py::test_epoch_zero_null_lease_claimable",
    ),
    (
        "M-SCH-16 acquire 写 expiry 不推进 epoch",
        SCHEDULER,
        '        "lease_epoch = lease_epoch + 1, "\n'
        '        "lease_expires_at = clock_timestamp() + make_interval(secs => :ttl) "\n'
        '        "WHERE tenant_id = :tid AND id = :op AND conversation_id = :cid "\n'
        '        "AND lease_epoch = :expected AND lease_expires_at IS NULL "',
        '        "lease_epoch = lease_epoch, "  # M-SCH-16\n'
        '        "lease_expires_at = clock_timestamp() + make_interval(secs => :ttl) "\n'
        '        "WHERE tenant_id = :tid AND id = :op AND conversation_id = :cid "\n'
        '        "AND lease_epoch = :expected AND lease_expires_at IS NULL "',
        "tests/composition/test_s5_sch_a_claim_lease.py::test_first_claim_creates_operation_full_checkpoints_and_lease",
    ),
]


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=TEST_DIR)


def apply(file: Path, old: str, new: str) -> None:
    src = file.read_text()
    assert old in src, f"anchor not found in {file}"
    file.write_text(src.replace(old, new, 1))


def pytest_cmd(test_id: str) -> subprocess.CompletedProcess:
    return run(["uv", "run", "pytest", test_id, "-q", "--tb=line"])


def restore(file: Path) -> None:
    run(["git", "restore", "--", str(file)])


def main() -> int:
    results = []
    for name, path, old, new, test_id in MUTATIONS:
        apply(path, old, new)
        mutated = pytest_cmd(test_id)
        kill = mutated.returncode != 0
        restore(path)
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
    sys.exit(main())
