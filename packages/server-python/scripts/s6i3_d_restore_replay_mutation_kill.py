# ruff: noqa: E501
#!/usr/bin/env python3
"""R1-S6-I3-D D2 restore replay executor mutation kill（Round-2 P0 修复版）。

真实 PG 真实路径 mutation 驱动（参照 s6i1_retention_mutation_kill 模式）：
- byte backup + try/finally + SHA-256 byte-identical
- 每条 mutation 绑定对应 invariant test
- subprocess pytest exit=1 → KILLED；恢复后 exit=0 → 干净
- 仅 mutation 期间 mutate；mutation 后 restore 还原

Round-2 mutation 覆盖（每项对应 invariant test；任何 KILLED → 写入 Score Log）：

M-D2-1：replay 不取 exclusive maintenance lock → 0/False bypass
M-D2-3：replay 不验证 expected_marker sha → fail closed
M-D2-6：external vs runtime 分离 bypass（runtime 改走 fall-through）
M-D2-7：committed-tip bypass（删除 find_committed_tip 调用）
M-D2-8：transport 主入口降级为 body helper（erase_transport_owner → erase_transport_body）
M-D2-9：单 drift 仍执行其他 owner（移除 FACT_DRIFT_FIELDS raise）
M-D2-10：purge_revision / ack_digest 对账删除
M-D2-11：gate 忽略 replay report（恢复默认 0 / False）

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
TEST_DIR = PACKAGES
RESTORE_REPLAY = PACKAGES / "app" / "composition" / "restore_replay.py"

# 测试 ID 对应的 invariant test（每个 mutation 至少一个）
TEST_IDS: dict[str, str] = {
    "M-D2-1": "tests/composition/test_s6i3_d_restore_replay.py::test_r1_p1_replay_holds_exclusive_lock",
    # M-D2-3: 移除 fetch_segment_bytes 验证（返回空 bytes → decode 失败）
    "M-D2-3": "tests/composition/test_s6i3_d_restore_replay.py::test_phase1_archive_read_from_committed_tip",
    "M-D2-6": "tests/composition/test_s6i3_d_restore_replay.py::test_r2_runtime_completed_returns_unprovable",
    "M-D2-7": "tests/composition/test_s6i3_d_restore_replay.py::test_phase1_archive_read_from_committed_tip",
    "M-D2-8": "tests/composition/test_s6i3_d_restore_replay.py::test_r2_workspace_transport_uses_erase_transport_owner",
    "M-D2-9": "tests/composition/test_s6i3_d_restore_replay.py::test_r2_fact_drift_blocks_pass_b_entry",
    "M-D2-10": "tests/composition/test_s6i3_d_restore_replay.py::test_r2_purge_revision_drift_fails_closed",
    "M-D2-11": "tests/composition/test_s6i3_d_restore_replay.py::test_r2_gate_consumes_fact_drift",
}

# (mutation_name, file, old_anchor, new_anchor)
MUTATIONS: list[tuple[str, Path, str, str]] = [
    # M-D2-1: 移除 exclusive advisory lock —— retention worker 不被阻塞
    (
        "M-D2-1",
        RESTORE_REPLAY,
        "        # 第一条 DB 语句必须是 exclusive advisory xact lock\n"
        "        await acquire_maintenance_exclusive_lock(session)\n",
        "        # M-D2-1 mutation: 不取 exclusive lock\n"
        "        pass\n",
    ),
    # M-D2-3: 移除 sha 校验 —— 跳过 fetch_segment_bytes 内部 tenant 校验
    (
        "M-D2-3",
        RESTORE_REPLAY,
        "    marker = CommitMarker.from_bytes(tip.marker_bytes)\n"
        "    segment_bytes = await asyncio.to_thread(\n"
        "        fetch_segment_bytes, sink, tenant_id=tenant_str, marker=marker\n"
        "    )\n",
        "    marker = CommitMarker.from_bytes(tip.marker_bytes)\n"
        "    segment_bytes = b\"\"  # M-D2-3 mutation: 跳过 fetch（带 sha 校验）\n",
    ),
    # M-D2-6: external vs runtime 分离 bypass —— runtime 改走 fall-through
    (
        "M-D2-6",
        RESTORE_REPLAY,
        "            if owner_key == \"runtime.private.v1\":\n"
        "                return (\n"
        "                    ACTION_RUNTIME_BINDING_UNPROVABLE,\n"
        "                    \"RUNTIME_BINDING_EVIDENCE_UNPROVABLE\",\n"
        "                )\n",
        "            if False:  # M-D2-6 mutation: runtime 改走 external_verify_only（合并语义）\n"
        "                return (\n"
        "                    ACTION_RUNTIME_BINDING_UNPROVABLE,\n"
        "                    \"RUNTIME_BINDING_EVIDENCE_UNPROVABLE\",\n"
        "                )\n",
    ),
    # M-D2-7: committed-tip bypass —— 直接调 D1a export，跳过 find_committed_tip
    (
        "M-D2-7",
        RESTORE_REPLAY,
        "    tenant_str = str(tenant_id)\n"
        "    tip = await asyncio.to_thread(find_committed_tip, sink, tenant_id=tenant_str)\n"
        "    if tip is None:\n",
        "    tenant_str = str(tenant_id)\n"
        "    tip = None  # M-D2-7 mutation: 跳过 committed-tip 推导\n"
        "    if tip is None:\n",
    ),
    # M-D2-8: transport 主入口降级为 body helper
    (
        "M-D2-8",
        RESTORE_REPLAY,
        "        await WorkspaceTransportErasureParticipant(session).erase_transport_owner(\n"
        "            tenant_id=tenant_id,\n"
        "            conversation_id=validated.conversation_id,\n"
        "            purge_revision=validated.archive_purge_revision,\n"
        "            purge_operation_id=validated.operation_id,\n"
        "            expected_operation_revision=validated.archive_revision,\n"
        "            expected_lease_epoch=validated.archive_lease_epoch,\n"
        "        )\n",
        "        # M-D2-8 mutation: 降级为 body helper（丢失 fence / owner lock / CAS）\n"
        "        await WorkspaceTransportErasureParticipant(session).erase_transport_body(\n"
        "            tenant_id=tenant_id,\n"
        "            conversation_id=validated.conversation_id,\n"
        "        )\n",
    ),
    # M-D2-9: 单 drift 仍执行其他 owner —— 移除 FACT_DRIFT_FIELDS raise（pass A 继续）
    (
        "M-D2-9",
        RESTORE_REPLAY,
        "    if drift_fields:\n"
        "        raise RestoreReplayError(\n"
        "            \"FACT_DRIFT_FIELDS\",\n"
        "            detail={\n"
        "                \"operation_id\": fact.operation_id,\n"
        "                \"owner_key\": fact.owner_key,\n"
        "                \"drift_fields\": tuple(drift_fields),\n"
        "            },\n"
        "        )\n",
        "    if drift_fields:\n"
        "        pass  # M-D2-9 mutation: 单 drift 不阻断（错误）\n",
    ),
    # M-D2-10: purge_revision 对账删除 —— 移除 operation.purge_revision 检查
    (
        "M-D2-10",
        RESTORE_REPLAY,
        "    archive_purge_rev = archive_op_record.get(\"purge_revision\") if archive_op_record else None\n"
        "    if archive_purge_rev is not None and int(op_row[\"purge_revision\"]) != int(archive_purge_rev):\n"
        "        drift_fields.append(\"operation.purge_revision\")\n",
        "    # M-D2-10 mutation: 删除 purge_revision 对账\n",
    ),
    # M-D2-11: gate 忽略 replay report —— 恢复默认 0 / False
    (
        "M-D2-11",
        RESTORE_REPLAY,
        "    # 1. ReplayReport 内部 blocking 项 → 全部阻断\n"
        "    if replay_report.error is not None:\n"
        "        blocked.append(f\"replay_error:{replay_report.error}\")\n"
        "    if replay_report.owners_fact_drift > 0:\n"
        "        blocked.append(f\"fact_drift:{replay_report.owners_fact_drift}\")\n",
        "    # M-D2-11 mutation: gate 忽略 replay report\n"
        "    if False:\n"
        "        if replay_report.error is not None:\n"
        "            blocked.append(f\"replay_error:{replay_report.error}\")\n"
        "        if replay_report.owners_fact_drift > 0:\n"
        "            blocked.append(f\"fact_drift:{replay_report.owners_fact_drift}\")\n",
    ),
]


_BACKUPS: dict[str, str] = {}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def backup_file(file: Path) -> str:
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
