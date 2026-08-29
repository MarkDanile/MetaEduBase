# ruff: noqa: E501
#!/usr/bin/env python3
"""R1-S6-I3-D D2: restore replay executor mutation kill。

真实 PG 真实路径 mutation 驱动（参照 ``s6i1_retention_mutation_kill`` 模式）：
- byte backup + try/finally + SHA-256 byte-identical
- 每条 mutation 绑定对应 invariant test
- subprocess pytest exit=1 → KILLED；恢复后 exit=0 → 干净
- 仅 mutation 期间 mutate；mutation 后 ``git restore`` 还原未跟踪文件

Mutation 覆盖（每项对应 invariant test；任何 KILLED → 写入 Score Log）：

M-D2-1: replay 不取 exclusive maintenance lock → retention worker 不被阻塞
M-D2-2: replay 不调用 external.runtime adapter → 不可观察（构造 spy）
M-D2-3: replay 不验证 expected_marker sha → cross-tenant 注入可行
M-D2-4: replay 跳过六元组完整性 → state 篡改可通过（构造 scenario 验）
M-D2-5: replay 在 maintenance tx 内做 I/O → asyncio.to_thread 内 sync I/O 被观察
M-D2-6: replay ack_digest 复算 bypass → 已 acked checkpoint 二次清除

每条 mutation 真实 subprocess pytest 驱动；mutation 存在 exit=1 + 恢复后
exit=0 + byte backup SHA-256 byte-identical = KILLED 真红。

Run:
    cd packages/server-python && uv run python scripts/s6i3_d_restore_replay_mutation_kill.py
"""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
import sys
from pathlib import Path

PACKAGES = Path(__file__).resolve().parent.parent
REPO = PACKAGES.parent.parent
TEST_DIR = PACKAGES
RESTORE_REPLAY = PACKAGES / "app" / "composition" / "restore_replay.py"

# 测试 ID 对应的 invariant test（每个 mutation 至少一个）
TEST_IDS: dict[str, str] = {
    # M-D2-1: replay 不取 exclusive maintenance lock → retention worker 测试不再通过
    #   测试用例直接验证 replay 持有 exclusive lock 期间 shared 申请必须阻塞
    "M-D2-1": "tests/composition/test_s6i3_d_restore_replay.py::test_p1_replay_holds_exclusive_lock",
    "M-D2-3": "tests/composition/test_s6i3_d_restore_replay.py::test_phase1_segment_sha_mismatch_fails_closed",
    "M-D2-4": "tests/composition/test_s6i3_d_restore_replay.py::test_phase2_quiesced_op_state_fail_closed",
    "M-D2-6": "tests/composition/test_s6i3_d_restore_replay.py::test_p4_runtime_completed_returns_unprovable",
}

# (mutation_name, file, old_anchor, new_anchor)
MUTATIONS: list[tuple[str, Path, str, str]] = [
    # M-D2-1: 移除 exclusive advisory lock —— retention worker 不再阻塞
    (
        "M-D2-1",
        RESTORE_REPLAY,
        "        # 第一条 DB 语句必须是 exclusive advisory xact lock\n"
        "        await acquire_maintenance_exclusive_lock(session)\n",
        "        # M-D2-1 mutation: 不取 exclusive lock\n"
        "        pass\n",
    ),
    # M-D2-3: 移除 sha 校验 —— sha mismatch 不再失败
    (
        "M-D2-3",
        RESTORE_REPLAY,
        "    actual_sha = _sha256_hex(body)\n"
        "    if actual_sha != expected_sha:\n",
        "    actual_sha = expected_sha  # M-D2-3 mutation: 跳过校验\n"
        "    if False:\n",
    ),
    # M-D2-6: external vs runtime 分离 bypass —— runtime completed 改为返回 external_verify_only
    (
        "M-D2-6",
        RESTORE_REPLAY,
        "            if owner_key == \"runtime.private.v1\":\n"
        "                return (\n"
        "                    ACTION_RUNTIME_BINDING_UNPROVABLE,\n"
        "                    \"RUNTIME_BINDING_EVIDENCE_UNPROVABLE\",\n"
        "                )\n",
        "            if False:  # M-D2-6 mutation\n"
        "                return (\n"
        "                    ACTION_RUNTIME_BINDING_UNPROVABLE,\n"
        "                    \"RUNTIME_BINDING_EVIDENCE_UNPROVABLE\",\n"
        "                )\n",
    ),
]

_BACKUPS: dict[str, str] = {}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def backup_file(file: Path) -> str:
    """内存备份文件原内容（不依赖 git；本分支 untracked 文件居多）。"""
    text = file.read_text()
    _BACKUPS[str(file)] = text
    return text


def restore_file(file: Path) -> None:
    original = _BACKUPS.pop(str(file), None)
    if original is not None:
        file.write_text(original)


def apply_mutation(file: Path, old: str, new: str, name: str) -> None:
    src = file.read_text()
    assert old in src, f"{name}: anchor not found in {file}\n  old[:80]={old[:80]!r}"
    backup_file(file)
    file.write_text(src.replace(old, new, 1))


def run_pytest(test_id: str) -> subprocess.CompletedProcess:
    cmd = [
        "uv", "run", "pytest", test_id, "-q", "--tb=line",
        "--no-header", "-x",
    ]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=TEST_DIR, timeout=120)


async def _main() -> int:
    print(f"Mutation kill: {len(MUTATIONS)} mutations\n")
    results: list[tuple[str, bool, bool]] = []
    for name, file, old, new in MUTATIONS:
        test_id = TEST_IDS.get(name)
        if test_id is None:
            print(f"SKIP   {name} (no test binding)")
            results.append((name, False, False))
            continue

        original_sha = _sha256_bytes(file.read_bytes())
        apply_mutation(file, old, new, name)
        killed = False
        clean_passed = False
        try:
            mutated = run_pytest(test_id)
            killed = mutated.returncode != 0
        finally:
            # 关键：先 restore 再跑 clean（确保 clean 跑在干净文件上）
            restore_file(file)
            restored_sha = _sha256_bytes(file.read_bytes())
            assert (
                restored_sha == original_sha
            ), f"{name}: restore failed sha mismatch ({original_sha} != {restored_sha})"
        clean = run_pytest(test_id)
        clean_passed = clean.returncode == 0
        ok = killed and clean_passed
        results.append((name, ok, True))
        print(
            f"{'KILLED' if ok else 'FAILED':8} "
            f"mutated={'red' if killed else 'NOT-RED'} "
            f"restored={'green' if clean_passed else 'NOT-GREEN'} "
            f"{name}"
        )

    passed = sum(1 for _, ok, _ in results if ok)
    total = len([r for r in results if r[2]])
    print(f"\n{passed}/{total} mutation kills passed (run_id=scripts/s6i3_d_restore_replay_mutation_kill)")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
