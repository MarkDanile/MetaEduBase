"""R1-S6 S6-I1 具名 mutation kill 驱动（可复现证据链）。

用法（须独占 metaedu_test——并发验证进程的 autouse TRUNCATE 会互相破坏）：

    cd packages/server-python
    uv run python ../../scripts/s6i1_retention_mutation_kill.py

每项：应用变异（内存字符串替换）→ 跑映射测试（期望 FAIL=红）→
git restore 生产文件 → 跑映射测试（期望 PASS=绿）。变异绝不提交。

映射：M-RET-* → ``test_s6i1_event_retention.py``；M-AUD-* →
``test_s6i1_audit_retention.py``；M-HOLD-* → ``test_s6i1_s5_compat_hold_expiry.py``；
M-043-1/2 → ``test_agent_erasure_migration_roundtrip.py``（roundtrip 自带 guard
swap）；M-043-3/4 → ``test_s3d_run_event_guard.py``（s3d guard 测试不重载
guard，文件变异需写回 DB——脚本在每项 M-043 test 前 apply 文件当前
``_GUARD_043`` 到 DB）；M-T2-* → ``test_s5_sch_d_settlement.py``。反例编号
对应各测试文件头部映射表。
"""

import asyncio as _asyncio
import re as _re
import subprocess
import sys as _sys
from pathlib import Path

import asyncpg as _asyncpg

REPO = Path(__file__).resolve().parents[1]
WORKER = REPO / "packages/server-python/app/composition/retention_workers.py"
SETTLEMENT = REPO / "packages/server-python/app/composition/settlement.py"
ERASURE_REPO = (
    REPO / "packages/server-python/app/contexts/agent_workspace/infrastructure/erasure_repository.py"
)
CLAIM = REPO / "packages/server-python/app/composition/conversation_purge_scheduler.py"
MIGRATION = (
    REPO / "packages/server-python/alembic/versions/043_run_event_retention_guard.py"
)
TEST_DIR = REPO / "packages/server-python"

# 显式加入 packages/server-python 到 sys.path（脚本位于 repo root scripts/，
# 但需要 import tests.conftest 拿到 TEST_DB_URL；无论 cwd 是什么都生效）。
_TEST_PKG_PATH = REPO / "packages" / "server-python"
if str(_TEST_PKG_PATH) not in _sys.path:
    _sys.path.insert(0, str(_TEST_PKG_PATH))

try:
    from tests.conftest import TEST_DB_URL as _TEST_DB_URL  # noqa: E402
except Exception:  # pragma: no cover - 直跑脚本时 tests 可能不在 sys.path
    _TEST_DB_URL = ""

_INITIAL_MIGRATION_SRC = MIGRATION.read_text()
_REAL_GUARD_043 = _re.search(r"_GUARD_043 = \"\"\"\n(.*?)\"\"\"", _INITIAL_MIGRATION_SRC, _re.S).group(1)
_REAL_GUARD_041 = _re.search(r"_GUARD_041 = \"\"\"\n(.*?)\"\"\"", _INITIAL_MIGRATION_SRC, _re.S).group(1)


def _sync_db_url() -> str:
    return _TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://", 1)


def _extract_guard_043(file_path: Path) -> str:
    src = file_path.read_text()
    return _re.search(r"_GUARD_043 = \"\"\"\n(.*?)\"\"\"", src, _re.S).group(1)


def _apply_guard_to_db(guard_sql: str) -> None:
    """通过 asyncpg 直连测试 DB 执行 guard SQL（CREATE OR REPLACE FUNCTION）。"""
    async def _go() -> None:
        conn = await _asyncpg.connect(_sync_db_url())
        try:
            await conn.execute(guard_sql)
        finally:
            await conn.close()

    _asyncio.run(_go())

MUTATIONS = [
    # --- run_event_retention（S6-RET-*） ---
    (
        "M-RET-1 inline expiry 不清 payload_inline",
        WORKER,
        '            "SET payload_inline = NULL, payload_state = \'expired\' "\n',
        '            "SET payload_state = \'expired\' "\n',
        "tests/composition/test_s6i1_event_retention.py::test_inline_payload_expiry_clears_body_keeps_envelope",
    ),
    (
        "M-RET-2 external expiry 写错 state",
        WORKER,
        '            "SET payload_state = \'expired\' "\n',
        '            "SET payload_state = \'archived\' "\n',
        "tests/composition/test_s6i1_event_retention.py::test_external_payload_expiry_state_only_preserves_ref",
    ),
    (
        "M-RET-3 prune 后不置 event_log_complete=False",
        WORKER,
        '            "event_log_complete = false "\n',
        '            "event_log_complete = true "\n',
        "tests/composition/test_s6i1_event_retention.py::test_continuous_prefix_prune_advances_first_available",
    ),
    (
        "M-RET-4 prune 不推进 first_available_event_seq",
        WORKER,
        '            "SET first_available_event_seq = :first_available, "\n',
        '            "SET first_available_event_seq = :old_first_available, "\n',
        "tests/composition/test_s6i1_event_retention.py::test_continuous_prefix_prune_advances_first_available",
    ),
    (
        "M-RET-5 hold 到期谓词宽化被还原",
        WORKER,
        '            "AND (expires_at IS NULL OR expires_at > :now))"\n',
        '            "AND true)"\n',
        "tests/composition/test_s6i1_event_retention.py::test_expired_hold_does_not_block",
    ),
    (
        "M-RET-6 prune 白名单去掉 payload_ref IS NULL",
        WORKER,
        '            "AND payload_inline IS NULL AND payload_ref IS NULL "\n',
        '            "AND payload_inline IS NULL "\n',
        "tests/composition/test_s6i1_event_retention.py::test_prune_stops_at_external_ref_row",
    ),
    # --- run_audit_retention（S6-AUD-*） ---
    (
        "M-AUD-1 删除集合漏 turn_inputs（children-first 顺序破坏）",
        WORKER,
        '            "DELETE FROM metaedu.agent_turn_inputs "\n',
        '            "DELETE FROM metaedu.agent_turn_inputs WHERE false "\n',
        "tests/composition/test_s6i1_audit_retention.py::test_terminal_run_pruned_children_first",
    ),
    (
        "M-AUD-2 events payload 未 tombstone 检查失效",
        WORKER,
        '            "  AND NOT (payload_state IN (\'redacted\', \'expired\', \'archived\') "\n',
        '            "  AND false AND NOT (payload_state IN (\'redacted\', \'expired\', \'archived\') "\n',
        "tests/composition/test_s6i1_audit_retention.py::test_blocked_when_events_not_tombstoned",
    ),
    (
        "M-AUD-3 outcome_unknown 检查失效",
        WORKER,
        '            "    AND e1.event_type = :unknown "\n',
        '            "    AND false "\n',
        "tests/composition/test_s6i1_audit_retention.py::test_blocked_on_outcome_unknown_then_resolved",
    ),
    (
        "M-AUD-4 未解决审批检查失效",
        WORKER,
        '            "    AND e1.event_type = :requested "\n',
        '            "    AND false "\n',
        "tests/composition/test_s6i1_audit_retention.py::test_blocked_on_unresolved_approval_then_resolved",
    ),
    (
        "M-AUD-5 存活子 run 检查失效",
        WORKER,
        '            "  WHERE tenant_id = :tid AND parent_run_id = :rid"\n',
        '            "  WHERE false"\n',
        "tests/composition/test_s6i1_audit_retention.py::test_blocked_on_surviving_child_run",
    ),
    # --- S5 修改点 #1 hold 到期读侧谓词（裁决一） ---
    (
        "M-HOLD-1 has_active_legal_hold 忽略 expires_at",
        ERASURE_REPO,
        "                ConversationLegalHoldModel.expires_at > func.clock_timestamp()",
        "                True",
        "tests/composition/test_s6i1_s5_compat_hold_expiry.py::test_repository_expired_hold_not_active",
    ),
    (
        "M-HOLD-2 claim _has_active_hold 忽略 expires_at",
        CLAIM,
        '                    "AND (expires_at IS NULL OR expires_at > clock_timestamp()))"\n',
        '                    "AND true)"\n',
        "tests/composition/test_s6i1_s5_compat_hold_expiry.py::test_claim_expired_hold_not_deferred",
    ),
    # --- migration 043（S6-10 冻结需求） ---
    (
        "M-043-1 downgrade 目标还原成 043（DELETE 洞未关）",
        MIGRATION,
        '_GUARD_041 = """\n',
        '_GUARD_041 = _GUARD_043  # M-043-1\n_GUARD_041_LEGACY = """\n',
        "tests/composition/test_agent_erasure_migration_roundtrip.py::test_043_retention_guard_downgrade_upgrade_round_trip",
    ),
    (
        "M-043-2 043(a) widening 还原成 redacted-only",
        MIGRATION,
        "        AND NEW.payload_state IN ('redacted', 'expired', 'archived')\n",
        "        AND NEW.payload_state = 'redacted'\n",
        "tests/composition/test_agent_erasure_migration_roundtrip.py::test_043_retention_guard_downgrade_upgrade_round_trip",
    ),
    (
        "M-043-3 043 branch 2（external state-only）widening 还原为要求 OLD.payload_state='redacted'（与 041 branch 3 同构）",
        MIGRATION,
        "        AND OLD.payload_state = 'external'\n",
        "        AND OLD.payload_state = 'redacted'\n",
        "tests/contexts/agent_control_plane/test_s3d_run_event_guard.py::test_guard_allows_external_state_only_tombstone[redacted]",
    ),
    (
        "M-043-4 043(b) DELETE branch 4 还原为无条件 RAISE（开放 live/非 tombstone DELETE 洞）",
        MIGRATION,
        "        AND OLD.payload_ref IS NULL\n    THEN\n        RETURN OLD;\n    END IF;\n",
        "        AND OLD.payload_ref IS NULL\n        AND false\n    THEN\n        RETURN OLD;\n    END IF;\n",
        "tests/contexts/agent_control_plane/test_s3d_run_event_guard.py::test_guard_allows_delete_of_tombstoned_row",
    ),
    # --- S5 修改点 #2 settlement T2 checkpoint.state 重验（裁决二） ---
    (
        "M-T2-1 T2 不重验 checkpoint.state",
        SETTLEMENT,
        "        if checkpoint.state != \"erasing\":\n",
        "        if False and checkpoint.state != \"erasing\":\n",
        "tests/composition/test_s5_sch_d_settlement.py::test_settlement_t2_checkpoint_state_verified",
    ),
]


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=TEST_DIR)


# 本分支文件尚未提交（新文件/未提交修改），git restore 对 untracked 文件无效——
# 用内存备份精确还原原文。
_BACKUPS: dict[str, str] = {}


def apply(file: Path, old: str, new: str) -> None:
    src = file.read_text()
    assert old in src, f"anchor not found in {file}: {old[:60]!r}"
    _BACKUPS[str(file)] = src
    file.write_text(src.replace(old, new, 1))


def restore(file: Path) -> None:
    original = _BACKUPS.pop(str(file), None)
    if original is not None:
        file.write_text(original)
    else:
        run(["git", "restore", "--", str(file)])


def pytest_cmd(test_id: str) -> subprocess.CompletedProcess:
    return run(["uv", "run", "pytest", test_id, "-q", "--tb=line"])


def main() -> int:
    results = []
    for name, path, old, new, test_id in MUTATIONS:
        apply(path, old, new)
        # 仅 M-043-* 需要 DB guard 重载（s3d/s4ea guard 测试不重载 guard，文件
        # 变异需写回 DB 才能被测试感知）；其他 mutation 改的是 worker/settlement/hold
        # 路径，guard 不变。
        if path == MIGRATION:
            _apply_guard_to_db(_extract_guard_043(path))
        try:
            mutated = pytest_cmd(test_id)
        finally:
            # 中断/异常也保证还原（P3-1：try/finally 兜底，不遗留变异文件）。
            restore(path)
            if path == MIGRATION:
                # 恢复真实 043 guard 到 DB（防止前次变异污染后续用例）。
                _apply_guard_to_db(_REAL_GUARD_043)
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
