# ruff: noqa: E501
#!/usr/bin/env python3
"""R1-S6-I3-D D2 restore replay executor mutation kill（Round-7 结构化 JUnit 版）。

真实 PG 真实路径 mutation 驱动（参照 s6i1_retention_mutation_kill 模式）：
- byte backup + try/finally + SHA-256 byte-identical
- 每条 mutation 绑定对应 invariant test
- 仅 mutation 期间 mutate；mutation 后 restore 还原

Round-7 强化（**结构化 pytest/JUnit 结果**判定 KILLED，替换 Round-5 的纯 exit-code 判定）：
- pytest 以 ``--junitxml`` 输出结构化结果；解析 ``<testcase>`` 的 ``<failure>`` / ``<error>``。
- **仅**测试**实际执行后**的 invariant failure 计 KILLED：
  ``<failure>`` 且 message 为断言签名（``AssertionError`` / ``assert`` / ``Failed``
  ——后者覆盖 ``pytest.raises`` DID-NOT-RAISE 与 ``pytest.fail``）。
- 以下**一律不计** KILLED：import / collection / usage / internal error（exit 2/3/4 或
  junit 解析失败）、setup / fixture / teardown error（``<error>``）、call 阶段**非断言**
  异常（``NameError`` 等 crash）、timeout、no-tests（exit 5 / 0 收集）、survived（exit 0 全绿）。
- 每条 mutant **必须是可运行 Python**（``compile()`` 预校验，syntax-invalid 单独分类、不计入）。
- 分类器见 ``classify_pytest_run``；其判别正确性由
  ``tests/composition/test_s6i3_d_mutation_classifier.py`` 自测覆盖。
- mutation 分母 = ``len(MUTATIONS)``（运行时按实际项计算，**不**预写数字）。

mutation 覆盖（每项对应 invariant test）：

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
M-D2-15：archive-fact 缺失 fallback —— _require_field 缺失字段默认 0
M-D2-17：verified-without-receipt —— 跳过整个 _verify_external_receipt
M-D2-18：NO_REPEAT 绕过完整 reverify（terminal_evidence 不经 _toctou_reverify_pass_b）
M-D2-19：duplicate binder bypass —— 删除 EXTERNAL_ARCHIVE_DUPLICATE 检查（取第一条）
M-D2-20：external final-scan bypass —— 删除 scan_total residual 检查（始终视为 clean）
M-D2-21：blocked outcome 误记 cleared（BLOCKED_KEPT → LOCAL_CLEARED）
M-D2-22：进入 pass B 前 owner_key 预验证 bypass（直接进入写事务）
M-D2-23：canonical UUID 严格 str 校验 bypass（隐式 str() 强转）
M-D2-24：external scan total 默认 0（bypass 严格校验冒充 clean）
M-D2-25：malformed external candidate 静默跳过（不 fail closed 为 TYPE_INVALID）
M-D2-26：reverify 永不返回 terminal evidence（NO_REPEAT 单快照失效）

Run:
    cd packages/server-python && uv run python scripts/s6i3_d_restore_replay_mutation_kill.py
"""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NamedTuple

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
    # Round-7 新增判别测试绑定
    "M-D2-21": "tests/composition/test_s6i3_d_restore_replay.py::test_r7_blocked_kept_real_pg_gate_stays_closed",
    "M-D2-22": "tests/composition/test_s6i3_d_restore_replay.py::test_r7_unknown_owner_prevalidated_zero_partial_commit",
    "M-D2-23": "tests/composition/test_s6i3_d_restore_replay.py::test_r7_canonical_uuid_strict_fail_closed",
    "M-D2-24": "tests/composition/test_s6i3_d_restore_replay.py::test_r7_external_scan_total_invalid_fail_closed",
    "M-D2-25": "tests/composition/test_s6i3_d_restore_replay.py::test_r7_external_malformed_candidate_type_invalid",
    "M-D2-26": "tests/composition/test_s6i3_d_restore_replay.py::test_r7_no_repeat_single_snapshot_terminal_evidence",
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
    # M-D2-17: verified-without-receipt —— 跳过整个 _verify_external_receipt（receipt+final-scan bypass）
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
    # M-D2-18: NO_REPEAT 绕过完整 reverify —— terminal_evidence 不经 _toctou_reverify_pass_b，
    # 仅凭 archive 状态判定（漂移不被发现 → 测试红）
    (
        "M-D2-18",
        RESTORE_REPLAY,
        "                terminal_evidence = await _toctou_reverify_pass_b(\n"
        "                    session,\n"
        "                    tenant_id=tenant_id,\n"
        "                    validated=validated,\n"
        "                )\n"
        "                if terminal_evidence:\n",
        "                terminal_evidence = (  # M-D2-18 mutation: NO_REPEAT 绕过完整 reverify\n"
        "                    validated.archive_checkpoint_state in (\"erasing\", \"pending\")\n"
        "                )\n"
        "                if terminal_evidence:\n",
    ),
    # M-D2-19: duplicate binder bypass —— 删除 EXTERNAL_ARCHIVE_DUPLICATE 检查（取第一条）
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
    (
        "M-D2-20",
        RESTORE_REPLAY,
        "    scan_total = getattr(scan_result, \"total\", None)\n"
        "    if not isinstance(scan_total, int) or isinstance(scan_total, bool) or scan_total < 0:\n"
        "        raise _fail(\"external_scan_total_invalid\")\n"
        "    if scan_total != 0:\n"
        "        raise _fail(f\"external_final_scan_residual:{scan_total}\")\n",
        "    scan_total = getattr(scan_result, \"total\", None)\n"
        "    if not isinstance(scan_total, int) or isinstance(scan_total, bool) or scan_total < 0:\n"
        "        raise _fail(\"external_scan_total_invalid\")\n"
        "    # M-D2-20 mutation: external final-scan bypass（不校验 residual）\n",
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
    # M-D2-8: transport 主入口降级为 body helper（丢失 fence / owner lock / CAS / ACK / final scan）
    (
        "M-D2-8",
        RESTORE_REPLAY,
        "        return await WorkspaceTransportErasureParticipant(session).erase_transport_owner(\n"
        "            tenant_id=tenant_id,\n"
        "            conversation_id=validated.conversation_id,\n"
        "            purge_revision=validated.archive_purge_revision,\n"
        "            purge_operation_id=validated.operation_id,\n"
        "            expected_operation_revision=validated.archive_revision,\n"
        "            expected_lease_epoch=validated.archive_lease_epoch,\n"
        "        )\n",
        "        # M-D2-8 mutation: 降级为 body helper（丢失 fence / owner lock / CAS / ACK / final scan）\n"
        "        from datetime import datetime, timezone\n"
        "        return await WorkspaceTransportErasureParticipant(session).erase_transport_body(\n"
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
        "    if replay_report.owners_blocked_kept > 0:\n"
        "        # local owner participant blocked=True（保留不清除）→ 仍有未清残留 → 保持关闭\n"
        "        blocked.append(f\"blocked_kept:{replay_report.owners_blocked_kept}\")\n"
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
    # ---- Round-7 新增 mutation ----
    # M-D2-21: blocked outcome 误记 cleared —— BLOCKED_KEPT 改为 LOCAL_CLEARED（误报已清除）
    (
        "M-D2-21",
        RESTORE_REPLAY,
        "                    if classification == _OUTCOME_BLOCKED:\n"
        "                        verdicts.append(\n"
        "                            ReplayOwnerVerdict(\n"
        "                                operation_id=str(validated.operation_id),\n"
        "                                owner_key=validated.archive_owner_key,\n"
        "                                action=ACTION_BLOCKED_KEPT,\n"
        "                                reason_code=outcome.block_reason,\n"
        "                            )\n"
        "                        )\n"
        "                        continue\n",
        "                    if classification == _OUTCOME_BLOCKED:\n"
        "                        verdicts.append(\n"
        "                            ReplayOwnerVerdict(\n"
        "                                operation_id=str(validated.operation_id),\n"
        "                                owner_key=validated.archive_owner_key,\n"
        "                                action=ACTION_LOCAL_CLEARED,  # M-D2-21 mutation: blocked 误记 cleared\n"
        "                                reason_code=outcome.block_reason,\n"
        "                            )\n"
        "                        )\n"
        "                        continue\n",
    ),
    # M-D2-22: 进入 pass B 前 owner_key 预验证 bypass —— 直接进入写事务（锁被获取 → 真红）
    (
        "M-D2-22",
        RESTORE_REPLAY,
        "    for _fact, validated in validated_facts:\n"
        "        if validated.archive_owner_key not in (LOCAL_OWNERS | NON_LOCAL_OWNERS):\n",
        "    for _fact, validated in validated_facts:\n"
        "        if False:  # M-D2-22 mutation: 跳过 owner_key 预验证（直接进入 pass B 写事务）\n",
    ),
    # M-D2-23: canonical UUID 严格 str 校验 bypass —— 隐式 str() 强转（UUID 对象不再 fail closed）
    (
        "M-D2-23",
        RESTORE_REPLAY,
        "    raw = _require_field(record, key, missing_code=missing_code)\n"
        "    if not isinstance(raw, str):\n"
        "        raise RestoreReplayError(\n"
        "            \"ARCHIVE_FACTS_TYPE_INVALID\",\n"
        "            detail={\"field\": field, \"expected_type\": \"canonical_uuid_str\"},\n"
        "        )\n",
        "    raw = _require_field(record, key, missing_code=missing_code)\n"
        "    if not isinstance(raw, str):\n"
        "        raw = str(raw)  # M-D2-23 mutation: 隐式 str() 强转（bypass 严格 str 校验）\n",
    ),
    # M-D2-24: external scan total 默认 0 —— bypass 严格校验（absent total 冒充 clean）
    (
        "M-D2-24",
        RESTORE_REPLAY,
        "    scan_total = getattr(scan_result, \"total\", None)\n"
        "    if not isinstance(scan_total, int) or isinstance(scan_total, bool) or scan_total < 0:\n"
        "        raise _fail(\"external_scan_total_invalid\")\n",
        "    scan_total = getattr(scan_result, \"total\", 0)  # M-D2-24 mutation: scan total 默认 0（bypass 严格校验）\n"
        "    if not isinstance(scan_total, int) or isinstance(scan_total, bool) or scan_total < 0:\n"
        "        raise _fail(\"external_scan_total_invalid\")\n",
    ),
    # M-D2-25: malformed external candidate 静默跳过 —— 不 fail closed 为 ARCHIVE_FACTS_TYPE_INVALID
    (
        "M-D2-25",
        RESTORE_REPLAY,
        "        rc = _require_canonical_uuid(\n"
        "            r.fields,\n"
        "            \"conversation_id\",\n"
        "            missing_code=\"ARCHIVE_FACTS_FIELD_MISSING\",\n"
        "            field=\"external_ref.conversation_id\",\n"
        "        )\n"
        "        if str(rc) == cid_str:\n"
        "            matches.append(r.fields)\n",
        "        try:  # M-D2-25 mutation: 静默跳过 malformed 候选（不 fail closed）\n"
        "            rc = _require_canonical_uuid(\n"
        "                r.fields,\n"
        "                \"conversation_id\",\n"
        "                missing_code=\"ARCHIVE_FACTS_FIELD_MISSING\",\n"
        "                field=\"external_ref.conversation_id\",\n"
        "            )\n"
        "        except RestoreReplayError:\n"
        "            continue\n"
        "        if str(rc) == cid_str:\n"
        "            matches.append(r.fields)\n",
    ),
    # M-D2-26: reverify 永不返回 terminal evidence —— NO_REPEAT 单快照失效（始终走矩阵）
    (
        "M-D2-26",
        RESTORE_REPLAY,
        "    # 无 drift → 返回同一 cp_row 快照上的 terminal evidence（caller 据此决定 NO_REPEAT）。\n"
        "    return is_terminal_single_direction\n",
        "    # 无 drift → 返回同一 cp_row 快照上的 terminal evidence（caller 据此决定 NO_REPEAT）。\n"
        "    return False  # M-D2-26 mutation: reverify 永不返回 terminal evidence（NO_REPEAT 失效）\n",
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


class _SyntaxInvalidMutantError(Exception):
    """mutant 不是可运行 Python（``compile()`` 预校验失败）——**不计入** KILLED。"""


def apply_mutation(file: Path, old: str, new: str, name: str) -> None:
    src = file.read_text()
    assert old in src, f"{name}: anchor not found in {file}\n  old[:80]={old[:80]!r}"
    mutated = src.replace(old, new, 1)
    # 预校验：mutant **必须是可运行 Python**——syntax-invalid 不计入 KILLED，强制重做。
    # 在 backup + 写盘前 compile() 预检，避免 SyntaxError 冒充真红（文件保持不被改写）。
    try:
        compile(mutated, str(file), "exec")
    except SyntaxError as exc:
        raise _SyntaxInvalidMutantError(f"{name}: mutant 不可运行（SyntaxError）") from exc
    backup_file(file)
    file.write_text(mutated)


# ---------------------------------------------------------------------------
# 结构化 pytest/JUnit 分类器（Round-7）
# ---------------------------------------------------------------------------

# 分类结果（仅 ``killed`` 计入 KILLED；其余一律不计）
CLS_KILLED = "killed"  # 实际执行后的 invariant failure（断言 / pytest.raises DID-NOT-RAISE）
CLS_SURVIVED = "survived"  # 测试全绿（exit 0）→ mutation 未被捕获
CLS_NO_TESTS = "no_tests"  # 0 测试收集（exit 5 / junit tests=0）
CLS_COLLECTION_ERROR = "collection_error"  # import/collection/usage/internal（exit 2/3/4 或 junit 解析失败）
CLS_SETUP_ERROR = "setup_error"  # fixture/setup/teardown error（testcase <error>）
CLS_CRASH = "crash"  # call 阶段非断言异常（NameError 等；非 invariant failure）
CLS_TIMEOUT = "timeout"  # subprocess 超时
CLS_SYNTAX_INVALID = "syntax_invalid"  # mutant 不可运行（compile 预检失败；未跑 pytest）

# 仅这些分类计为 KILLED
_KILLED_CLASSES = frozenset({CLS_KILLED})

# invariant failure 的 ``<failure>`` message 前缀（pytest 断言重写 / pytest.raises DID-NOT-RAISE /
# pytest.fail）。**非断言**异常（NameError/TypeError/...）以异常类名开头 → 不匹配 → crash。
_INVARIANT_FAILURE_PREFIXES = ("AssertionError", "assert", "Failed")

# pytest 退出码：2=collection/usage 中断，3=internal，4=usage，5=no tests collected
_COLLECTION_OR_USAGE_EXIT = frozenset({2, 3, 4})
_NO_TESTS_EXIT = 5


def _is_invariant_failure(message: str) -> bool:
    """``<failure>`` message 是否为**断言级** invariant failure（实际执行后的业务断言失败）。

    匹配 pytest 断言重写（``AssertionError`` / ``assert ...``）与 ``pytest.raises``
    DID-NOT-RAISE / ``pytest.fail``（``Failed``）。**不**匹配 call 阶段崩溃
    （``NameError:`` / ``TypeError:`` 等以异常类名开头）——后者不是 invariant failure。
    """
    m = (message or "").lstrip()
    return m.startswith(_INVARIANT_FAILURE_PREFIXES)


def classify_pytest_run(
    *,
    returncode: int | None,
    timed_out: bool,
    junit_xml_text: str,
) -> str:
    """把一次 pytest 运行分类为结构化结果；仅 ``killed`` 计入 mutation KILLED。

    判定顺序（Req 5——import/collection/setup/fixture/environment/internal/timeout/
    no-tests 均不计 KILLED，仅实际执行后的 invariant failure 计）：

    1. ``timed_out`` → ``timeout``（不计）。
    2. exit 5 → ``no_tests``（不计）；exit 2/3/4 → ``collection_error``（不计）。
    3. exit 0 → ``survived``（测试全绿，mutation 未被捕获；不计）。
    4. 解析 JUnit；解析失败 → ``collection_error``（不计）。
    5. 任一 ``<testcase><failure>`` 为断言级 → ``killed``（**计** KILLED）。
    6. 否则任一 ``<failure>``（call 阶段非断言崩溃）→ ``crash``（不计）。
    7. 否则任一 ``<error>``（setup/fixture/teardown）→ ``setup_error``（不计）。
    8. 0 个 ``<testcase>`` → ``no_tests``（不计）；其余 → ``collection_error``（不计）。
    """
    if timed_out:
        return CLS_TIMEOUT
    if returncode == _NO_TESTS_EXIT:
        return CLS_NO_TESTS
    if returncode in _COLLECTION_OR_USAGE_EXIT:
        return CLS_COLLECTION_ERROR
    if returncode == 0:
        return CLS_SURVIVED
    try:
        root = ET.fromstring(junit_xml_text or "")
    except ET.ParseError:
        return CLS_COLLECTION_ERROR
    tests = 0
    saw_invariant = False
    saw_crash = False
    saw_setup_error = False
    for tc in root.iter("testcase"):
        tests += 1
        for failure in tc.findall("failure"):
            if _is_invariant_failure(failure.get("message", "")):
                saw_invariant = True
            else:
                saw_crash = True
        for _err in tc.findall("error"):
            saw_setup_error = True
    if tests == 0:
        return CLS_NO_TESTS
    if saw_invariant:
        return CLS_KILLED
    if saw_crash:
        return CLS_CRASH
    if saw_setup_error:
        return CLS_SETUP_ERROR
    return CLS_COLLECTION_ERROR


def is_killed(classification: str) -> bool:
    """该分类是否计为 KILLED（仅实际执行后的 invariant failure）。"""
    return classification in _KILLED_CLASSES


class _RunResult(NamedTuple):
    returncode: int | None
    timed_out: bool
    junit_xml_text: str


def run_pytest(test_id: str, junit_path: Path) -> _RunResult:
    cmd = [
        "uv", "run", "pytest", test_id, "-q", "--tb=line",
        "--no-header", "-x", "-p", "no:cacheprovider",
        f"--junitxml={junit_path}",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=TEST_DIR, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return _RunResult(returncode=None, timed_out=True, junit_xml_text="")
    junit_xml_text = junit_path.read_text() if junit_path.exists() else ""
    return _RunResult(
        returncode=proc.returncode, timed_out=False, junit_xml_text=junit_xml_text,
    )


async def _main() -> int:
    print(f"Mutation kill: {len(MUTATIONS)} mutations\n")
    junit_dir = Path(tempfile.mkdtemp(prefix="s6i3_d_mutation_"))
    # name -> (classification, clean_passed)
    results: list[tuple[str, str, bool]] = []
    for name, file, old, new in MUTATIONS:
        test_id = TEST_IDS.get(name)
        if test_id is None:
            print(f"SKIP   {name} (no test binding)")
            results.append((name, "skip_no_binding", False))
            continue

        original_sha = _sha256_bytes(file.read_bytes())
        mutated_junit = junit_dir / f"{name}.mutated.xml"
        clean_junit = junit_dir / f"{name}.clean.xml"

        syntax_invalid = False
        try:
            apply_mutation(file, old, new, name)
        except _SyntaxInvalidMutantError:
            syntax_invalid = True

        try:
            if syntax_invalid:
                # mutant 不可运行（compile 预检失败，未写盘）→ 单独分类，不计 KILLED
                classification = CLS_SYNTAX_INVALID
            else:
                mutated = run_pytest(test_id, mutated_junit)
                classification = classify_pytest_run(
                    returncode=mutated.returncode,
                    timed_out=mutated.timed_out,
                    junit_xml_text=mutated.junit_xml_text,
                )
        finally:
            # 关键：先 restore 再跑 clean（确保 clean 跑在干净文件上）
            restore_file(file)
            restored_sha = _sha256_bytes(file.read_bytes())
            assert (
                restored_sha == original_sha
            ), f"{name}: restore failed sha mismatch ({original_sha} != {restored_sha})"

        clean = run_pytest(test_id, clean_junit)
        clean_passed = clean.returncode == 0
        # 真红 = 结构化 invariant failure（killed）+ 恢复后绿
        ok = is_killed(classification) and clean_passed
        results.append((name, classification, clean_passed))
        verdict = "KILLED" if ok else ("SYNTAX-INVALID" if syntax_invalid else "FAILED")
        print(
            f"{verdict:15} "
            f"mutated={classification} "
            f"restored={'green' if clean_passed else 'NOT-GREEN'} "
            f"{name}"
        )

    killed = sum(1 for _, cls, ok_clean in results if is_killed(cls) and ok_clean)
    # 分母 = 实际 mutation 项数（len(MUTATIONS)，运行时计算，**不**预写数字）
    total = len(MUTATIONS)
    not_killed = [(n, c) for n, c, _ in results if not is_killed(c)]
    print(
        f"\n{killed}/{total} mutation kills passed "
        f"(structured JUnit invariant-failure red + byte-identical restore green; "
        f"分母按实际 {total} 项登记) "
        f"(run_id=scripts/s6i3_d_restore_replay_mutation_kill)"
    )
    if not_killed:
        print("⚠️  非 KILLED 项（不计入；import/collection/setup/crash/timeout/no-tests/survived/syntax）：")
        for n, c in not_killed:
            print(f"    {n}: {c}")
    return 0 if killed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
