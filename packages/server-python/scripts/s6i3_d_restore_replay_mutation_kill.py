# ruff: noqa: E501
#!/usr/bin/env python3
"""R1-S6-I3-D D2 restore replay executor mutation kill（Round-5 真红证据版）。

真实 PG 真实路径 mutation 驱动（参照 s6i1_retention_mutation_kill 模式）：
- byte backup + try/finally + SHA-256 byte-identical
- 每条 mutation 绑定对应 invariant test
- subprocess pytest exit=1 → KILLED；恢复后 exit=0 → 干净
- 仅 mutation 期间 mutate；mutation 后 restore 还原

Round-5 强化（每条 mutant **必须是可运行 Python**——禁止 SyntaxError 冒充真红）：
- mutated pytest 失败必须**因业务不变量**（assertion / drift / rollback），
  **不是** collection SyntaxError
- 输出区分 ``syntax``（mutant 不可运行，**不计入** KILLED）vs
  ``behavioral``（业务不变量失败，计入 KILLED）
- 每条 mutation 绑定真实存在的测试；恢复后 SHA-256 byte-identical

Round-2 mutation 覆盖（每项对应 invariant test；任何 KILLED → 写入 Score Log）：

M-D2-1：replay 不取 exclusive maintenance lock → 0/False bypass
M-D2-3：replay 不验证 expected_marker sha → fail closed
M-D2-6：external vs runtime 分离 bypass（runtime 改走 fall-through）
M-D2-7：committed-tip bypass（删除 find_committed_tip 调用）
M-D2-8：transport 主入口降级为 body helper（erase_transport_owner → erase_transport_body）
M-D2-9：单 drift 仍执行其他 owner（移除 FACT_DRIFT_FIELDS raise）
M-D2-10：purge_revision 对账删除（移除 operation.purge_revision drift 检查）
M-D2-11：gate 忽略 replay report（恢复默认 0 / False）
M-D2-12：archive/live ack_digest 严格相等删除
M-D2-14：partial commit —— participant 失败 catch-and-continue（吞掉异常继续提交）
M-D2-15：archive-fact 缺失 fallback —— _require_field 缺失字段默认 0（bypass 严格缺失校验）
M-D2-17：verified-without-receipt —— 跳过整个 _verify_external_receipt（receipt+final-scan bypass）
M-D2-18：NO_REPEAT 绕过完整 reverify（NO_REPEAT 候选跳过 _toctou_reverify_pass_b）
M-D2-19：duplicate binder bypass —— 删除 EXTERNAL_ARCHIVE_DUPLICATE 检查（取第一条）
M-D2-20：external final-scan bypass —— 删除 scan_total residual 检查（始终视为 clean）

每条 mutation 真实 subprocess pytest 驱动；mutation 存在 exit=1 + 恢复后
exit=0 + byte backup SHA-256 byte-identical = KILLED 真红（behavioral）。

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
    "M-D2-12": "tests/composition/test_s6i3_d_restore_replay.py::test_r3_ack_digest_archive_live_mismatch",
    "M-D2-14": "tests/composition/test_s6i3_d_restore_replay.py::test_r2_two_owner_one_fails_rolls_back_all",
    "M-D2-15": "tests/composition/test_s6i3_d_restore_replay.py::test_r5_archive_facts_missing_field",
    "M-D2-17": "tests/composition/test_s6i3_d_restore_replay.py::test_r6_external_receipt_mismatch",
    "M-D2-18": "tests/composition/test_s6i3_d_restore_replay.py::test_r6_toctou_drift_under_no_repeat_exception",
    "M-D2-19": "tests/composition/test_s6i3_d_restore_replay.py::test_r5_external_record_duplicate_in_archive",
    "M-D2-20": "tests/composition/test_s6i3_d_restore_replay.py::test_r6_external_final_scan_residual",
}

# (mutation_name, file, old_anchor, new_anchor)
MUTATIONS: list[tuple[str, Path, str, str]] = [
    # M-D2-1: 移除 exclusive advisory lock —— retention worker 不被阻塞
    (
        "M-D2-1",
        RESTORE_REPLAY,
        "            # 第一条 DB 语句必须是 exclusive advisory xact lock\n"
        "            await acquire_maintenance_exclusive_lock(session)\n",
        "            # M-D2-1 mutation: 不取 exclusive lock\n"
        "            pass\n",
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
        "    if owner_key == \"runtime.private.v1\":\n"
        "        if operation_state == \"completed\":\n"
        "            return (\n"
        "                ACTION_RUNTIME_BINDING_UNPROVABLE,\n"
        "                \"RUNTIME_BINDING_EVIDENCE_UNPROVABLE\",\n"
        "            )\n",
        "    if False:  # M-D2-6 mutation: runtime 改走 external_verify_only（合并语义）\n"
        "        if operation_state == \"completed\":\n"
        "            return (\n"
        "                ACTION_RUNTIME_BINDING_UNPROVABLE,\n"
        "                \"RUNTIME_BINDING_EVIDENCE_UNPROVABLE\",\n"
        "            )\n",
    ),
    # M-D2-12: archive/live ack_digest 严格相等删除 —— 移除 archive/live 严格相等校验
    (
        "M-D2-12",
        RESTORE_REPLAY,
        "            if (\n"
        "                archive_ack is not None\n"
        "                and live_ack is not None\n"
        "                and archive_ack == live_ack\n"
        "                and archive_cp_state == \"acked\"\n"
        "            ):\n"
        "                pass  # 严格相等 → OK\n"
        "            elif (\n"
        "                archive_ack is not None\n"
        "                and live_ack is not None\n"
        "                and archive_ack != live_ack\n"
        "                and archive_cp_state == \"acked\"\n"
        "            ):\n"
        "                drift_fields.append(\"checkpoint.ack_digest_archive_live_mismatch\")\n",
        "            # M-D2-12 mutation: 删除 archive/live 严格相等校验\n"
        "            pass  # ack_digest_mismatch 不再阻断 gate\n",
    ),
    # M-D2-13: TOCTOU continue —— 任何 TOCTOU drift 改为 continue（**禁止**——必 raise）
    # 跳过此 mutation（行为正确性已通过 atomic rollback 测试覆盖）
    # M-D2-15: archive-fact 缺失 fallback —— _require_field 缺失字段默认 0（bypass 严格缺失校验）
    (
        "M-D2-15",
        RESTORE_REPLAY,
        "    if key not in record or record[key] is None:\n"
        "        raise RestoreReplayError(\n"
        "            missing_code,\n"
        "            detail={\"missing_field\": key},\n"
        "        )\n"
        "    return record[key]\n",
        "    return record.get(key, 0)  # M-D2-15 mutation: 缺失字段默认 0（archive-fact fallback bypass）\n",
    ),
    # M-D2-14: partial commit —— participant 失败 catch-and-continue（吞掉异常继续提交）
    (
        "M-D2-14",
        RESTORE_REPLAY,
        "                        participant_failure_count += 1\n"
        "                        raise RestoreReplayError(\n"
        "                            \"PARTICIPANT_FAILURE\",\n"
        "                            detail={\n"
        "                                \"owner_key\": validated.archive_owner_key,\n"
        "                                \"operation_id\": str(validated.operation_id),\n"
        "                                \"error_type\": type(exc).__name__,\n"
        "                                \"error\": str(exc),\n"
        "                            },\n"
        "                        ) from exc\n",
        "                        participant_failure_count += 1\n"
        "                        pass  # M-D2-14 mutation: catch-and-continue（吞掉 participant 异常 → partial commit）\n",
    ),
    # M-D2-16: external record 错绑 —— 退回取任意 LIVE row 冒充 archive 证据
    # 跳过此 mutation（已通过 test_r3_external_record_wrong_binding 真实 PG 负例覆盖）
    # M-D2-17: verified-without-receipt —— 跳过整个 _verify_external_receipt（receipt+final-scan bypass）
    # 绑定 receipt_mismatch：跳过校验 → receipt 漂移不被发现 → report.error=None → 测试红
    (
        "M-D2-17",
        RESTORE_REPLAY,
        "                            await _verify_external_receipt(\n"
        "                                session,\n"
        "                                tenant_id=tenant_id,\n"
        "                                validated=validated,\n"
        "                                manifest=manifest,\n"
        "                            )\n",
        "                            pass  # M-D2-17 mutation: verified-without-receipt（跳过 receipt+final-scan 校验）\n",
    ),
    # M-D2-18: NO_REPEAT 绕过完整 reverify —— NO_REPEAT 候选跳过 _toctou_reverify_pass_b
    # 绑定 toctou_drift_under_no_repeat_exception：跳过 reverify → operation.revision drift
    # 不被发现 → report.error=None → 测试红
    (
        "M-D2-18",
        RESTORE_REPLAY,
        "                await _toctou_reverify_pass_b(\n"
        "                    session,\n"
        "                    tenant_id=tenant_id,\n"
        "                    validated=validated,\n"
        "                    allow_terminal_single_direction=_is_no_repeat_candidate,\n"
        "                )\n",
        "                if not _is_no_repeat_candidate:  # M-D2-18 mutation: NO_REPEAT 绕过完整 reverify\n"
        "                    await _toctou_reverify_pass_b(\n"
        "                        session,\n"
        "                        tenant_id=tenant_id,\n"
        "                        validated=validated,\n"
        "                        allow_terminal_single_direction=_is_no_repeat_candidate,\n"
        "                    )\n",
    ),
    # M-D2-19: duplicate binder bypass —— 删除 EXTERNAL_ARCHIVE_DUPLICATE 检查（取第一条）
    # 绑定 duplicate_in_archive：删除重复检测 → 恰好 1 条假象 → verified → 测试红
    (
        "M-D2-19",
        RESTORE_REPLAY,
        "    if len(matches) > 1:\n"
        "        raise RestoreReplayError(\n"
        "            \"EXTERNAL_ARCHIVE_DUPLICATE\",\n"
        "            detail={\n"
        "                \"conversation_id\": cid_str,\n"
        "                \"owner_key\": owner_key,\n"
        "                \"count\": len(matches),\n"
        "                \"reason\": \"duplicate_archive_external_ref\",\n"
        "            },\n"
        "        )\n",
        "    # M-D2-19 mutation: duplicate binder bypass（删除重复检测，取第一条）\n",
    ),
    # M-D2-20: external final-scan bypass —— 删除 scan_total residual 检查（始终视为 clean）
    # 绑定 final_scan_residual：删除 residual 检查 → registered 残留不被发现 → 测试红
    (
        "M-D2-20",
        RESTORE_REPLAY,
        "    scan_result = await scan_fn(tenant_id=tenant_id, conversation_id=cid)\n"
        "    scan_total = int(getattr(scan_result, \"total\", 0))\n"
        "    if scan_total != 0:\n"
        "        raise _fail(f\"external_final_scan_residual:{scan_total}\")\n",
        "    scan_result = await scan_fn(tenant_id=tenant_id, conversation_id=cid)\n"
        "    scan_total = int(getattr(scan_result, \"total\", 0))\n"
        "    # M-D2-20 mutation: external final-scan bypass（不校验 residual）\n",
    ),
    # M-D2-18: 幂等路径 bypass —— 删 NO_REPEAT 检查（archive non-terminal + live acked 仍调 participant）
    # 跳过此 mutation（已通过 test_r1_idempotent_replay_db_acked_drift 真实 PG 负例覆盖）
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
    # M-D2-8: transport 主入口降级为 body helper（丢失 fence / owner lock / CAS / ACK / final scan）
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
        "        # M-D2-8 mutation: 降级为 body helper（丢失 fence / owner lock / CAS / ACK / final scan）\n"
        "        from datetime import datetime, timezone\n"
        "        await WorkspaceTransportErasureParticipant(session).erase_transport_body(\n"
        "            tenant_id=tenant_id,\n"
        "            conversation_id=validated.conversation_id,\n"
        "            purge_revision=validated.archive_purge_revision,\n"
        "            now=datetime.now(timezone.utc),\n"
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
        "                \"owner_key\": archive_cp_owner_key,\n"
        "                \"drift_fields\": tuple(drift_fields),\n"
        "            },\n"
        "        )",
        "    if drift_fields:\n"
        "        pass  # M-D2-9 mutation: 单 drift 不阻断（错误）",
    ),
    # M-D2-10: purge_revision 对账删除 —— 移除 operation.purge_revision drift 检查
    (
        "M-D2-10",
        RESTORE_REPLAY,
        "    if int(op_row[\"purge_revision\"]) != archive_purge_rev:\n"
        "        drift_fields.append(\"operation.purge_revision\")\n",
        "    # M-D2-10 mutation: 删除 purge_revision 对账\n",
    ),
    # M-D2-11: gate 忽略 replay report —— 移除全部 report 内部 blocking 消费
    (
        "M-D2-11",
        RESTORE_REPLAY,
        "    # 1. ReplayReport 内部 blocking 项 → 全部阻断\n"
        "    if replay_report.error is not None:\n"
        "        blocked.append(f\"replay_error:{replay_report.error}\")\n"
        "    if replay_report.pass_a_drift > 0:\n"
        "        blocked.append(f\"pass_a_drift:{replay_report.pass_a_drift}\")\n"
        "    if replay_report.toctou_drift > 0:\n"
        "        blocked.append(f\"toctou_drift:{replay_report.toctou_drift}\")\n"
        "    if replay_report.participant_failures > 0:\n"
        "        blocked.append(f\"participant_failure:{replay_report.participant_failures}\")\n"
        "    if replay_report.owners_fact_drift > 0:\n"
        "        blocked.append(f\"fact_drift:{replay_report.owners_fact_drift}\")\n"
        "    if replay_report.runtime_binding_evidence_unprovable > 0:\n"
        "        blocked.append(\n"
        "            f\"RUNTIME_BINDING_EVIDENCE_UNPROVABLE:\"\n"
        "            f\"{replay_report.runtime_binding_evidence_unprovable}\"\n"
        "        )\n"
        "    if replay_report.external_verification_failed > 0:\n"
        "        blocked.append(\n"
        "            f\"external_verification_failed:\"\n"
        "            f\"{replay_report.external_verification_failed}\"\n"
        "        )\n"
        "    if replay_report.owners_non_local_blocked > 0:\n"
        "        blocked.append(\n"
        "            f\"non_local_blocked:{replay_report.owners_non_local_blocked}\"\n"
        "        )\n",
        "    # 1. ReplayReport 内部 blocking 项 → 全部阻断\n"
        "    pass  # M-D2-11 mutation: gate 忽略 replay report（不消费内部 blocking 项）\n",
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
    mutated = src.replace(old, new, 1)
    # 预校验：mutant **必须是可运行 Python**——syntax-invalid 不计入 KILLED，强制重做。
    # 在写盘 + 跑 pytest 前 compile() 预检，避免 SyntaxError 冒充真红。
    compile(mutated, str(file), "exec")
    file.write_text(mutated)


def run_pytest(test_id: str) -> subprocess.CompletedProcess:
    cmd = [
        "uv", "run", "pytest", test_id, "-q", "--tb=line",
        "--no-header", "-x",
    ]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=TEST_DIR, timeout=120)


def _is_syntax_failure(proc: subprocess.CompletedProcess) -> bool:
    """mutated pytest 失败是否因 mutant **不可运行**（SyntaxError / IndentationError / TabError）。

    语法失败的 mutant **不是** 真红证据（pytest 连业务断言都跑不到）——必须重做
    为可运行 Python，**不计入** KILLED。behavioral 失败（assertion / drift / rollback）
    才计入 KILLED。
    """
    out = (proc.stdout or "") + (proc.stderr or "")
    return (
        "SyntaxError" in out
        or "IndentationError" in out
        or "TabError" in out
    )


async def _main() -> int:
    print(f"Mutation kill: {len(MUTATIONS)} mutations\n")
    # name -> (behavioral_killed, clean_passed, syntax_invalid)
    results: list[tuple[str, bool, bool, bool]] = []
    for name, file, old, new in MUTATIONS:
        test_id = TEST_IDS.get(name)
        if test_id is None:
            print(f"SKIP   {name} (no test binding)")
            results.append((name, False, False, False))
            continue

        original_sha = _sha256_bytes(file.read_bytes())
        apply_mutation(file, old, new, name)
        killed = False
        syntax_invalid = False
        clean_passed = False
        try:
            mutated = run_pytest(test_id)
            killed = mutated.returncode != 0
            syntax_invalid = killed and _is_syntax_failure(mutated)
        finally:
            # 关键：先 restore 再跑 clean（确保 clean 跑在干净文件上）
            restore_file(file)
            restored_sha = _sha256_bytes(file.read_bytes())
            assert (
                restored_sha == original_sha
            ), f"{name}: restore failed sha mismatch ({original_sha} != {restored_sha})"
        clean = run_pytest(test_id)
        clean_passed = clean.returncode == 0
        # 真红 = behavioral 红（**非** syntax）+ 恢复后绿
        ok = killed and not syntax_invalid and clean_passed
        results.append((name, ok, clean_passed, syntax_invalid))
        if syntax_invalid:
            verdict = "SYNTAX-INVALID"
            detail = "syntax (mutant 不可运行，不计入 KILLED)"
        else:
            verdict = "KILLED" if ok else "FAILED"
            detail = "behavioral" if killed else "NOT-RED"
        print(
            f"{verdict:15} "
            f"mutated={detail} "
            f"restored={'green' if clean_passed else 'NOT-GREEN'} "
            f"{name}"
        )

    passed = sum(1 for _, ok, _, _ in results if ok)
    syntax_bad = sum(1 for _, _, _, syn in results if syn)
    print(
        f"\n{passed}/{len(MUTATIONS)} mutation kills passed "
        f"(behavioral red + byte-identical restore green; "
        f"syntax-invalid={syntax_bad} 不计入) "
        f"(run_id=scripts/s6i3_d_restore_replay_mutation_kill)"
    )
    if syntax_bad:
        print(f"⚠️  {syntax_bad} mutant(s) 不可运行（SyntaxError）——必须重做为可运行 Python")
    return 0 if passed == len(MUTATIONS) and syntax_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
